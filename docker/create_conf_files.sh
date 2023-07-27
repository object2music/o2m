#!/bin/bash

############## mopidy.conf ##############
# Create the mopidy.conf file
cat > mopidy.conf << EOF
[logging]
config_file = /etc/mopidy/logging.conf
debug_file = /var/log/mopidy/mopidy-debug.log

[audio]
output = $AUDIO_OUTPUT

[spotify]
username = $SPOTIFY_USERNAME
password = $SPOTIFY_PASSWORD
client_id = $SPOTIFY_CLIENT_ID
client_secret = $SPOTIFY_CLIENT_SECRET

[spotipy]
spotipy_redirect_uri = $SPOTIPY_REDIRECT_URI
client_id_spotipy = $SPOTIPY_CLIENT_ID
client_secret_spotipy = $SPOTIPY_CLIENT_SECRET

[http]
enabled = $HTTP_ENABLED
hostname = $HTTP_HOSTNAME
port = $HTTP_PORT

[mpd]
hostname = $MPD_HOSTNAME

[file]
enabled = $FILE_ENABLED
media_dirs = $FILE_MEDIA_DIRS

[local]
enabled = $LOCAL_ENABLED
media_dir = $LOCAL_MEDIA_DIR

[youtube]
enabled = $YOUTUBE_ENABLED
youtube_api_key = $YOUTUBE_API_KEY
api_enabled = $YOUTUBE_API_ENABLED

[podcast]
enabled = $PODCAST_ENABLED
browse_root = $PODCAST_BROWSE_ROOT

[scrobbler]
username = $SCROBBLER_USERNAME
password = $SCROBBLER_PASSWORD

[beets]
enabled = $BEETS_ENABLED
hostname = $BEETS_HOSTNAME
port = $BEETS_PORT

[IRControl]
enabled = $IRCONTROL_ENABLED
mute = $IRCONTROL_MUTE
next = $IRCONTROL_NEXT
previous = $IRCONTROL_PREVIOUS
playpause = $IRCONTROL_PLAYPAUSE
stop = $IRCONTROL_STOP
volumeup = $IRCONTROL_VOLUMEUP
volumedown = $IRCONTROL_VOLUMEDOWN
EOF

echo "mopidy.conf file created successfully."



############## o2m.conf ##############

# Create the o2m.conf file
cat > o2m.conf << EOF
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
cp mopidy.conf /etc/mopidy/mopidy.conf
#cp mopidy.conf /root/.config/mopidy/mopidy.conf
cp o2m.conf /etc/mopidy/o2m.conf

# TODO: put the correct permissions on the files
chmod 777 /etc/mopidy/o2m.conf
chmod 777 /etc/mopidy/mopidy.conf