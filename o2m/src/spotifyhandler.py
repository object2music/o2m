import configparser, os, json, sys, random, re, time
from pathlib import Path
import spotipy as spotipy
import src.util as util

class SpotifyHandler:
    def __init__(self):
        self.spotipy_config = util.get_config_file("o2m.conf")["spotipy"]
        self.cache_path = ".cache_spotipy"
        self.scope = "user-library-read playlist-modify-private playlist-modify-public user-read-recently-played user-top-read user-follow-modify user-follow-read playlist-read-private playlist-read-collaborative user-library-modify"
        os.environ['SPOTIPY_REDIRECT_URI'] = self.spotipy_config["spotipy_redirect_uri"]
        os.environ['SPOTIPY_CLIENT_ID'] = self.spotipy_config["client_id_spotipy"]
        os.environ['SPOTIPY_CLIENT_SECRET'] = self.spotipy_config["client_secret_spotipy"]
        self._rate_limit_file = ".spotify_rate_limit"
        self._rate_limited_until = self._load_rate_limit()
        self._last_retry_after = None  # captured from Retry-After response header
        self._db = None  # set via set_db_handler() after DatabaseHandler is ready
        self.init_token_sp()

    def set_db_handler(self, db_handler):
        """Inject the DatabaseHandler to enable local cache read/write."""
        self._db = db_handler

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

    def init_token_sp(self):
        import requests
        cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=self.cache_path)
        auth_manager = spotipy.oauth2.SpotifyOAuth(scope=self.scope,cache_handler=cache_handler,show_dialog=False)
        if auth_manager.validate_token(cache_handler.get_cached_token()):
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
        else:
            print("Token is not valid")

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
        """
        Replacement for Spotify's removed /recommendations endpoint.
        Phase 1 — style: scores user's followed artists by genre overlap with seeds.
        Phase 2 — rhythm: refines track selection via audio features (tempo/energy/danceability)
                          if the endpoint is still accessible.
        """
        try:
            target_genres = set(seed_genres or [])
            seed_artist_ids = set()

            # True when the artist cache is rich enough to avoid individual sp.artist() calls
            use_cache_only = bool(self._db and self._db.is_cache_rich('artists'))

            # Resolve seed tracks → artist ids (DB-first via TrackArtist, API fallback)
            if seed_tracks:
                from src.o2mmodels import TrackArtist
                track_ids = seed_tracks if isinstance(seed_tracks, list) else [seed_tracks]
                track_ids = [self.normalize_spotify_id(t) for t in track_ids if t][:3]
                for track_id in track_ids:
                    if self._is_rate_limited():
                        break
                    # DB-first: resolve via TrackArtist table
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
                        continue  # cache rich but track not in TrackArtist — skip API
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

            # Fetch genres for seed artists — cache-first, API only when cache is sparse
            for artist_id in list(seed_artist_ids)[:50]:
                if self._is_rate_limited():
                    break
                cached = self._db.get_artist(artist_id) if self._db else None
                if cached:
                    target_genres.update(self._db.get_artist_genres(artist_id))
                    continue
                if use_cache_only:
                    continue  # skip API when cache is rich enough
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

            # Score user's followed artists by genre overlap (batched, max 200)
            followed = self.get_all_followed_artists()
            followed_set = set(followed)
            candidates = [i for i in followed if i not in seed_artist_ids]
            random.shuffle(candidates)

            # Augment with external artists proportional to discover_level
            # sp.search is intentionally NOT gated by use_cache_only: it provides novelty at high DL
            n_external = discover_level * 10
            if n_external > 0 and target_genres and not self._is_rate_limited():
                external_ids = []
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

            scored = []
            for artist_id in candidates[:10]:
                if self._is_rate_limited():
                    break
                # cache-first for scoring — API only when cache is sparse
                cached = self._db.get_artist(artist_id) if self._db else None
                if cached:
                    genres = set(self._db.get_artist_genres(artist_id))
                    overlap = len(genres & target_genres)
                    if overlap > 0:
                        scored.append((overlap, artist_id))
                    continue
                if use_cache_only:
                    continue  # skip API when cache is rich enough
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
            if not artist_pool:
                return []

            # Collect tracks from matching artists
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
        """Get human-readable name from Spotify URI (playlist, album, artist)"""
        if self._is_rate_limited():
            return uri  # return raw URI rather than blocking
        try:
            if not uri or uri == '':
                return ''

            uri = self.normalize_spotify_uri(uri)
            
            # Handle o2m: custom URIs
            if uri.startswith('o2m:'):
                return uri.replace('o2m:', '').replace('_', ' ').title()
            
            # Handle Spotify URIs
            if uri.startswith('spotify:'):
                parts = uri.split(':')
                if len(parts) >= 3:
                    resource_type = parts[1]
                    resource_id = self.normalize_spotify_id(parts[2])

                    # Defensive: only call Spotify APIs with a real base62 id.
                    # Spotify IDs are 22 chars; values like "Calm" must be treated as display names.
                    if not re.fullmatch(r"[A-Za-z0-9]{22}", str(resource_id or "")):
                        return uri
                    
                    try:
                        if resource_type == 'playlist':
                            playlist = self.sp.playlist(resource_id, fields='name')
                            name = playlist.get('name', uri)
                            return name if name else uri
                        elif resource_type == 'album':
                            # cache-first
                            cached = self._db.get_album(resource_id) if self._db else None
                            if cached:
                                return f"{cached.name}".strip() or uri
                            album = self.sp.album(resource_id)
                            self._cache_album(album)
                            album_name = album.get('name', '')
                            artist_name = album.get('artists', [{}])[0].get('name', '')
                            return f"{album_name} - {artist_name}".strip(' -') if album_name else uri
                        elif resource_type == 'artist':
                            # cache-first
                            cached = self._db.get_artist(resource_id) if self._db else None
                            if cached:
                                return cached.name or uri
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
            import traceback
            traceback.print_exc()
            return uri

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
    _WARMUP_TTL = {'liked': 7, 'artists': 7, 'albums': 7, 'playlist_tracks': 3}

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
                    # cache tracks if not already fresh
                    if self._db and not self._db.is_album_track_cache_fresh(album['id']):
                        for pos, track in enumerate(album.get('tracks', {}).get('items') or []):
                            if track and track.get('uri'):
                                track.setdefault('album', album)
                                self._cache_track(track)
                                self._db.save_album_track(album['id'], track['uri'], pos)
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

    def get_my_albums_tracks(self,limit=1,unit=1):
        # Cache-first: use saved albums from DB if available (avoids API call for total)
        if self._db:
            saved_ids = self._db.get_saved_album_ids()
            if saved_ids:
                if self._is_rate_limited() or self._db.is_cache_rich('albums'):
                    if self._is_rate_limited():
                        print(f"get_my_albums_tracks: rate-limited, using {len(saved_ids)} cached saved albums")
                    t_list = []
                    selected = random.sample(saved_ids, min(limit, len(saved_ids)))
                    for album_id in selected:
                        tracks = self._db.get_album_tracks(album_id)
                        if tracks and unit != 0:
                            for _ in range(unit):
                                t_list.append(random.choice(tracks))
                        elif tracks:
                            t_list.extend(tracks)
                    if t_list:
                        return t_list
                # Cache sparse or no AlbumTrack rows yet — fall through to API

        if self._is_rate_limited():
            return []

        t_list=[]
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
                else:
                    for j in range(len(tracks['items'])):
                        t_list.append(tracks['items'][j]['uri'])
        return t_list


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
        while response and response['artists']['items']:
            for artist in response['artists']['items']:
                all_followed.append(artist['id'])
                # Full artist object includes genres — cache + mark followed
                self._cache_artist(artist)
                if self._db:
                    self._db.mark_artist_followed(artist['id'])
            if response['artists']['next']:
                response = self.sp.next(response['artists'])
            else:
                break
        return all_followed
    
    def get_my_artists_tracks(self,limit=1,unit=1):
        t_list=[]
        total=0
        try:
            # get_all_followed_artists handles rate-limit via Artist.followed=1 cache
            artists = self.get_all_followed_artists()
            if len(artists)>0:
                for i in range(limit):
                    artist = random.choice(artists)
                    # top-tracks endpoint restricted since Nov 2024 — use albums instead
                    tracks = self.get_artist_all_tracks(artist, limit=unit if unit > 0 else 10)
                    if tracks and unit != 0:
                        for j in range(unit):
                            track = random.choice(tracks)
                            t_list.append(track)
                    else:
                        t_list.append('spotify:artist:'+artist)
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
        
        return t_list

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
