from __future__ import print_function
from time import sleep

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.System import readers
from smartcard.scard import SCardEstablishContext, SCardTransmit, SCardConnect, SCARD_PROTOCOL_T1, SCARD_PROTOCOL_T0, SCARD_SHARE_SHARED, SCARD_S_SUCCESS, SCARD_SCOPE_USER

from events import Events

cmdMap = {
	"mute":[0xFF, 0x00, 0x52, 0x00, 0x00],
	"unmute":[0xFF, 0x00, 0x52, 0xFF, 0x00],
	"getuid":[0xFF, 0xCA, 0x00, 0x00, 0x00],
	"firmver":[0xFF, 0x00, 0x48, 0x00, 0x00],
}

# a simple card observer that prints inserted/removed cards
class PrintObserver(CardObserver):
    """A simple card observer that is notified
    when cards are inserted/removed from the system and
    prints the list of cards
    """
    addedcards = []
    removedcards = []
    def __init__(self):
        self.events = Events()

    def update(self, observable, actions):
        (addedcards, removedcards) = actions
        for card in addedcards:
            # Methode 1
            readerObject = self.get_reader_by_name(card.reader)
            uid_str = self.get_id_with_reader(readerObject)
            print('METHODE 1 : Card id : {} in reader : {}'.format(uid_str, readerObject))

            # Methode 2
            int_id = self.get_id(card.reader)
            card.id = self.convert_to_hex_as_string(int_id)
            print("METHODE 2 : +Inserted: {} in reader : {}".format(card.id, card.reader))

        for card in removedcards:
            print("-Removed: {} from reader : {}".format(card.id, card.reader))

        self.addedcards = addedcards
        self.removedcards = removedcards
        self.events.on_change(addedcards)

    ''' 
    Deuxième méthode de connexion 

    Avantages : Plus simple à lire, pas besoin de retirer les données en surplus
    Necessite l'object PCSCReader et pas juste le nom du reader (chaine de caractère)
    '''
    def get_reader_by_name(self, reader_name):
        return next((x for x in readers() if x.name == reader_name), None)

    def get_id_with_reader(self, reader):
        return self.launch_command_with_reader(reader, cmdMap['getuid'])

    def launch_command_with_reader(self, reader, command):
        connection = reader.createConnection()
        connection.connect()
        data, sw1, sw2 = connection.transmit(command)
        return self.convert_to_hex_as_string(data)

    '''
        Première méthode de connexion à la carte
        Le nom du reader suffit mais renvoie plus de donnée que nécessaire (obligé de tronquer le résultat)
    '''    
    def get_id(self, reader_name):
        return self.launch_command(reader_name, cmdMap['getuid'])[:4] # we keep only the fourth first elements of the response

    def launch_command(self, reader_name, command):
        hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
        assert hresult==SCARD_S_SUCCESS

        hresult, hcard, dwActiveProtocol = SCardConnect(
            hcontext,
            reader_name,
            SCARD_SHARE_SHARED,
            SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

        # hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])
        hresult, response = SCardTransmit(hcard,dwActiveProtocol, command)
        return response

    def convert_to_hex_as_string(self, data):
        hexData = [format(i, 'X').zfill(2) for i in data] # we convert to hex with format and add a 0 digit if necessary
        return ''.join(hexData)

class NfcReader():

    def __init__(self):
        print("NFCReader initializing...")
        print("Insert or remove a smartcard in the system.")
        print("")

        self.events = Events()
        self.cardmonitor = CardMonitor()
        self.cardobserver = PrintObserver()
        self.cardmonitor.addObserver(self.cardobserver)
        self.cardobserver.events.on_change += self.update_change
        
        self.mute_all_readers()
        
        self.events.on_init()

    def update_change(self, reason):
        print('update change {}'.format(reason))
        self.events.on_change(reason)

    def loop(self):
        try:
            while True:
                sleep(10)
        except KeyboardInterrupt:
            print('interrupted!')
            self.close()

    # marche uniquement si une carte est ajoutée
    def mute_all_readers(self):
        for r in readers():
            #Methode 1
            # self.cardobserver.launch_command(r.name, cmdMap['mute'])
            #Methode 2
            connection = r.createConnection()
            connection.connect()
            connection.transmit(cmdMap['mute'])
            print('Reader {} muted!'.format(r))



    def close(self):
        # don't forget to remove observer, or the
        # monitor will poll forever...
        self.cardmonitor.deleteObserver(self.cardobserver)
        print('Observer removed!')

if __name__ == '__main__':
    nfc = NfcReader()
    nfc.loop()
    