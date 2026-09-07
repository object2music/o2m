#!/bin/bash
# Spike entrypoint for the Mopidy 4 candidate image.
# Differences from the Mopidy 3 entrypoint, all consequences of dropping Iris:
#   - no index.html / app.js / o2m.js / o2m.css copied into mopidy_iris/static
#   - no sed rewriting the API port and backoffice URI inside o2m.js
# The UI is o2m's own (served by the o2m Flask container), so mopidy only has to
# serve the JSON-RPC / websocket API and push audio.
set -e
bash create_conf_files4.sh
mkdir -p /root/.local/share/mopidy/spotify/credentials-cache
export GST_DEBUG=${GST_DEBUG:-3}
exec mopidy --config /etc/mopidy/mopidy.conf
