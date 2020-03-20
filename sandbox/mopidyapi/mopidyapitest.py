'''
    dépot et documentation de la librairie : 
        https://github.com/AsbjornOlling/mopidyapi

    pip3 install mopidyapi
'''
from mopidyapi import MopidyAPI
import time

START_BOLD = '\033[1m'
END_BOLD = '\033[0m'

m = MopidyAPI()
tracks = m.tracklist.get_tracks()
# print(tracks[0].name)

m.tracklist.clear()


presets = ['spotify:track:4evj46yiEKdN8gr6K0e7PX', 'local:track:ah.mp3', 'tunein:station:s15200']
response = m.tracklist.add(uris=presets)

m.playback.play()

# Liste des evenements : https://docs.mopidy.com/en/latest/api/core/#core-events
@m.on_event('track_playback_started')
def print_newtracks(event):
    print(f"Started playing track: {event.tl_track.track.name}")

@m.on_event('track_playback_paused')
def print_paused_events(event):
    print(f"Paused song : {START_BOLD}{event.tl_track.track.name}{END_BOLD} at : {START_BOLD}{event.time_position}{END_BOLD} ms")

m.playback.next()

time.sleep(1.4)

m.playback.pause()

if __name__ == '__main__':

    # Main loop
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
