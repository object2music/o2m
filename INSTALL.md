
INSTALL

```
Sudo apt-get update
Sudo apt-get upgrade

sudo apt-get install gcc swig pcsc-tools pcscd libnfc-bin autoconf libtool libpcsclite-dev libusb-dev

Sudo apt-get install python3-pip
pip3 install pyscard
```

// DOESN'T WORK YET! WE NEED A PATCHED VERSION OF LIBNFC FOR THE TIMEOUT ERROR ON ACS ACR122U READERS

```
sudo nano /etc/modprobe.d/blacklist-libnfc.conf
blacklist nfc
blacklist pn533
blacklist pn533_usb

sudo modprobe -r pn533_usb
sudo modprobe -r pn533
```

```
Apt-get csh gawk libblkid-dev libffi-dev libfl2 libglib2.0-bin libglib2.0-dev libglib2.0-dev-bin liblzma-dev libmount-dev libnfc-dev libpcre16-3 libpcre3-dev libpcre32-3 libpcrecpp0v5 libselinux1-dev libsepol1-dev uuid-dev

apt-get install git binutils make csh g++ sed gawk autoconf automake autotools-dev libglib2.0-dev liblzma-dev libtool 

git clone https://github.com/jpwidera/libnfc.git
cd libnfc
autoreconf -is
./configure --prefix=/usr --sysconfdir=/etc
Make
Sudo make install
Cd /usr/lib
sudo cp -p libnfc.* arm-linux-gnueabihf/
```

// IT WORKS!


FOR TESTING YOUR READERS AND YOUR INSTALL : 
``nfc-scan-device -v``

REFERENCE (IN FRENCH): https://www.latelierdugeek.fr/2019/09/30/acr122u-resoudre-lerreur-unable-to-set-alternate-setting-on-usb-interface/