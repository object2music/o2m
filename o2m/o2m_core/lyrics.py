"""Song lyrics, for the Invert theme's lyrics pane.

Two free sources, no key:
- LRCLIB (lrclib.net) — SYNCED lyrics (LRC: one timestamp per line), which is
  what lets the pane follow the song. Asked by title, artist, album and length
  (its `get` matches within a couple of seconds), then by search.
- lyrics.ovh — plain text only, the fallback when LRCLIB has nothing or is down
  (it answers 503 "ServerOverloaded" for minutes at a time).

An answer is cached in memory: a hit for a week, "no lyrics anywhere" for a day,
and anything decided while LRCLIB was down for ten minutes. A source that failed (timeout, 5xx) is NOT an answer — remembering it would hide
the lyrics of that song for a day because of one bad minute.
"""
import re
import time
import threading

import requests

UA = 'o2m (https://github.com/object2music/o2m)'
TIMEOUT = 8
_TTL_HIT = 7 * 86400
_TTL_MISS = 86400
_TTL_RETRY = 600

_cache = {}
_lock = threading.Lock()


class Unavailable(Exception):
    """Every source failed: ask again later."""


_LRC_LINE = re.compile(r'^\s*((?:\[\d+:\d+(?:[.:]\d+)?\])+)(.*)$')
_LRC_TS = re.compile(r'\[(\d+):(\d+)(?:[.:](\d+))?\]')


def parse_lrc(text):
    """LRC → [[ms, line], ...] sorted by time. A line may carry several stamps
    (a chorus written once); metadata tags ([ar:], [ti:]…) are dropped."""
    out = []
    for raw in (text or '').splitlines():
        m = _LRC_LINE.match(raw)
        if not m:
            continue
        words = m.group(2).strip()
        for mm, ss, frac in _LRC_TS.findall(m.group(1)):
            ms = (int(mm) * 60 + int(ss)) * 1000
            if frac:
                ms += int(frac.ljust(3, '0')[:3])
            out.append([ms, words])
    out.sort(key=lambda x: x[0])
    return out


_DECOR = re.compile(
    r'\s+-\s+.*\b(remaster(ed)?|live|version|edit|mix|mono|stereo|demo|acoustic|bonus)\b.*$'
    r'|\s*[\(\[](feat\.?|ft\.?|with)\s[^\)\]]*[\)\]]', re.I)


def clean_title(name):
    """'Song - Remastered 2009' / 'Song (feat. X)' → 'Song': the lyrics databases
    file the song, not the release."""
    return _DECOR.sub('', name or '').strip() or (name or '').strip()


def main_artist(artist):
    return re.split(r'\s*(?:,|&| feat\.? | ft\.? | x )\s*', artist or '', maxsplit=1)[0].strip()


def _lrclib_search(params, duration_s):
    r = requests.get('https://lrclib.net/api/search', params=params,
                     headers={'User-Agent': UA}, timeout=TIMEOUT)
    if r.status_code >= 500:
        raise Unavailable('lrclib %s' % r.status_code)
    rows = r.json() if r.status_code == 200 else []
    if duration_s:
        # The search ignores length: keep those within 5 s, nearest first.
        rows = sorted((x for x in rows if abs((x.get('duration') or 0) - duration_s) <= 5),
                      key=lambda x: abs((x.get('duration') or 0) - duration_s))
    return [x for x in rows if x.get('syncedLyrics') or x.get('plainLyrics')]


def pick_row(rows):
    """The first SYNCED row, else the first with plain lyrics: LRCLIB often holds
    the same song several times, one upload timed and the others not."""
    for x in rows:
        if x.get('syncedLyrics'):
            return x
    return rows[0] if rows else None


def _lrclib(title, artist, album, duration_s):
    params = {'track_name': title, 'artist_name': artist}
    if album:
        params['album_name'] = album
    if duration_s:
        params['duration'] = int(round(duration_s))
    r = requests.get('https://lrclib.net/api/get', params=params,
                     headers={'User-Agent': UA}, timeout=TIMEOUT)
    if r.status_code >= 500:
        raise Unavailable('lrclib %s' % r.status_code)
    hit = r.json() if r.status_code == 200 else None
    if not hit or not hit.get('syncedLyrics'):
        # Nothing, or only untimed text: another upload of the song may be timed.
        # By title and artist first, then as free text (a "feat." or an accent
        # spelled differently defeats the fielded search).
        rows = _lrclib_search({'track_name': title, 'artist_name': artist}, duration_s)
        if not any(x.get('syncedLyrics') for x in rows):
            rows += _lrclib_search({'q': '%s %s' % (artist, title)}, duration_s)
        better = pick_row(rows)
        if better and (not hit or better.get('syncedLyrics')):
            hit = better
    if not hit or hit.get('instrumental'):
        return {'instrumental': True} if hit else None
    synced = parse_lrc(hit.get('syncedLyrics') or '')
    plain = (hit.get('plainLyrics') or '').strip()
    if not synced and not plain:
        return None
    return {'synced': synced or None, 'plain': plain or None, 'source': 'LRCLIB'}


def _lyrics_ovh(title, artist):
    r = requests.get('https://api.lyrics.ovh/v1/%s/%s' % (
        requests.utils.quote(artist, safe=''), requests.utils.quote(title, safe='')),
        headers={'User-Agent': UA}, timeout=TIMEOUT)
    if r.status_code >= 500:
        raise Unavailable('lyrics.ovh %s' % r.status_code)
    text = ((r.json() or {}).get('lyrics') or '').strip() if r.status_code == 200 else ''
    # lyrics.ovh prefixes some answers with a "Paroles de la chanson …" line.
    text = re.sub(r'^Paroles de la chanson .*\n', '', text).strip()
    return {'synced': None, 'plain': text, 'source': 'lyrics.ovh'} if text else None


def find(key, name, artist, album='', duration_ms=0):
    """{'synced': [[ms, line]…] | None, 'plain': str | None, 'source'} or
    {'instrumental': True} or None (nothing anywhere). Raises Unavailable when
    every source failed."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    title, who = clean_title(name), main_artist(artist)
    if not title or not who:
        return None
    dur = (duration_ms or 0) / 1000.0
    res, failed, lrclib_down = None, 0, False
    try:
        res = _lrclib(title, who, album, dur)
    except Exception:
        failed += 1
        lrclib_down = True
    if not res or (not res.get('synced') and not res.get('plain') and not res.get('instrumental')):
        try:
            res = _lyrics_ovh(title, who) or res
        except Exception:
            failed += 1
    if res is None and failed == 2:
        raise Unavailable('no lyrics source answered')
    # With LRCLIB down, what lyrics.ovh gave (plain text, or nothing) is only an
    # answer for now: the synced version may be one retry away.
    ttl = _TTL_RETRY if lrclib_down else (_TTL_HIT if res else _TTL_MISS)
    with _lock:
        _cache[key] = (now + ttl, res)
    return res
