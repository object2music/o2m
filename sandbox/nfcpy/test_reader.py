import nfc
import datetime

def on_connect(tag):
    '''
    Callback function when a tag is detected
    '''
    uid = str(tag.identifier) 
    print(datetime.datetime.now().strftime("%H:%M:%S") + ' : ' + str(tag) + ' UID : ' + uid)
    if tag.ndef:
        print(tag.ndef)

def main():
    clf = nfc.ContactlessFrontend('usb')
    rdwr_options = {
            # 'on-startup': self.on_startup,
            'on-connect': on_connect,
            # 'beep-on-connect': False,
            # 'iterations': 1,
            # 'interval': 0.1
        }
    while True:
        tag = clf.connect(rdwr=rdwr_options)
        if tag == False:
            clf.close()

    
    print('end program')

if __name__ == "__main__":
    main()