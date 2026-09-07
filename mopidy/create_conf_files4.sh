#!/bin/bash
# Mopidy 4 config. Dropped vs Mopidy 3: [iris] (extension gone), and the
# scrobbler / beets / IRControl sections that Mopidy 3 already warned about
# ("Ignoring config section ... no matching extension was found").
# [spotify] username/password are config.Deprecated() in mopidy-spotify 5.0 —
# left out so startup stays warning-free.
cat > /etc/mopidy/mopidy.conf << CONF
[core]
max_tracklist_length = 2000
restore_state = true

[audio]
output = $AUDIO_OUTPUT

[spotify]
enabled = true
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
allow_cache = true
youtube_dl_package = $YOUTUBE_DL_PACKAGE

[podcast]
enabled = $PODCAST_ENABLED
browse_root = $PODCAST_BROWSE_ROOT

[o2m]
enabled = true
api_url = http://o2m:${PORT_O2M_API:-6681}/api/
CONF
chmod 666 /etc/mopidy/mopidy.conf
echo "mopidy.conf created (Mopidy 4, no Iris)."
