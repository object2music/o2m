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
            print("+Inserted: ", toHexString(card.atr))
        for card in removedcards:
            print("-Removed: ", toHexString(card.atr))

if __name__ == '__main__':
    print("Insert or remove a smartcard in the system.")
    print("This program will exit in 10 seconds")
    print("")
    cardmonitor = CardMonitor()
    cardobserver = PrintObserver()
    cardmonitor.addObserver(cardobserver)

    sleep(100)

    # don't forget to remove observer, or the
    # monitor will poll forever...
    cardmonitor.deleteObserver(cardobserver)


    # hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)

    # assert hresult==SCARD_S_SUCCESS

    # hresult, readers = SCardListReaders(hcontext, [])

    # assert len(readers)>0

    # reader = readers[0]

    # hresult, hcard, dwActiveProtocol = SCardConnect(
    #     hcontext,
    #     reader,
    #     SCARD_SHARE_SHARED,
    #     SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

    # hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])

    # print(response)