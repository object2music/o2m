"""o2m's mopidy-spotify patch, ported to Mopidy-Spotify 5.0.0 / Mopidy 4.

Bind-mounted over `mopidy_spotify/backend.py` (see docker-compose). It keeps two
o2m-specific behaviours that upstream does not have:

1. **Streaming identity.** librespot authenticates with a *user* token fetched
   from o2m (`/api/spotify_stream_token`) rather than the client-credentials
   token, so it can mint the durable credentials blob. Since 2026-08-10 login5
   rejects blobs minted with a third-party client_id, hence the separate
   keymaster identity and the cache purge below.
2. **Resilient login.** A single failed `login()` used to leave the web client
   permanently logged out — library lookups silently returned 0 (music empty
   while podcasts kept working) until someone restarted mopidy by hand.

The Mopidy 3 / 5.0.0a3 version of this file lives next to it as
`mopidy_spotify_backend.py` and is still what the un-migrated stack mounts. Keep
both until every instance runs Mopidy 4 — an older image must keep working.

Ported against 5.0.0: `SpotifyBackend.__init__` and `SpotifyOAuthClient.__init__`
are keyword-only, `uri_schemes` is a ClassVar instead of an instance attribute,
and `Extension().get_credentials_dir()` replaces the manual `get_data_dir()` +
mkdir of the credentials cache.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
from typing import Any, ClassVar

import pykka
from mopidy import backend
from mopidy.types import UriScheme

from mopidy_spotify import Extension, library, playlists, web

logger = logging.getLogger(__name__)

# Where the o2m API lives, tried in order: Docker service name first, then
# localhost for installs that run mopidy and o2m side by side on the same host
# (Raspberry Pi without Docker). Set O2M_API_URL to pin it explicitly.
O2M_API_BASES = (
    [os.environ["O2M_API_URL"].rstrip("/")]
    if os.environ.get("O2M_API_URL")
    else ["http://o2m:6681", "http://127.0.0.1:6681"]
)


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):
    # ClassVar in 5.0.0 — setting it in __init__ as the 3.x patch did leaves the
    # backend registered for no uri scheme at all, so nothing spotify: resolves.
    uri_schemes: ClassVar[list[UriScheme]] = [UriScheme("spotify")]

    def __init__(self, *, config, audio) -> None:  # keyword-only since 5.0.0
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

    def on_start(self) -> None:
        self._web_client = web.SpotifyOAuthClient(
            client_id=self._config["spotify"]["client_id"],
            client_secret=self._config["spotify"]["client_secret"],
            proxy_config=self._config["proxy"],
        )
        # Retry login() off the actor thread with capped backoff, so a transient
        # token-broker failure self-heals instead of poisoning the whole session,
        # and so on_start does not block mopidy's startup.
        threading.Thread(
            target=self._login_until_ok, daemon=True, name="o2m-spotify-login"
        ).start()

    def _login_until_ok(self) -> None:
        attempt = 0
        while True:
            try:
                # `logged_in` is a property in 5.0.0: cheap to check, and it
                # avoids re-logging in when a previous attempt already won.
                if self._web_client.logged_in or self._web_client.login():
                    if self.playlists is not None:
                        try:
                            self.playlists.refresh()
                        except Exception:
                            logger.exception("o2m: Spotify playlist refresh failed")
                    return
            except Exception:
                logger.debug("o2m: Spotify login attempt failed", exc_info=True)
            attempt += 1
            time.sleep(min(10 * attempt, 60))


class SpotifyPlaybackProvider(backend.PlaybackProvider):
    backend: SpotifyBackend

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        config = self.backend._config
        self._cache_location = Extension().get_cache_dir(config)
        self._data_location = Extension().get_data_dir(config)
        # 5.0.0 creates the directory itself (mode 0o700, exist_ok).
        self._credentials_dir = Extension().get_credentials_dir(config)
        self._config = config["spotify"]
        self._o2m_base = None

    def _o2m_get(self, path: str) -> str | None:
        """GET a small text payload from the o2m API.

        Probe the candidate bases once, then stick to whichever answered;
        reset on failure so the next call re-probes.
        """
        bases = [self._o2m_base] if self._o2m_base else O2M_API_BASES
        for base in bases:
            try:
                data = urllib.request.urlopen(f"{base}{path}", timeout=4).read()
                self._o2m_base = base
                return data.decode().strip()
            except Exception:
                continue
        self._o2m_base = None
        return None

    def _sync_credentials_cache(self, identity: str | None) -> None:
        """Wipe librespot's cached credentials when the streaming identity changes.

        The blob is derived from the access token that minted it, so a blob
        created with our own client_id stays rejected by login5
        (mopidy-spotify#437) even once a valid keymaster token is supplied.
        Purge it exactly once per switch, tracked by a marker file.
        """
        if not identity:
            return
        marker = self._data_location / "stream-identity"
        try:
            if marker.exists() and marker.read_text().strip() == identity:
                return
            for entry in self._credentials_dir.iterdir():
                if entry.is_file():
                    entry.unlink()
            marker.write_text(identity)
            logger.info(
                "o2m: Spotify streaming identity changed — cleared cached credentials."
            )
        except Exception as e:
            logger.warning(f"o2m: could not sync Spotify credentials cache: {e}")

    def on_source_setup(self, source: Any) -> None:
        source.set_property("bitrate", str(self._config["bitrate"]))
        source.set_property("cache-credentials", self._credentials_dir)
        # Prefer o2m's user token so librespot authenticates as the user and
        # mints the durable blob; fall back to the client-credentials token if
        # o2m is unreachable or not yet authenticated.
        user_token = self._o2m_get("/api/spotify_stream_token")
        if user_token:
            self._sync_credentials_cache(
                self._o2m_get("/api/spotify_stream_identity")
            )
        else:
            logger.warning(
                "o2m: no streaming token from the API — falling back to the "
                "client-credentials token (playback may be refused by login5)."
            )
        web_token = self.backend._web_client.token() if self.backend._web_client else None
        source.set_property("access-token", user_token or web_token)
        if self._config["allow_cache"]:
            source.set_property("cache-files", self._cache_location)
            source.set_property(
                "cache-max-size", self._config["cache_size"] * 1048576
            )
