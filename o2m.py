from pyscard.nfcreader import NfcReader
from events import Events


class NfcToMopidy():

    def __init__(self):
        nfcreader = NfcReader()
        nfcreader.loop()
        
        # nfcreader.events.nfc_cards_update += self.get_new_cards
        # nfcreader.cardobserver.events.on_change += self.get_new_cards
        # nfcreader.on_init += self.on_init
        # nfcreader.on_change += self.get_new_cards

    def on_init(self):
        print('init!')

    def get_new_cards(self, reason):
        print('O2M CHANGE : {}'.format(reason))

if __name__ == "__main__":
    nfcHandler = NfcToMopidy()