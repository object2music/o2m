import logging, time, configparser
from pathlib import Path
from mopidyapi import MopidyAPI


from src.nfcreader import NfcReader
from src.dbhandler import DatabaseHandler, Tag
from src.spotifyrecommendations import SpotifyRecommendations

logging.basicConfig(format='%(levelname)s CLASS : %(name)s FUNCTION : %(funcName)s LINE : %(lineno)d TIME : %(asctime)s MESSAGE : %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG,
                    filename='./logs/o2m.log', 
                    filemode='a')

'''
    TODO :
        * Décider de la structure de la base
        * Logs : séparer les logs par ensemble de fonctionnalités (database, websockets, spotify etc...)

'''
'''
    INSTALL : 
    pip3 install mopidyapi

'''

class NfcToMopidy():
    activecards = {}
    last_tag_uid = None

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.log.info('NFC TO MOPIDY INITIALIZATION')

        self.mydb = DatabaseHandler()
        self.mopidy = MopidyAPI()
        self.recoHandler = SpotifyRecommendations()
        
        nfcreader = NfcReader(self)
        nfcreader.loop()
        
    def get_new_cards(self, addedCards, removedCards, activeCards):
        self.activecards = activeCards
        
        # Décommenter la ligne en dessous pour avoir de l'info sur les données récupérées dans le terminal
        # self.pretty_print_nfc_data(addedCards, removedCards)
        
        # Put some timestamps on cards ?
        
        # Do some stuff in sqlite database
        for card in addedCards:
            tag = self.mydb.get_tag_by_uid(card.id)
            if tag != None:
            	if tag.uid != self.last_tag_uid:
                    tag.add_count()
                    print(f'Tag : {tag}' )
                    # self.last_tag_uid = tag.uid
                    media_parts = tag.media.split(':')
                    if media_parts[1] == 'recommendation':
                        if media_parts[3] == 'genres':
                            genres = media_parts[4].split(',')
                            tracks_uris = self.recoHandler.get_recommendations(seed_genres=genres)
                            self.launch_tracks(tracks_uris)
                        elif media_parts[3] == 'artists':
                            artists = media_parts[4].split(',')
                            tracks_uris = self.recoHandler.get_recommendations(seed_artists=artists)
                            self.launch_tracks(tracks_uris)
                    else:
                        self.launch_track(tag.media)
            	else:
            		print(f'Tag : {tag.uid} & last_tag_uid : {self.last_tag_uid}' )
            		self.launch_next()
            else:
                print(card.id)
                self.mydb.create_tag(card.id, '')

        for card in removedCards:
            print('Stopping music')
            self.mopidy.playback.stop()

        # Launch some commands to mopidy

    def launch_next(self):
        self.mopidy.playback.next()
        self.mopidy.playback.play()

    def launch_track(self, uri):
        print(f'Playing one track')
        self.mopidy.tracklist.clear()
        self.mopidy.tracklist.add(uris=[uri])
        self.mopidy.playback.play()
    
    def launch_tracks(self, uris):
        print(f'Playing {len(uris)} tracks')
        self.mopidy.tracklist.clear()
        self.mopidy.tracklist.add(uris=uris)
        self.mopidy.playback.play()

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


if __name__ == "__main__":


    # mydb = DatabaseHandler()
    # mydb.create_tag('super_uid2', 'super_media')

    # tags = mydb.get_all_tags()
    # print(tags)
    nfcHandler = NfcToMopidy()