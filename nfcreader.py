import nfc
import time
import datetime

class NfcReader():
    def __init__(self, usb_bus, name):
        self.bus = usb_bus
        self.name = name
        self.clf = nfc.ContactlessFrontend(self.bus)
        self.rdwr_options = {
            'on-startup': self.on_startup,
            'on-connect': self.on_connect,
            'beep-on-connect': False,
            'iterations': 1,
            'interval': 0.1
        }
        print(self.clf)

    def on_startup(self, targets):
        for target in targets:
            target.sensf_req = bytearray.fromhex("0012FC0000")
        return targets

    def on_connect(self, tag):
        '''
        Callback function when a tag is detected
        '''
        uid = str(tag.identifier) 
        print(datetime.datetime.now().strftime("%H:%M:%S") + '    ' + self.name + ' : ' + str(tag) + ' on bus : ' + self.bus + ' UID : ' + uid)
        if tag.ndef:
            print(tag.ndef)

    def connect(self):
        '''
        This lambda function is used to terminate the while loop inside the connect function after some time
        A lambda function is a function as variable that we can passed in as an argument

        Inside this connect function, there is a while loop that sense the reader with some intervals and iterations
        defined in the rdwr_options variable. We use the terminate argument to kill the while loop after some time
        '''
        after_some_time = lambda: datetime.datetime.now() - started > datetime.timedelta(milliseconds=100)
        started = datetime.datetime.now()
        tag = self.clf.connect(rdwr=self.rdwr_options, terminate=after_some_time)
        if tag == False:
            self.clf.close()
    
    def disconnect(self):
        self.clf.close()

def main():
    # find the bus information with this command : python3 -m nfc
    try:
        reader1 = NfcReader('usb:020:003', 'READER 1')
        reader2 = NfcReader('usb:020:005', 'READER 2')

        while True:
            reader1.connect()
            reader2.connect()
    except OSError as err:
        print("OS error: {0}".format(err))

    print('end program')

if __name__ == "__main__":
    main()

'''
        CONTACTLESS FRONTEND CONNECT FUNCTION DOCUMENTATION
        """Connect with a Target or Initiator

        The calling thread is blocked until a single activation and
        deactivation has completed or a callback function supplied as
        the keyword argument ``terminate`` returns a true value. The
        example below makes :meth:`~connect()` return after 5 seconds,
        regardless of whether a peer device was connected or not.

        >>> import nfc, time
        >>> clf = nfc.ContactlessFrontend('usb')
        >>> after5s = lambda: time.time() - started > 5
        >>> started = time.time(); clf.connect(llcp={}, terminate=after5s)

        Connect options are given as keyword arguments with dictionary
        values. Possible options are:

        * ``rdwr={key: value, ...}`` - options for reader/writer
        * ``llcp={key: value, ...}`` - options for peer to peer
        * ``card={key: value, ...}`` - options for card emulation

        **Reader/Writer Options**

        'targets' : iterable
           A list of bitrate and technology type strings that will
           produce the :class:`~nfc.clf.RemoteTarget` objects to
           discover. The default is ``('106A', '106B', '212F')``.

        'on-startup' : function(targets)
           This function is called before any attempt to discover a
           remote card. The *targets* argument provides a list of
           :class:`RemoteTarget` objects prepared from the 'targets'
           bitrate and technology type strings. The function must
           return a list of of those :class:`RemoteTarget` objects
           that shall be finally used for discovery, those targets may
           have additional attributes. An empty list or anything else
           that evaluates false will remove the 'rdwr' option
           completely.

        'on-discover' : function(target)
           This function is called when a :class:`RemoteTarget` has
           been discovered. The *target* argument contains the
           technology type specific discovery responses and should be
           evaluated for multi-protocol support. The target will be
           further activated only if this function returns a true
           value. The default function depends on the 'llcp' option,
           if present then the function returns True only if the
           target does not indicate peer to peer protocol support,
           otherwise it returns True for all targets.

        'on-connect' : function(tag)
           This function is called when a remote tag has been
           activated. The *tag* argument is an instance of class
           :class:`nfc.tag.Tag` and can be used for tag reading and
           writing within the callback or in a separate thread. Any
           true return value instructs :meth:`connect` to wait until
           the tag is no longer present and then return True, any
           false return value implies immediate return of the
           :class:`nfc.tag.Tag` object.

        'on-release' : function(tag)
           This function is called when the presence check was run
           (the 'on-connect' function returned a true value) and
           determined that communication with the *tag* has become
           impossible, or when the 'terminate' function returned a
           true value. The *tag* object may be used for cleanup
           actions but not for communication.

        'iterations' : integer
           This determines the number of sense cycles performed
           between calls to the terminate function. Each iteration
           searches once for all specified targets. The default value
           is 5 iterations and between each iteration is a waiting
           time determined by the 'interval' option described below.
           As an effect of math there will be no waiting time if
           iterations is set to 1.

        'interval' : float
           This determines the waiting time between iterations. The
           default value of 0.5 seconds is considered a sensible
           tradeoff between responsiveness in terms of tag discovery
           and power consumption. It should be clear that changing
           this value will impair one or the other. There is no free
           beer.

'''