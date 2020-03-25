import configparser, os, json, sys
from pathlib import Path

sys.path.append('.')
from lib.spotipy.oauth2 import SpotifyClientCredentials
import lib.spotipy as spotipy
import src.util as util

class SpotifyRecommendations():
    def __init__(self):
        spotify_config = util.get_config()['spotify']

        client_credentials_manager = SpotifyClientCredentials(client_id=spotify_config['client_id'], client_secret=spotify_config['client_secret'])
        self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    def get_recommendations(self, seed_genres=None, seed_artists=None, seed_tracks= None, limit=50, **kwargs):
        reco = self.sp.recommendations(seed_genres=seed_genres, seed_artists=seed_artists, seed_tracks=seed_tracks, country='from_token', limit=limit, **kwargs)
        return self.parse_recommendations(reco)

    def parse_recommendations(self, recos):
        uris = []
        print('INFOS RÉSULTATS RECOMMANDATION')
        print(recos['seeds'])
        for track in recos['tracks']:
            uris.append(track['uri'])
        return uris

