#Installed from pip3 install https://github.com/ismailof/mopidy-json-client/archive/master.zip
from mopidy_json_client import MopidyClient

mopidy = MopidyClient()
mopidy.bind_event('track_playback_started', print_track_info)
mopidy.playback.play()