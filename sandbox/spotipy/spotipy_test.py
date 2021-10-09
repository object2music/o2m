import configparser, os, json, sys
from pathlib import Path

import spotipy as spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth

#token = spotipy.util.prompt_for_user_token(username, scope, client_id, client_secret, redirect_uri)
#logger = logging.getLogger('examples.artist_recommendations')
#logging.basicConfig(level='INFO')
#client_credentials_manager = SpotifyClientCredentials()
#sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

client_credentials_manager = SpotifyClientCredentials()
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

#sp = spotipy.Spotify(client_credentials_manager=creds)

'''
    INSTALL : 
        - pip3 install spotipy
        - Ouvrir le fichier /usr/local/lib/python3.7/site-packages/spotipy/oauth2.py
        - Remplacer la ligne 82 par : OAUTH_TOKEN_URL = "https://auth.mopidy.com/spotify/token"
    
    La modification d'url permet de réutiliser le client_id et client_secret de mopidy-spotify et évite un second process d'autorisation et de récupération de tokens

    A terme, on pourrait ne pas installer la dépendance via pip, mais directement l'intégrer à notre code source avec notre modification.
    L'étape de remplacement d'url ne serait plus nécessaire.
'''

# On récupère le fichier de config de mopidy
#config = configparser.ConfigParser()
#config.read(str(Path.home()) + '/.config/mopidy/mopidy.conf')
# On cible la section spotify
#spotify_config = config['spotify']
# On passe les valeurs à spotipy
#client_credentials_manager = SpotifyClientCredentials(client_id=spotify_config['client_id'], client_secret=spotify_config['client_secret'])
#1sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

## Exemple de requete de recommandations
reco = sp.recommendations(  seed_genres=['french', 'electro'], seed_artists=None, seed_tracks=None, country='from_token', limit=3, 
                            min_energy='0.8', 
                            max_instrumentalness='0.5',
                            target_valence='0.7')
# print('SEEDS ')
# print(reco['seeds'])
# print('TRACKS ')
# print(reco['tracks'])

print(reco)

## Exemple qui print les playlist d'un utilisateur
# playlists = sp.user_playlists('spotify')
# while playlists:
#     for i, playlist in enumerate(playlists['items']):
#         print("%4d %s %s" % (i + 1 + playlists['offset'], playlist['uri'],  playlist['name']))
#     if playlists['next']:
#         playlists = sp.next(playlists)
#     else:
#         playlists = None