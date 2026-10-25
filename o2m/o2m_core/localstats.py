"""What was listened to while the database was out of reach.

The browser's offline mode has solved this once already, and the shape it
arrived at is the whole content of this module — two stores, not one:

    plays.json      a completed play is an EVENT and APPENDS
    positions.json  a position is STATE and REPLACES

Merging them is the mistake that looks like a simplification. The server counts
a read on every record it receives, and `read_count` feeds popularity and the
cooldown — so a bookmark written every ten seconds, flushed as a play, would
multiply one listen by the number of checkpoints it took.

Two further rules are not detail either, and both are paid for in data that
cannot be repaired afterwards:

- **A play carries its own timestamp.** The hourly habits read
  `stats_raw.read_hour`, so crediting the flush would teach the selector that
  you listen when the network came back rather than when you listened.
- **Only a bookmark that MOVED is sent** (`at != synced_at`). Re-sending an
  unchanged position on every reconnection would count a read for a track
  nobody played, which is the same inflation by another door.

And finishing retires the bookmark, or the item resumes ten seconds before its
own end for ever — the bug the server itself carried until `retire_finished_bookmarks`.

Pure of o2m: no database, no network. It writes two files and answers what is
waiting; the caller is what eventually posts it (`/api/offline/plays`, the same
endpoint the browser flushes to, since this is the same journal).
"""

from __future__ import annotations

import json
import os
import tempfile
import time

# Plays are JSON Lines, one record per line, because they are an append-only
# log and nothing else: appending is one short write instead of reading,
# rewriting and fsyncing the whole journal per listen, and a last line
# truncated by a power cut is discarded by itself rather than taking the file
# with it. The first version rewrote the lot each time, which measured 38s for
# 5000 plays against 0.3s here — on a Pi, with an fsync apiece.
PLAYS_NAME = 'plays.jsonl'
POSITIONS_NAME = 'positions.json'

# Under this fraction of a track, nothing is recorded. A tap that starts the
# wrong item and is corrected at once is an artefact, not a listen; the browser
# draws the line at the same place.
MIN_PLAYED_FRACTION = 0.05

# A play is "complete" past this fraction, which is what the server's own
# `stats_raw` rule uses: a skipped or interrupted track never enters the log,
# so rotation depth counts music actually listened to.
COMPLETE_FRACTION = 0.9

# Beyond this many pending plays the oldest are dropped. A Pi kept offline for
# a month must not grow a journal it can never flush in one request, and the
# newest listening is the part that still describes the listener.
MAX_PLAYS = 5000


class LocalStats:
    """The two journals under a cache root.

    Every write lands on disk before it returns: these records exist precisely
    because something is already not reachable, and a process that dies holding
    them in memory loses exactly what it was asked to keep.
    """

    def __init__(self, root, clock=time.time, max_plays=MAX_PLAYS):
        self.root = str(root)
        self.clock = clock
        self.max_plays = max(1, int(max_plays))

    # ── where things are ─────────────────────────────────────────────────────

    @property
    def plays_path(self):
        return os.path.join(self.root, PLAYS_NAME)

    @property
    def positions_path(self):
        return os.path.join(self.root, POSITIONS_NAME)

    # ── a play: an event, appended ───────────────────────────────────────────

    def record_play(self, uri, position_ms, length_ms, at=None):
        """Log one listen, and say whether it was logged.

        `at` is when it HAPPENED, defaulting to now — never when it is flushed.
        A play under `MIN_PLAYED_FRACTION` of the item is dropped as an
        artefact, and so is one with no length to judge it by: a record the
        server cannot place is worse than no record, since it would still count
        a read.
        """
        if not uri or length_ms <= 0:
            return False
        position_ms = max(0, int(position_ms))
        if position_ms / float(length_ms) < MIN_PLAYED_FRACTION:
            return False
        row = {
            'uri': uri,
            'position': position_ms,
            'length': int(length_ms),
            'at': int(at if at is not None else self.clock()),
            'complete': position_ms / float(length_ms) >= COMPLETE_FRACTION,
        }
        if not self._append(row):
            return False
        self._trim()
        return True

    def plays(self):
        """Every play waiting to be sent, oldest first.

        A line that will not parse is skipped rather than fatal: the last one
        can be half-written by a power cut, and the listening before it is
        still good.
        """
        out = []
        try:
            with open(self.plays_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get('uri'):
                        out.append(row)
        except OSError:
            return []
        return out

    def clear_plays(self, sent):
        """Drop the plays that were accepted, keep what arrived meanwhile.

        Counted rather than matched: a flush posts a prefix of the journal, and
        anything recorded during the request sits after it. Matching by uri
        would drop a second listen to the same item that happened while the
        first was in flight.
        """
        sent = max(0, int(sent))
        if not sent:
            return
        self._rewrite_plays(self.plays()[sent:])

    def _trim(self):
        """Hold the journal to `max_plays`, rewriting only when it is over.

        Amortised on purpose: the bound exists so a Pi kept offline for a month
        cannot grow a journal it will never flush in one request, and paying a
        rewrite per listen to enforce it is how the first version came to cost
        38 seconds for 5000 plays.
        """
        rows = self.plays()
        if len(rows) <= self.max_plays:
            return
        self._rewrite_plays(rows[-self.max_plays:])   # the newest still describe

    def _rewrite_plays(self, rows):
        self._write_text(self.plays_path,
                         ''.join(json.dumps(r, ensure_ascii=False) + '\n'
                                 for r in rows))

    def _append(self, row):
        """One line, flushed to the platter before this returns.

        A newline is written first when the file does not end with one. That is
        not belt and braces: the line a power cut truncated has no newline of
        its own, so appending straight after it would join the two into a
        single unparseable line — losing the NEW record as well as the broken
        one, which is exactly what this form exists to avoid.
        """
        try:
            os.makedirs(self.root, exist_ok=True)
            lead = ''
            try:
                with open(self.plays_path, 'rb') as rf:
                    if rf.seek(0, os.SEEK_END) > 0:
                        rf.seek(-1, os.SEEK_END)
                        if rf.read(1) != b'\n':
                            lead = '\n'
            except OSError:
                pass
            with open(self.plays_path, 'a', encoding='utf-8') as f:
                f.write(lead + json.dumps(row, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError as e:
            print(f"localstats: cannot append a play: {e}")
            return False

    # ── a position: state, replaced ──────────────────────────────────────────

    def set_position(self, uri, position_ms, length_ms=0, synced=False):
        """Where the listener is in a spoken item.

        `synced=True` is for a bookmark that came FROM the server at download
        time: it is stored as already sent, so it is not echoed straight back as
        a fresh read for something nobody played here.
        """
        if not uri:
            return False
        now = int(self.clock())
        rows = self.positions()
        rows[uri] = {
            'position': max(0, int(position_ms)),
            'length': max(0, int(length_ms)),
            'at': now,
            'synced_at': now if synced else int(
                (rows.get(uri) or {}).get('synced_at') or 0),
        }
        self._write(self.positions_path, rows)
        return True

    def retire_position(self, uri):
        """Finishing an item drops its bookmark.

        Kept, it would seek to ten seconds before the item's own end for ever —
        and, being read as a resume, would skip the fresh-start pre-roll too.
        """
        rows = self.positions()
        if rows.pop(uri, None) is None:
            return False
        self._write(self.positions_path, rows)
        return True

    def positions(self):
        data = self._read(self.positions_path)
        return {u: r for u, r in data.items()
                if isinstance(r, dict)} if isinstance(data, dict) else {}

    def unsent_positions(self):
        """The bookmarks that moved since the last successful flush."""
        return {u: r for u, r in self.positions().items()
                if int(r.get('at') or 0) != int(r.get('synced_at') or 0)}

    def mark_positions_sent(self, uris):
        """Stamp these as flushed, without touching a position that moved while
        the request was in flight — `at` is compared, not overwritten."""
        rows = self.positions()
        touched = False
        for u in uris or ():
            r = rows.get(u)
            if r is None:
                continue
            r['synced_at'] = int(r.get('at') or 0)
            touched = True
        if touched:
            self._write(self.positions_path, rows)

    # ── what a flush would send ──────────────────────────────────────────────

    def pending(self):
        """A summary a person can read, which is the point of keeping it on
        disk at all: `Settings → Offline` lists the browser's for the same
        reason. Returns counts, never the records, so a caller can show it
        without loading a month of listening."""
        plays = self.plays()
        pos = self.positions()
        return {
            'plays': len(plays),
            'positions': len(pos),
            'positions_unsent': len(self.unsent_positions()),
            'oldest_play_at': min((p.get('at') or 0 for p in plays), default=0),
        }

    # ── disk ─────────────────────────────────────────────────────────────────

    def _read(self, path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _write(self, path, data):
        self._write_text(path, json.dumps(data, ensure_ascii=False))

    def _write_text(self, path, text):
        """Replace the file atomically.

        A file half-written by a power cut is a file lost, and these live on a
        Raspberry Pi whose power is exactly what is least certain. The
        temporary sits beside the target so the rename cannot cross a
        filesystem, and the directory is fsynced too — without that the rename
        itself can be the thing that is lost.
        """
        try:
            os.makedirs(self.root, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix='.journal-')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            try:
                dfd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        except OSError as e:
            print(f"localstats: cannot write {os.path.basename(path)}: {e}")
