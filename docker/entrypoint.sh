#!/bin/bash

bash create_conf_files.sh

# replace index.html with our own
cp index.html /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/index.html

# Launch
mopidy --config /etc/mopidy/mopidy.conf -vvv &
python3 main.py -m flask &

tail -f /dev/null