"""Play the offline cache with no database and no network.

Everywhere else in o2m, deciding what to play starts with a query: the box, its
lines, the tracks, their popularity and their mood. On an instance whose
database is somewhere else — pi1 and pi2 read theirs over the internet — that
makes holding every byte useless the moment the link goes: the base is what
says which boxes exist and what they hold.

The cache already answers both, on the disk, for anyone who reads it:

    cache/index.json                         what each item IS, keyed by uri
    cache/Boxes/Auto music [04AD…]/All.m3u8  what a box holds, in order
    cache/Boxes/Auto music [04AD…]/Favorites.m3u8          one of its sources
    cache/Boxes/Auto music [04AD…]/Chansons [04D4…]/All.m3u8   an included box

and **the NFC uid is in the folder name**, so a tag put down resolves to a
playlist without asking anything. That is the whole mechanism; this module is
only its reader.

**What it deliberately cannot do.** An inventory holds what it takes to PLAY an
item, never what it takes to CHOOSE one — there is no popularity here, no
energy/valence, no play history, no cooldown. So this plays a selection the
server made earlier, in the order it was written, exactly as the browser's
offline mode replays a tracklist rather than running the engine. Calling that
"offline" is honest about the bytes and dishonest about the choosing, which is
why the degraded order is the view's own and not a pretend sampler.

Pure of o2m: no database, no network, no Mopidy. The filesystem and the clock
are the only things it touches, which is what makes it testable without any of
them (`test_localcache.py`).
"""

from __future__ import annotations

import json
import os
import posixpath
import random
import re

from o2m_core import cachelayout

INDEX_NAME = 'index.json'
M3U8 = '.m3u8'

# A spoken item resumes `RESUME_LEAD_MS` before where it was left, the same
# ten seconds the server gives back (`track_started_event`): a sentence cut in
# half is worth hearing again, and landing exactly on the cut sounds like a
# fault.
RESUME_LEAD_MS = 10_000


class Entry:
    """One playable line of a view: a file, and what is known about it.

    `uri` is the canonical uri when the index names this file, '' otherwise —
    and '' is a normal answer, not a failure: a file whose index row is missing
    still plays, with the title and length the `#EXTINF` carries. Nothing here
    may require the index, or the degraded mode would depend on the very
    freshness it exists to do without.
    """

    __slots__ = ('file', 'uri', 'title', 'seconds', 'kind', 'cat', 'position',
                 'ad_skip', 'volume_boost', 'finished', 'liked')

    def __init__(self, file, uri='', title='', seconds=0, kind='music', cat='',
                 position=0, ad_skip=0, volume_boost=0, finished=False,
                 liked=False):
        self.file = file
        self.uri = uri
        self.title = title
        self.seconds = seconds
        self.kind = kind
        self.cat = cat
        self.position = position
        self.ad_skip = ad_skip
        self.volume_boost = volume_boost
        self.finished = finished
        self.liked = liked

    @property
    def spoken(self):
        return self.kind == 'spoken'

    def start_ms(self):
        """Where playback should begin, in ms.

        The server's own rule, and the two halves of it are not symmetrical: a
        spoken item resumes a little before its bookmark, and a fresh start
        skips the channel's pre-roll instead. Music always starts at zero — a
        music track played to the end carries `read_position == its duration`,
        so honouring it would restart every favourite at its last note.
        """
        if not self.spoken:
            return 0
        if self.position > 0:
            return max(0, self.position - RESUME_LEAD_MS)
        return max(0, self.ad_skip)

    def __repr__(self):                                     # pragma: no cover
        return f"<Entry {self.title or os.path.basename(self.file)!r}>"


class Box:
    """A box as the disk knows it: a uid, a label and a folder under Boxes/."""

    __slots__ = ('uid', 'label', 'rel')

    def __init__(self, uid, label, rel):
        self.uid = uid
        self.label = label
        self.rel = rel              # posix path under Boxes/, '' for none

    @property
    def name(self):
        return self.label or self.uid

    def __repr__(self):                                     # pragma: no cover
        return f"<Box {self.uid} {self.label!r}>"


class LocalCache:
    """The cache root, read as a playable thing.

    `root` is the same directory `SPOTDL_CACHE_DIR` names — `<media_dir>/cache`.
    Every path handed out is absolute, so a caller never has to know this
    layout; every path read is relative, so the tree stays portable.
    """

    def __init__(self, root, rng=None):
        self.root = os.path.realpath(str(root))
        self.rng = rng or random
        self._index = None
        self._index_stamp = None

    # ── the inventory ────────────────────────────────────────────────────────

    @property
    def boxes_dir(self):
        return os.path.join(self.root, cachelayout.BOXES)

    def index(self):
        """`{uri: row}` from `index.json`, re-read when the file moves.

        A missing or broken index is an empty one, never an error: the views
        remain playable without it. It is written by whichever instance prunes
        the cache, so on a shared disk it can be a little behind — which costs
        a resume position, not a track.
        """
        path = os.path.join(self.root, INDEX_NAME)
        try:
            stamp = os.stat(path).st_mtime_ns
        except OSError:
            self._index, self._index_stamp = {}, None
            return self._index
        if self._index is not None and stamp == self._index_stamp:
            return self._index
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f) or {}
            items = data.get('items') or {}
            self._index = {u: r for u, r in items.items() if isinstance(r, dict)}
        except (OSError, ValueError):
            self._index = {}
        self._index_stamp = stamp
        return self._index

    def _by_path(self):
        """`{path relative to the root: (uri, row)}` — how a view's line, which
        names a file and not a uri, finds what it is."""
        out = {}
        for uri, row in self.index().items():
            rel = _norm(row.get('path'))
            if rel:
                out[rel] = (uri, row)
        return out

    # ── the boxes ────────────────────────────────────────────────────────────

    def boxes(self):
        """Every box the disk holds, including those included by another.

        Returned deepest-last, so a caller listing them sees the outer ones
        first. A folder that is not a box folder (a source's `.m3u8` lives
        beside them) is skipped by `parse_box_folder` returning no uid.
        """
        found, seen = [], set()
        base = self.boxes_dir
        if not os.path.isdir(base):
            return found
        for dirpath, dirnames, _files in os.walk(base):
            dirnames.sort()
            if dirpath == base:
                continue
            rel = os.path.relpath(dirpath, base)
            parsed = cachelayout.parse_box_folder(os.path.basename(dirpath))
            if not parsed:
                continue
            label, uid = parsed
            if not uid or uid in seen:
                continue            # the outermost folder of a uid wins
            seen.add(uid)
            found.append(Box(uid, label, _norm(rel)))
        return found

    def box(self, uid):
        """The box a tag names, or None. Compared case-insensitively: an NFC
        reader and the folder that was written for it need not agree on case.
        """
        want = (uid or '').strip().lower()
        if not want:
            return None
        for b in self.boxes():
            if b.uid.lower() == want:
                return b
        return None

    # ── the views ────────────────────────────────────────────────────────────

    def views(self, box):
        """The playlists of a box, `All` first then its sources by name.

        An included box's own views are NOT listed here — they are that box's,
        and `All` already holds its items, which is what `playlists()` builds.
        """
        folder = os.path.join(self.boxes_dir, *_parts(box.rel))
        try:
            names = sorted(n for n in os.listdir(folder) if n.endswith(M3U8))
        except OSError:
            return []
        alls = [n for n in names if n == cachelayout.ALL + M3U8]
        return [posixpath.join(box.rel, n) for n in alls + [n for n in names
                                                            if n not in alls]]

    def entries(self, view):
        """The playable lines of one `.m3u8`, in the order written.

        A line whose file is gone is dropped rather than handed on: the view is
        rewritten only when its content moves, so it can name a file the expiry
        has since taken, and a caller cannot tell a missing file from a silent
        one until Mopidy adds nothing for it.
        """
        path = os.path.join(self.boxes_dir, *_parts(view))
        try:
            with open(path, encoding='utf-8') as f:
                lines = f.read().splitlines()
        except OSError:
            return []
        here = os.path.dirname(path)
        by_path = self._by_path()
        out, title, seconds = [], '', 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                m = re.match(r'#EXTINF:(-?\d+)\s*,\s*(.*)$', line)
                if m:
                    seconds = max(0, int(m.group(1)))
                    title = m.group(2).strip()
                continue
            target = os.path.realpath(os.path.join(here, line))
            if not os.path.isfile(target):
                title, seconds = '', 0
                continue
            rel = _norm(os.path.relpath(target, self.root))
            uri, row = by_path.get(rel, ('', {}))
            out.append(_entry(target, uri, row, title, seconds))
            title, seconds = '', 0
        return out

    # ── what a tag put down should play ──────────────────────────────────────

    def queue(self, uid, sort='', include_finished=False):
        """What to hand the player for this box: its `All`, ordered.

        `sort` is the box's own `option_sort`, carried in the index — `asc` as
        written, `desc` reversed, anything else shuffled. That is the rule
        `add_tracks` already applies on the server, borrowed rather than
        reinvented: an explicit order is the one statement a box makes about
        sequence, and a view without one is an accumulation whose written order
        would otherwise be replayed identically every time.

        A spoken item heard to the end is left out, as the server's pools and
        the browser's queue both leave it out; music is never filtered this way
        — a favourite is meant to come back.
        """
        box = self.box(uid) if isinstance(uid, str) else uid
        if box is None:
            return []
        all_view = posixpath.join(box.rel, cachelayout.ALL + M3U8)
        items = self.entries(all_view)
        if not items:                        # no All yet: fall back to a source
            for v in self.views(box):
                items = self.entries(v)
                if items:
                    break
        if not include_finished:
            items = [e for e in items if not (e.spoken and e.finished)]
        return _ordered(items, sort, self.rng)


def _entry(target, uri, row, title, seconds):
    """One index row plus one `#EXTINF` into an Entry, the index winning where
    both speak: it was written from the database, the `#EXTINF` from whatever
    the title was when the view was last rewritten."""
    return Entry(
        file=target,
        uri=uri or '',
        title=(row.get('title') or title or ''),
        seconds=int(row.get('seconds') or seconds or 0),
        kind=(row.get('kind') or 'music'),
        cat=(row.get('cat') or ''),
        position=int(row.get('position') or 0),
        ad_skip=int(row.get('ad_skip') or 0),
        volume_boost=int(row.get('volume_boost') or 0),
        finished=bool(row.get('finished')),
        liked=bool(row.get('liked')),
    )


def _ordered(items, sort, rng):
    sort = (sort or '').strip().lower()
    if sort == 'asc':
        return list(items)
    if sort == 'desc':
        return list(reversed(items))
    out = list(items)
    rng.shuffle(out)
    return out


def _parts(rel):
    return [p for p in (rel or '').split('/') if p and p not in ('.', '..')]


def _norm(path):
    """A path as the index and the views both spell it: posix, no `./`."""
    if not path:
        return ''
    return posixpath.normpath(str(path).replace(os.sep, '/')).lstrip('./')
