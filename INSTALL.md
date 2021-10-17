
# INSTALL

```
sudo apt-get update
sudo apt-get upgrade

# NFC
sudo apt-get install gcc swig pcsc-tools pcscd autoconf libtool libpcsclite-dev libusb-dev 
# Python
sudo apt-get install python3.7 python3.7-dev python3-pip build-essential libssl-dev libffi-dev libxml2-dev libxslt1-dev zlib1g-dev liblircclient-dev lirc
# Mopidy
wget -q -O - https://apt.mopidy.com/mopidy.gpg | sudo apt-key add -
sudo wget -q -O /etc/apt/sources.list.d/mopidy.list https://apt.mopidy.com/buster.list
sudo apt update
sudo apt-get install mopidy python-spotify libspotify-dev

sudo python3 -m pip install -r requirements.txt

# Mopidy running as a service 
sudo systemctl enable mopidy
sudo adduser mopidy video
echo "mopidy ALL=NOPASSWD: /usr/local/lib/python3.7/dist-packages/mopidy_iris/system.sh" | sudo tee -a /etc/sudoers

# Finalise modpidy configuration
sudo cp samples/mopidy.conf /etc/mopidy/mopidy.conf
sudo chmod 777 /etc/mopidy/mopidy.conf
sudo vi /etc/mopidy/mopidy.conf #and configure as needed
sudo mopidyctl local scan

#Tags db initialisation
sudo cp samples/o2m.db o2m.db #and modify as needed
sudo cp samples/o2m.conf /etc/mopidy/o2m.conf
sudo chmod 777 /etc/mopidy/o2m.conf


#autorun o2m
sudo cp samples/o2m.service /lib/systemd/system/o2m.service
sudo chmod 644 /lib/systemd/system/o2m.service
sudo vi lib/systemd/system/o2m.service #and configure if needed
sudo systemctl enable o2m.service
sudo systemctl start o2m.service

```
============================================NFC=======================================================
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

=======================================LIRC==============================================================
sudo apt-get install lirc
sudo cp samples/lirc/lirc_options.conf.dist /etc/lirc/lirc_options.conf
sudo cp samples/lirc/lircrc .
sudo cp samples/lirc/irexec.service /lib/systemd/system/irexec.service
sudo systemctl enable irexec.service
