#!/bin/bash

mkdir /etc/mopidy/

bash create_conf_files.sh

#sleep 40
python -u main.py -m flask &


tail -f /dev/null