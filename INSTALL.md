
# INSTALL

```
sudo apt-get update
sudo apt-get upgrade

sudo apt-get install gcc swig pcsc-tools pcscd autoconf libtool libpcsclite-dev libusb-dev python3.7

sudo apt-get install python3-pip
python-3.7 -m pip install -r requirements.txt
```

**Doesn't work yet! we need a patched version of libnfc for the timeout error on acs acr122u readers**

```
sudo nano /etc/modprobe.d/blacklist-libnfc.conf
blacklist nfc
blacklist pn533
blacklist pn533_usb

sudo modprobe -r pn533_usb
sudo modprobe -r pn533
```

```
sudo apt-get install csh gawk libblkid-dev libffi-dev libfl2 libglib2.0-bin libglib2.0-dev libglib2.0-dev-bin liblzma-dev libmount-dev libpcre16-3 libpcre3-dev libpcre32-3 libpcrecpp0v5 libselinux1-dev libsepol1-dev uuid-dev git binutils make csh g++ sed gawk autoconf automake autotools-dev libglib2.0-dev liblzma-dev libtool 

git clone https://github.com/jpwidera/libnfc.git
cd libnfc
autoreconf -is
./configure --prefix=/usr --sysconfdir=/etc
make
sudo make install
cd /usr/lib
sudo cp -p libnfc.* arm-linux-gnueabihf/
sudo cp -p libnfc.* i386-linux-gnu/
```

### **IT WORKS!**


For testing your readers and your install : 

``sudo nfc-scan-device -v``

Reference (in french): 

https://www.latelierdugeek.fr/2019/09/30/acr122u-resoudre-lerreur-unable-to-set-alternate-setting-on-usb-interface/
