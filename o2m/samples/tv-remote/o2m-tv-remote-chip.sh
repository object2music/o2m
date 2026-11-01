#!/bin/sh
# The Pi 3's Bluetooth chip sits on a UART and its firmware load at boot
# sometimes times out ("BCM: Reset failed (-110)", then bthelper "Can't init
# device hci0"). hci0 still exists in sysfs but the kernel never registers the
# controller: btmgmt lists no index, bluetoothd has no adapter, and the box can
# no longer be woken until the next reboot. Rebinding the UART driver loads the
# firmware again, and does it on the first try (measured 2026-11-01).
DEV=serial0-0
DRV=/sys/bus/serial/drivers/hci_uart_bcm

ready() { btmgmt info 2>/dev/null | grep -q '^hci0:'; }

for try in 1 2 3; do
    ready && exit 0
    [ -e "$DRV/bind" ] || { echo "no $DRV"; exit 1; }
    echo "Bluetooth controller missing, rebinding $DEV (try $try)"
    [ -e "$DRV/$DEV" ] && echo "$DEV" > "$DRV/unbind"
    sleep 2
    echo "$DEV" > "$DRV/bind"
    sleep 8
done
ready
