
from pyscard.nfcreader import NfcReader


class NfcToMopidy():

    def __init__(self):
        nfcreader = NfcReader(self)
        nfcreader.loop()

    def get_new_cards(self, reason):
        print('O2M CHANGE : {}'.format(reason))

if __name__ == "__main__":
    nfcHandler = NfcToMopidy()