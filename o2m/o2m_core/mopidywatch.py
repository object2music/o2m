"""A Mopidy that started without Spotify stays without it, silently.

mopidy-spotify loads the account's profile once, at backend start. When that
fails — and the ordinary cause is simply that the machine had no network at
that second — the backend latches: it answers `[]` to every `spotify:` lookup
and logs `Spotify search aborted: Spotify is offline` for the whole life of the
process. Nothing retries, and **nothing reports it**.

Measured on pi1 (2026-10-28). Mopidy started at 23:49 the night before, during
one of that machine's network drops:

    ERROR mopidy_spotify.web Retrying https://auth.mopidy.com/spotify/token …
    ERROR mopidy_spotify.web OAuth token refresh failed: Unknown error.
    ERROR mopidy_spotify.web Failed to load Spotify user profile

Twenty-two hours later every bucket of the AUTO mix added nothing —
`AUTO: 1 tracks queued for a target of 30` — because every bucket at DL 0 is
Spotify tracks and Mopidy returned nothing for all of them. The one track that
played came from the machine's own offline cache. The symptom is not an error
anywhere: it is a fill that quietly queues one track for thirty, which is why
this needs watching rather than reading.

**What this does NOT do: poll Spotify.** The state is latched per PROCESS, so
asking twice a minute would learn nothing a single question does not answer, and
would spend the Spotify request quota — which is shared by every instance of the
installation and has already stopped the whole app for seventeen hours once. The
question is asked once per Mopidy process, and the answer comes from Mopidy's own
journal, which is free, local, needs no network and is the authority.

Pure: `spotify_verdict` and `decide` take text and numbers. The gathering and the
restart live in `samples/mopidy-spotify-watchdog.py`, and `test_mopidywatch.py`
drives everything that decides.
"""

from __future__ import annotations

# mopidy-spotify's own words. One of the first two means the backend came up
# with an account; the others mean it did not. Matched as substrings so a
# version that adds detail around them still reads.
ALIVE_MARKS = (
    'Logged into Spotify Web API as',
    'Logged in to Spotify',
)
DEAD_MARKS = (
    'Failed to load Spotify user profile',
    'OAuth token refresh failed',
    'Spotify is offline',
)

# Mopidy logged its Spotify verdict 3s after start when it worked and 12s after
# when it failed, so this is not about the backend: it is about not acting on a
# process that may still be settling, and about leaving the playlist background
# refresh alone.
GRACE_S = 120

# A revoked token, a changed password, an account problem: all look exactly like
# a network blip from here, and none is cured by restarting. Three cuts into
# whatever is playing is already more than the problem is worth, so after that
# it says so and holds.
MAX_ATTEMPTS = 3

# `attempts` is counted over a WINDOW, never per process, and that is the one
# thing easy to get wrong here: a restart makes a new PID, so a counter kept
# against the PID resets on the very event it is meant to be counting and the
# cap caps nothing. An hour also forgives by itself — a blip tonight must not
# leave the machine refusing to repair itself next week.
ATTEMPT_WINDOW_S = 3600


def spotify_verdict(journal):
    """`'alive'` | `'dead'` | `'unknown'` for one Mopidy process's log.

    The LAST decisive line wins, not the first: mopidy-spotify retries its token
    around startup, and a success after a failure means the backend has an
    account. `'unknown'` is a real answer and the common one — a log that says
    nothing about Spotify (the extension disabled, a version that words it
    differently, a journal already rotated) must lead to doing nothing at all.
    """
    verdict = 'unknown'
    for line in (journal or '').splitlines():
        if any(m in line for m in ALIVE_MARKS):
            verdict = 'alive'
        elif any(m in line for m in DEAD_MARKS):
            verdict = 'dead'
    return verdict


def decide(verdict, uptime_s, network_ok, attempts,
           grace_s=GRACE_S, max_attempts=MAX_ATTEMPTS):
    """What to do about it: `('restart'|'wait'|'give-up'|'none', why)`.

    Only an explicit `dead` acts. Every other branch holds, and each holds for a
    reason worth keeping separate in the log, because they are the four ways
    this can be wrong: too early, no network, already tried, nothing wrong.
    """
    if verdict != 'dead':
        return 'none', f"Spotify reads {verdict}"
    if uptime_s < grace_s:
        return 'wait', f"Mopidy is {int(uptime_s)}s old, under the {grace_s}s grace"
    if not network_ok:
        # Restarting into the same outage would cut the music for nothing and
        # burn an attempt on a cause that has not gone away.
        return 'wait', 'no network: a restart would land in the same place'
    if attempts >= max_attempts:
        return 'give-up', (f"Spotify still absent after {attempts} restart(s): "
                           f"this is not the network — check the account")
    return 'restart', f"Spotify absent on a reachable network (attempt {attempts + 1})"
