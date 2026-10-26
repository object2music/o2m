"""The last Snapcast speaker leaving pauses the music.

Where the audio comes out decides what losing a browser means, and an instance
has one of two answers:

* **Snapcast** (Mopidy writes into the snap fifo): the sound reaches a room only
  through snapclients, and in practice through the browser pages that ARE those
  clients. When the last one goes — the browser closed for good, the phone off
  the network — the server keeps playing into a fifo nobody reads, and the next
  time someone listens the track has moved on by an hour. A page cannot say it
  is closing (its last JavaScript is not guaranteed to run, and a reload looks
  the same from inside), so this is watched from the server, where it is a plain
  fact: snapserver marks the client disconnected.
* **Local output** (a Pi playing to its own speakers): the browser is only a
  remote, and losing it must change nothing. The watcher is simply not started
  (`snap_output_enabled`), the same test that hides the Snapcast button.

A page in the BACKGROUND keeps its socket and stays a listener; only a real
departure counts. A Bluetooth cut is not a departure either — the OS re-routes
to the phone's speaker and the client stays connected; the page handles that one
itself (`pauseFromRouteLoss`).

Pure apart from `fetch_connected` and `run`: `ListenerWatch` takes counts and a
clock, which is what `test_snapwatch.py` drives.
"""

import json
import time
import urllib.request

POLL_S = 3
# A reload drops the socket and opens a new one within a second or two; a phone
# switching from Wi-Fi to mobile data, a few more. Pausing inside that window
# would stop the room on every refresh of the page.
GRACE_S = 10


def snap_output_enabled(audio_output):
    """Same rule as /api/client_config: Mopidy feeds snapserver."""
    a = (audio_output or '').lower()
    return 'snapfifo' in a or 'snapcast' in a


def connected_clients(status):
    """Ids of the clients snapserver currently reports as connected."""
    server = (status or {}).get('server') or {}
    out = set()
    for g in server.get('groups') or []:
        for c in g.get('clients') or []:
            if c.get('connected'):
                out.add(c.get('id'))
    return out


class ListenerWatch:
    """Decides when the room has gone silent for good.

    Fires once per departure: when at least one listener was there and none has
    been for `grace_s`. Never fires on an instance that never had a listener — a
    server played from a page used purely as a remote is not this case's business.
    """

    def __init__(self, grace_s=GRACE_S):
        self.grace_s = grace_s
        self.had_listener = False
        self.empty_since = None

    def observe(self, n_connected, now):
        if n_connected > 0:
            self.had_listener = True
            self.empty_since = None
            return False
        if not self.had_listener:
            return False
        if self.empty_since is None:
            self.empty_since = now
            return False
        if now - self.empty_since >= self.grace_s:
            self.had_listener = False      # once; the next listener re-arms it
            self.empty_since = None
            return True
        return False


def fetch_connected(url, timeout=5):
    """The connected client ids, or None when snapserver did not answer — a
    snapserver we cannot reach says nothing about who is listening."""
    body = json.dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'Server.GetStatus'}).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return connected_clients(json.load(r).get('result'))
    except Exception:
        return None


def run(url, get_state, pause, poll_s=POLL_S, grace_s=GRACE_S, log=print):
    """Loop for ever: pause the server when its last listener has gone."""
    watch = ListenerWatch(grace_s)
    last = None
    while True:
        ids = fetch_connected(url)
        if ids is not None:
            if last is not None and len(ids) != len(last):
                log(f"[snapwatch] listeners {len(last)} → {len(ids)}")
            last = ids
            if watch.observe(len(ids), time.monotonic()):
                try:
                    if get_state() == 'playing':
                        log("[snapwatch] last Snapcast listener gone → pausing")
                        pause()
                except Exception as e:
                    log(f"[snapwatch] pause failed: {e}")
        time.sleep(poll_s)
