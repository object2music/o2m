import pykka
from mopidy import backend

from mopidy_spotify import Extension, library, playlists, web


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):
    def __init__(self, config, audio):
        super().__init__()

        self._config = config
        self._audio = audio
        self._bitrate = config["spotify"]["bitrate"]
        self._web_client = None

        self.library = library.SpotifyLibraryProvider(backend=self)
        self.playback = SpotifyPlaybackProvider(audio=audio, backend=self)
        if config["spotify"]["allow_playlists"]:
            self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)
        else:
            self.playlists = None
        self.uri_schemes = ["spotify"]

    def on_start(self):
        self._web_client = web.SpotifyOAuthClient(
            client_id=self._config["spotify"]["client_id"],
            client_secret=self._config["spotify"]["client_secret"],
            proxy_config=self._config["proxy"],
        )
        # o2m: the token broker (auth.mopidy.com) hiccups intermittently; a single failed
        # login() left the web client permanently 'not logged in' → library.lookup returned 0
        # (music silently empty while podcasts still worked) until a manual mopidy restart.
        # Retry login() in the background with capped backoff so a transient broker failure
        # self-heals; refresh playlists once logged in. Runs off the actor thread so on_start
        # doesn't block mopidy startup.
        import threading, time as _time
        def _login_until_ok():
            attempt = 0
            while True:
                try:
                    if self._web_client.login():
                        if self.playlists is not None:
                            try:
                                self.playlists.refresh()
                            except Exception:
                                pass
                        return
                except Exception:
                    pass
                attempt += 1
                _time.sleep(min(10 * attempt, 60))
        threading.Thread(target=_login_until_ok, daemon=True, name="o2m-spotify-login").start()


class SpotifyPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_location = Extension().get_cache_dir(self.backend._config)
        self._data_location = Extension().get_data_dir(self.backend._config)
        self._config = self.backend._config["spotify"]

        self._credentials_dir = self._data_location / "credentials-cache"
        if not self._credentials_dir.exists():
            self._credentials_dir.mkdir(mode=0o700)

    def on_source_setup(self, source):
        source.set_property("bitrate", str(self._config["bitrate"]))
        source.set_property("cache-credentials", self._credentials_dir)
        # o2m: prefer the USER token (from o2m /api/spotify_stream_token) so librespot
        # authenticates as the user and mints the durable credentials blob; fall back to
        # the client_credentials token if o2m is unreachable / not yet authenticated.
        _ut = None
        try:
            import urllib.request as _ureq
            _ut = _ureq.urlopen("http://o2m:6681/api/spotify_stream_token", timeout=4).read().decode().strip()
        except Exception:
            _ut = None
        source.set_property("access-token", _ut or self.backend._web_client.token())
        if self._config["allow_cache"]:
            source.set_property("cache-files", self._cache_location)
            source.set_property("cache-max-size", self._config["cache_size"] * 1048576)
