import configparser, os, json, sys, random, re
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
        self.init_token_sp()

    def init_token_sp(self):
        cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=self.cache_path)
        auth_manager = spotipy.oauth2.SpotifyOAuth(scope=self.scope,cache_handler=cache_handler,show_dialog=False)
        if auth_manager.validate_token(cache_handler.get_cached_token()):
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
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
        self, seed_genres=None, seed_artists=None, seed_tracks=None, limit=10, **kwargs
    ):
        # Note: Spotify restricted the recommendations endpoint in late 2024.
        # It may return 404 for most apps — handle gracefully.
        try:
            reco = self.sp.recommendations(
                seed_genres=seed_genres,
                seed_artists=seed_artists,
                seed_tracks=seed_tracks,
                market="FR",
                limit=limit,
                **kwargs
            )
            return self.parse_tracks(reco)
        except Exception as e:
            print(f"Spotify recommendations unavailable (endpoint may be restricted): {e}")
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
                            album = self.sp.album(resource_id)
                            album_name = album.get('name', '')
                            artist_name = album.get('artists', [{}])[0].get('name', '')
                            return f"{album_name} - {artist_name}".strip(' -') if album_name else uri
                        elif resource_type == 'artist':
                            artist = self.sp.artist(resource_id)
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
        results = self.sp.user_playlist_add_tracks(username, playlist_uri, track_uris)
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
        results = self.sp.playlist_items(playlist_id, additional_types=())
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
                tracks_response = self.sp.playlist_items(playlist['id'], additional_types=())
                tracks = [item['track']['uri'] for item in tracks_response['items'] if item and item.get('track') and item['track'].get('uri')]
                
                if tracks:
                    # Select one random track from the current playlist
                    track_uri = random.choice(tracks)
                    t_list.append(track_uri)
                    lib_link.append("spotify:playlist:"+playlist['id'])
            except Exception as val_e:
                print(f"Erreur lors de la récupération des pistes de la playlist {playlist['name']}: {val_e}")
                continue
        
        return (t_list,lib_link)

################### ALBUMS  #############################

    def get_album_all_tracks(self, album_uri, limit=10):
        tracks_uris = []
        tracks_json = self.sp.album_tracks(album_uri)
        tracks_uris = self.parse_tracks(tracks_json)
        random.shuffle(tracks_uris)
        return tracks_uris[:limit]

    def get_my_albums_tracks(self,limit=1,unit=1):
        t_list=[]
        total=0
        try: 
            total = self.sp.current_user_saved_albums()['total']
        except Exception as val_e: 
            print(f"Erreur albums : {val_e}")

        if int(total) < limit: limit = int(total)
        #print (limit)
        #print (int(total))

        if total>0:
            #Extract one album n=limit times
            for i in range(limit):
                try: 
                    album = self.sp.current_user_saved_albums(limit=1,offset=random.randint(0,total-1))
                except Exception as val_e: 
                    print(f"Erreur albums2 : {val_e}")
                #album = random.choice(albums['items'])
                try: 
                    tracks = self.sp.album_tracks(album['items'][0]['album']['id'])
                except Exception as val_e: 
                    print(f"Erreur albums3 : {val_e}")
                #Extract n=unit tracks from the album
                if unit != 0:
                    for j in range(unit):
                        track = random.choice(tracks['items'])
                        t_list.append(track['uri'])
                else:
                    #t_list.append('spotify:album:'+album['items'][i]['album']['id'])
                    for j in range(len(tracks['items'])):
                        t_list.append(tracks['items'][j]['uri'])
        return t_list


    def get_track_album(self, track_id):
        album=self.sp.track(track_id)['album']
        #print (album)
        album_uri = album['uri']
        return album_uri


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
        artists=self.sp.track(track_id)['artists']
        #print (artists)
        random.shuffle(artists)
        artist_id = artists[0]['id']
        return artist_id

    def get_artist_all_tracks(self, artist_id, limit=10):
        # spotipy 2.25.2 always sends country=None; Spotify API now requires market=
        trid = self.sp._get_id("artist", artist_id)
        albums = self.sp._get(f"artists/{trid}/albums", include_groups="album,single", market="FR")
        tracks_uris = []

        for album in albums["items"]:
            tracks_json = self.sp.album_tracks(album["uri"])
            tracks_uris += self.parse_tracks(tracks_json)

        random.shuffle(tracks_uris)
        return tracks_uris[:limit]
    
    def get_all_followed_artists(self):
        all_followed = []
        for offset in range(0, 1000, 50):
            response = self.sp.current_user_followed_artists(limit=50,after=offset)
            for artist in response['artists']['items']:
                name = artist['name']
                id = artist['id']
                #all_followed.update({name: id})
                all_followed.append(id)
        return all_followed
    
    def get_my_artists_tracks(self,limit=1,unit=1):
        t_list=[]
        total=0
        try:
            artists = self.get_all_followed_artists()
            if len(artists)>0:
                for i in range(limit):
                    artist = random.choice(artists)
                    tracks = self.get_artist_top_tracks(artist)
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
        #Warning : may probably be the last 20 only
        t_list=[]
        total=0
        total = self.sp.current_user_saved_tracks()['total']
        print (total)
        if (total>0):
            for i in range(limit):
                #print (tracks[i]['track']['uri'])
                rand = random.randint(0,total)
                tracks = self.sp.current_user_saved_tracks(limit=1,offset=rand)
                t_list.append(tracks['items'][0]['track']['uri'])
        return t_list

    def get_library_recent_tracks(self, limit):
        #Warning : may probably be the last 20 only
        t_list=[]
        try: 
            tracks = self.sp.current_user_recently_played()
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            tracks = self.sp.current_user_recently_played()
        if tracks:
            tracks=tracks['items']
            random.shuffle(tracks)
            for i in range(limit):
                #print (tracks[i]['track']['uri'])
                t_list.append(tracks[i]['track']['uri'])

        return t_list
