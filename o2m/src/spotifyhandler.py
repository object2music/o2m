import configparser, os, json, sys, random, re, time
from pathlib import Path
import spotipy as spotipy
import src.util as util

class SpotifyHandler:
    def __init__(self):
        self.spotipy_config = util.get_config_file("o2m.conf")["spotipy"]
        o2m_config = util.get_config_file("o2m.conf")["o2m"]
        self._lastfm_api_key = o2m_config.get("lastfm_api_key", "").strip() or None
        self.cache_path = ".cache_spotipy"
        # Instance baseline = the fixed "house" account. Streaming (librespot blob) is pinned
        # to it, and the Web API falls back to it when no per-user overlay is signed in.
        self.instance_cache_path = ".cache_spotify_instance"
        # Unified scope: Web API (Spotipy) + streaming (librespot/mopidy-spotify) + identity (edit-auth /v1/me)
        self.scope = "user-library-read playlist-modify-private playlist-modify-public user-read-recently-played user-top-read user-follow-modify user-follow-read playlist-read-private playlist-read-collaborative user-library-modify streaming user-read-private user-read-email"
        os.environ['SPOTIPY_REDIRECT_URI'] = self.spotipy_config["spotipy_redirect_uri"]
        os.environ['SPOTIPY_CLIENT_ID'] = self.spotipy_config["client_id_spotipy"]
        os.environ['SPOTIPY_CLIENT_SECRET'] = self.spotipy_config["client_secret_spotipy"]
        self._rate_limit_file = ".spotify_rate_limit"
        self._rate_limited_until = self._load_rate_limit()
        self._last_retry_after = None  # captured from Retry-After response header
        self._db = None  # set via set_db_handler() after DatabaseHandler is ready
        self._tag_mood_map = self._build_tag_mood_map_from_class()
        self.init_token_sp()

    def set_db_handler(self, db_handler):
        """Inject the DatabaseHandler to enable local cache read/write."""
        self._db = db_handler
        self._init_tag_features()

    def _init_tag_features(self):
        """Seed TagFeature table if empty, then load into instance attributes."""
        if not self._db:
            return
        try:
            from src.o2mmodels import TagFeature
            if TagFeature.select().count() == 0:
                self._seed_tag_features()
            self._reload_tag_features()
        except Exception as e:
            print(f"_init_tag_features error: {e} — falling back to hardcoded dicts")
            self._tag_mood_map = self._build_tag_mood_map_from_class()

    def _seed_tag_features(self):
        """Populate TagFeature from hardcoded class-level dicts (runs once on first startup)."""
        from src.o2mmodels import TagFeature, db as _db
        entries = {}  # tag → {energy, valence, mood, is_noise}

        for tag, (energy, valence) in self.__class__._TAG_FEATURES.items():
            entries[tag] = {'energy': energy, 'valence': valence, 'mood': None, 'is_noise': 0}

        for cat, tags in self.__class__._MOOD_TAGS.items():
            for tag in tags:
                if tag not in entries:
                    entries[tag] = {'energy': None, 'valence': None, 'mood': cat, 'is_noise': 0}
                elif entries[tag]['mood'] is None:
                    entries[tag]['mood'] = cat

        for cat, tags in self.__class__._GENRE_MOOD.items():
            for tag in tags:
                if tag not in entries:
                    entries[tag] = {'energy': None, 'valence': None, 'mood': cat, 'is_noise': 0}
                elif entries[tag]['mood'] is None:
                    entries[tag]['mood'] = cat

        for tag in self.__class__._NOISE_TAGS:
            if tag not in entries:
                entries[tag] = {'energy': None, 'valence': None, 'mood': None, 'is_noise': 1}
            else:
                entries[tag]['is_noise'] = 1

        with _db.atomic():
            for tag, data in entries.items():
                TagFeature.insert({'tag': tag, **data}).on_conflict_ignore().execute()
        print(f"_seed_tag_features: {len(entries)} entries seeded to DB")

    def _reload_tag_features(self):
        """Load TagFeature table into instance attributes, replacing hardcoded dicts."""
        from src.o2mmodels import TagFeature
        tag_features = {}
        tag_mood_map = {}
        noise_tags = set()

        for tf in TagFeature.select():
            if tf.is_noise:
                noise_tags.add(tf.tag)
                continue
            if tf.energy is not None and tf.valence is not None:
                tag_features[tf.tag] = (tf.energy, tf.valence)
            if tf.mood:
                tag_mood_map[tf.tag] = tf.mood

        self._TAG_FEATURES = tag_features
        self._tag_mood_map = tag_mood_map
        self._NOISE_TAGS   = frozenset(noise_tags)
        print(f"_reload_tag_features: {len(tag_features)} features, "
              f"{len(tag_mood_map)} mood mappings, {len(noise_tags)} noise tags")

    def _build_tag_mood_map_from_class(self):
        """Fallback: build {tag: mood_cat} from hardcoded class constants."""
        m = {}
        for cat, tags in self.__class__._MOOD_TAGS.items():
            for t in tags:
                m[t] = cat
        for cat, tags in self.__class__._GENRE_MOOD.items():
            for t in tags:
                if t not in m:
                    m[t] = cat
        return m

    def cache_track_from_mopidy(self, mopidy_track):
        """Populate track cache from a Mopidy track object — zero API calls.

        Mopidy already carries name, length, track_no and the album URI from
        which we derive the Spotify album ID.  Called on every playback event
        so metadata is captured even without a full Spotify sync.
        Only writes if the track has no cached metadata yet.
        """
        if not self._db or not mopidy_track:
            return
        uri = getattr(mopidy_track, 'uri', None)
        if not uri or not uri.startswith('spotify:track:'):
            return
        # Skip if already cached (fresh)
        if self._db.get_track(uri):
            return

        # Extract album_id from Mopidy album URI (spotify:album:ID)
        album_id = None
        album_name = None
        artist_name = None
        mopidy_album = getattr(mopidy_track, 'album', None)
        if mopidy_album:
            album_uri = getattr(mopidy_album, 'uri', '') or ''
            parts = album_uri.split(':')
            if len(parts) >= 3 and parts[1] == 'album':
                album_id = parts[2]
            album_name = getattr(mopidy_album, 'name', None)

        mopidy_artists = getattr(mopidy_track, 'artists', None) or []
        if mopidy_artists:
            artist_name = getattr(next(iter(mopidy_artists)), 'name', None)

        # Build a minimal track dict compatible with save_track_metadata()
        track_dict = {
            'uri':          uri,
            'name':         getattr(mopidy_track, 'name', None),
            'duration_ms':  getattr(mopidy_track, 'length', None),
            'track_number': getattr(mopidy_track, 'track_no', None),
            'preview_url':  None,
            'album':        {'id': album_id, 'name': album_name,
                             'artists': [{'id': None, 'name': artist_name}]
                             } if album_id else {},
            'artists':      [],  # Spotify artist IDs not available from Mopidy
        }
        self._db.save_track_metadata(track_dict)

        # Cache album with artist_name if not already present
        if album_id and not self._db.get_album(album_id):
            self._db.save_album({
                'id':          album_id,
                'uri':         getattr(mopidy_album, 'uri', None),
                'name':        album_name,
                'artists':     [{'id': None, 'name': artist_name}] if artist_name else [],
            })

    # ── cache write helpers ───────────────────────────────────────────────────

    def cache_playlist_by_id(self, playlist_id):
        """Cache a playlist (metadata + tracks) by its Spotify ID.
        Cache-first: does nothing if already fresh. Uses sp.playlist() (1 API call)
        which embeds the first 100 tracks, avoiding a separate playlist_items call."""
        if not self._db or not playlist_id:
            return
        if self._db.get_playlist(playlist_id):
            return  # already fresh in cache
        if self._is_rate_limited():
            return
        try:
            pl_data = self.sp.playlist(playlist_id)
            if not pl_data:
                return
            position = 0
            tracks_page = pl_data.get('tracks') or pl_data.get('items')
            while tracks_page:
                for item in (tracks_page.get('items') or []):
                    if self._is_rate_limited():
                        return  # don't mark as cached — will be retried next time
                    track = (item.get('track') or item.get('item')) if item else None
                    if track and track.get('uri'):
                        self._cache_track(track)
                        self._db.save_playlist_track(
                            playlist_id, track['uri'],
                            position=position, added_at=item.get('added_at'))
                        position += 1
                if tracks_page.get('next'):
                    tracks_page = self.sp.next(tracks_page)
                else:
                    break
            # Only mark as cached once all pages are done
            self._db.save_playlist(pl_data)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
        except Exception:
            pass

    def _fetch_and_cache_playlist_tracks(self, playlist):
        """Fetch and cache tracks for a playlist.
        Tries playlist_items first; on 403 falls back to sp.playlist() which
        embeds the first 100 tracks without requiring elevated quota.
        Returns list of track URIs (may be empty if truly inaccessible)."""
        playlist_id = playlist['id']

        def _save_items(items):
            tracks = []
            for position, item in enumerate(items or []):
                track = (item.get('track') or item.get('item')) if item else None
                if track and track.get('uri'):
                    tracks.append(track['uri'])
                    if self._db:
                        self._cache_track(track)
                        self._db.save_playlist_track(
                            playlist_id, track['uri'],
                            position=position, added_at=item.get('added_at'))
            return tracks

        # Primary: playlist_items (full pagination)
        try:
            response = self.sp.playlist_items(playlist_id, additional_types=('track',))
            return _save_items(response.get('items') or [])
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
                return []
            if e.http_status != 403:
                raise

        # Fallback on 403: sp.playlist() embeds first 100 tracks in metadata
        print(f"playlist_items 403 for '{playlist['name']}' — trying sp.playlist() fallback")
        try:
            pl_data = self.sp.playlist(playlist_id)
            items = (pl_data.get('tracks') or pl_data or {}).get('items') or []
            return _save_items(items)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            else:
                print(f"sp.playlist() also failed for '{playlist['name']}': {e}")
            return []
        except Exception as e:
            print(f"sp.playlist() fallback error for '{playlist['name']}': {e}")
            return []

    def _cache_artist(self, artist_data):
        if self._db and artist_data and artist_data.get('id'):
            self._db.save_artist(artist_data)

    def _cache_album(self, album_data):
        if self._db and album_data and album_data.get('id'):
            self._db.save_album(album_data)

    def _cache_track(self, track_data):
        if self._db and track_data and track_data.get('uri'):
            self._db.save_track_metadata(track_data)
            # Note: artist genres are NOT fetched here — sp.artist() in a loop would
            # hammer the API. Genres are populated by get_all_followed_artists() and
            # get_recommendations() which run infrequently as bulk operations.

    def _load_rate_limit(self):
        """Read persisted rate-limit timestamp from disk (survives restarts)."""
        try:
            with open(self._rate_limit_file) as f:
                ts = float(f.read().strip())
                if ts > time.time():
                    remaining = int(ts - time.time())
                    print(f"Spotify rate limit still active — {remaining}s remaining")
                    return ts
        except Exception:
            pass
        return 0

    def _save_rate_limit(self):
        """Persist rate-limit timestamp so restarts don't retry too early."""
        try:
            with open(self._rate_limit_file, 'w') as f:
                f.write(str(self._rate_limited_until))
        except Exception:
            pass

    def _is_rate_limited(self):
        return time.time() < self._rate_limited_until

    def _on_rate_limit(self, e):
        """Parse a 429 SpotifyException, set the cooldown, log and persist it."""
        retry_after = 3600  # safe default (1h) — avoids hammering Spotify on repeated 429s
        try:
            # Priority 1: Retry-After header captured by the requests session hook
            if self._last_retry_after and self._last_retry_after > 0:
                retry_after = self._last_retry_after
                self._last_retry_after = None
            else:
                # Priority 2: parse from exception message (older spotipy versions)
                m = re.search(r'Retry will occur after:\s*(\d+)', str(e))
                if m:
                    retry_after = int(m.group(1))
        except Exception:
            pass
        self._rate_limited_until = time.time() + retry_after
        self._save_rate_limit()
        print(f"Rate limited by Spotify — skipping API calls for {retry_after}s ({retry_after//3600}h {(retry_after%3600)//60}m)")

    def seed_instance_cache_if_absent(self):
        """Establish the instance baseline (fixed house account) once, from whatever active
        token already exists. Never overwrite it afterwards — so a guest signing in later
        overlays only the Web API, it cannot hijack the streaming/fallback account."""
        import shutil
        try:
            if os.path.exists(self.instance_cache_path):
                return
            if os.path.exists(self.cache_path):
                shutil.copyfile(self.cache_path, self.instance_cache_path)
                print("Seeded Spotify instance baseline from active cache.")
        except Exception as e:
            print(f"seed instance cache error: {e}")

    def reload_sp(self):
        """(Re)build self.sp from the active per-user overlay (.cache_spotipy) if valid,
        else fall back to the instance baseline (.cache_spotify_instance). Returns the cache
        path used, or None if neither holds a valid token."""
        import requests
        for path in (self.cache_path, self.instance_cache_path):
            cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=path)
            auth_manager = spotipy.oauth2.SpotifyOAuth(scope=self.scope, cache_handler=cache_handler, show_dialog=False)
            if not auth_manager.validate_token(cache_handler.get_cached_token()):
                continue
            session = requests.Session()
            def _capture_retry_after(response, *args, **kwargs):
                if response.status_code == 429:
                    try:
                        self._last_retry_after = int(response.headers.get('Retry-After', 0))
                    except Exception:
                        pass
            session.hooks['response'].append(_capture_retry_after)
            # retries=0: disable spotipy's internal blocking retry-on-429.
            # Our _on_rate_limit() handles 429 immediately without freezing the thread.
            self.sp = spotipy.Spotify(auth_manager=auth_manager, retries=0, requests_session=session)
            return path
        print("Token is not valid (no active overlay nor instance baseline)")
        return None

    def init_token_sp(self):
        self.seed_instance_cache_if_absent()
        self.reload_sp()

    def refresh_token0(self):
        cached_token = self.spo.get_cached_token()
        refreshed_token = cached_token['refresh_token']
        new_token = self.spo.refresh_access_token(refreshed_token)
        print(new_token['access_token'])  # <--
        # also we need to specifically pass `auth=new_token['access_token']`
        self.sp = spotipy.Spotify(auth=new_token['access_token'])
        return new_token

    def get_token(self):
        token_info = self.spo.get_cached_token()
        if token_info:
            access_token = token_info['access_token']
            return access_token
        else:
            auth = self.spo.get_authorize_url()
            print(auth)
            auth_url = input('Click the link above and copy and paste the url here: ')
            re_auth = re.findall(_auth_finder, auth_url)
            access_token = self.spo.get_access_token(_re_auth[0])
            return access_token

    def get_recommendations(
        self, seed_genres=None, seed_artists=None, seed_tracks=None, limit=10, discover_level=5
    ):
        """Replacement for Spotify's removed /recommendations endpoint.

        Primary path: Last.fm artist.getSimilar (collaborative filtering).
          - Seed artists resolved from tracks/artists/genres.
          - Similar artists mixed: followed (low DL) vs external (high DL).
          - External artists resolved DB-first, sp.search() fallback up to budget.

        Fallback (no Last.fm key, or similar list empty):
          - Genre overlap scoring on local cache.
          - External discovery via Last.fm tag.getTopArtists (or sp.search as last resort).
        """
        try:
            seed_artist_ids = set()
            use_cache_only = bool(self._db and self._db.is_cache_rich('artists'))

            # ── 1. Resolve seed tracks → artist IDs ────────────────────────
            if seed_tracks:
                from src.o2mmodels import TrackArtist
                track_ids = seed_tracks if isinstance(seed_tracks, list) else [seed_tracks]
                track_ids = [self.normalize_spotify_id(t) for t in track_ids if t][:3]
                for track_id in track_ids:
                    if self._is_rate_limited():
                        break
                    uri = f"spotify:track:{track_id}"
                    try:
                        rows = list(TrackArtist.select(TrackArtist.artist_id)
                                    .where(TrackArtist.track_uri == uri))
                        if rows:
                            seed_artist_ids.update(r.artist_id for r in rows)
                            continue
                    except Exception:
                        pass
                    if use_cache_only:
                        continue
                    try:
                        t0 = time.time()
                        info = self.sp.track(track_id)
                        print(f"[TIMING] get_recommendations: sp.track() took {time.time()-t0:.2f}s for {track_id}")
                        seed_artist_ids.update(a['id'] for a in info.get('artists', []))
                    except spotipy.SpotifyException as e:
                        if e.http_status == 429:
                            self._on_rate_limit(e)
                        break
                    except Exception:
                        break

            if seed_artists:
                ids = seed_artists if isinstance(seed_artists, list) else [seed_artists]
                seed_artist_ids.update(self.normalize_spotify_id(i) for i in ids if i)

            # ── 2. Seed artist names for Last.fm lookup ─────────────────────
            seed_artist_names = []
            if self._db:
                for artist_id in list(seed_artist_ids)[:3]:
                    cached = self._db.get_artist(artist_id)
                    if cached and cached.name:
                        seed_artist_names.append(cached.name)

            followed = self.get_all_followed_artists()
            followed_set = set(followed)

            # ── 3. PRIMARY: Last.fm artist.getSimilar ───────────────────────
            artist_pool = []
            if self._lastfm_api_key and seed_artist_names:
                # Collect and merge similar artists from up to 2 seed artists
                merged = {}  # name → max score
                for name in seed_artist_names[:2]:
                    for similar_name, score in self._lastfm_get_similar_artists(name, limit=40):
                        if similar_name not in merged or score > merged[similar_name]:
                            merged[similar_name] = score

                similar_sorted = sorted(merged.items(), key=lambda x: -x[1])

                if similar_sorted:
                    # Budget for sp.search() API calls to resolve unknown artists
                    api_budget = max(0, discover_level // 2)  # 0..5 calls
                    resolved_followed = []   # (artist_id, score)
                    resolved_external = []   # (artist_id, score)

                    for sim_name, score in similar_sorted[:30]:
                        # DB-first resolution
                        artist_id = self._resolve_artist_spotify_id(sim_name, allow_api=False)
                        # API fallback if budget allows
                        if not artist_id and api_budget > 0:
                            artist_id = self._resolve_artist_spotify_id(sim_name, allow_api=True)
                            if artist_id:
                                api_budget -= 1
                        if not artist_id or artist_id in seed_artist_ids:
                            continue
                        if artist_id in followed_set:
                            resolved_followed.append((artist_id, score))
                        else:
                            resolved_external.append((artist_id, score))

                    # Mix: prioritise followed at low DL, external at high DL
                    n_followed = max(2, 8 - discover_level)
                    n_external = min(discover_level, len(resolved_external))
                    pool = (
                        [aid for aid, _ in resolved_followed[:n_followed]]
                        + [aid for aid, _ in resolved_external[:n_external]]
                    )
                    random.shuffle(pool)
                    artist_pool = pool
                    print(f"get_recommendations: lastfm similar → {len(resolved_followed)} followed, "
                          f"{len(resolved_external)} external; pool={len(artist_pool)}")

            # ── 4. FALLBACK: genre overlap on local cache ───────────────────
            if not artist_pool:
                target_genres = set(seed_genres or [])

                # Infer genres from seed artists (DB-first)
                for artist_id in list(seed_artist_ids)[:50]:
                    if self._is_rate_limited():
                        break
                    cached = self._db.get_artist(artist_id) if self._db else None
                    if cached:
                        target_genres.update(self._db.get_artist_genres(artist_id))
                        continue
                    if use_cache_only:
                        continue
                    try:
                        a = self.sp.artist(artist_id)
                        if a:
                            target_genres.update(a.get('genres', []))
                            self._cache_artist(a)
                    except spotipy.SpotifyException as e:
                        if e.http_status == 429:
                            self._on_rate_limit(e)
                            break
                    except Exception:
                        pass

                candidates = [i for i in followed if i not in seed_artist_ids]
                random.shuffle(candidates)

                # External artists: Last.fm tag.getTopArtists (DB-only resolution)
                n_external = discover_level * 10
                if n_external > 0 and target_genres and not self._is_rate_limited():
                    external_ids = []
                    if self._lastfm_api_key:
                        for genre in list(target_genres)[:3]:
                            if len(external_ids) >= n_external:
                                break
                            for name in self._lastfm_get_tag_artists(genre, limit=20):
                                aid = self._resolve_artist_spotify_id(name, allow_api=False)
                                if aid and aid not in followed_set and aid not in seed_artist_ids:
                                    external_ids.append(aid)
                    else:
                        # Last resort: sp.search(genre:...)
                        for genre in list(target_genres)[:3]:
                            if len(external_ids) >= n_external or self._is_rate_limited():
                                break
                            try:
                                results = self.sp.search(
                                    q=f'genre:"{genre}"', type='artist', limit=20,
                                    offset=random.randint(0, 50)
                                )
                                for artist in results.get('artists', {}).get('items', []):
                                    aid = artist['id']
                                    if aid not in followed_set and aid not in seed_artist_ids:
                                        external_ids.append(aid)
                            except spotipy.SpotifyException as e:
                                if e.http_status == 429:
                                    self._on_rate_limit(e)
                                break
                            except Exception:
                                pass
                    random.shuffle(external_ids)
                    candidates.extend(external_ids[:n_external])
                    random.shuffle(candidates)

                # Score by genre overlap
                scored = []
                for artist_id in candidates[:10]:
                    if self._is_rate_limited():
                        break
                    cached = self._db.get_artist(artist_id) if self._db else None
                    if cached:
                        genres = set(self._db.get_artist_genres(artist_id))
                        overlap = len(genres & target_genres)
                        if overlap > 0:
                            scored.append((overlap, artist_id))
                        continue
                    if use_cache_only:
                        continue
                    try:
                        a = self.sp.artist(artist_id)
                        if a:
                            overlap = len(set(a.get('genres', [])) & target_genres)
                            if overlap > 0:
                                scored.append((overlap, artist_id))
                            self._cache_artist(a)
                    except spotipy.SpotifyException as e:
                        if e.http_status == 429:
                            self._on_rate_limit(e)
                            break
                    except Exception:
                        pass

                scored.sort(reverse=True)
                artist_pool = [aid for _, aid in scored[:8]] or candidates[:5]
                print(f"get_recommendations: genre fallback → genres={target_genres}, pool={len(artist_pool)}")

            if not artist_pool:
                return []

            # ── 5. Collect tracks from artist pool ──────────────────────────
            per_artist = max(2, (limit * 2) // min(len(artist_pool), 5))
            result = []
            for artist_id in artist_pool[:5]:
                tracks = self.get_artist_all_tracks(artist_id, limit=per_artist)
                result.extend(tracks)

            random.shuffle(result)
            return result[:limit]

        except Exception as e:
            print(f"Recommendation fallback error: {e}")
            return []

    def parse_tracks(self, tracks_json):
        uris = []

        if "tracks" in tracks_json:
            for track in tracks_json["tracks"]:
                uris.append(track["uri"])
        elif "items" in tracks_json:
            for item in tracks_json["items"]:
                uris.append(item["uri"])
        return uris

    def normalize_spotify_id(self, value):
        """Extract a clean Spotify base62 ID (usually 22 chars) from a noisy string."""
        try:
            if value is None:
                return None
            s = str(value)
            # strip common control artifacts seen in logs / m3u parsing
            s = s.replace("\r", "").replace("\n", "").replace("\t", "").strip()
            s = s.replace("#015", "").strip()
            # remove fragments like ...#something
            if "#" in s:
                s = s.split("#", 1)[0]
            # find first base62-ish token, prefer 22-char IDs
            m22 = re.search(r"[A-Za-z0-9]{22}", s)
            if m22:
                return m22.group(0)
            m = re.search(r"[A-Za-z0-9]{10,}", s)
            return m.group(0) if m else s
        except Exception:
            return value

    def normalize_spotify_uri(self, uri):
        """Normalize spotify:* URIs by stripping control chars and normalizing the resource id."""
        try:
            if not uri:
                return uri
            s = str(uri)
            s = s.replace("\r", "").replace("\n", "").replace("\t", "").strip()
            s = s.replace("#015", "").strip()
            if not s.startswith("spotify:"):
                return s
            parts = s.split(":")
            if len(parts) < 3:
                return s
            resource_type = parts[1]
            resource_id = self.normalize_spotify_id(parts[2])
            return f"spotify:{resource_type}:{resource_id}"
        except Exception:
            return uri
    
    def get_resource_name(self, uri):
        """Get human-readable name from Spotify URI (playlist, album, artist).
        DB cache is always checked first — API only called when cache misses and not rate-limited."""
        try:
            if not uri or uri == '':
                return ''

            # o2m: URIs are internal constants — no API call ever needed
            if str(uri).startswith('o2m:'):
                return str(uri).replace('o2m:', '').replace('_', ' ').title()

            uri = self.normalize_spotify_uri(uri)

            if uri.startswith('spotify:'):
                parts = uri.split(':')
                if len(parts) >= 3:
                    resource_type = parts[1]
                    resource_id = self.normalize_spotify_id(parts[2])

                    # Non-ID values (e.g. display names stored as 'playlist:Calm') — return as-is
                    if not re.fullmatch(r"[A-Za-z0-9]{22}", str(resource_id or "")):
                        return uri

                    # ── DB cache-first (works even when rate-limited) ──────────
                    if self._db:
                        if resource_type == 'playlist':
                            try:
                                from src.o2mmodels import Playlist
                                p = Playlist.get_by_id(resource_id)
                                if p and p.name:
                                    return p.name
                            except Exception:
                                pass
                        elif resource_type == 'album':
                            cached = self._db.get_album(resource_id)
                            if cached and cached.name:
                                return cached.name.strip() or uri
                        elif resource_type == 'artist':
                            cached = self._db.get_artist(resource_id)
                            if cached and cached.name:
                                return cached.name or uri

                    # ── API fallback (skipped when rate-limited) ──────────────
                    if self._is_rate_limited():
                        return uri

                    try:
                        if resource_type == 'playlist':
                            playlist = self.sp.playlist(resource_id, fields='name')
                            name = playlist.get('name', uri)
                            return name if name else uri
                        elif resource_type == 'album':
                            album = self.sp.album(resource_id)
                            self._cache_album(album)
                            album_name = album.get('name', '')
                            artist_name = album.get('artists', [{}])[0].get('name', '')
                            return f"{album_name} - {artist_name}".strip(' -') if album_name else uri
                        elif resource_type == 'artist':
                            artist = self.sp.artist(resource_id)
                            self._cache_artist(artist)
                            name = artist.get('name', uri)
                            return name if name else uri
                    except Exception as api_e:
                        print(f"Spotify API error for {resource_type} {resource_id}: {api_e}")
                        return uri

            return uri
        except Exception as e:
            print(f"Error getting resource name for {uri}: {e}")
            return uri

################### SAVED / LIKED TRACKS #################

    def _track_id(self, track_uri):
        return str(track_uri).split(':')[-1]

    def is_track_saved(self, track_uri):
        """True/False si le morceau est dans les titres likés du compte serveur, None si erreur."""
        try:
            return bool(self.sp.current_user_saved_tracks_contains([self._track_id(track_uri)])[0])
        except Exception as e:
            print(f"is_track_saved error: {e}")
            return None

    def set_track_saved(self, track_uri, saved):
        """Ajoute/retire le morceau des titres likés du compte serveur."""
        tid = [self._track_id(track_uri)]
        if saved:
            self.sp.current_user_saved_tracks_add(tid)
        else:
            self.sp.current_user_saved_tracks_delete(tid)
        return True

################### PLAYLISTS #############################

    def add_tracks_playlist(self, username, playlist_uri, track_uris):
        results = self.sp.playlist_add_items(playlist_uri, track_uris)
        print(f"Adding track succesful from playlist {results}")
        return results

    def remove_tracks_playlist(self, playlist_uri, track_uris):
        # normalize playlist id (accept spotify:playlist:ID, open.spotify.com urls or plain id)
        from urllib.parse import urlparse
        playlist_id = playlist_uri
        try:
            if playlist_uri.startswith("spotify:playlist:"):
                playlist_id = playlist_uri.split(":")[2]
            elif "open.spotify.com" in playlist_uri:
                path = urlparse(playlist_uri).path
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 2:
                    playlist_id = parts[1]
        except Exception:
            playlist_id = playlist_uri

        # normalize tracks to spotify:track:ID or IDs
        tracks = []
        for t in track_uris:
            if t is None:
                continue
            if isinstance(t, dict):
                # if code ever passed {"uri": "..."}
                t = t.get("uri") or t.get("id") or str(t)
            if t.startswith("spotify:track:") or len(t) == 22:
                tracks.append(t)
            elif t.startswith("spotify:"):
                tracks.append(t)  # other spotify uri types — let API validate
            else:
                # assume plain id -> build full uri
                tracks.append(f"spotify:track:{t}")

        print(f"Removing from playlist_id={playlist_id} tracks={tracks}")
        results = self.sp.playlist_remove_all_occurrences_of_items(playlist_id, tracks, snapshot_id=None)
        print(f"Removing track successful from playlist: {results}")
        return results

    def get_playlist_id_by_name(self,username, playlist_name):
        playlist_id = ''
        playlists = self.sp.user_playlists(username)
        for playlist in playlists['items']:  
            if playlist['name'] == playlist_name:
                playlist_id = playlist['id']
        return playlist_id

    def get_playlist_id_by_option_type(self,username, option_type):
        playlist_id = ''
        playlists =  self.sp.user_playlists(username)
        for playlist in playlists['items']:  
            if playlist['name'] == playlist_name:
                playlist_id = playlist['id']
        return playlist_id

    def is_track_in_playlist(self, username, track_id, playlist_id):
        results = self.sp.playlist_items(playlist_id, additional_types=('track',))
        tracks = results['items']
        while results['next']:
            results = self.sp.next(results)
            tracks.extend(results['items'])
        for track in tracks:
            if track.get("track") and track["track"].get("id") == track_id:
                return True
        return False
    
    # Original get_playlists_tracks function (archived)
    # def get_playlists_tracks_original(self,limit=1,discover_level=5):
    #     #Get last tracks from each playlist
    #     #To be upgraded : remove trash playlist, enlarge the window
    #     t_list=[]
    #     lib_link=[]
    #     total=0
    #     try: 
    #         playlists = self.sp.current_user_playlists()
    #     except Exception as val_e: 
    #         print(f"Erreur playlist : {val_e}")

    #     #Remove unwanted playlists
    #     print(f"Lenght playlists {len(playlists)}")
    #     if len(playlists)>0:
    #         playlists = playlists['items']
    #         for pl in range(len(playlists)):
    #             #TODO : Remove also option_type='Hidden' 
    #             if playlists[pl]['name']=='Trash':
    #                 playlists.remove(playlists[pl])
    #                 break
            
    #         if len(playlists) < limit: limit = len(playlists)

    #         if len(playlists)>0:
    #             for i in range(limit):
    #                 playlist = random.choice(playlists)
                    
    #                 tracks = self.sp.playlist_tracks(playlist['id'])['items']
    #                 #We take some of the latests tracks added in the playlist
    #                 #size = int(len(playlist)*discover_level/10)
    #                 #if size < len(tracks): tracks = tracks[-size:]
    #                 #print(f"Tracks {len(tracks)} - Size {size}")

    #                 if len(tracks)>0:
    #                     track = random.choice(tracks)
    #                     t_list.append(track['track']['uri'])
    #                     lib_link.append("spotify:playlist:"+playlist['id'])
    #                     #for j in range(unit):
    #                         #track = tracks['items'][-unit:]
    #                         #track = random.choice(tracks['items'])
    #                         #track = tracks[0:1]
    #                         #t_list.append(track['uri'])
    #     return (t_list,lib_link)

    def get_playlists_tracks(self,limit=1,discover_level=5):
        if self._is_rate_limited():
            if self._db:
                cached_ids = self._db.get_all_cached_playlist_ids()
                if cached_ids:
                    print(f"get_playlists_tracks: rate-limited, using {len(cached_ids)} cached playlists")
                    t_list, lib_link = [], []
                    selected = random.sample(cached_ids, min(limit, len(cached_ids)))
                    for pid in selected:
                        uris = self._db.get_playlist_track_uris(pid)
                        if uris:
                            t_list.append(random.choice(uris))
                            lib_link.append(f"spotify:playlist:{pid}")
                    if t_list:
                        return (t_list, lib_link)
                print(f"get_playlists_tracks: rate-limited, playlist cache empty — falling back to play history")
                fallback = self._db.get_random_played_track_uris(limit)
                if fallback:
                    return (fallback, ['o2m:history'] * len(fallback))
            return ([], [])
        #Get random tracks from a selection of user's playlists
        t_list=[]
        lib_link=[]

        try:
            playlists_response = self.sp.current_user_playlists()
        except Exception as val_e:
            print(f"Erreur playlist : {val_e}")
            return ([], [])

        if not playlists_response or not playlists_response['items']:
            return ([], [])

        playlists = playlists_response['items']
        
        # Filter out unwanted playlists (e.g., 'Trash')
        playlists = [pl for pl in playlists if pl['name'] != 'Trash'] # and pl['name'] != 'Hidden' (if implemented)

        if not playlists:
            return ([], [])

        # Select 'limit' unique playlists randomly
        selected_playlists = random.sample(playlists, min(limit, len(playlists)))
        
        for playlist in selected_playlists:
            try:
                # cache-first: use cached tracks if playlist is fresh
                tracks = None
                if self._db and self._db.get_playlist(playlist['id']):
                    tracks = self._db.get_playlist_track_uris(playlist['id'])

                if not tracks:
                    tracks = self._fetch_and_cache_playlist_tracks(playlist)
                    if tracks and self._db:
                        self._db.save_playlist(playlist)
                    elif self._db:
                        # Truly inaccessible — save metadata only so we don't retry for 7 days
                        self._db.save_playlist(playlist)

                if tracks:
                    t_list.append(random.choice(tracks))
                    lib_link.append("spotify:playlist:" + playlist['id'])
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    self._on_rate_limit(e)
                    break
                print(f"Erreur lors de la récupération des pistes de la playlist {playlist['name']}: {e}")
                continue
            except Exception as val_e:
                print(f"Erreur lors de la récupération des pistes de la playlist {playlist['name']}: {val_e}")
                continue
        
        return (t_list,lib_link)

    def cache_all_playlists(self):
        """Bulk cache : fetch ALL user playlists and ALL their tracks.
        Skips silently if rate-limited.  Returns total tracks cached."""
        if self._is_rate_limited():
            print("cache_all_playlists: rate-limited, skipping")
            return 0
        cached = 0
        try:
            response = self.sp.current_user_playlists(limit=50)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            return 0
        except Exception as e:
            print(f"cache_all_playlists error: {e}")
            return 0

        while response and response.get('items'):
            for playlist in response['items']:
                if not playlist or playlist.get('name') == 'Trash':
                    continue
                if self._is_rate_limited():
                    return cached
                if self._db:
                    self._db.save_playlist(playlist)
                print(f"cache_all_playlists: processing '{playlist.get('name')}' ({playlist.get('id')})")
                try:
                    pl_data = self.sp.playlist(playlist['id'])
                    if not pl_data:
                        continue
                    items_response = pl_data.get('tracks') or pl_data.get('items')
                except spotipy.SpotifyException as e:
                    if e.http_status == 429:
                        self._on_rate_limit(e)
                        return cached
                    print(f"cache_all_playlists sp.playlist() SpotifyException http_status={e.http_status} for '{playlist.get('name')}': {e}")
                    continue
                except Exception as e:
                    print(f"cache_all_playlists sp.playlist() {type(e).__name__} for '{playlist.get('name')}': {e!r}")
                    continue

                before = cached
                position = 0
                while items_response:
                    for item in (items_response.get('items') or []):
                        if self._is_rate_limited():
                            return cached
                        track = (item.get('track') or item.get('item')) if item else None
                        if track and track.get('uri'):
                            self._cache_track(track)
                            if self._db:
                                added_at = item.get('added_at')
                                self._db.save_playlist_track(
                                    playlist['id'], track['uri'],
                                    position=position, added_at=added_at)
                            cached += 1
                            position += 1
                    try:
                        if items_response.get('next'):
                            items_response = self.sp.next(items_response)
                        else:
                            break
                    except spotipy.SpotifyException as e:
                        if e.http_status == 429:
                            self._on_rate_limit(e)
                            return cached
                        break
                    except Exception:
                        break
                print(f"cache_all_playlists: '{playlist.get('name')}' → {cached - before} tracks cached")

            if response.get('next'):
                try:
                    response = self.sp.next(response)
                except Exception:
                    break
            else:
                break

        print(f"cache_all_playlists: {cached} tracks cached")
        if self._db:
            self._db.set_cache_meta('warmup_playlist_tracks_at', cached)
        return cached

    # ─── Cache health ──────────────────────────────────────────────────────────

    # TTL (days) between warmup runs per entity type
    _WARMUP_TTL = {'liked': 7, 'artists': 7, 'albums': 7, 'playlist_tracks': 3, 'genres': 14, 'moods': 30, 'mood_retry': 1, 'mood_retry_all': 1, 'spotify_features': 7}

    _MOOD_TAGS = {
        'calm':      {'ambient', 'calm', 'chill', 'chillout', 'relaxing', 'peaceful', 'mellow',
                      'soft', 'gentle', 'background', 'meditation', 'sleep', 'quiet', 'downtempo',
                      'lo fi', 'lofi', 'slow', 'new age', 'nature', 'atmospheric'},
        'energetic': {'energetic', 'energy', 'upbeat', 'dance', 'workout', 'intense', 'driving',
                      'fast', 'exciting', 'party', 'power', 'aggressive', 'hard', 'loud',
                      'high energy', 'adrenaline', 'pump up'},
        'dark':      {'sad', 'melancholic', 'melancholy', 'dark', 'gloomy', 'depressing',
                      'emotional', 'heartbreak', 'sorrow', 'lonely', 'tears', 'grief',
                      'bittersweet', 'introspective'},
        'happy':     {'happy', 'feel good', 'feelgood', 'cheerful', 'uplifting', 'positive',
                      'joyful', 'fun', 'summer', 'sunshine', 'optimistic', 'euphoric'},
    }
    # Genre tags that can infer mood when track-level tags are absent
    _GENRE_MOOD = {
        'calm':      {'classical', 'piano', 'jazz', 'folk', 'acoustic', 'ambient', 'new age',
                      'chamber', 'baroque', 'bossa nova', 'easy listening', 'smooth jazz',
                      'instrumental', 'world', 'meditation',
                      'chanson', 'chanson francaise', 'french pop',
                      'singer songwriter',
                      'contemporary jazz', 'jazz manouche', 'cool jazz', 'nu jazz',
                      'lo fi', 'lofi', 'neo soul'},
        'energetic': {'metal', 'punk', 'hardcore', 'edm', 'techno', 'house', 'drum and bass',
                      'dubstep', 'electro', 'trance', 'breakbeat', 'industrial',
                      'rock', 'alternative', 'alternative rock', 'indie rock', 'hard rock',
                      'progressive rock', 'post rock', 'classic rock',
                      'post punk', 'new wave', 'jangle pop', 'britpop', 'indie pop',
                      'synthpop', 'art pop', 'psychedelic pop', 'psychedelic', 'neo psychedelia',
                      'hip hop', 'rap', 'electronic', 'r&b', 'indie',
                      'bebop', 'post bop', 'free jazz', 'acid jazz', 'jazz fusion', 'fusion'},
        'dark':      {'blues', 'gothic', 'black metal', 'doom metal', 'darkwave',
                      'experimental', 'noise', 'avant garde', 'drone metal', 'shoegaze',
                      'dark folk', 'dark ambient', 'emo', 'grunge',
                      'drone', 'trip hop'},
        'happy':     {'pop', 'reggae', 'funk', 'soul', 'disco', 'ska',
                      'african', 'afrobeat', 'afropop', 'latin', 'cumbia', 'salsa', 'samba',
                      'swing', 'big band', 'dance', 'pop rock', 'world music'},
    }

    # Numeric (energy, valence) per Last.fm tag — weighted average across matching tags.
    # energy: 0.0 = silence/sleep  → 1.0 = extreme metal
    # valence: 0.0 = grief/despair → 1.0 = euphoria/joy
    # Instruments (trumpet, guitar…) intentionally absent — they describe timbre, not mood.
    _TAG_FEATURES = {
        # ── Very low energy ───────────────────────────────────────────────────────
        'sleep':          (0.05, 0.50), 'ambient':        (0.10, 0.52),
        'meditation':     (0.08, 0.62), 'drone':          (0.08, 0.38),
        'nature':         (0.10, 0.65),
        # ── Low energy — ambiance calme ───────────────────────────────────────────
        'calm':           (0.18, 0.62), 'chill':          (0.22, 0.62),
        'chillout':       (0.22, 0.60), 'relaxing':       (0.18, 0.65),
        'peaceful':       (0.15, 0.70), 'mellow':         (0.25, 0.58),
        'soft':           (0.18, 0.62), 'gentle':         (0.15, 0.65),
        'background':     (0.12, 0.55), 'quiet':          (0.12, 0.58),
        'downtempo':      (0.28, 0.48), 'lo fi':          (0.22, 0.55),
        'lofi':           (0.22, 0.55), 'slow':           (0.18, 0.48),
        'new age':        (0.10, 0.65), 'atmospheric':    (0.18, 0.48),
        # ── Low-medium energy — acoustique / classique ────────────────────────────
        'classical':      (0.32, 0.55), 'piano':          (0.30, 0.55),
        'acoustic':       (0.38, 0.62), 'folk':           (0.38, 0.65),
        'instrumental':   (0.32, 0.55), 'easy listening': (0.25, 0.62),
        'chamber':        (0.28, 0.55), 'baroque':        (0.30, 0.55),
        'chanson':        (0.35, 0.58),
        # ── Jazz — famille ────────────────────────────────────────────────────────
        # Jazz = présence, swing, sophistication — PAS lounge (0.35 était trop bas)
        'jazz':           (0.52, 0.60), 'smooth jazz':    (0.35, 0.62),
        'cool jazz':      (0.40, 0.60), 'bossa nova':     (0.45, 0.72),
        'nu jazz':        (0.50, 0.58), 'jazz manouche':  (0.55, 0.68),
        'acid jazz':      (0.62, 0.65), 'jazz fusion':    (0.65, 0.55),
        'bebop':          (0.72, 0.58), 'post-bop':       (0.65, 0.55),
        'swing':          (0.68, 0.78), 'big band':       (0.65, 0.72),
        'electro jazz':   (0.60, 0.62), 'groovy':         (0.68, 0.75),
        # ── Medium energy ─────────────────────────────────────────────────────────
        'world':          (0.50, 0.62), 'country':        (0.55, 0.68),
        'blues':          (0.50, 0.28), 'soul':           (0.58, 0.70),
        'r&b':            (0.60, 0.65), 'indie':          (0.62, 0.55),
        'alternative':    (0.65, 0.48), 'pop':            (0.65, 0.72),
        'reggae':         (0.58, 0.78), 'funk':           (0.72, 0.78),
        'disco':          (0.75, 0.80), 'ska':            (0.72, 0.78),
        'rock':           (0.72, 0.50), 'hip hop':        (0.70, 0.52),
        'rap':            (0.72, 0.50),
        'trip hop':       (0.35, 0.42), 'shoegaze':       (0.60, 0.32),
        # rock / pop sous-genres
        'indie rock':     (0.70, 0.50), 'indie pop':      (0.62, 0.65),
        'jangle pop':     (0.65, 0.60), 'britpop':        (0.68, 0.55),
        'new wave':       (0.68, 0.45), 'post punk':      (0.70, 0.28),
        'synthpop':       (0.72, 0.62), 'art pop':        (0.58, 0.60),
        'psychedelic pop':(0.62, 0.65), 'psychedelic':    (0.60, 0.58),
        'neo psychedelia':(0.58, 0.55),
        'alternative rock': (0.68, 0.48), 'hard rock':    (0.80, 0.42),
        'progressive rock': (0.72, 0.50), 'classic rock':  (0.70, 0.50),
        'grunge':         (0.75, 0.30), 'emo':            (0.65, 0.22),
        'metalcore':      (0.88, 0.30), 'post rock':      (0.62, 0.42),
        # ── Dark/sad ──────────────────────────────────────────────────────────────
        'sad':            (0.30, 0.12), 'melancholic':    (0.28, 0.15),
        'melancholy':     (0.28, 0.15), 'dark':           (0.42, 0.18),
        'gloomy':         (0.28, 0.15), 'depressing':     (0.22, 0.10),
        'emotional':      (0.35, 0.28), 'heartbreak':     (0.28, 0.12),
        'sorrow':         (0.25, 0.15), 'lonely':         (0.22, 0.20),
        'grief':          (0.18, 0.08), 'bittersweet':    (0.38, 0.38),
        'introspective':  (0.30, 0.38), 'gothic':         (0.55, 0.20),
        'darkwave':       (0.58, 0.22),
        # ── Happy/positive ────────────────────────────────────────────────────────
        'happy':          (0.68, 0.90), 'feel good':      (0.65, 0.88),
        'feelgood':       (0.65, 0.88), 'cheerful':       (0.62, 0.88),
        'uplifting':      (0.65, 0.85), 'positive':       (0.62, 0.85),
        'joyful':         (0.68, 0.90), 'fun':            (0.70, 0.88),
        'summer':         (0.70, 0.85), 'sunshine':       (0.65, 0.88),
        'optimistic':     (0.62, 0.85), 'euphoric':       (0.82, 0.92),
        # ── High energy ───────────────────────────────────────────────────────────
        'energetic':      (0.85, 0.70), 'energy':         (0.85, 0.70),
        'upbeat':         (0.80, 0.80), 'dance':          (0.80, 0.78),
        'workout':        (0.85, 0.68), 'intense':        (0.85, 0.55),
        'driving':        (0.78, 0.58), 'fast':           (0.82, 0.58),
        'exciting':       (0.80, 0.75), 'party':          (0.82, 0.80),
        'power':          (0.82, 0.60), 'high energy':    (0.88, 0.68),
        'adrenaline':     (0.90, 0.60), 'pump up':        (0.88, 0.70),
        'electronic':     (0.68, 0.60), 'electro':        (0.72, 0.60),
        'edm':            (0.85, 0.70), 'house':          (0.80, 0.68),
        'techno':         (0.85, 0.55), 'trance':         (0.85, 0.65),
        'drum and bass':  (0.88, 0.58), 'dubstep':        (0.85, 0.50),
        'breakbeat':      (0.82, 0.58),
        # ── Very high energy ──────────────────────────────────────────────────────
        'punk':           (0.85, 0.52), 'metal':          (0.90, 0.35),
        'hardcore':       (0.92, 0.40), 'black metal':    (0.90, 0.18),
        'doom metal':     (0.72, 0.18), 'industrial':     (0.85, 0.28),
        'aggressive':     (0.88, 0.35), 'hard':           (0.82, 0.45),
        'loud':           (0.85, 0.50),
    }

    # Tags Last.fm sans valeur musicale pour le scoring mood/energy/valence.
    # Complété par _is_noise_tag() qui filtre aussi les tags décennie/année (80s, 1986…).
    _NOISE_TAGS = frozenset({
        # Personnel / collection
        'seen live', 'favorites', 'favourite', 'favourites', 'love', 'loved',
        'my favorite', 'favourite albums', 'favourite songs', 'my favourites',
        'wishlist', 'to buy', 'owned',
        # Qualité générique
        'good', 'best', 'awesome', 'cool', 'great', 'amazing', 'beautiful',
        'perfect', 'classic', 'all', 'under 2000',
        # Nationalité (non-genre)
        'american', 'british', 'english', 'german', 'swedish', 'norwegian',
        'japanese', 'australian', 'canadian', 'irish', 'scottish',
        'italian', 'spanish',
        # Artiste utilisé comme tag
        'manu chao', 'miles', 'the smiths', 'nirvana',
        # Bruit divers
        'various artists', 'unknown', 'albums i own', 'check', 'spotify',
    })

    import re as _re
    _NOISE_TAG_RE = _re.compile(r'^\d+s?$')  # 80s, 1986, 00s, 2000s…

    @staticmethod
    def _normalize_tag(name):
        """Lowercase, strip accents, hyphens→spaces, collapse whitespace."""
        import unicodedata as _ud
        n = name.lower().strip()
        n = _ud.normalize('NFKD', n)
        n = ''.join(c for c in n if not _ud.combining(c))
        n = n.replace('-', ' ')
        return ' '.join(n.split())

    def _is_noise_tag(self, name):
        n = self._normalize_tag(name)
        return n in self._NOISE_TAGS or bool(self._NOISE_TAG_RE.match(n))

    def fetch_spotify_totals(self):
        """Fetch Spotify totals (liked, artists, albums, playlists) and store in CacheMeta.
        Called once at startup; safe to call again to refresh.
        Skips silently if rate-limited or DB unavailable."""
        if not self._db or self._is_rate_limited():
            return
        pairs = [
            ('total_liked',     lambda: self.sp.current_user_saved_tracks(limit=1)['total']),
            ('total_artists',   lambda: self.sp.current_user_followed_artists(limit=1)['artists']['total']),
            ('total_albums',    lambda: self.sp.current_user_saved_albums(limit=1)['total']),
            ('total_playlists', lambda: self.sp.current_user_playlists(limit=1)['total']),
        ]
        for key, fetch in pairs:
            if self._is_rate_limited():
                break
            try:
                value = fetch()
                self._db.set_cache_meta(key, value)
                print(f"fetch_spotify_totals: {key}={value}")
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    self._on_rate_limit(e)
                break
            except Exception as e:
                print(f"fetch_spotify_totals {key} error: {e}")

    def should_warmup(self, entity_type, discover_level=5):
        """Return True if a warmup run is needed for *entity_type*.

        Triggers when EITHER:
          - TTL since last warmup is exceeded, OR
          - fill rate is below the discover_level-adjusted threshold.

        discover_level influence: higher DL → stricter threshold (needs more novelty).
          dl=0  → 30 %   dl=5 → 55 %   dl=10 → 80 %
        """
        if not self._db:
            return False
        import datetime as dt
        # TTL check
        _, last_at = self._db.get_cache_meta(f'warmup_{entity_type}_at')
        ttl = self._WARMUP_TTL.get(entity_type, 7)
        if last_at:
            days_since = (dt.datetime.utcnow() - last_at).days if isinstance(last_at, dt.datetime) else ttl + 1
            if days_since < ttl:
                # TTL still fresh — only trigger if fill rate is below DL threshold
                threshold = 0.30 + 0.05 * discover_level
                return not self._db.is_cache_rich(entity_type, threshold)
        # TTL expired → always warmup
        return True

    def warmup_liked_tracks(self):
        """Page through all liked tracks and cache them (liked=1)."""
        if self._is_rate_limited():
            return
        print("warmup: syncing liked tracks…")
        count = 0
        try:
            response = self.sp.current_user_saved_tracks(limit=50)
            while response and response.get('items'):
                for item in response['items']:
                    if self._is_rate_limited():
                        return
                    track = item.get('track')
                    if track and track.get('uri'):
                        self._cache_track(track)
                        if self._db:
                            self._db.mark_track_liked(track['uri'], item.get('added_at'))
                        count += 1
                if response.get('next'):
                    response = self.sp.next(response)
                else:
                    break
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            return
        except Exception as e:
            print(f"warmup_liked_tracks error: {e}")
            return
        print(f"warmup: {count} liked tracks synced")
        if self._db:
            self._db.set_cache_meta('warmup_liked_at', count)

    def warmup_saved_albums(self):
        """Page through all saved albums, cache metadata + tracks via AlbumTrack."""
        if self._is_rate_limited():
            return
        print("warmup: syncing saved albums…")
        count = 0
        try:
            response = self.sp.current_user_saved_albums(limit=50)
            while response and response.get('items'):
                for item in response['items']:
                    if self._is_rate_limited():
                        return
                    album = item.get('album')
                    if not album:
                        continue
                    self._cache_album(album)
                    if self._db:
                        self._db.mark_album_saved(album['id'])
                    # cache tracks if not already fully fresh
                    if self._db and not self._db.is_album_track_cache_fresh(album['id']):
                        tracks_page = album.get('tracks', {})
                        pos = 0
                        while tracks_page:
                            for track in (tracks_page.get('items') or []):
                                if track and track.get('uri'):
                                    track.setdefault('album', album)
                                    self._cache_track(track)
                                    self._db.save_album_track(album['id'], track['uri'], pos)
                                    pos += 1
                            next_url = tracks_page.get('next')
                            if next_url and not self._is_rate_limited():
                                tracks_page = self.sp.next(tracks_page)
                            else:
                                break
                    count += 1
                if response.get('next'):
                    response = self.sp.next(response)
                else:
                    break
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            return
        except Exception as e:
            print(f"warmup_saved_albums error: {e}")
            return
        print(f"warmup: {count} saved albums synced")
        if self._db:
            self._db.set_cache_meta('warmup_albums_at', count)

    def _lastfm_get_top_tags(self, artist_name, max_tags=8, min_count=5):
        """Fetch top tags for an artist from Last.fm API.

        Returns a list of tag name strings (up to max_tags), or None on error.
        """
        import requests as req
        if not self._lastfm_api_key:
            return None
        try:
            resp = req.get(
                'https://ws.audioscrobbler.com/2.0/',
                params={
                    'method': 'artist.getTopTags',
                    'artist': artist_name,
                    'api_key': self._lastfm_api_key,
                    'autocorrect': 1,
                    'format': 'json',
                },
                timeout=8,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            tags = (data.get('toptags') or {}).get('tag') or []
            if isinstance(tags, dict):
                tags = [tags]
            result = []
            for t in tags:
                name = (t.get('name') or '').strip().lower()
                count = int(t.get('count') or 0)
                if name and count >= min_count and not self._is_noise_tag(name):
                    result.append(name)
                if len(result) >= max_tags:
                    break
            return result
        except Exception as e:
            print(f"lastfm_get_top_tags({artist_name}): {e}")
            return None

    def _lastfm_get_similar_artists(self, artist_name, limit=40):
        """Return [(name, match_score), ...] from Last.fm artist.getSimilar, sorted by score desc."""
        import requests as req
        if not self._lastfm_api_key or not artist_name:
            return []
        try:
            resp = req.get(
                'https://ws.audioscrobbler.com/2.0/',
                params={
                    'method': 'artist.getSimilar',
                    'artist': artist_name,
                    'api_key': self._lastfm_api_key,
                    'autocorrect': 1,
                    'limit': limit,
                    'format': 'json',
                },
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            artists = (data.get('similarartists') or {}).get('artist') or []
            if isinstance(artists, dict):
                artists = [artists]
            return [(a['name'], float(a.get('match', 0))) for a in artists if a.get('name')]
        except Exception as e:
            print(f"lastfm_get_similar_artists({artist_name}): {e}")
            return []

    def _lastfm_get_tag_artists(self, tag, limit=20):
        """Return [artist_name, ...] from Last.fm tag.getTopArtists."""
        import requests as req
        if not self._lastfm_api_key or not tag:
            return []
        try:
            resp = req.get(
                'https://ws.audioscrobbler.com/2.0/',
                params={
                    'method': 'tag.getTopArtists',
                    'tag': tag,
                    'api_key': self._lastfm_api_key,
                    'limit': limit,
                    'format': 'json',
                },
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            artists = (data.get('topartists') or {}).get('artist') or []
            if isinstance(artists, dict):
                artists = [artists]
            return [a['name'] for a in artists if a.get('name')]
        except Exception as e:
            print(f"lastfm_get_tag_artists({tag}): {e}")
            return []

    def _resolve_artist_spotify_id(self, artist_name, allow_api=True):
        """Resolve an artist name to a Spotify ID. DB-first, then sp.search() if allow_api."""
        if not artist_name:
            return None
        if self._db:
            from src.o2mmodels import Artist
            try:
                return Artist.get(Artist.name == artist_name).id
            except Exception:
                pass
        if not allow_api or self._is_rate_limited():
            return None
        try:
            results = self.sp.search(q=f'artist:"{artist_name}"', type='artist', limit=1)
            items = (results.get('artists') or {}).get('items') or []
            if items:
                a = items[0]
                if a.get('name', '').lower() == artist_name.lower():
                    self._cache_artist(a)
                    return a['id']
        except Exception:
            pass
        return None

    def warmup_artist_genres(self):
        """Fetch genres for up to 30 artists not yet in ArtistGenre via Last.fm API.

        Falls back to sp.search() if no Last.fm API key is configured.
        Conservative: 0.3s sleep between calls (Last.fm allows 5 req/s).
        Not run automatically — only triggered via /api/warmup_genres or /api/diag/genres.
        Returns a dict of results for diagnostic use.
        """
        if not self._db:
            return {'error': 'no db'}
        from src.o2mmodels import ArtistGenre, Artist
        existing_before = ArtistGenre.select().count()
        artist_ids = self._db.get_artist_ids_without_genres(max_count=30)
        if not artist_ids:
            print(f"warmup_artist_genres: all artists already have genres ({existing_before} genre entries)")
            return {'genre_entries_before': existing_before, 'genre_entries_after': existing_before,
                    'artists_checked': [], 'count_with_genres': 0, 'count_without': 0}

        use_lastfm = bool(self._lastfm_api_key)
        source = 'lastfm' if use_lastfm else 'spotify_search'
        print(f"warmup_artist_genres: {existing_before} genre entries, fetching for {len(artist_ids)} artists via {source}")
        count = 0
        no_genre_count = 0
        artists_checked = []

        for artist_id in artist_ids:
            if not use_lastfm and self._is_rate_limited():
                print("warmup_artist_genres: rate-limited, aborting")
                break
            try:
                try:
                    artist_name = Artist.get_by_id(artist_id).name
                except Exception:
                    artist_name = None

                if not artist_name:
                    artists_checked.append({'id': artist_id, 'name': artist_id, 'genres_raw': None, 'skip': 'no_name'})
                    no_genre_count += 1
                    continue

                if use_lastfm:
                    genres = self._lastfm_get_top_tags(artist_name)
                    artists_checked.append({'id': artist_id, 'name': artist_name, 'genres_raw': genres, 'source': 'lastfm'})
                    if genres:
                        self._db.save_artist_genres(artist_id, genres)
                        count += 1
                        print(f"  genres: {artist_name} → {genres[:3]}")
                    else:
                        no_genre_count += 1
                    time.sleep(0.3)
                else:
                    # Fallback: Spotify search (may return empty genres)
                    results = self.sp.search(q=f'artist:{artist_name}', type='artist', limit=5)
                    items = (results.get('artists') or {}).get('items') or []
                    match = next((a for a in items if a['id'] == artist_id), None)
                    if match:
                        genres = match.get('genres') or []
                        artists_checked.append({'id': artist_id, 'name': artist_name, 'genres_raw': genres, 'source': 'spotify'})
                        if genres:
                            self._db.save_artist_genres(artist_id, genres)
                            self._cache_artist(match)
                            count += 1
                            print(f"  genres: {artist_name} → {genres[:3]}")
                        else:
                            no_genre_count += 1
                    else:
                        artists_checked.append({'id': artist_id, 'name': artist_name, 'genres_raw': None, 'skip': 'no_search_match'})
                        no_genre_count += 1
                    time.sleep(0.5)

            except spotipy.SpotifyException as e:
                artists_checked.append({'id': artist_id, 'name': artist_id, 'error': str(e)})
                if e.http_status == 429:
                    self._on_rate_limit(e)
                    print("warmup_artist_genres: rate-limited, aborting")
                    break
                elif e.http_status == 403:
                    print("warmup_artist_genres: endpoint returned 403, aborting")
                    break
                else:
                    print(f"warmup_artist_genres error ({artist_id}): {e}")
            except Exception as e:
                artists_checked.append({'id': artist_id, 'name': artist_id, 'error': str(e)})
                print(f"warmup_artist_genres error ({artist_id}): {e}")

        existing_after = ArtistGenre.select().count()
        print(f"warmup_artist_genres: done — {count} with genres, {no_genre_count} without, out of {len(artist_ids)}")
        # Only set TTL when no artists remain — lets warmup_cache re-run each startup until complete
        remaining = self._db.get_artist_ids_without_genres(max_count=1)
        if not remaining:
            self._db.set_cache_meta('warmup_genres_at', existing_after or 1)
            print("warmup_artist_genres: all artists covered, TTL set (next run in 14 days)")
        return {
            'genre_entries_before': existing_before,
            'genre_entries_after': existing_after,
            'artists_checked': artists_checked,
            'count_with_genres': count,
            'count_without': no_genre_count,
        }

    def _lastfm_get_track_mood(self, artist_name, track_name, album_name=None,
                               track_uri=None, album_id=None):
        """Return (mood, energy, valence) for a track via Last.fm tags.

        Fallback chain: track.getTopTags → album.getTopTags → artist genre cache → artist.getTopTags
        track_uri / album_id: when provided, DB cache (TrackGenre / AlbumGenre) is checked before
        calling the API, and results are persisted after a successful API call.
        Returns (None, None, None) if Last.fm key absent or no signal found.
        """
        if not self._lastfm_api_key:
            return None, None, None

        def _score_mood(tags_wc):
            # tags_wc: [(name, weight), ...] — weight = Last.fm count or 1 for equal weight
            # Uses self._tag_mood_map: {normalized_tag: mood_cat} loaded from DB
            scores = {'calm': 0, 'energetic': 0, 'dark': 0, 'happy': 0}
            for tag, weight in tags_wc:
                tn = self._normalize_tag(tag)
                cat = self._tag_mood_map.get(tn)
                if cat and cat in scores:
                    scores[cat] += weight
            best_cat = max(scores, key=scores.get)
            return best_cat if scores[best_cat] > 0 else None

        def _score_features(tags_wc):
            # tags_wc: [(name, weight), ...] — weighted average of (energy, valence)
            matches = [(e, v, w) for tag, w in tags_wc
                       for k, (e, v) in self._TAG_FEATURES.items()
                       if self._normalize_tag(tag) == k]
            if not matches:
                return None, None
            total_w = sum(w for _, _, w in matches)
            return (
                round(sum(e * w for e, _, w in matches) / total_w, 3),
                round(sum(v * w for _, v, w in matches) / total_w, 3),
            )

        def _finalize(mood, energy, valence):
            """Derive mood from quadrant when energy/valence are available; tag-mood as fallback only."""
            if energy is not None:
                v = valence if valence is not None else 0.5
                # 4-quadrant Russell circumplex: mood = f(energy, valence)
                # happy=haut-droite, energetic=bas-droite, calm=haut-gauche, dark=bas-gauche
                if energy > 0.5 and v > 0.5:
                    mood = 'happy'
                elif energy > 0.5:
                    mood = 'energetic'
                elif v > 0.5:
                    mood = 'calm'
                else:
                    mood = 'dark'
            # else: no features found → keep tag-based mood as fallback
            return mood, energy, valence

        # --- Primary: track.getTopTags (DB cache first) ---
        if track_uri and self._db:
            cached = self._db.get_track_genres(track_uri)
            if cached:
                energy, valence = _score_features(cached)
                mood = None if energy is not None else _score_mood(cached)
                if energy is not None or mood:
                    return _finalize(mood, energy, valence)

        try:
            url = (
                f"https://ws.audioscrobbler.com/2.0/?method=track.getTopTags"
                f"&artist={requests.utils.quote(artist_name)}"
                f"&track={requests.utils.quote(track_name)}"
                f"&api_key={self._lastfm_api_key}&format=json"
            )
            resp = requests.get(url, timeout=5)
            data = resp.json()
            raw_tags = (data.get('toptags') or {}).get('tag') or []
            if isinstance(raw_tags, dict):
                raw_tags = [raw_tags]
            tags_wc = [(t['name'], int(t.get('count', 0)))
                       for t in raw_tags
                       if int(t.get('count', 0)) >= 2
                       and not self._is_noise_tag(t.get('name', ''))]
            if tags_wc:
                if track_uri and self._db:
                    self._db.save_track_genres(track_uri, tags_wc)
                energy, valence = _score_features(tags_wc)
                mood = None if energy is not None else _score_mood(tags_wc)
                if energy is not None or mood:
                    return _finalize(mood, energy, valence)
        except Exception:
            pass

        # --- Fallback 1: album.getTopTags (DB cache first) ---
        if album_id and self._db:
            cached = self._db.get_album_genres(album_id)
            if cached:
                energy, valence = _score_features(cached)
                mood = None if energy is not None else _score_mood(cached)
                if energy is not None or mood:
                    return _finalize(mood, energy, valence)

        if album_name:
            try:
                url = (
                    f"https://ws.audioscrobbler.com/2.0/?method=album.getTopTags"
                    f"&artist={requests.utils.quote(artist_name)}"
                    f"&album={requests.utils.quote(album_name)}"
                    f"&autocorrect=1&api_key={self._lastfm_api_key}&format=json"
                )
                resp = requests.get(url, timeout=5)
                data = resp.json()
                raw_tags = (data.get('toptags') or {}).get('tag') or []
                if isinstance(raw_tags, dict):
                    raw_tags = [raw_tags]
                tags_wc = [(t['name'], int(t.get('count', 0)))
                           for t in raw_tags
                           if int(t.get('count', 0)) >= 2
                           and not self._is_noise_tag(t.get('name', ''))]
                if tags_wc:
                    if album_id and self._db:
                        self._db.save_album_genres(album_id, tags_wc)
                    energy, valence = _score_features(tags_wc)
                    mood = None if energy is not None else _score_mood(tags_wc)
                    if energy is not None or mood:
                        return _finalize(mood, energy, valence)
            except Exception:
                pass

        # --- Fallback 2: artist genre cache DB (poids égaux) ---
        try:
            artist_id = self._resolve_artist_spotify_id(artist_name, allow_api=False)
            if artist_id and self._db:
                genres = self._db.get_artist_genres(artist_id)
                if genres:
                    genres_wc = [(g, 1) for g in genres]
                    energy, valence = _score_features(genres_wc)
                    mood = None if energy is not None else _score_mood(genres_wc)
                    if energy is not None or mood:
                        return _finalize(mood, energy, valence)
        except Exception:
            pass

        # --- Fallback 3: artist.getTopTags direct Last.fm (poids égaux) ---
        try:
            artist_tags = self._lastfm_get_top_tags(artist_name, min_count=5) or []
            if artist_tags:
                # Store in ArtistGenre for future cache hits, regardless of mood result
                try:
                    a_id = self._resolve_artist_spotify_id(artist_name, allow_api=False)
                    if a_id and self._db:
                        self._db.save_artist_genres(a_id, artist_tags)
                except Exception:
                    pass
                artist_wc = [(t, 1) for t in artist_tags]
                energy, valence = _score_features(artist_wc)
                mood = None if energy is not None else _score_mood(artist_wc)
                if energy is not None or mood:
                    return _finalize(mood, energy, valence)
        except Exception:
            pass

        return None, None, None

    def warmup_spotify_features(self, batch_size=100, max_batches=20):
        """Fetch energy+valence from Spotify audio_features for all spotify:track: URIs.

        Covers both NULL tracks and '_' sentinel tracks. 100 tracks per API call,
        no sleep needed. Last.fm pipeline remains as fallback for local/non-Spotify tracks.
        Returns (assigned, remaining) counts.
        """
        if not self.sp:
            print("warmup_spotify_features: skipped (no Spotify connection)")
            return 0, 0
        if not self._db:
            print("warmup_spotify_features: skipped (no DB)")
            return 0, 0
        # Check if endpoint was previously found to be unavailable (403)
        disabled, _ = self._db.get_cache_meta('spotify_features_disabled')
        if disabled:
            print("warmup_spotify_features: skipped (audio_features endpoint unavailable for this app)")
            return 0, 0

        total_assigned = 0
        for batch_num in range(max_batches):
            if self._is_rate_limited():
                print("warmup_spotify_features: rate-limited, stopping")
                break

            uris = self._db.get_spotify_tracks_without_features(limit=batch_size)
            if not uris:
                self._db.set_cache_meta('warmup_spotify_features_at', 1)
                print("warmup_spotify_features: all Spotify tracks have features, TTL set")
                break

            print(f"warmup_spotify_features: batch {batch_num+1}/{max_batches} — {len(uris)} tracks")
            try:
                features_list = self.sp.audio_features(uris)
            except spotipy.SpotifyException as e:
                if e.http_status == 403:
                    # Endpoint deprecated/unavailable for this Spotify app — disable permanently
                    self._db.set_cache_meta('spotify_features_disabled', 1)
                    print("warmup_spotify_features: audio_features endpoint returned 403 — disabled (Spotify API deprecation)")
                elif e.http_status == 429:
                    self._on_rate_limit(e)
                else:
                    print(f"warmup_spotify_features: Spotify error: {e}")
                break
            except Exception as e:
                print(f"warmup_spotify_features: error: {e}")
                break

            batch_assigned = 0
            for uri, features in zip(uris, features_list or []):
                if not features:
                    self._db.update_track_features(uri, mood='_')
                    continue
                energy = features.get('energy')
                valence = features.get('valence')
                if energy is None:
                    self._db.update_track_features(uri, mood='_')
                    continue
                v = valence if valence is not None else 0.5
                if energy > 0.5 and v > 0.5:
                    mood = 'happy'
                elif energy > 0.5:
                    mood = 'energetic'
                elif v > 0.5:
                    mood = 'calm'
                else:
                    mood = 'dark'
                self._db.update_track_features(uri, mood=mood, energy=energy, valence=valence)
                batch_assigned += 1

            total_assigned += batch_assigned
            print(f"warmup_spotify_features: batch done — {batch_assigned}/{len(uris)} assigned")

        remaining = self._db.count_spotify_tracks_without_features()
        print(f"warmup_spotify_features: session total {total_assigned} assigned, {remaining} remaining")
        return total_assigned, remaining

    def warmup_track_moods(self, batch_size=50, max_batches=1):
        """Fetch Last.fm mood for tracks that don't have one yet.

        Processes up to batch_size*max_batches tracks; stops early if rate-limited or all done.
        Returns (assigned, remaining) counts.
        Smart TTL activates only when all tracks are covered.
        """
        if not self._db or not self._lastfm_api_key:
            print("warmup_track_moods: skipped (no DB or no Last.fm key)")
            return 0, 0

        total_assigned = 0
        for batch_num in range(max_batches):
            if self._is_rate_limited():
                print("warmup_track_moods: rate-limited, stopping")
                break

            tracks = self._db.get_tracks_without_mood(limit=batch_size)
            if not tracks:
                self._db.set_cache_meta('warmup_moods_at', 1)
                print("warmup_track_moods: all tracks have features, TTL set (30 days)")
                return total_assigned, 0

            print(f"warmup_track_moods: batch {batch_num+1}/{max_batches} — {len(tracks)} tracks via Last.fm")
            batch_assigned = 0
            for uri, track_name, artist_name, album_name, album_id in tracks:
                if self._is_rate_limited():
                    break
                try:
                    mood, energy, valence = self._lastfm_get_track_mood(
                        artist_name, track_name, album_name, track_uri=uri, album_id=album_id)
                    if mood or energy is not None:
                        self._db.update_track_features(uri, mood=mood, energy=energy, valence=valence)
                        batch_assigned += 1
                        print(f"  {artist_name} – {track_name} → mood={mood} e={energy} v={valence}")
                    else:
                        # Mark as attempted so it isn't retried endlessly this session
                        self._db.update_track_features(uri, mood='_')
                    time.sleep(0.25)
                except Exception as e:
                    print(f"warmup_track_moods error ({track_name}): {e}")

            total_assigned += batch_assigned
            print(f"warmup_track_moods: batch done — {batch_assigned}/{len(tracks)} assigned")

        remaining = self._db.count_tracks_without_mood()
        print(f"warmup_track_moods: session total {total_assigned} assigned, {remaining} remaining")
        return total_assigned, remaining

    def warmup_retry_sentinels(self, batch_size=50, max_batches=2):
        """Re-process tracks with mood='_' whose artist now has genres in DB.

        These tracks were marked as 'no data' before artist genres were populated.
        With the new fallback 2 (direct artist.getTopTags), they can now be resolved.
        """
        if not self._db or not self._lastfm_api_key:
            return 0
        total = 0
        for batch_num in range(max_batches):
            if self._is_rate_limited():
                break
            tracks = self._db.get_sentinel_tracks_with_artist_genres(limit=batch_size)
            if not tracks:
                print("warmup_retry_sentinels: no eligible sentinel tracks remaining")
                break
            print(f"warmup_retry_sentinels: batch {batch_num+1}/{max_batches} — {len(tracks)} tracks")
            batch_assigned = 0
            for uri, track_name, artist_name, album_name, album_id in tracks:
                if self._is_rate_limited():
                    break
                try:
                    mood, energy, valence = self._lastfm_get_track_mood(
                        artist_name, track_name, album_name, track_uri=uri, album_id=album_id)
                    if mood or energy is not None:
                        self._db.update_track_features(uri, mood=mood, energy=energy, valence=valence)
                        batch_assigned += 1
                        print(f"  retry: {artist_name} – {track_name} → mood={mood} e={energy} v={valence}")
                    time.sleep(0.25)
                except Exception as e:
                    print(f"warmup_retry_sentinels error ({track_name}): {e}")
            total += batch_assigned
            print(f"warmup_retry_sentinels: batch done — {batch_assigned}/{len(tracks)} resolved")
        print(f"warmup_retry_sentinels: done — {total} total resolved")
        return total

    def warmup_retry_all_sentinels(self, batch_size=50, max_batches=5):
        """Re-process ALL tracks with mood='_', not just those with cached artist genres.

        Runs the full _lastfm_get_track_mood chain (track → album → artist cache → artist API).
        Effective now that:
        - thresholds are lower (count >= 2 for tracks/albums, >= 5 for artists)
        - artist tags from Fallback 3 are stored in ArtistGenre for future hits
        Tracks still unresolved keep mood='_'.
        """
        if not self._db or not self._lastfm_api_key:
            return 0
        total = 0
        for batch_num in range(max_batches):
            if self._is_rate_limited():
                break
            tracks = self._db.get_all_sentinel_tracks(limit=batch_size)
            if not tracks:
                print("warmup_retry_all_sentinels: no sentinel tracks remaining")
                break
            print(f"warmup_retry_all_sentinels: batch {batch_num+1}/{max_batches} — {len(tracks)} tracks")
            batch_assigned = 0
            for uri, track_name, artist_name, album_name, album_id in tracks:
                if self._is_rate_limited():
                    break
                try:
                    mood, energy, valence = self._lastfm_get_track_mood(
                        artist_name, track_name, album_name, track_uri=uri, album_id=album_id)
                    if mood or energy is not None:
                        self._db.update_track_features(uri, mood=mood, energy=energy, valence=valence)
                        batch_assigned += 1
                        print(f"  resolved: {artist_name} – {track_name} → mood={mood} e={energy} v={valence}")
                    # Do NOT re-mark as '_' here — leave sentinel as-is so we retry next run
                    time.sleep(0.3)
                except Exception as e:
                    print(f"warmup_retry_all_sentinels error ({track_name}): {e}")
            total += batch_assigned
            print(f"warmup_retry_all_sentinels: batch done — {batch_assigned}/{len(tracks)} resolved")
        print(f"warmup_retry_all_sentinels: done — {total} total resolved")
        return total

    def warmup_cache(self, discover_level=5):
        """Orchestrate all warmup passes based on should_warmup() decision.
        Designed to run in a background thread at startup."""
        print(f"warmup_cache: starting (dl={discover_level})")
        self.fetch_spotify_totals()
        for entity_type, method in [
            ('liked',           self.warmup_liked_tracks),
            ('albums',          self.warmup_saved_albums),
            ('artists',         self.get_all_followed_artists),   # already pages + caches
            ('playlist_tracks', self.cache_all_playlists),
            ('genres',            self.warmup_artist_genres),       # 30/run via Last.fm; repeats until all done
            ('spotify_features',  lambda: self.warmup_spotify_features(batch_size=100, max_batches=5)),  # up to 500/startup via Spotify
            ('moods',             lambda: self.warmup_track_moods(batch_size=50, max_batches=5)),  # up to 250/startup via Last.fm fallback
            ('mood_retry',        lambda: self.warmup_retry_sentinels(batch_size=50, max_batches=2)),  # retry '_' with cached artist genres
            ('mood_retry_all',    lambda: self.warmup_retry_all_sentinels(batch_size=50, max_batches=2)),  # broader: all sentinels via full chain
        ]:
            if self._is_rate_limited():
                print(f"warmup_cache: rate-limited, stopping before {entity_type}")
                break
            if self.should_warmup(entity_type, discover_level):
                print(f"warmup_cache: running warmup for {entity_type}")
                method()
                # Save warmup timestamp for entities whose methods don't do it themselves
                if entity_type == 'artists' and self._db:
                    self._db.set_cache_meta('warmup_artists_at', 1)
            else:
                print(f"warmup_cache: {entity_type} cache is rich enough, skipping")
        print("warmup_cache: done")

################### ALBUMS  #############################

    def get_album_all_tracks(self, album_uri, limit=10):
        if not album_uri:
            return []
        # Cache-first: extract album_id from URI and check AlbumTrack table
        album_id = None
        parts = str(album_uri).split(':')
        if len(parts) >= 3 and parts[1] == 'album':
            album_id = parts[2]
        if album_id and self._db:
            cached = self._db.get_album_tracks(album_id)
            if cached:
                print(f"[TIMING] get_album_all_tracks: cache hit ({len(cached)} tracks) for {album_id}")
                random.shuffle(cached)
                return cached[:limit]
        if self._is_rate_limited():
            return []
        try:
            t0 = time.time()
            tracks_json = self.sp.album_tracks(album_uri)
            print(f"[TIMING] get_album_all_tracks: sp.album_tracks() took {time.time()-t0:.2f}s for {album_uri}")
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            print(f"get_album_all_tracks error: {e}")
            return []
        except Exception as e:
            print(f"get_album_all_tracks error: {e}")
            return []
        tracks_uris = self.parse_tracks(tracks_json)
        # Persist to AlbumTrack cache for future calls
        if album_id and self._db:
            for pos, uri in enumerate(tracks_uris):
                self._db.save_album_track(album_id, uri, pos)
        random.shuffle(tracks_uris)
        return tracks_uris[:limit]

    def get_my_albums_tracks(self, limit=1, unit=1, return_source=False, return_pairs=False):
        album_uri = None
        # Cache-first: use saved albums from DB if available (avoids API call for total)
        if self._db:
            saved_ids = self._db.get_saved_album_ids()
            if saved_ids:
                if self._is_rate_limited() or self._db.is_cache_rich('albums'):
                    if self._is_rate_limited():
                        print(f"get_my_albums_tracks: rate-limited, using {len(saved_ids)} cached saved albums")
                    t_list = []
                    pairs = []
                    selected = random.sample(saved_ids, min(limit, len(saved_ids)))
                    for album_id in selected:
                        tracks = self._db.get_album_tracks(album_id)
                        src = f"spotify:album:{album_id}"
                        if tracks and unit != 0:
                            chosen = [random.choice(tracks) for _ in range(unit)]
                            t_list.extend(chosen)
                            if return_pairs:
                                pairs.extend([(t, src) for t in chosen])
                        elif tracks:
                            t_list.extend(tracks)
                            if return_pairs:
                                pairs.extend([(t, src) for t in tracks])
                        album_uri = src
                    t_list = list(dict.fromkeys(t_list))  # deduplicate preserving order
                    if t_list:
                        if return_pairs:
                            return pairs
                        return (t_list, album_uri) if return_source else t_list
                # Cache sparse or no AlbumTrack rows yet — fall through to API

        if self._is_rate_limited():
            return [] if return_pairs else (([], None) if return_source else [])

        t_list=[]
        pairs=[]
        total=0
        try:
            total = self.sp.current_user_saved_albums()['total']
        except spotipy.SpotifyException as val_e:
            if val_e.http_status == 429:
                self._on_rate_limit(val_e)
            print(f"Erreur albums : {val_e}")
        except Exception as val_e:
            print(f"Erreur albums : {val_e}")

        if int(total) < limit: limit = int(total)

        if total>0:
            #Extract one album n=limit times
            for i in range(limit):
                try:
                    album_response = self.sp.current_user_saved_albums(limit=1,offset=random.randint(0,total-1))
                except Exception as val_e:
                    print(f"Erreur albums2 : {val_e}")
                    continue
                album_data = album_response['items'][0]['album']
                album_uri = album_data['uri']
                self._cache_album(album_data)
                if self._db:
                    self._db.mark_album_saved(album_data['id'])
                try:
                    tracks = self.sp.album_tracks(album_data['id'])
                except Exception as val_e:
                    print(f"Erreur albums3 : {val_e}")
                    continue
                # bulk cache all tracks from this album
                for pos, item in enumerate(tracks.get('items') or []):
                    if item and item.get('uri'):
                        item.setdefault('album', album_data)
                        self._cache_track(item)
                        if self._db:
                            self._db.save_album_track(album_data['id'], item['uri'], pos)
                #Extract n=unit tracks for playback
                if unit != 0:
                    for j in range(unit):
                        track = random.choice(tracks['items'])
                        t_list.append(track['uri'])
                        if return_pairs:
                            pairs.append((track['uri'], album_uri))
                else:
                    for j in range(len(tracks['items'])):
                        t_list.append(tracks['items'][j]['uri'])
                        if return_pairs:
                            pairs.append((tracks['items'][j]['uri'], album_uri))
        t_list = list(dict.fromkeys(t_list))  # deduplicate preserving order
        if return_pairs:
            return pairs
        return (t_list, album_uri) if return_source else t_list


    def get_track_album(self, track_id):
        # Cache-first: avoid API call if album_id already stored
        if self._db:
            album_id = self._db.get_cached_album_id(track_id)
            if album_id:
                print(f"[TIMING] get_track_album: cache hit for {track_id}")
                return f"spotify:album:{album_id}"
        if self._is_rate_limited():
            return None
        try:
            t0 = time.time()
            album = self.sp.track(track_id)['album']
            print(f"[TIMING] get_track_album: sp.track() took {time.time()-t0:.2f}s for {track_id}")
            album_uri = album['uri']
            self._cache_album(album)
            return album_uri
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            print(f"get_track_album error: {e}")
            return None
        except Exception as e:
            print(f"get_track_album error: {e}")
            return None


################### ARTIST #############################

    def get_artist_top_tracks(self, artist_id):
        # artist top-tracks endpoint restricted by Spotify since Nov 2024 (requires Extended quota)
        try:
            trid = self.sp._get_id("artist", artist_id)
            tracks = self.sp._get(f"artists/{trid}/top-tracks", market="FR")
            return self.parse_tracks(tracks)
        except Exception as val_e:
            print(f"Erreur artist top tracks (endpoint may be restricted): {val_e}")
            return []

    def get_track_artist(self, track_id):
        # Cache-first: avoid API call if artist already linked in TrackArtist
        if self._db:
            artist_id = self._db.get_cached_artist_id(track_id)
            if artist_id:
                print(f"[TIMING] get_track_artist: cache hit for {track_id}")
                return artist_id
        if self._is_rate_limited():
            return None
        try:
            t0 = time.time()
            artists = self.sp.track(track_id)['artists']
            print(f"[TIMING] get_track_artist: sp.track() took {time.time()-t0:.2f}s for {track_id}")
            random.shuffle(artists)
            artist_id = artists[0]['id']
            return artist_id
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            print(f"get_track_artist error: {e}")
            return None
        except Exception as e:
            print(f"get_track_artist error: {e}")
            return None

    def get_artist_all_tracks(self, artist_id, limit=10):
        if not artist_id:
            return []
        # Cache-first: get album IDs from AlbumArtist, then tracks from AlbumTrack
        if self._db:
            from src.o2mmodels import AlbumArtist
            album_ids = [
                r.album_id for r in
                AlbumArtist.select(AlbumArtist.album_id).where(AlbumArtist.artist_id == artist_id)
            ]
            if album_ids:
                cached_uris = []
                for aid in album_ids:
                    tracks = self._db.get_album_tracks(aid)
                    if tracks:
                        cached_uris.extend(tracks)
                if cached_uris:
                    print(f"[TIMING] get_artist_all_tracks: cache hit ({len(cached_uris)} tracks across {len(album_ids)} albums) for {artist_id}")
                    random.shuffle(cached_uris)
                    return cached_uris[:limit]

        if self._is_rate_limited():
            return []
        # spotipy 2.25.2 always sends country=None; Spotify API now requires market=
        try:
            t0 = time.time()
            trid = self.sp._get_id("artist", artist_id)
            albums = self.sp._get(f"artists/{trid}/albums", include_groups="album,single", market="FR")
            print(f"[TIMING] get_artist_all_tracks: artists/albums took {time.time()-t0:.2f}s for {artist_id} ({len(albums.get('items',[]))} albums)")
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            print(f"get_artist_all_tracks error: {e}")
            return []
        except Exception as e:
            print(f"get_artist_all_tracks error: {e}")
            return []
        tracks_uris = []

        for album in albums["items"]:
            if self._is_rate_limited():
                break
            self._cache_album(album)
            album_id = album.get('id')
            # Check AlbumTrack cache before calling API for each album
            if album_id and self._db:
                cached = self._db.get_album_tracks(album_id)
                if cached:
                    tracks_uris.extend(cached)
                    continue
            try:
                t1 = time.time()
                tracks_json = self.sp.album_tracks(album["uri"])
                print(f"[TIMING] get_artist_all_tracks: album_tracks took {time.time()-t1:.2f}s for {album.get('name','?')}")
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    self._on_rate_limit(e)
                print(f"get_artist_all_tracks album_tracks error: {e}")
                break
            except Exception as e:
                print(f"get_artist_all_tracks album_tracks error: {e}")
                continue
            # cache simplified track objects (album reference added manually)
            for pos, item in enumerate(tracks_json.get("items") or []):
                if item and item.get('uri'):
                    item.setdefault('album', album)
                    self._cache_track(item)
                    tracks_uris.append(item["uri"])
                    if album_id and self._db:
                        self._db.save_album_track(album_id, item["uri"], pos)

        random.shuffle(tracks_uris)
        return tracks_uris[:limit]
    
    def get_all_followed_artists(self):
        if self._is_rate_limited():
            if self._db:
                cached = self._db.get_followed_artist_ids()
                if cached:
                    print(f"get_all_followed_artists: rate-limited, using {len(cached)} cached followed artists")
                    return cached
                print("get_all_followed_artists: rate-limited, followed cache empty")
            return []
        all_followed = []
        response = self.sp.current_user_followed_artists(limit=50)
        while response:
            # sp.next() may return the outer {'artists': {...}} or the raw paging object
            page = response.get('artists', response)
            items = page.get('items', [])
            if not items:
                break
            for artist in items:
                all_followed.append(artist['id'])
                # Full artist object includes genres — cache + mark followed
                self._cache_artist(artist)
                if self._db:
                    self._db.mark_artist_followed(artist['id'])
            if page.get('next'):
                response = self.sp.next(page)
            else:
                break
        print(f"get_all_followed_artists: cached {len(all_followed)} followed artists")
        return all_followed
    
    def get_my_artists_tracks(self, limit=1, unit=1, return_source=False, return_pairs=False):
        t_list=[]
        artist_uri=None
        pairs=[]
        total=0
        try:
            # get_all_followed_artists handles rate-limit via Artist.followed=1 cache
            artists = self.get_all_followed_artists()
            if len(artists)>0:
                for i in range(limit):
                    artist = random.choice(artists)
                    artist_uri = 'spotify:artist:' + artist
                    # top-tracks endpoint restricted since Nov 2024 — use albums instead
                    tracks = self.get_artist_all_tracks(artist, limit=unit if unit > 0 else 10)
                    if tracks and unit != 0:
                        for j in range(unit):
                            track = random.choice(tracks)
                            t_list.append(track)
                            if return_pairs:
                                pairs.append((track, artist_uri))
                    else:
                        t_list.append('spotify:artist:'+artist)
                        if return_pairs:
                            pairs.append(('spotify:artist:'+artist, artist_uri))
            '''total = self.sp.current_user_followed_artists()['artists']['total']
            if int(total) < limit: limit = int(total)
            if total>0:
                for i in range(limit):
                    artist = self.sp.current_user_followed_artists(limit=1,after=random.randint(0,total-1))['artists']['items'][0]['id']
                    if artist: 
                        tracks = self.get_artist_top_tracks(artist)
                        print (tracks)
                        if tracks and unit != 0:
                            for j in range(unit):
                                track = random.choice(tracks)
                                t_list.append(track)
                        else:
                            t_list.append('spotify:artist:'+artist)
                            #for j in range(len(tracks['items'])):
                            #    t_list.append(tracks['items'][j]['uri'])'''
            
        except Exception as val_e:
            print(f"Erreur artist : {val_e}")

        if return_pairs:
            return pairs
        return (t_list, artist_uri) if return_source else t_list

################### FAVORITES AND MISC #############################

    def get_library_favorite_tracks(self, limit=20, offset=0, market=None):
        # Cache-first only when cache is rich enough (or rate-limited)
        if self._db:
            cached = self._db.get_liked_track_uris()
            if cached:
                if self._is_rate_limited() or self._db.is_cache_rich('liked'):
                    if self._is_rate_limited():
                        print(f"get_library_favorite_tracks: rate-limited, using {len(cached)} cached liked tracks")
                    random.shuffle(cached)
                    return cached[:limit]
                # Cache exists but is sparse → fall through to API

        if self._is_rate_limited():
            return []
        #Warning : may probably be the last 20 only
        t_list=[]
        total=0
        try:
            total = self.sp.current_user_saved_tracks()['total']
        except spotipy.SpotifyException as val_e:
            if val_e.http_status == 429:
                self._on_rate_limit(val_e)
            return []
        except Exception:
            return []
        print (total)
        if (total>0):
            for i in range(limit):
                #print (tracks[i]['track']['uri'])
                rand = random.randint(0,total)
                tracks = self.sp.current_user_saved_tracks(limit=1,offset=rand)
                t_list.append(tracks['items'][0]['track']['uri'])
        return t_list

    def get_library_recent_tracks(self, limit):
        if self._is_rate_limited():
            return []
        #Warning : may probably be the last 20 only
        t_list=[]
        try:
            tracks = self.sp.current_user_recently_played()
        except spotipy.SpotifyException as val_e:
            if val_e.http_status == 429:
                self._on_rate_limit(val_e)
            print(f"Erreur : {val_e}")
            return []
        except Exception as val_e:
            print(f"Erreur : {val_e}")
            return []
        if tracks:
            tracks=tracks['items']
            random.shuffle(tracks)
            for i in range(limit):
                #print (tracks[i]['track']['uri'])
                t_list.append(tracks[i]['track']['uri'])

        return t_list

    def cache_all_liked_tracks(self):
        """Bulk cache : fetch ALL liked/saved tracks (paginated).
        Liked tracks come with full metadata → album + artists cached too.
        Skips silently if rate-limited.  Returns total tracks cached."""
        if self._is_rate_limited():
            print("cache_all_liked_tracks: rate-limited, skipping")
            return 0
        cached = 0
        try:
            response = self.sp.current_user_saved_tracks(limit=50)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                self._on_rate_limit(e)
            return 0
        except Exception as e:
            print(f"cache_all_liked_tracks error: {e}")
            return 0

        while response and response.get('items'):
            for item in response['items']:
                if self._is_rate_limited():
                    return cached
                track = (item.get('track') or item.get('item')) if item else None
                if track and track.get('uri'):
                    self._cache_track(track)
                    if self._db:
                        import datetime as _dt
                        added_at = item.get('added_at')
                        self._db.mark_track_liked(track['uri'], liked_at=added_at)
                    cached += 1
            if response.get('next'):
                try:
                    response = self.sp.next(response)
                except spotipy.SpotifyException as e:
                    if e.http_status == 429:
                        self._on_rate_limit(e)
                    break
                except Exception:
                    break
            else:
                break

        print(f"cache_all_liked_tracks: {cached} tracks cached")
        return cached

    def cache_spotify_library(self):
        """Convenience method : bulk-cache the full Spotify library.
        Runs all four sources sequentially, stops early if rate-limited."""
        print("=== cache_spotify_library start ===")
        total = 0
        for method, label in [
            (self.cache_all_liked_tracks,  "liked tracks"),
            (self.cache_all_playlists,     "playlists"),
            (lambda: self.get_my_albums_tracks(limit=500, unit=0),  "albums"),
            (lambda: self.get_my_artists_tracks(limit=200, unit=0), "artists"),
        ]:
            if self._is_rate_limited():
                print(f"Rate-limited, stopping before '{label}'")
                break
            result = method()
            n = len(result) if isinstance(result, list) else result
            print(f"  {label}: {n}")
            if isinstance(n, int):
                total += n
        print(f"=== cache_spotify_library done — {total} items processed ===")
