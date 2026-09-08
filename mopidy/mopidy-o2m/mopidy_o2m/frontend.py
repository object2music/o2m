"""Mopidy frontend that pushes playback events to the O2M API.

Why this exists
---------------
O2M's brain lives in the o2m service, not here, and it needs three playback
events to do its work: `track_playback_started` (resume a spoken item, skip the
pre-roll, duck the volume), `track_playback_ended` and `track_playback_paused`
(write stats, add recommendations, refill the tracklist when it runs dry).

Until now it received them over a websocket, as a `mopidyapi` client. That
transport cost three separate rounds of workarounds — a thread leak that
exhausted a 32-bit address space, a handshake that never reconnected, and
Mopidy 4 renaming the model marker from `__model__` to `model` in the event
stream only. Every one of them failed the same way: playback kept working while
stats and refill silently stopped.

A frontend receives the events **in-process**, as method calls. No socket, no
reconnection, no deserialisation, so none of those failure modes exist. What is
left is one HTTP POST to the o2m API, which either works or returns an error we
can see.

Deliberate boundary
-------------------
This is an adapter, never the seat of the logic: it translates a Mopidy event
into an HTTP call and stops there. Everything else stays in the o2m service, so
a second facade (a Home Assistant integration, say) can be a client of the same
API rather than a client of Mopidy. Nothing here may import Mopidy-Iris.

Note that the o2m side only dispatches these when it is configured to take
events over HTTP; otherwise it accepts and ignores them, and its websocket
listener stays authoritative. That makes the switch — and the rollback — a
one-variable change on the o2m side, with no plugin rebuild.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.request

import pykka
from mopidy import core

logger = logging.getLogger(__name__)

# Bounded so a wedged API can never grow the queue without limit. Playback
# events arrive at human pace, so this is minutes of backlog, not seconds.
_QUEUE_MAX = 100
_POST_TIMEOUT = 5


class O2mFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config, core):
        super().__init__()
        self.core = core
        self._api_url = config["o2m"]["api_url"].rstrip("/") + "/"
        self._enabled = config["o2m"]["forward_events"]
        self._queue = queue.Queue(maxsize=_QUEUE_MAX)
        self._worker = None
        # Logged once, on the first send that the o2m side actually acted on,
        # so the transport in use is visible without turning on debug logging.
        self._announced = False

    def on_start(self):
        if not self._enabled:
            logger.info("O2M: event forwarding disabled (forward_events = false)")
            return
        self._worker = threading.Thread(
            target=self._drain, name="o2m-event-sender", daemon=True
        )
        self._worker.start()
        logger.info("O2M: forwarding playback events to %sevent", self._api_url)

    def on_stop(self):
        # Sentinel rather than a flag: it also wakes the worker out of its
        # blocking get() immediately.
        if self._worker:
            self._queue.put(None)

    # --- Mopidy events (called on the actor thread — never block here) -------

    def track_playback_started(self, tl_track):
        self._enqueue("track_playback_started", tl_track, None)

    def track_playback_ended(self, tl_track, time_position):
        self._enqueue("track_playback_ended", tl_track, time_position)

    def track_playback_paused(self, tl_track, time_position):
        self._enqueue("track_playback_paused", tl_track, time_position)

    # --- internals ----------------------------------------------------------

    def _enqueue(self, name, tl_track, time_position):
        if not self._enabled or tl_track is None:
            return
        track = tl_track.track
        # Exactly the six fields the o2m handlers read off the event. Kept
        # explicit rather than dumping the model, so the contract is visible
        # here and a Mopidy-side model change cannot silently reshape it.
        payload = {
            "event": name,
            "time_position": time_position,
            "tl_track": {
                "tlid": tl_track.tlid,
                "track": {
                    "uri": track.uri,
                    "name": track.name,
                    "length": track.length,
                    "track_no": track.track_no,
                },
            },
        }
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            # Dropping is the right failure here: blocking would stall playback
            # to protect a statistic.
            logger.warning("O2M: event queue full, dropped %s", name)

    def _drain(self):
        while True:
            payload = self._queue.get()
            if payload is None:
                return
            try:
                self._post(payload)
            except Exception:
                logger.exception("O2M: failed to forward %s", payload["event"])

    def _post(self, payload):
        req = urllib.request.Request(
            f"{self._api_url}event",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_POST_TIMEOUT) as resp:
                body = json.loads(resp.read().decode() or "{}")
        except urllib.error.URLError as e:
            logger.warning("O2M: %s not delivered (%s)", payload["event"], e)
            return
        if body.get("dispatched") and not self._announced:
            self._announced = True
            logger.info("O2M: the API is taking playback events over HTTP")
