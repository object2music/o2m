#!/bin/bash

mkdir /etc/mopidy/

sh create_conf_files.sh

#sleep 40
python3 -u main.py -m flask 
