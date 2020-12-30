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
        spotipy_config = util.get_config_file("mopidy.conf")["spotipy"]
        spotify_config = util.get_config_file("mopidy.conf")["spotify"] 

        #Method 1 : Authorization Code (all authorizations but need explicit credential via terminal)
        if spotipy_config["auth_method"] == 'authorization_code':
            token = util.prompt_for_user_token(
            username=spotify_config["username"],
            scope='user-library-read user-follow-modify playlist-modify-private playlist-modify-public',
            client_id=spotipy_config["client_id_spotipy"],
            client_secret=spotipy_config["client_secret_spotipy"],
            redirect_uri='http://localhost')

            if token:
                self.sp = spotipy.Spotify(auth=token)
                print ("Spotipy initialisation 1")
            else:
                spotipy_config["auth_method"] = ''

        #Method 2 : Client Credential (simple but not permit to modify users playlists)
        if spotipy_config["auth_method"] != 'authorization_code':
            client_credentials_manager = SpotifyClientCredentials(
                client_id=spotipy_config["client_id_spotipy"],
                client_secret=spotipy_config["client_secret_spotipy"]
            )
            self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
            print ("Spotipy initialisation 2")

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
        # print('INFOS RÉSULTATS RECOMMANDATION')
        # print(reco['seeds'])

        """reco = self.sp.recommendations(  seed_genres=['french', 'electro'], seed_artists=None, seed_tracks=None, country='from_token', limit=3, 
                            min_energy='0.8', 
                            max_instrumentalness='0.5',
                            target_valence='0.7')"""
        # print(reco)
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
        tracks = self.sp.artist_top_tracks(artist_id, country="FR")
        return self.parse_tracks(tracks)

    def get_track_artist(self, track_id):
        #print (track_id)
        artists=self.sp.track(track_id)['artists']
        #print (artists)
        random.shuffle(artists)
        artist_id = artists[0]['id']
        return artist_id

    def get_artist_all_tracks(self, artist_id, limit=10):
        albums = self.sp.artist_albums(artist_id, country="FR")
        tracks_uris = []

        for album in albums["items"]:
            tracks_json = self.sp.album_tracks(album["uri"])
            tracks_uris += self.parse_tracks(tracks_json)

        random.shuffle(tracks_uris)
        return tracks_uris[:limit]

    def add_tracks_playlist(self, username, playlist_id, track_ids):
        #sp = spotipy.Spotify(auth=token)
        #self.sp.trace = False
        results = self.sp.user_playlist_add_tracks(username, playlist_id, track_ids)
        return results

    def get_playlist_id_by_name(self,username, playlist_name):
        playlist_id = ''
        playlists = sp.user_playlists(username)
        for playlist in playlists['items']:  
            if playlist['name'] == playlist_name:
                playlist_id = playlist['id']
        return playlist_id

    def get_playlist_id_by_option_type(self,username, option_type):
        playlist_id = ''
        playlists = sp.user_playlists(username)
        for playlist in playlists['items']:  
            if playlist['name'] == playlist_name:
                playlist_id = playlist['id']
        return playlist_id

if __name__ == "__main__":
    reco = SpotifyHandler()

    reco.get_recommendations(
        seed_artists=["1gR0gsQYfi6joyO1dlp76N", "63MQldklfxkjYDoUE4Tpp"]
    )
    print(reco)
