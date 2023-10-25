#!/bin/bash

############## o2m.conf ##############

# Create the o2m.conf file
cat > o2m.conf << EOF

[spotipy]
spotipy_redirect_uri = $SPOTIPY_REDIRECT_URI
client_id_spotipy = $SPOTIPY_CLIENT_ID
client_secret_spotipy = $SPOTIPY_CLIENT_SECRET

[o2m]
discover = $O2M_DISCOVER
api_result_limit = $O2M_API_RESULT_LIMIT
shuffle = $O2M_SHUFFLE
default_volume = $O2M_DEFAULT_VOLUME
discover_level = $O2M_DISCOVER_LEVEL
podcast_newest_first = $O2M_PODCAST_NEWEST_FIRST
option_autofill_playlists = $O2M_OPTION_AUTOFILL_PLAYLISTS
option_add_reco_after_track = $O2M_OPTION_ADD_RECO_AFTER_TRACK

# mysql or sqlite
db_type = $DB_TYPE
db_username = $DB_USERNAME
db_password = $DB_PASSWORD
db_host = $DB_HOST
db_port = $DB_PORT
db_name = $DB_NAME

# Alternative for SQLite
# db_type = sqlite
# db_sqlite_path = $DB_SQLITE_PATH
EOF

echo "o2m.conf file created successfully."

# move the files to the correct location
#cp mopidy.conf /root/.config/mopidy/mopidy.conf
cp o2m.conf /etc/mopidy/o2m.conf

# TODO: put the correct permissions on the files
chmod 777 /etc/mopidy/o2m.conf
