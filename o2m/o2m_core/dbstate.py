"""Is the database answering? A verdict with a cadence, not a question per query.

An instance whose database is somewhere else — pi1 and pi2 read theirs over the
internet — has to answer a question no other part of o2m ever had to ask: *can
I reach it at all right now*. The answer cannot be asked per query, because the
expensive failure is the one that waits: a blackholed address takes the whole
connect timeout (measured on pi1: 5.0s at `connect_timeout=5`, the pymysql
default being 10), so a page that makes a dozen lookups would hang for a minute
before reporting what the first one already knew. A refused port and an
unresolvable name answer in 0.0s, which is the easy case and not the one to
design for.

So the verdict is cached and re-probed on a cadence:

- **up** is trusted outright. Nothing is probed while the database works, which
  is what keeps this free on every instance that has one locally.
- **down** is re-probed at most every `retry_s`, so a caller may ask in a loop
  and a dead database is tried once a cadence, not once a call.
- **unknown** probes at once: a process that has not yet asked must not report
  a degraded mode it never verified.

Only failures are reported in (`note_failure`), and only by code that has
actually caught one — a query that succeeds says so by itself, since a verdict
of up is never doubted until something fails. That asymmetry is deliberate: it
needs no hook in the hundreds of places that query.

Pure: no database, no network. `probe` is any callable raising on failure, which
is what makes this testable without either (`test_dbstate.py`).
"""

from __future__ import annotations

import time

# How long a "down" verdict stands before the next caller pays for a probe.
# Long enough that a page polling every second costs one probe a cadence,
# short enough that a link coming back is noticed within a box activation.
RETRY_S = 30


class DbState:
    """The database's reachability, as this process last observed it."""

    def __init__(self, probe, clock=time.monotonic, retry_s=RETRY_S):
        self.probe = probe
        self.clock = clock
        self.retry_s = max(1, float(retry_s))
        self._up = None                 # None: never asked
        self._probed_at = None
        self.failures = 0               # what a diagnostic reports

    # ── asking ───────────────────────────────────────────────────────────────

    def available(self):
        """Can the database be reached? Probes only when it must."""
        if self._up:
            return True
        now = self.clock()
        if (self._up is not None and self._probed_at is not None
                and now - self._probed_at < self.retry_s):
            return False                # still within the cadence: no probe
        return self._run_probe(now)

    def _run_probe(self, now):
        self._probed_at = now
        try:
            self.probe()
        except Exception as e:
            if self._up is not False:   # only the transition is worth a line
                print(f"[DB] unreachable, degraded mode: {str(e)[:120]}")
            self._up = False
            self.failures += 1
            return False
        if self._up is False:
            print("[DB] reachable again")
        self._up = True
        return True

    # ── telling ──────────────────────────────────────────────────────────────

    def note_failure(self, exc=None):
        """A query just failed: the verdict is down, and the cadence restarts.

        Called by code that CAUGHT the failure, so it is not re-probed to be
        confirmed — the caller's own query was the probe, and a better one than
        any this class could make.
        """
        if self._up is not False:
            print(f"[DB] unreachable, degraded mode: {str(exc)[:120]}"
                  if exc else "[DB] unreachable, degraded mode")
        self._up = False
        self._probed_at = self.clock()
        self.failures += 1

    def note_success(self):
        """A query just worked. Cheap to call and the only way a process that
        never probes learns the link is back."""
        if self._up is False:
            print("[DB] reachable again")
        self._up = True

    # ── reporting ────────────────────────────────────────────────────────────

    @property
    def degraded(self):
        """True only when the database is KNOWN to be away.

        Not the opposite of `available()`: this one never probes, so a status
        line, a log or a header can read it as often as it likes. Unknown reads
        as not degraded — claiming a degraded mode that was never verified
        would be a worse answer than saying nothing.
        """
        return self._up is False

    def state(self):
        return {'up': self._up, 'degraded': self.degraded,
                'failures': self.failures,
                'probed_s_ago': (None if self._probed_at is None
                                 else round(self.clock() - self._probed_at, 1))}
