from mopidy_json_client import MopidyClient

mopidy = MopidyClient()
mopidy.bind_event('track_playback_started', print_track_info)
mopidy.playback.play()