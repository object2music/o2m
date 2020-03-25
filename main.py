import logging, time, configparser, contextlib
from pathlib import Path
from mopidyapi import MopidyAPI
from mopidy_podcast import feeds, Extension

from src.nfcreader import NfcReader
from src.dbhandler import DatabaseHandler, Tag
from src.spotifyhandler import SpotifyHandler
from src import util

logging.basicConfig(format='%(levelname)s CLASS : %(name)s FUNCTION : %(funcName)s LINE : %(lineno)d TIME : %(asctime)s MESSAGE : %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG,
                    filename='./logs/o2m.log', 
                    filemode='a')

START_BOLD = '\033[1m'
END_BOLD = '\033[0m'

'''
    TODO :
        * Logs : séparer les logs par ensemble de fonctionnalités (database, websockets, spotify etc...)
        * Timestamps sur les tags

    INSTALL : 
    pip3 install -r requirements.txt

    CONFIG : 
    Dans le fichier de conf de mopidy : 
        [o2m]
        database_path = src/o2mv1.db
    Le script de recherche de fichier config est dans le fichier src/util.py
'''

class NfcToMopidy():
    activecards = {}
    last_tag_uid = None

    def __init__(self, mopidyHandler):
        self.log = logging.getLogger(__name__)
        self.log.info('NFC TO MOPIDY INITIALIZATION')
        
        self.dbHandler = DatabaseHandler() # Gère la base de données
        self.mopidyHandler = mopidyHandler # Commandes mopidy via websockets
        self.spotifyHandler = SpotifyHandler() # Appel à l'api spotify pour recommandations
        self.nfcHandler = NfcReader(self) # Contrôle les lecteurs nfc et renvoie les identifiants des cartes
        
    def start_nfc(self):
        self.nfcHandler.loop() # démarre la boucle infinie de détection nfc/rfid
    
    '''
    Fonction appellée automatiquement dès qu'un changement est détecté au niveau des lecteurs rfid
    '''
    def get_new_cards(self, addedCards, removedCards, activeCards):
        self.activecards = activeCards
        
        # Décommenter la ligne en dessous pour avoir de l'info sur les données récupérées dans le terminal
        # self.pretty_print_nfc_data(addedCards, removedCards)
        
        # Boucle sur les cartes ajoutées
        for card in addedCards:
            tag = self.dbHandler.get_tag_by_uid(card.id) # On récupère le tag en base de données via l'identifiant rfid
            if tag != None:
                tag.add_count() # Incrémente le compteur de contacts pour ce tag
                if tag.uid != self.last_tag_uid: # Si différent du précédent tag détecté (Fonctionnel uniquement avec un lecteur)
                    print(f'Tag : {tag}' )
                    # self.last_tag_uid = tag.uid # On stocke en variable de classe le tag pour le comparer ultérieurement
                    media_parts = tag.data.split(':') # on découpe le champs média du tag en utilisant le séparateur : 
                    if media_parts[1] == 'recommendation':
                        if media_parts[3] == 'genres': # si les seeds sont des genres
                            genres = media_parts[4].split(',') # on sépare les genres et on les ajoute un par un dans une liste
                            tracks_uris = self.spotifyHandler.get_recommendations(seed_genres=genres) # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                            self.launch_tracks(tracks_uris) # Envoie les uris au mopidy Handler pour modifier la tracklist
                        elif media_parts[3] == 'artists': # si les seeds sont des artistes
                            artists = media_parts[4].split(',') # on sépare les artistes et on les ajoute un par un dans une liste
                            tracks_uris = self.spotifyHandler.get_recommendations(seed_artists=artists) # Envoie les paramètres au recoHandler pour récupérer les uris recommandées
                            self.launch_tracks(tracks_uris) # Envoie les uris au mopidy Handler pour modifier la tracklist
                    elif media_parts[0] == 'm3u': # C'est une playlist hybride / mopidy / iris
                        playlist_uris = []
                        playlist = self.mopidyHandler.playlists.lookup(tag.data) # On retrouve le contenu avec son uri
                        for track in playlist.tracks: # Parcourt la liste de tracks
                            playlist_uris.append(track.uri) # Recupère l'uri de chaque track pour l'ajouter dans une liste
                        self.launch_tracks(playlist_uris) # Envoie les uris en lecture
                    elif media_parts[0] == 'spotify' and media_parts[1] == 'artist':
                        print('find tracks of artist : ' + tag.description)
                        # tracks_uris = self.spotifyHandler.get_artist_top_tracks(media_parts[2]) # 10 tops tracks of artist
                        tracks_uris = self.spotifyHandler.get_artist_all_tracks(media_parts[2]) # all tracks of artist with no specific order
                        self.launch_tracks(tracks_uris)
                    elif tag.tag_type == 'podcasts:channel':
                        print('channel! get unread podcasts')
                        uris = self.get_unread_podcasts(tag.data, tag.option_items_length)
                        self.launch_tracks(uris)
                    else:
                        self.launch_track(tag.data) # Ce n'est pas une reco alors on envoie directement l'uri à mopidy
                else:
                    print(f'Tag : {tag.uid} & last_tag_uid : {self.last_tag_uid}' )
                    self.launch_next() # Le tag détecté est aussi le dernier détecté donc on passe à la chanson suivante
            else:
                if card.id != '':
                    print(card.id)
                    self.dbHandler.create_tag(card.id, '') # le tag n'est pas présent en bdd donc on le rajoute
                else:
                    print('Reading card error ! : ' + card)

        for card in removedCards:
            print('card removed')
            # print('Stopping music')
            # self.mopidyHandler.playback.stop() # si une carte est retirée on coupe la musique

    def get_unread_podcasts(self, data, last_track_played):
        uris = []
        feedurl = data.split('+')[1]
        f = Extension.get_url_opener(util.get_config()).open(feedurl, timeout=10)
        with contextlib.closing(f) as source:
            feed = feeds.parse(source)
        shows = list(feed.items())
        unread_shows = shows[last_track_played:] # Supprime le n premiers éléments (déjà lus)
        for item in unread_shows:
            uris.append(item.uri)
        return uris

    # Lance la chanson suivante sur mopidy
    def launch_next(self):
        self.mopidyHandler.playback.next()
        self.mopidyHandler.playback.play()

    # Vide la tracklist, ajoute une uri puis lance la lecture
    def launch_track(self, uri):
        print(f'Playing one track : ' + uri)
        self.mopidyHandler.tracklist.clear()
        self.mopidyHandler.tracklist.add(uris=[uri])
        self.mopidyHandler.playback.play()

    # Vide la tracklist, ajoute plusieurs uris puis lance la lecture
    def launch_tracks(self, uris):
        print(f'Playing {len(uris)} tracks')
        self.mopidyHandler.tracklist.clear()
        self.mopidyHandler.tracklist.add(uris=uris)
        self.mopidyHandler.playback.play()
    
    # Appelle ou rappelle la fonction de recommandation pour allonger la tracklist et poursuivre la lecture de manière transparente
    def update_tracks(self):
        print('should update tracks')

    # Pour le debug, print en console dans le détail les tags détectés et retirés
    # TODO : Déplacer dans la partie NFCreader, plus très utile ici ?
    def pretty_print_nfc_data(self, addedCards, removedCards):
        print('-------')
        print('NFC TAGS CHANGED!')
        print('COUNT : \n     ADDED : {}  \n     REMOVED : {} '.format(len(addedCards), len(removedCards)))
        print('ACTIONS : ')
        print('     ADDED : {} \n     REMOVED : {}'.format( 
            [x.reader + ' : ' + x.id for x in addedCards], 
            [x.reader + ' : ' + x.id for x in removedCards]))
        
        print('CURRENT CARDS ACTIVED : ')
        for key, card in self.activecards.items():
            print('     Reader : {} with card : {} '.format(key, card.id))
        print('-------')

'''
    Pas très clean de mettre les fonction de callback aux évènements dans le main 
    Mais on a besoin de l'instance de mopidyApi et la fonction callback à besoin de l'instance nfcHandler pour lancer les recos...

    Piste : Ajouter encore une classe mère pour remplacer le main?
'''
if __name__ == "__main__":

    mopidy = MopidyAPI()
    nfcHandler = NfcToMopidy(mopidy)

    # Fonction appellée à chaque changement de chanson
    @mopidy.on_event('track_playback_ended')
    def print_ended_events(event):
        track = event.tl_track.track
        print(f"Ended song : {START_BOLD}{track.name}{END_BOLD} at : {START_BOLD}{event.time_position}{END_BOLD} ms")
        
        if 'podcast' in track.uri:
            if event.time_position / track.length > 0.5: # Si la lecture de l'épisode est au delà de la moitié
                tag = nfcHandler.dbHandler.get_tag_by_data(track.album.uri) # Récupère le tag correspondant à la chaine
                if tag != None:
                    if tag.tag_type == 'podcasts:channel':
                        tag.option_items_length = track.track_no # actualise le numéro du dernier podcast écouté
                        tag.update()
                        tag.save()

        tracklist_length = mopidy.tracklist.get_length()
        index = mopidy.tracklist.index() + 1
        tracks_left_count = tracklist_length - index # Nombre de chansons restante dans la tracklist
        print(tracks_left_count)
        if tracks_left_count < 10: 
            nfcHandler.update_tracks() # si besoin on ajoute des chansons à la tracklist avec de la reco 

    # Démarre la boucle infinie pour détecter les tags
    nfcHandler.start_nfc()