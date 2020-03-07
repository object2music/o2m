
from pyscard.nfcreader import NfcReader
import pprint

class NfcToMopidy():
    activecards = {}

    def __init__(self):
        nfcreader = NfcReader(self)
        nfcreader.loop()
        
    def get_new_cards(self, addedCards, removedCards, activeCards):
        self.activecards = activeCards
        self.pretty_print_nfc_data(addedCards, removedCards)

        # Put some timestamps on cards ?
        
        # Do some stuff in sqlite database

        # Launch some commands to mopidy


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
    nfcHandler = NfcToMopidy()