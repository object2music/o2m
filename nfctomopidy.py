from nfcreader import NfcReader
from dbhandler import DatabaseHandler, Tag
from mopidyapi import MopidyAPI
import logging, time

logging.basicConfig(format='%(levelname)s CLASS : %(name)s FUNCTION : %(funcName)s LINE : %(lineno)d TIME : %(asctime)s MESSAGE : %(message)s', 
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG,
                    filename='o2m.log', 
                    filemode='a')

'''
    TODO :
        * Décider de la structure de la base
        * 
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
	                time.sleep(0.1)
	                tag.add_count()
	                print(f'Tag : {tag}' )
	                self.last_tag_uid = tag.uid
	                self.launch_track_mopidy(tag.media)
            	else:
            		print(f'Tag : {tag.uid} & last_tag_uid : {self.last_tag_uid}' )
            		self.launch_next()
            else:
                print(card.id)

        for card in removedCards:
            print('Stopping music')
            self.mopidy.playback.stop()

        # Launch some commands to mopidy

    def launch_next(self):
        self.mopidy.playback.next()
        self.mopidy.playback.play()

    def launch_track_mopidy(self, uri):
        time.sleep(1)
        self.mopidy.tracklist.clear()
        self.mopidy.tracklist.add(uris=[uri])
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