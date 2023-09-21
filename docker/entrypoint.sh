#!/bin/bash

bash create_conf_files.sh

# replace index.html with our own > to move in create_conf ?
cp index.html /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/index.html

# Get env vars
O2M_API_PORT=${O2M_API_PORT:-5000}
O2M_BACKOFFICE_URI=${O2M_BACKOFFICE_URI:-http://localhost:5011}
sed -ci "s/:6691\/api\//:$O2M_API_PORT\/api\//g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js
sed -ci "s/http:\/\/localhost:5011:$O2M_BACKOFFICE_URI/g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js

#Create Mysql
#rm -rf mysql_data

# Launch processes
#mopidy --config /etc/mopidy/mopidy.conf -vvv &
mopidy --config /etc/mopidy/mopidy.conf &
P1=$!
#sleep 40
/usr/bin/python3 -u main.py -m flask &
P2=$!

#wait $P1 $P2
# Wait for any process to exit
#wait -n

# Exit with status of process that exited first
#exit $?

tail -f /dev/null