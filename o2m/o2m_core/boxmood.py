"""The mood of a box's content: where its tracks sit on the energy/valence plane.

The box editor shows it under the content (the "Mood of the content" section):
the average point, the selection's mood radius at discover level 5 drawn around
it, every measured track, and the tracks listed by their distance to the average.

It reads the CACHE only — what the library mirror already holds for a playlist,
an album, an artist, a tag — and never the network: it answers in a few
milliseconds and is safe to ask each time the editor opens. A line whose content
is a RULE rather than a set (`auto:library`, `now:library`, a feed, a stream) has
no fixed tracks to measure, and is reported as such rather than guessed at.
Resolving the box instead (`resolve_box_uris`) would have measured those too,
but for every mood-driven line the answer would follow the CURRENT dials — the
average of a box would be whatever mood was set when someone opened it.

Pure: the caller hands a `reader` with the four cache lookups (see `measure`),
so the tests run without a database.
"""
import math
import random
import re

from o2m_core import boxdirectives as bdir

# The selection's mood radius at discover level 5: σ = DL/20 + 0.05
# (_mood_pick, the concentric Gaussian around the target).
DL_REF = 5
SIGMA = DL_REF / 20 + 0.05

# Per line, enough tracks for the average and the plot; an artist holds up to
# ~300 cached tracks and a tag thousands. Beyond this, a random sample.
MAX_PER_LINE = 400

_ID = r'([A-Za-z0-9]+)'
_KINDS = (
    ('track', re.compile(r'^spotify:track:' + _ID + r'$')),
    ('album', re.compile(r'^spotify:album:' + _ID + r'$')),
    ('artist', re.compile(r'^spotify:artist:' + _ID + r'$')),
    # The old `spotify:user:<u>:playlist:<id>` spelling names the same object.
    ('playlist', re.compile(r'^spotify:(?:user:[^:]+:)?playlist:' + _ID + r'$')),
)


def classify(line):
    """(kind, key) for a content line, or (None, None) when it names no fixed
    set of tracks. kind: track | album | artist | playlist | tag.

    An included box (`box:`) is not measured for now: a cascade is reported as
    a line like a rule, not followed."""
    p = (line or '').strip()
    if p.startswith('tag:'):
        name = p[4:].strip()
        return ('tag', name) if name else (None, None)
    for kind, rx in _KINDS:
        m = rx.match(p)
        if m:
            return kind, m.group(1)
    return None, None


def content_lines(data):
    """The lines that count: every hour's (a window says WHEN a line plays, not
    whether it belongs to the box), without `#` lines, labels or directives."""
    out = []
    for _applies, payload in bdir.iter_lines(data or ''):
        p = (payload or '').strip()
        if not p or p.startswith('#') or bdir.is_directive(p):
            continue
        out.append(p)
    return out


def measure(data, reader, rng=None):
    """Read a box's content into weighted points.

    reader: an object with
      track_uris(kind, key) -> [uri]   for track/album/artist/playlist/tag
      features(uris)        -> {uri: {'energy','valence','name','artist'}}
                                         only for the uris that HAVE both values
    Returns (points, lines). Each point carries `w`, its share of the average:
    every line that measured anything weighs the same, split between its
    tracks — the box budget gives each line an equal share of the places, so
    that is what the box actually plays, where a plain per-track mean would let
    a 300-track artist drown the playlist beside it.
    """
    rng = rng or random
    lines, groups = [], []
    for line in content_lines(data):
        kind, key = classify(line)
        info = {'line': line, 'kind': kind, 'tracks': 0, 'measured': 0}
        lines.append(info)
        if kind is None:
            continue
        uris = [u for u in dict.fromkeys(reader.track_uris(kind, key) or []) if u]
        info['tracks'] = len(uris)
        feats = reader.features(uris) if uris else {}
        found = [u for u in uris if u in feats]
        if len(found) > MAX_PER_LINE:
            found = rng.sample(found, MAX_PER_LINE)
        info['measured'] = len(found)
        if found:
            w = 1.0 / len(found)
            groups.append([dict(feats[u], uri=u, w=w, line=line) for u in found])
    points = []
    if groups:
        per_line = 1.0 / len(groups)
        for g in groups:
            points.extend(dict(p, w=p['w'] * per_line) for p in g)
    return points, lines


def summarize(points, sigma=SIGMA):
    """The weighted average point, and every track's distance to it.

    Returns {'energy', 'valence', 'spread', 'inside', 'tracks'}, `tracks` sorted
    from the most divergent to the closest. `closeness` is the selection's own
    mood weight at the reference DL, exp(-d²/2σ²) — 1 on the average, 0.61 on
    the radius. `spread` is the weighted RMS distance; `inside` the share of the
    weight within σ. A track reached by two lines appears once, at the sum of
    its weights. None when nothing was measured."""
    merged = {}
    for p in points:
        u = p.get('uri')
        if u in merged:
            merged[u]['w'] += p['w']
        else:
            merged[u] = dict(p)
    pts = list(merged.values())
    total = sum(p['w'] for p in pts)
    if not pts or total <= 0:
        return None
    e = sum(p['energy'] * p['w'] for p in pts) / total
    v = sum(p['valence'] * p['w'] for p in pts) / total
    out, sq, inside = [], 0.0, 0.0
    for p in pts:
        d = math.hypot(p['energy'] - e, p['valence'] - v)
        sq += p['w'] * d * d
        if d <= sigma:
            inside += p['w']
        out.append(dict(p, w=p['w'] / total, distance=round(d, 4),
                        closeness=round(math.exp(-d * d / (2 * sigma * sigma)), 4)))
    out.sort(key=lambda t: (-t['distance'], t.get('name') or ''))
    return {
        'energy': round(e, 4), 'valence': round(v, 4),
        'spread': round(math.sqrt(sq / total), 4),
        'inside': round(inside / total, 4),
        'tracks': out,
    }
