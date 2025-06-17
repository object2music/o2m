#!/bin/bash

bash create_conf_files.sh

# replace index.html with our own > to move in create_conf ?
cp index.html /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/index.html
cp app.js /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/app.js
# Fix new crendentials OAuth Spotify
mkdir -p /root/.local/share/mopidy/spotify/credentials-cache
#cp -f credentials.json /root/.local/share/mopidy/spotify/credentials-cache/credentials.json

# Get env vars
O2M_API_PORT=${PORT_O2M_API:-5000}
O2M_BACKOFFICE_URI=${O2M_BACKOFFICE_URI:-'http://localhost:5011'}

sed -i "s/:6681\/api\//:$O2M_API_PORT\/api\//g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js
sed -i "s/http:\/\/localhost:5011/$O2M_BACKOFFICE_URI/g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js

<<com
# Get env vars
FILE=tmp_o2m.js
if test -f "$FILE"; then
    rm tmp_o2m.js
fi
O2M_API_PORT=${O2M_API_PORT:-5000}  
sed "s/:6681\/api\//:$O2M_API_PORT\/api\//g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js > tmp_o2m.js
cp tmp_o2m.js /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js
rm tmp_o2m.js

FILE=tmp_o2m1.js
if test -f "$FILE"; then
    rm tmp_o2m1.js
fi
O2M_BACKOFFICE_URI=${O2M_BACKOFFICE_URI:-'http://localhost:5011'}
sed "s/http:\/\/localhost:5011/$O2M_BACKOFFICE_URI/g" /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js > tmp_o2m1.js
cp tmp_o2m1.js /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js
rm tmp_o2m1.js
com
#Create Mysql
#rm -rf mysql_data

# Launch processes
#mopidy --config /etc/mopidy/mopidy.conf -vvv &
export GST_DEBUG=3
mopidy --config /etc/mopidy/mopidy.conf &

tail -f /dev/null

