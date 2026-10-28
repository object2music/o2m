#!/usr/bin/env python3
"""Restart Mopidy when it came up without Spotify (see o2m_core/mopidywatch.py).

Installed on a native instance (a Raspberry Pi) as a systemd oneshot beside its
timer; the companion `mopidy-watchdog.sh` watches a different fault — a core that
stopped answering at all — and the two are kept apart on purpose, since one
restarts a hung Mopidy and this one a Mopidy that answers perfectly well and
simply has no Spotify.

It is deliberately dull: it reads Mopidy's own journal for the running process,
checks the network is back, and restarts at most three times an hour. It never
asks Spotify anything — the request quota is shared by every instance of the
installation, and the state it is looking for is latched per process anyway.

Run as root (it restarts a unit). All decisions are in `mopidywatch.decide`.
"""

import json
import os
import socket
import subprocess
import sys
import time

REPO = os.environ.get('O2M_REPO', '/home/pi/o2m/o2m')
sys.path.insert(0, REPO)

from o2m_core import mopidywatch as mw            # noqa: E402

UNIT = os.environ.get('MOPIDY_UNIT', 'mopidy.service')
STATE = os.environ.get('WATCHDOG_STATE', '/run/mopidy-spotify-watchdog.json')
# What "the network is back" means here: the host mopidy-spotify could not
# reach. Nothing is sent — a TCP connect is enough to tell an outage from an
# account problem, and it costs no request.
REACH_HOST = ('auth.mopidy.com', 443)
REACH_TIMEOUT = 5


def sh(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout
    except Exception as e:
        log(f"{args[0]} failed: {e}")
        return ''


def log(msg):
    print(msg, flush=True)
    subprocess.run(['logger', '-t', 'mopidy-spotify-watchdog', msg],
                   capture_output=True)


def unit_facts():
    """(main pid, seconds since the unit went active). (0, 0) when it is not."""
    out = sh('systemctl', 'show', UNIT, '-p', 'ActiveState',
             '-p', 'MainPID', '-p', 'ActiveEnterTimestampMonotonic')
    f = dict(l.split('=', 1) for l in out.splitlines() if '=' in l)
    if f.get('ActiveState') != 'active':
        return 0, 0
    pid = int(f.get('MainPID') or 0)
    # systemd's monotonic stamp and time.monotonic() are the same clock on
    # Linux: microseconds since boot.
    started = int(f.get('ActiveEnterTimestampMonotonic') or 0) / 1e6
    return pid, max(0.0, time.monotonic() - started) if started else 0.0


def network_ok():
    try:
        with socket.create_connection(REACH_HOST, timeout=REACH_TIMEOUT):
            return True
    except OSError:
        return False


def recent_restarts(now):
    """When we restarted lately, within the window. Counted over TIME and not
    per process: a restart makes a new PID, so counting against the PID would
    reset on the very event being counted."""
    try:
        with open(STATE, encoding='utf-8') as f:
            stamps = json.load(f).get('restarts') or []
    except (OSError, ValueError):
        return []
    return [t for t in stamps if isinstance(t, (int, float))
            and now - t < mw.ATTEMPT_WINDOW_S]


def note_restart(stamps, now):
    try:
        with open(STATE, 'w', encoding='utf-8') as f:
            json.dump({'restarts': stamps + [now]}, f)
    except OSError as e:
        log(f"cannot write {STATE}: {e}")


def main():
    pid, uptime = unit_facts()
    if not pid:
        return 0                       # not running: not this watchdog's business
    journal = sh('journalctl', f'_PID={pid}', '--no-pager', '-o', 'cat')
    verdict = mw.spotify_verdict(journal)
    now = time.time()
    stamps = recent_restarts(now)
    # The network is only asked about when the answer can change what we do —
    # it is the one step here that leaves the machine.
    net = network_ok() if verdict == 'dead' and uptime >= mw.GRACE_S else True
    action, why = mw.decide(verdict, uptime, net, len(stamps))
    if action == 'none':
        return 0                       # the quiet case: say nothing, every 2 min
    log(f"{action}: {why}")
    if action == 'restart':
        note_restart(stamps, now)
        sh('systemctl', 'restart', UNIT)
        log('Mopidy restarted to recover Spotify')
    return 0


if __name__ == '__main__':
    sys.exit(main())
