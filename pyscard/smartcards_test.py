from __future__ import print_function
from time import sleep

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.scard import *

# a simple card observer that prints inserted/removed cards
class PrintObserver(CardObserver):
    """A simple card observer that is notified
    when cards are inserted/removed from the system and
    prints the list of cards
    """
    def update(self, observable, actions):
        (addedcards, removedcards) = actions
        for card in addedcards:
            int_id = self.get_id(card.reader)[:4] # we keep only the fourth first elements of the response
            hexa_id2 = [format(i, 'X').zfill(2) for i in int_id] # we convert to hex with format and add a 0 digit if necessary
            card.id = ''.join(hexa_id2)
            
            # print("+Inserted: ", toHexString(card.atr))
            print("+Inserted: {} in reader : {}".format(card.id, card.reader))

        for card in removedcards:
            # print("-Removed: ", toHexString(card.atr))
            print("-Removed: {} from reader : {}".format(card.id, card.reader))

    def get_id(self, reader):
        hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
        assert hresult==SCARD_S_SUCCESS

        hresult, hcard, dwActiveProtocol = SCardConnect(
            hcontext,
            reader,
            SCARD_SHARE_SHARED,
            SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

        hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])
        return response

if __name__ == '__main__':
    print("Insert or remove a smartcard in the system.")
    print("")
    cardmonitor = CardMonitor()
    cardobserver = PrintObserver()
    cardmonitor.addObserver(cardobserver)

    try:
        while True:
            sleep(10)
    except KeyboardInterrupt:
        print('interrupted!')
        # don't forget to remove observer, or the
        # monitor will poll forever...
        cardmonitor.deleteObserver(cardobserver)
    