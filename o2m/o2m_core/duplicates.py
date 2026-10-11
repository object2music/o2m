"""Duplicate tracks: one recording under several Spotify uris.

Spotify publishes the same recording on an album, a compilation, a deluxe
edition, a regional release — each with its own track uri. o2m keys everything
on the uri, so the plays of one song were split between rows: on 2026-10-11 a
Rachid Taha track read "last played 2 weeks ago" while it had just been played
under its other uri (57 reads on one, 13 on the other).

This module is pure — it neither reads the database nor the clock:
  * `find_groups` proposes groups from plain rows (same normalised title, same
    main artist, durations within `DURATION_TOL_MS`). It only PROPOSES: a live
    take or a re-recording can match all three, which is why a person confirms
    each merge (the /duplicates page) and can dismiss a group.
  * `merged_counters` says what the kept row holds once the others are folded
    into it.
"""
import re
import unicodedata

# Same recording, different release: lengths agree to the second or two
# (measured on the Rachid Taha pair: identical). A radio edit or a live take is
# usually much further away than this.
DURATION_TOL_MS = 3000

# Release decorations that do not change the recording.
_DECORATION = re.compile(
    r'\s*(?:[-–—]\s*|\(|\[)\s*(?:\d{4}\s+)?(?:digital(?:ly)?\s+)?remaster(?:ed)?(?:\s+\d{4})?(?:\s+version)?\s*[)\]]?\s*$'
    r'|\s*(?:[-–—]\s*|\(|\[)\s*(?:single|album|lp)\s+version\s*[)\]]?\s*$',
    re.I)


def normalize_title(name):
    """A title as the grouping compares it: lower case, accents kept (they make
    different words in French), release decorations dropped, spaces folded."""
    t = unicodedata.normalize('NFC', str(name or '')).strip()
    prev = None
    while prev != t:                     # "X - 2011 Remaster (Single Version)"
        prev, t = t, _DECORATION.sub('', t).strip()
    return re.sub(r'\s+', ' ', t).lower()


def group_key(uris):
    """The identity of a group, for dismissing it."""
    return '|'.join(sorted(uris))


def find_groups(rows, tol_ms=DURATION_TOL_MS, aliased=(), dismissed=(), min_played=1):
    """rows: dicts with uri, name, artist (main artist id), duration_ms,
    read_count. Returns groups (lists of rows, most read first), each holding
    at least two uris and at least `min_played` that were read. Uris already
    merged away (`aliased`) are left out; a group whose key is in `dismissed`
    is not proposed."""
    aliased, dismissed = set(aliased), set(dismissed)
    by_key = {}
    for r in rows:
        if r.get('uri') in aliased or not r.get('name') or not r.get('artist'):
            continue
        by_key.setdefault((normalize_title(r['name']), r['artist']), []).append(r)
    out = []
    for members in by_key.values():
        if len(members) < 2:
            continue
        # Split by length: sorted, a gap wider than the tolerance starts a new
        # group. A row with no known length cannot be told apart, so it stays out.
        timed = sorted((m for m in members if m.get('duration_ms')), key=lambda m: m['duration_ms'])
        cluster = []
        for m in timed:
            if cluster and m['duration_ms'] - cluster[-1]['duration_ms'] > tol_ms:
                out.append(cluster)
                cluster = []
            cluster.append(m)
        if cluster:
            out.append(cluster)
    groups = []
    for g in out:
        if len(g) < 2 or group_key(m['uri'] for m in g) in dismissed:
            continue
        if sum(1 for m in g if (m.get('read_count') or 0) > 0) < min_played:
            continue
        groups.append(sorted(g, key=lambda m: (-(m.get('read_count') or 0), m['uri'])))
    groups.sort(key=lambda g: -sum(m.get('read_count') or 0 for m in g))
    return groups


_SUMS = ('read_count', 'read_count_end', 'skipped_count')
_LATEST = ('last_read_date', 'last_play_seq')


def merged_counters(keep, others):
    """The counters `keep` holds once `others` are folded into it.

    Counts add up. The latest date and play sequence win (they are what the
    anti-repeat cooldown reads: the song was heard when EITHER uri was). The
    completion average is weighted by reads. A like on any version is a like
    on the recording; a dislike likewise. Everything else stays `keep`'s."""
    rows = [keep] + list(others)
    out = {k: sum(int(r.get(k) or 0) for r in rows) for k in _SUMS}
    for k in _LATEST:
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        out[k] = max(vals) if vals else None
    total = out['read_count']
    if total:
        out['read_end'] = sum(float(r.get('read_end') if r.get('read_end') is not None else .5)
                              * int(r.get('read_count') or 0) for r in rows) / total
    else:
        out['read_end'] = keep.get('read_end')
    out['liked'] = 1 if any(r.get('liked') for r in rows) else 0
    out['disliked'] = 1 if any(r.get('disliked') for r in rows) else 0
    if out['liked'] and out['disliked']:
        out['disliked'] = 0              # mutually exclusive; the like is the commitment
    return out


def certain_merges(groups, isrc):
    """The merges that need no one's eye: within each proposed group, the
    members sharing one ISRC are the same recording. `isrc` maps uri -> code
    ('' or missing = unknown, never matched). Returns [(keep, [others])], keep
    being the most read of the subset (groups come most read first)."""
    out = []
    for g in groups:
        by = {}
        for m in g:
            code = (isrc.get(m['uri']) or '').strip().upper()
            if code:
                by.setdefault(code, []).append(m['uri'])
        for uris in by.values():
            if len(uris) > 1:
                out.append((uris[0], uris[1:]))
    return out

