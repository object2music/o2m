#!/bin/bash

echo "Creating config files"

sh create_conf_files.sh


echo "Starting o2m service"

systemctl start o2m.service

echo "Starting mopidy service"

/usr/bin/ mopidyctl  local scan

/usr/bin/mopidy --config /etc/mopidy/mopidy.conf &


python3 main.py

tail -f /dev/null