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
