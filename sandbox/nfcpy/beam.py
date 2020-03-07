import nfc
import ndef
from threading import Thread

def beam(llc):
    snep_client = nfc.snep.SnepClient(llc)
    snep_client.put_records([ndef.UriRecord('http://nfcpy.org')])

def connected(llc):
    Thread(target=beam, args=(llc,)).start()
    return True

with nfc.ContactlessFrontend('usb') as clf:
    clf.connect(llcp={'on-connect': connected})