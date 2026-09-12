"""Box-data directives: time windows, and forcing mood or discover level.

A box's data is a list of lines. Two things are layered on top of that here, and
both are deliberately *pure* — no DB, no clock of their own beyond what is passed
in — so they can be reasoned about and tested on their own.

1. A TIME WINDOW may prefix ANY line:

       08:00-10:00 > infos:library
       18:00-23:00 > meta_radios
       22:00-02:00 > dl:2

   The line applies only inside the window; outside it, it is as if absent. The
   window is generic on purpose: gating the news to the morning is as useful as
   gating a mood, and the mechanism should not care which it is.

2. Two DIRECTIVES force what the UI dials otherwise decide:

       dl:7                 discover level, 0-10
       mood:calm            one of the five named moods
       mood:0.3,0.8         energy,valence — the precise form

   Directives are read in a PRE-PASS, never in the line-by-line dispatch: the
   fill's mood and discover level are settled before any entry is served, so a
   'mood:' line sitting after 'auto:library' would otherwise have no effect on it
   and the order inside the box would silently change the result.

Windows are evaluated against LOCAL time — a listener writing "08:00" means their
morning, not UTC. See local_now() for how that is obtained without depending on
the deployment.
"""

import datetime
import os
import re

# Same five names, and the same pairs, as the BASIC view's mood detents — one
# vocabulary for the whole product rather than a second one hidden in box data.
MOOD_NAMES = {
    'intense':   (0.85, 0.25),
    'calm':      (0.20, 0.55),
    'normy':     (0.50, 0.50),
    'happy':     (0.55, 0.90),
    'energetic': (0.90, 0.75),
}

# Where a window's hours are read. The compose files set TZ, but each instance has
# its own and it sits outside the sparse checkout, so it cannot be relied on to
# carry this: a box written on one instance must mean the same hours on another.
DEFAULT_TZ = 'Europe/Paris'


def local_now():
    """Wall-clock time as a listener reads it, tz-naive for easy comparison.

    The process timezone wins when the deployment sets one (TZ in compose, or
    O2M_TIMEZONE to override just this); otherwise DEFAULT_TZ is applied
    explicitly, so a window still means local hours on an instance whose compose
    was never updated instead of silently drifting to UTC.
    """
    name = os.environ.get('O2M_TIMEZONE')
    if not name:
        if os.environ.get('TZ'):
            return datetime.datetime.now()
        name = DEFAULT_TZ
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(name)).replace(tzinfo=None)
    except Exception:
        return datetime.datetime.now()


_COND_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*>\s*(.*)$')
_DL_RE = re.compile(r'^dl\s*:\s*(\d{1,2})\s*$', re.I)
_MOOD_RE = re.compile(r'^mood\s*:\s*(.+?)\s*$', re.I)


def split_condition(line):
    """'08:00-10:00 > x' -> ((480, 600), 'x'). A plain line -> (None, line).

    Minutes-since-midnight rather than (h, m) pairs: the comparison below is then
    a plain integer one, including for a window that wraps past midnight.
    """
    m = _COND_RE.match(line or '')
    if not m:
        return None, (line or '').strip()
    h1, m1, h2, m2 = (int(g) for g in m.groups()[:4])
    if not (0 <= h1 <= 23 and 0 <= h2 <= 24 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
        return None, (line or '').strip()      # nonsense window: treat as plain text
    return (h1 * 60 + m1, h2 * 60 + m2), m.group(5).strip()


def window_matches(window, now=None):
    """Is `now` inside the window? Start inclusive, end exclusive.

    A window whose end is not after its start wraps midnight (22:00-02:00), which
    is exactly when someone wants a late-evening rule, so it is supported rather
    than rejected."""
    if not window:
        return True
    start, end = window
    now = now or local_now()
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end          # wraps midnight


def line_applies(line, now=None):
    """(applies_now, payload) for one raw line, inline window only.

    Blocks need the lines around them, so use iter_lines for a whole box."""
    window, payload = split_condition(line)
    return window_matches(window, now), payload


def iter_lines(data, now=None):
    """Yield (applies_now, payload) for every content line of a box.

    Resolves both shapes of window. Inline, one line at a time:

        08:00-10:00 > infos:library

    Or as a BLOCK, when the header carries the window and nothing else — every
    indented line below belongs to it, until a line that is not indented:

        08:00-10:00 >
          infos:library
          mood:calm
        auto:library            <- outside the block again

    The block exists because repeating the same window on six lines is where a
    typo lives, and because the lines of a morning belong together. An inline
    window on a line inside a block wins for that line: the more specific
    statement should be the one that counts.

    Blank lines and comments do not close a block — a label above a gated line is
    exactly the case that would otherwise break.
    """
    block = None
    for raw in (data or '').splitlines():
        line = (raw or '').rstrip()
        if not line.strip():
            yield window_matches(block, now), ''
            continue
        indented = line[:1] in (' ', '\t')
        stripped = line.strip()

        m = _COND_RE.match(stripped)
        if m and not m.group(5).strip():          # header: a window and nothing else
            window, _ = split_condition(stripped + 'x')   # reuse the same validation
            block = window
            continue
        if block is not None and not indented and not stripped.startswith('#'):
            block = None                          # back to the left margin: block over

        window, payload = split_condition(stripped)
        if window is None:
            window = block if indented or stripped.startswith('#') else None
        yield window_matches(window, now), payload


def parse_mood(value):
    """'calm' or '0.3,0.8' -> (energy, valence), or None if neither."""
    v = (value or '').strip().lower()
    if v in MOOD_NAMES:
        return MOOD_NAMES[v]
    parts = [p.strip() for p in v.replace(';', ',').split(',')]
    if len(parts) == 2:
        try:
            e, a = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if 0.0 <= e <= 1.0 and 0.0 <= a <= 1.0:
            return (e, a)
    return None


def _is_gated(data, payload, now=None):
    """Was this payload under a window (inline or block)? A gated statement beats an
    ungated one, so the pre-pass has to tell them apart."""
    for raw in (data or '').splitlines():
        w, p = split_condition(raw.strip())
        if p == payload and w is not None:
            return True
    block = None
    for raw in (data or '').splitlines():
        line = (raw or '').rstrip()
        if not line.strip():
            continue
        m = _COND_RE.match(line.strip())
        if m and not m.group(5).strip():
            block = True
            continue
        indented = line[:1] in (' ', '\t')
        if block and not indented and not line.strip().startswith('#'):
            block = None
        if line.strip() == payload and block and indented:
            return True
    return False


def read_directives(data, now=None):
    """Pre-pass over a box's data: the mood and discover level it forces.

    Returns {'energy', 'valence', 'dl'} with None for anything the box does not
    set. Later lines win over earlier ones, and a conditional line that matches
    wins over an unconditional one — the more specific statement should be the one
    that counts, whatever order it was typed in.
    """
    out = {'energy': None, 'valence': None, 'dl': None}
    conditional = {'mood': False, 'dl': False}
    # Same expansion as the dispatcher, so a directive inside a block is gated like
    # any other line rather than being read unconditionally.
    for applies, payload in iter_lines(data, now):
        if not payload or payload.startswith('#'):
            continue
        if not applies:
            continue
        is_cond = _is_gated(data, payload, now)

        m = _DL_RE.match(payload)
        if m:
            if is_cond or not conditional['dl']:
                dl = int(m.group(1))
                if 0 <= dl <= 10:
                    out['dl'] = dl
                    conditional['dl'] = conditional['dl'] or is_cond
            continue

        m = _MOOD_RE.match(payload)
        if m:
            pair = parse_mood(m.group(1))
            if pair and (is_cond or not conditional['mood']):
                out['energy'], out['valence'] = pair
                conditional['mood'] = conditional['mood'] or is_cond
    return out


def is_directive(payload):
    """True for a line the pre-pass owns, so the dispatch loop can skip it."""
    p = (payload or '').strip()
    return bool(_DL_RE.match(p) or _MOOD_RE.match(p))
