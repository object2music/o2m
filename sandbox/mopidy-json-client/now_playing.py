#!/usr/bin/python
#Installed from pip3 install https://github.com/ismailof/mopidy-json-client/archive/master.zip

import time
from mopidy_json_client import MopidyClient

def print_track_info(tl_track):
    track = tl_track.get('track') if tl_track else None
    if not track:
        print ('No Track')
        return

    trackinfo = {
        'name': track.get('name'),
        'artists': ', '.join([artist.get('name') for artist in track.get('artists')])
    }
    print('Now playing: {artists} - {name}'.format(**trackinfo))

def print_tracklist_info():
    print('Tracklist changed!')

mopidy = MopidyClient()
mopidy.bind_event('track_playback_started', print_track_info)
mopidy.bind_event('tracklist_changed', print_tracklist_info)
#mopidy.playback.next()
#mopidy.playback.get_volume()

mopidy.tracklist.clear()

presets = ['spotify:track:4evj46yiEKdN8gr6K0e7PX', 'local:track:ah.mp3']
response = mopidy.tracklist.add(uris=presets)

mopidy.playback.play()

if __name__ == '__main__':

    # Main loop
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
