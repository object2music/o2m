#!/bin/bash
# Spike entrypoint for the Mopidy 4 candidate image.
# No Iris here, so nothing to patch into it: the Mopidy 3 entrypoint used to
# copy index.html / app.js / o2m.js / o2m.css into mopidy_iris/static and sed the
# API port into o2m.js. All of that, and the image that did it, is deleted. The
# UI is o2m's own (served by the o2m Flask container), so mopidy only has to
# serve the JSON-RPC / websocket API and push audio.
set -e
bash create_conf_files4.sh
mkdir -p /root/.local/share/mopidy/spotify/credentials-cache
export GST_DEBUG=${GST_DEBUG:-3}
exec mopidy --config /etc/mopidy/mopidy.conf
