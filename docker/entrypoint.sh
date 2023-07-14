#!/bin/bash

bash create_conf_files.sh

# replace index.html with our own > to move in create_conf ?
cp index.html /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/index.html

# Launch processes
#mopidy --config /etc/mopidy/mopidy.conf -vvv &
mopidy --config /etc/mopidy/mopidy.conf &
P1=$!
sleep 40
/usr/bin/python3 main.py -m flask &
P2=$!

#wait $P1 $P2
# Wait for any process to exit
#wait -n

# Exit with status of process that exited first
#exit $?

tail -f /dev/null