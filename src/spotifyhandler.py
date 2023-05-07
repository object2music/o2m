import configparser, os, json, sys, random
from pathlib import Path


# sys.path.append('.')
# from lib.spotipy.oauth2 import SpotifyClientCredentials
# import lib.spotipy as spotipy
import spotipy as spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth
import src.util as util


class SpotifyHandler:
    def __init__(self):
        self.spotipy_config = util.get_config_file("mopidy.conf")["spotipy"]
        self.spotify_config = util.get_config_file("mopidy.conf")["spotify"] 
        self.init_token_sp()


    def init_token_sp(self):
        #Some scopes are not working
        #scope = "user-library-read playlist-modify-private playlist-modify-public user-read-recently-played user-top-read"
        scope='user-library-read, user-follow-modify, playlist-modify-private, playlist-modify-public'

        #Method 1 : Authorization Code (all authorizations but need explicit credential via terminal)
        if self.spotipy_config["auth_method"] == 'authorization_code':
            token = util.prompt_for_user_token(
            username=self.spotify_config["username"],
            scope=scope,
            client_id=self.spotipy_config["client_id_spotipy"],
            client_secret=self.spotipy_config["client_secret_spotipy"],
            redirect_uri='https://localhost')

            '''self.spo = oauth.SpotifyOAuth(
            username=spotify_config["username"],
            scope='user-library-read user-follow-modify playlist-modify-private playlist-modify-public',
            client_id=spotipy_config["client_id_spotipy"],
            client_secret=spotipy_config["client_secret_spotipy"],
            redirect_uri='http://localhost')'''

            if token:
                self.sp = spotipy.Spotify(auth=token)
                print ("Spotipy initialisation 1")
            else:
                self.spotipy_config["auth_method"] = ''

        #Method 2 : Client Credential (simple but not allow to modify users playlists)
        if self.spotipy_config["auth_method"] != 'authorization_code':
            client_credentials_manager = SpotifyClientCredentials(
                client_id=spotipy_config["client_id_spotipy"],
                client_secret=spotipy_config["client_secret_spotipy"]
            )
            self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
            print ("Spotipy initialisation 2")

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
            _re_auth = re.findall(_auth_finder, auth_url)
            access_token = self.spo.get_access_token(_re_auth[0])
            return access_token

    '''
    except spotipy.client.SpotifyException:
    SpotifyHandler.init_token_sp()
    print("Got an exception ")
    '''

    def get_recommendations(
        self, seed_genres=None, seed_artists=None, seed_tracks=None, limit=10, **kwargs
    ):
        # print ('tr : '+seed_tracks)
        reco = self.sp.recommendations(
            seed_genres=seed_genres,
            seed_artists=seed_artists,
            seed_tracks=seed_tracks,
            country="FR",
            limit=limit,
            **kwargs
        )
        return self.parse_tracks(reco)

    def parse_tracks(self, tracks_json):
        uris = []

        if "tracks" in tracks_json:
            for track in tracks_json["tracks"]:
                uris.append(track["uri"])
        elif "items" in tracks_json:
            for item in tracks_json["items"]:
                uris.append(item["uri"])
        return uris

    def get_artist_top_tracks(self, artist_id):
        try: 
            tracks = self.sp.artist_top_tracks(artist_id, country="FR")
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            self.init_token_sp()
            tracks = self.sp.artist_top_tracks(artist_id, country="FR")
        return self.parse_tracks(tracks)

    def get_track_artist(self, track_id):
        artists=self.sp.track(track_id)['artists']
        #print (artists)
        random.shuffle(artists)
        artist_id = artists[0]['id']
        return artist_id

    def get_track_album(self, track_id):
        album=self.sp.track(track_id)['album']
        #print (album)
        album_uri = album['uri']
        return album_uri

    def get_artist_all_tracks(self, artist_id, limit=10):
        albums = self.sp.artist_albums(artist_id, country="FR")
        tracks_uris = []

        for album in albums["items"]:
            tracks_json = self.sp.album_tracks(album["uri"])
            tracks_uris += self.parse_tracks(tracks_json)

        random.shuffle(tracks_uris)
        return tracks_uris[:limit]

    def get_album_all_tracks(self, album_uri, limit=10):
        tracks_uris = []
        tracks_json = self.sp.album_tracks(album_uri)
        tracks_uris = self.parse_tracks(tracks_json)
        random.shuffle(tracks_uris)
        return tracks_uris[:limit]

    def add_tracks_playlist(self, username, playlist_uri, track_uris):
        results = self.sp.user_playlist_add_tracks(username, playlist_uri, track_uris)
        print(f"Adding track succesful from playlist {results}")
        return results

    def remove_tracks_playlist(self, playlist_uri, track_uris):
        results = self.sp.playlist_remove_all_occurrences_of_items(playlist_uri, track_uris, snapshot_id=None)
        print(f"Removing track succesful from playlist  {results}")
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

    def is_track_in_playlist(self,username,track_id,playlist_id):
        results =  self.sp.user_playlist_tracks(username,playlist_id)
        tracks = results['items']
        while results['next']:
            results = self.sp.next(results)
            tracks.extend(results['items'])
        #print(tracks)
        for track in tracks:
            if track["track"]["id"]==track_id: return True
        return False

    def get_library_tracks(self,limit=1):
        t_list=[]
        try: 
            albums = self.sp.current_user_saved_albums()
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            self.init_token_sp()
            albums = self.sp.current_user_saved_albums() 

        if albums:
            for i in range(limit):
                album = random.choice(albums['items'])
                tracks = self.sp.album_tracks(album['album']['id'])     
                track = random.choice(tracks['items'])
                t_list.append(track['uri'])

        return t_list

    def get_library_favorite_tracks(self, limit=20, offset=0, market=None):
        #Warning : may probably be the last 20 only
        t_list=[]
        try: 
            tracks = self.sp.current_user_saved_tracks()
        except Exception as val_e: 
            print(f"Erreur : {val_e}")
            tracks = self.sp.current_user_saved_tracks()        
        if tracks:
            tracks=tracks['items']
            random.shuffle(tracks)
            for i in range(limit):
                print (tracks[i]['track']['uri'])
                t_list.append(tracks[i]['track']['uri'])

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

        