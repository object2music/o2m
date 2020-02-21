# Object 2 Music

### Dependencies

* [NfcPy](https://pypi.org/project/nfcpy/)- Python module for Near Field Communication.

### Installation

O2M requires Python3 to run.

NfcPy requires libusb to run, on linux nfcpy and libusb are already installed.

Otherwise : 

```sh
$ pip3 install -U nfcpy
$ python3 -m nfc
```

[NfcPy Documentation](https://nfcpy.readthedocs.io/en/latest/topics/get-started.html)

##### Mac OS

On Mac, the service ifreader is getting rights instead of nfcpy and the command *python3 -m nfc* doesnt work. You have to stop the service before using nfcpy

```sh
$ sudo launchctl remove com.apple.ifdreader
$ sudo launchctl stop com.apple.ifdreader
$ python3 -m nfc
```

For convenience with zsh and ohmyzsh in your config file .zhrc :
```
find_nfc_devices(){
  stop_ifreader
  python3 -m nfc
}
```

You can then use the command *find_nfc_devices* in your shell

### Usage

There is a *main()* function inside nfcreader for testing purpose. You have to set the correct Bus information for your nfc readers. You can find them with the *python3 -m nfc* command : 
```
This is the 1.0.3 version of nfcpy run in Python 3.7.6
on Darwin-19.3.0-x86_64-i386-64bit
I'm now searching your system for contactless devices
** found ACS ACR122U PN532v1.6 at usb:020:006
** found ACS ACR122U PN532v1.6 at usb:020:005
I'm not trying serial devices because you haven't told me
-- add the option '--search-tty' to have me looking
-- but beware that this may break other serial devs
```

### Todos

 - 

License
----

GPL-3.0

