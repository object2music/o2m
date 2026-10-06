"""One budget for a box, shared between its lines.

Every line of a box used to draw the box's full max_results. Three playlists made
45 candidates for 15 places, and add_tracks keeps the FIRST 15 — the first playlist
took the box and the others gave nothing. A `box:` include filled with its own
quota on top of the parent's, so a cascade of four boxes queued five quotas.

The rule here: each line that draws several items gets an equal share of what is
left, and a shortfall (a short playlist, an empty feed) rolls forward to the lines
after it. A line naming ONE item (a track, an episode, a stream) is not a share: it
reserves its one place up front, so a box of three playlists and a radio still
gives the radio its place and the playlists the rest.

Pure: no database, no Mopidy — `tracklistappend_box` measures what each line
actually added and reports it back with `spent`.
"""

_SINGLE_PREFIXES = ('spotify:track:', 'yt:video:', 'youtube:video:', 'tunein:',
                    'local:track:', 'file:', 'http://', 'https://')


def is_single_item_line(line):
    """A box line naming ONE playable item, as opposed to one that draws several
    (a playlist, an artist, a feed, a pattern, an included box)."""
    l = (line or '').strip()
    if l.startswith(_SINGLE_PREFIXES):
        return True
    return l.startswith('podcast+') and '#' in l


class BoxBudget:
    def __init__(self, total, lines):
        lines = [l for l in lines if l and l.strip()]
        singles = sum(1 for l in lines if is_single_item_line(l))
        self.left = max(0, int(total or 0) - singles)
        self.shares_left = len(lines) - singles

    def take(self, line):
        """The number of items this line may add, or None for a single-item line
        (its place is already reserved). 0 means the budget is spent."""
        if is_single_item_line(line):
            return None
        if self.shares_left <= 0 or self.left <= 0:
            self.shares_left = max(0, self.shares_left - 1)
            return 0
        share = max(1, round(self.left / self.shares_left))
        self.shares_left -= 1
        return share

    def spent(self, n):
        """What the line just served actually added."""
        self.left = max(0, self.left - max(0, int(n or 0)))


def split(weights, n):
    """Share n places between sources by weight, every source with a positive
    weight keeping at least one place when there are enough to go round.

    The AUTO mix used to round each source on its own and hand the rounding error
    to the last one. That was invisible at 30 tracks and wrong at 10, which is what
    an auto:library line gets once it shares a box with two included boxes:
    incoming (weight 0.3·DL) rounded to 0 up to DL 5, so a source the DL asked for
    never came out. Here: the largest-remainder method (the sum is exactly n, and
    nothing goes negative), then any positive source left at 0 takes one place from
    the source holding the most. With fewer places than sources, the heaviest win.
    A source of weight 0 stays at 0: that is the DL saying "none", not rounding.
    """
    n = max(0, int(n or 0))
    keys = list(weights)
    w = {k: max(0.0, float(weights[k] or 0)) for k in keys}
    total = sum(w.values())
    if n == 0 or total <= 0:
        return {k: 0 for k in keys}
    exact = {k: w[k] / total * n for k in keys}
    out = {k: int(exact[k]) for k in keys}
    by_rest = sorted(keys, key=lambda k: (exact[k] - out[k], w[k]), reverse=True)
    for k in by_rest[:n - sum(out.values())]:
        out[k] += 1
    for k in sorted((k for k in keys if w[k] > 0 and out[k] == 0),
                    key=lambda k: w[k], reverse=True):
        donor = max(keys, key=lambda d: (out[d], -w[d]))
        if out[donor] <= 1:
            break   # fewer places than sources: the heaviest already hold them
        out[donor] -= 1
        out[k] = 1
    return out
