from __future__ import print_function
from time import sleep
import configparser, sys, time, os

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.System import readers
from smartcard.scard import SCardEstablishContext, SCardTransmit, SCardConnect, SCARD_PROTOCOL_T1, SCARD_PROTOCOL_T0, SCARD_SHARE_SHARED, SCARD_S_SUCCESS, SCARD_SCOPE_USER
from smartcard.Exceptions import NoCardException

from events import Events
import logging
import requests
#from urllib.request import urlretrieve

cmdMap = {
    "mute":[0xFF, 0x00, 0x52, 0x00, 0x00],
    "unmute":[0xFF, 0x00, 0x52, 0xFF, 0x00],
    "getuid":[0xFF, 0xCA, 0x00, 0x00, 0x00],
    "firmver":[0xFF, 0x00, 0x48, 0x00, 0x00],
}

'''
    TODO :
    *   Choose a connection method
    *   Clean the code
    *   Improve comments
'''
class PrintObserver(CardObserver):
    """A simple card observer that is notified
    when cards are inserted/removed from the system and
    prints the list of cards
    """

    def __init__(self):
        self.events = Events()
        self.muted_readers_names = []
        self.active_cards = {}
        self.log = logging.getLogger(__name__)

    def update(self, observable, actions):
        # self.mute_all_readers()
        (addedcards, removedcards) = actions
        for card in addedcards:
            #Temporaly ractivate beep sound waiting for better feedback implementation
            #self.mute_reader(card.reader) # The reader has a card on it so we can try to remove the beep
            # Methode 1
            int_id = self.get_id(card.reader)
            card.id = self.convert_to_hex_as_string(int_id)
            # print("METHODE 1 : +Inserted: {} in reader : {}".format(card.id, card.reader))

            # Methode 2
            readerObject = self.get_reader_by_name(card.reader)
            uid_str = self.get_id_with_reader(readerObject)
            # if uid_str != None:
            #     print('METHODE 2 : Card id : {} in reader : {}'.format(uid_str, readerObject))
            # else:
            #     print('METHODE 2 : ERROR')
            self.log.info('+Inserted: {} in reader : {}'.format(card.id, card.reader))
            self.active_cards[card.reader] = card # active cards dict update

        for card in removedcards:
            card.id = self.active_cards[card.reader].id
            self.log.info('+Removed: {} in reader : {}'.format(card.id, card.reader))
            self.active_cards[card.reader] = None # active cards dict update

        self.events.on_change(addedcards, removedcards, self.active_cards) # Launch the event 

    '''
        Mute the readers | Remove the beep sound on card/tag connection
        Works only if a card is on the reader
        Throw an exception otherwise

        Two differents methods that works the same way but throw differents exceptions

        Once a reader is muted, the settings is live until the reader is unplugged.
        we store in a the muted_readers_names list of the readers already muted and launch the mute command only if useful
    '''
    def mute_reader(self, reader_name):
        reader = self.get_reader_by_name(reader_name)
        if reader != None:
            if reader.name not in self.muted_readers_names:
                # Methode 1
                # try:
                #     self.launch_command(reader.name, cmdMap['mute'])
                #     print('Reader {} muted!'.format(reader.name))
                #     self.muted_readers_names.append(reader.name)
                # except SystemError as err:
                #     print(err)
                #Methode 2
                try:
                    connection = reader.createConnection()
                    connection.connect()
                    connection.transmit(cmdMap['mute'])
                    self.muted_readers_names.append(reader.name)
                    self.log.info('Reader {} muted!'.format(reader.name))
                except NoCardException as err:
                    print('Error : {} on reader : {}'.format(err, reader.name))

    '''
        First connection method
        The reader name is enough but this method get too much data, we need to truncate the response to get the right uid
        Return : the response minus the two last elements of the byte list
    '''    
    def get_id(self, reader_name):
        return self.launch_command(reader_name, cmdMap['getuid'])

    def launch_command(self, reader_name, command):
        try:
            hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
            assert hresult==SCARD_S_SUCCESS

            hresult, hcard, dwActiveProtocol = SCardConnect(
                hcontext,
                reader_name,
                SCARD_SHARE_SHARED,
                SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

            # hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])
            hresult, response = SCardTransmit(hcard,dwActiveProtocol, command)
            
            return response[:len(response)-2]
        except SystemError as err:
            print("Error in launch command : {}".format(err))
            return None

    ''' 
        Second connection method

        Pros : easier to read, no need to truncate the response
        Cons : need a PCSCReader as parameter instead of a name
    '''
    def get_reader_by_name(self, reader_name):
        return next((x for x in readers() if x.name == reader_name), None)

    def get_id_with_reader(self, reader):
        return self.launch_command_with_reader(reader, cmdMap['getuid'])

    def launch_command_with_reader(self, reader, command):
        try:
            connection = reader.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit(command)
            return self.convert_to_hex_as_string(data)
        except NoCardException as err: 
            print(err)
            return None

    '''
        Util function used by both methods
    '''
    def convert_to_hex_as_string(self, data):
        hexData = [format(i, 'X').zfill(2) for i in data] # we convert to hex with format and add a 0 digit if necessary
        return ''.join(hexData)

   

class NfcReader():

    def __init__(self, o2m=None):

        #CONFIG
        nfcconf = self.get_config_file("nfc.conf")
        connexion = nfcconf["connexion"]  # o2m
        
        if "url_base" in connexion: self.url_base = connexion["url_base"]
        if "port" in connexion: self.port = connexion["port"]


        #NFC INIT AND LOOP
        print("NFCReader initializing...")
        print("Insert or remove a smartcard in the system.")
        print("")

        self.log = logging.getLogger(__name__)
        self.cardmonitor = CardMonitor()
        self.cardobserver = PrintObserver()
        self.cardmonitor.addObserver(self.cardobserver)
        self.cardobserver.events.on_change += self.update_change


    def get_config_file(self,filename):
        config = configparser.ConfigParser()
        config.read(filename)
        return config

    '''
        Callback function called when the card observer triggers the event on_change.
        this function just pass the parameters to the parent NfcToMopidy object
    '''    
    def update_change(self, addedCards, removedCards, activeCards):
        #self.o2m.get_new_cards(addedCards, removedCards, activeCards)
        url1 = self.url_base+"/box"
        #url1 = self.url_base+"/box"+":"+self.port

        if (addedCards != None):
            for uid in addedCards:
                params = {'uid':uid.id, 'mode':'add'}
                r = requests.get(url = url1, params = params)
                #url = url1 + "?uid=" + uid.id + "&mode=add" 
                #thing = urlretrieve(url)
        if (removedCards != None):
            for uid in removedCards:
                params = {'uid':uid.id, 'mode':'remove'}
                r = requests.get(url = url1, params = params)
                #data = r.json()             
                #url = url1+"?uid="+uid.id+"&mode=remove"
                #thing = urlretrieve(url)


    '''
        Start an infinite loop to keep the readers polling
    '''
    def loop(self):
        try:
            while True:
                sleep(10)
        except KeyboardInterrupt:
            self.remove_observer()
            self.log.info('Keyboard Interrupt : Removing observer')

    '''
        If killed properly we remove the observer to prevent forever polling on the readers
    '''
    def remove_observer(self):
        # don't forget to remove observer, or the
        # monitor will poll forever...
        self.cardmonitor.deleteObserver(self.cardobserver)
        self.log.info('Observer removed : Connection closed')

if __name__ == '__main__':
    nfc = NfcReader()
    nfc.loop()
    