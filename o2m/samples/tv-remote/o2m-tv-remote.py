#!/usr/bin/env python3
"""The Pi as a Bluetooth LE remote control (HID over GATT), to WAKE the TV box.

Why it exists: a Mi Box in deep standby leaves the Wi-Fi altogether (measured:
no ping, no Cast, no port open), so no network command can reach it, and a `tv:`
tag put down hours after the box was switched off did nothing. Its paired
Bluetooth remotes keep their link through that standby, and a key sent on it
wakes the box: back on the network, Cast answering, 6 s after the key.

o2m (tvcast) writes a key name to the FIFO; this daemon sends it:

    echo wakeup > /run/o2m-tv-remote.fifo
    (power wakeup home back select up down left right playpause)

`power` is a TOGGLE (it sleeps a box that is awake); `wakeup` (System Wake Up,
Android KEYCODE_WAKEUP) only ever wakes.

Runs as root, beside bluetoothd, with python3-dbus and python3-gi (both in
Raspberry Pi OS). It needs the controller set up by o2m-tv-remote-address.service
first — LE only, its own public address — see that unit for why. Pair it once
from the box: Settings → Remotes & accessories → Add accessory → "o2m remote".
"""
import os
import threading
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BUS = 'org.bluez'
ADAPTER = '/org/bluez/hci0'
PROPS = 'org.freedesktop.DBus.Properties'
OM = 'org.freedesktop.DBus.ObjectManager'
SVC = 'org.bluez.GattService1'
CHR = 'org.bluez.GattCharacteristic1'
DSC = 'org.bluez.GattDescriptor1'
FIFO = os.environ.get('O2M_REMOTE_FIFO', '/run/o2m-tv-remote.fifo')
NAME = os.environ.get('O2M_REMOTE_NAME', 'o2m remote')

# Report 1: consumer control (one 16-bit usage). Report 2: keyboard.
# Report 3: system control, one bit per usage: power down, sleep, wake up.
REPORT_MAP = bytes([
    0x05, 0x0C, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x01,
    0x15, 0x00, 0x26, 0xFF, 0x03, 0x19, 0x00, 0x2A, 0xFF, 0x03,
    0x75, 0x10, 0x95, 0x01, 0x81, 0x00, 0xC0,
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x85, 0x02,
    0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01,
    0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
    0x95, 0x01, 0x75, 0x08, 0x81, 0x01,
    0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65,
    0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xC0,
    0x05, 0x01, 0x09, 0x80, 0xA1, 0x01, 0x85, 0x03,
    0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x03,
    0x09, 0x81, 0x09, 0x82, 0x09, 0x83, 0x81, 0x02,
    0x95, 0x05, 0x81, 0x01, 0xC0,
])

CONSUMER = {'power': 0x30, 'home': 0x223, 'back': 0x224, 'playpause': 0xCD}
KEYBOARD = {'select': 0x28, 'up': 0x52, 'down': 0x51, 'left': 0x50, 'right': 0x4F}
SYSTEM = {'wakeup': 0x04}       # bit 2 of report 3: System Wake Up


def log(*a):
    print(time.strftime('%T'), *a, flush=True)


def ay(data):
    return dbus.Array([dbus.Byte(b) for b in data], signature='y')


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/o2m/remote'
        self.services = []
        super().__init__(bus, self.path)

    @dbus.service.method(OM, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        out = {}
        for s in self.services:
            out[s.get_path()] = s.get_properties()
            for c in s.chars:
                out[c.get_path()] = c.get_properties()
                for d in c.descs:
                    out[d.get_path()] = d.get_properties()
        return out


class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid):
        self.path = '/o2m/remote/service%d' % index
        self.bus = bus
        self.uuid = uuid
        self.chars = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {SVC: {'UUID': self.uuid, 'Primary': True,
                      'Characteristics': dbus.Array([c.get_path() for c in self.chars], signature='o')}}

    def add(self, uuid, flags, value=b'', report_ref=None):
        c = Characteristic(self.bus, len(self.chars), uuid, flags, self, value)
        self.chars.append(c)
        if report_ref:
            c.descs.append(Descriptor(self.bus, 0, '2908', ['encrypt-read'], c, report_ref))
        return c


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service, value):
        self.path = service.path + '/char%d' % index
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.value = bytes(value)
        self.descs = []
        self.notifying = False
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {CHR: {'Service': self.service.get_path(), 'UUID': self.uuid, 'Flags': self.flags,
                      'Descriptors': dbus.Array([d.get_path() for d in self.descs], signature='o')}}

    @dbus.service.method(CHR, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return ay(self.value)

    @dbus.service.method(CHR, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        self.value = bytes(value)

    @dbus.service.method(CHR)
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(CHR)
    def StopNotify(self):
        self.notifying = False

    @dbus.service.signal(PROPS, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def send(self, data):
        self.value = bytes(data)
        if self.notifying:
            self.PropertiesChanged(CHR, {'Value': ay(self.value)}, [])
        return self.notifying


class Descriptor(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, chrc, value):
        self.path = chrc.path + '/desc%d' % index
        self.uuid = uuid
        self.flags = flags
        self.chrc = chrc
        self.value = bytes(value)
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {DSC: {'Characteristic': self.chrc.get_path(), 'UUID': self.uuid, 'Flags': self.flags}}

    @dbus.service.method(DSC, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return ay(self.value)


class Advertisement(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/o2m/remote/adv0'
        super().__init__(bus, self.path)

    @dbus.service.method(PROPS, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return {'Type': 'peripheral',
                'ServiceUUIDs': dbus.Array(['1812'], signature='s'),
                'Appearance': dbus.UInt16(0x03C1),   # keyboard
                'LocalName': NAME,
                'Discoverable': True}

    @dbus.service.method('org.bluez.LEAdvertisement1')
    def Release(self):
        log('advertisement released')


class Agent(dbus.service.Object):
    """Just Works pairing: the box shows no code to type."""
    IFACE = 'org.bluez.Agent1'

    @dbus.service.method(IFACE, in_signature='', out_signature='')
    def Release(self):
        pass

    @dbus.service.method(IFACE, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        pass

    @dbus.service.method(IFACE, in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        pass

    @dbus.service.method(IFACE, in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        pass

    @dbus.service.method(IFACE, in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        return '0000'

    @dbus.service.method(IFACE, in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method(IFACE, in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        pass

    @dbus.service.method(IFACE, in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method(IFACE, in_signature='', out_signature='')
    def Cancel(self):
        log('pairing cancelled')


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = bus.get_object(BUS, ADAPTER)
    aprops = dbus.Interface(adapter, PROPS)
    for k, v in (('Powered', True), ('Alias', NAME), ('Pairable', True),
                 ('Discoverable', True), ('DiscoverableTimeout', dbus.UInt32(0))):
        aprops.Set('org.bluez.Adapter1', k, v)

    Agent(bus, '/o2m/remote/agent')
    am = dbus.Interface(bus.get_object(BUS, '/org/bluez'), 'org.bluez.AgentManager1')
    am.RegisterAgent('/o2m/remote/agent', 'NoInputNoOutput')
    am.RequestDefaultAgent('/o2m/remote/agent')

    app = Application(bus)
    hid = Service(bus, 0, '1812')
    app.services.append(hid)
    hid.add('2a4a', ['encrypt-read'], bytes([0x11, 0x01, 0x00, 0x03]))  # HID 1.11, RemoteWake|NormallyConnectable
    hid.add('2a4b', ['encrypt-read'], REPORT_MAP)
    hid.add('2a4c', ['write-without-response'], b'\x00')
    hid.add('2a4e', ['encrypt-read', 'write-without-response'], b'\x01')
    reports = {
        1: hid.add('2a4d', ['encrypt-read', 'notify'], bytes(2), bytes([1, 1])),
        2: hid.add('2a4d', ['encrypt-read', 'notify'], bytes(8), bytes([2, 1])),
        3: hid.add('2a4d', ['encrypt-read', 'notify'], bytes(1), bytes([3, 1])),
    }
    bat = Service(bus, 1, '180f')
    app.services.append(bat)
    bat.add('2a19', ['read', 'notify'], bytes([100]))
    info = Service(bus, 2, '180a')
    app.services.append(info)
    info.add('2a29', ['read'], b'o2m')
    info.add('2a50', ['read'], bytes([0x02, 0x6b, 0x1d, 0x46, 0x02, 0x00, 0x01]))  # PnP ID

    dbus.Interface(adapter, 'org.bluez.GattManager1').RegisterApplication(
        app.path, {}, reply_handler=lambda: log('GATT application registered'),
        error_handler=lambda e: log('GATT error', e))
    adv = Advertisement(bus)
    dbus.Interface(adapter, 'org.bluez.LEAdvertisingManager1').RegisterAdvertisement(
        adv.path, {}, reply_handler=lambda: log('advertising as', NAME),
        error_handler=lambda e: log('advertising error', e))

    def on_props(interface, changed, invalidated, path=None):
        if interface == 'org.bluez.Device1':
            seen = {k: bool(v) for k, v in changed.items() if k in ('Connected', 'Paired')}
            if seen:
                log(path.rsplit('/', 1)[-1], seen)
    bus.add_signal_receiver(on_props, dbus_interface=PROPS, signal_name='PropertiesChanged',
                            path_keyword='path')

    def press(word):
        if word in CONSUMER:
            rep, down, up = reports[1], CONSUMER[word].to_bytes(2, 'little'), bytes(2)
        elif word in KEYBOARD:
            rep, down, up = reports[2], bytes([0, 0, KEYBOARD[word], 0, 0, 0, 0, 0]), bytes(8)
        elif word in SYSTEM:
            rep, down, up = reports[3], bytes([SYSTEM[word]]), bytes(1)
        else:
            log('unknown key', word)
            return False
        ok = rep.send(down)
        GLib.timeout_add(120, lambda: rep.send(up) and False)
        log('key', word, 'sent' if ok else 'NOT sent: no box connected')
        return False

    def reader():
        if not os.path.exists(FIFO):
            os.mkfifo(FIFO)
        os.chmod(FIFO, 0o666)
        while True:
            with open(FIFO) as f:
                for line in f:
                    if line.strip():
                        GLib.idle_add(press, line.strip())
    threading.Thread(target=reader, daemon=True).start()

    log('ready, keys on', FIFO)
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
