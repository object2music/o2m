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

mopidy = MopidyClient()
#mopidy.bind_event('track_playback_started', print_track_info)
#mopidy.playback.next()
#mopidy.playback.get_volume()

mopidy.tracklist.add()

presets = ['spotify:track:28cnXtME493VX9NOw9cIUh','local:track:0-MK/MK%2090/01.%20I%20Won%27t%20Back%20Down.mp3']
mopidy.tracklist.add(uris=presets)


if __name__ == '__main__':

    # Main loop
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
