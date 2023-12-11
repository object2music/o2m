#!/bin/bash

############## mopidy.conf ##############
# Create the mopidy.conf file
cat > mopidy.conf << EOF
[core]
max_tracklist_length =2000
restore_state = true

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

[http]
enabled = $HTTP_ENABLED
hostname = $HTTP_HOSTNAME
port = $HTTP_PORT
allowed_origins = $ALLOWED_ORIGINS
csrf_protection = $CSRF_PROTECTION
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


# move the files to the correct location
cp mopidy.conf /etc/mopidy/mopidy.conf
chmod 777 /etc/mopidy/mopidy.conf