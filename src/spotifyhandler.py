import configparser, os, json, sys
from pathlib import Path


sys.path.append('.')
from lib.spotipy.oauth2 import SpotifyClientCredentials
import lib.spotipy as spotipy
import src.util as util

class SpotifyHandler():
    def __init__(self):
        spotify_config = util.get_config()['spotify']

        client_credentials_manager = SpotifyClientCredentials(client_id=spotify_config['client_id'], client_secret=spotify_config['client_secret'])
        self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    def get_recommendations(self, seed_genres=None, seed_artists=None, seed_tracks= None, limit=50, **kwargs):
        reco = self.sp.recommendations(seed_genres=seed_genres, seed_artists=seed_artists, seed_tracks=seed_tracks, country='from_token', limit=limit, **kwargs)
        print('INFOS RÉSULTATS RECOMMANDATION')
        print(reco['seeds'])
        return self.parse_tracks(reco)

    def parse_tracks(self, tracks_json):
        uris = []
        
        if 'tracks' in tracks_json:
            for track in tracks_json['tracks']:
                uris.append(track['uri'])
        elif 'items' in tracks_json:
            for item in tracks_json['items']:
                uris.append(item['uri'])
        return uris

    def get_artist_top_tracks(self, artist_id):
        tracks = self.sp.artist_top_tracks(artist_id, country='FR')
        return self.parse_tracks(tracks)
    
    def get_artist_all_tracks(self, artist_id):
        albums = self.sp.artist_albums(artist_id, country='FR')
        tracks_uris = []
        for album in albums['items']:
            tracks_json = self.sp.album_tracks(album['uri'])
            tracks_uris += self.parse_tracks(tracks_json)
            
        return tracks_uris

if __name__ == "__main__":
    reco = SpotifyHandler()

    reco.get_recommendations(seed_artists=['1gR0gsQYfi6joyO1dlp76N','63MQldklfxkjYDoUE4Tpp'])
    print(reco)
    