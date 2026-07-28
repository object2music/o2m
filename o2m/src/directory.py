"""External content directories — podcast channels and radio stations.

O2M's own cache is empty on a fresh install, so the box-creation wizard cannot
rely on `search_local` alone: a new user has nothing to pick from. These helpers
browse/search public keyless directories instead, and return lines that are
directly usable as box `data` content:

* podcast browse  — iTunes top charts per genre. The RSS charts endpoint only
  returns collection ids, so each page is completed with a `/lookup` call, the
  only iTunes endpoint that still exposes `feedUrl` (this is exactly what
  Mopidy-Podcast-iTunes does internally). Genre names come back localized.
* podcast search  — fyyd.de, which returns the feed URL directly and has good
  European/French coverage. iTunes' `/search` no longer exposes `feedUrl`, so it
  cannot be used for keyword search.
* radio          — radio-browser.info, which returns *resolved* stream URLs
  (.aac / .m3u8 / icecast), i.e. what a radio box's data line needs and what
  `_box_category` recognizes as a radio source.

Every function returns a list of uniform dicts:
    {'name', 'uri', 'image', 'sub', 'source'}
where `uri` is the ready-to-use data line ('podcast+<feed>' or a stream URL).
Network failures degrade to an empty list — a directory being down must never
break the wizard.
"""

import logging
import os
import time

import requests

log = logging.getLogger(__name__)

ITUNES_BASE = 'https://itunes.apple.com'
ITUNES_GENRES = ITUNES_BASE + '/WebObjects/MZStoreServices.woa/ws/genres'
ITUNES_CHARTS = ITUNES_BASE + '/%s/rss/toppodcasts/limit=%d/genre=%s/json'
ITUNES_LOOKUP = ITUNES_BASE + '/lookup'
FYYD_SEARCH = 'https://api.fyyd.de/0.2/search/podcast'
RADIO_BROWSER = 'https://all.api.radio-browser.info/json/stations'

PODCAST_ROOT_GENRE = '26'      # iTunes "Podcasts" root, parent of every genre
USER_AGENT = 'o2m/1.0 (+https://github.com/o2m)'
TIMEOUT = 12
_CACHE_TTL = 30 * 60           # directories move slowly; be polite to free APIs

_cache = {}


def default_country():
    """ISO country code for the stores/directories. Overridable per request."""
    return (os.environ.get('O2M_DIRECTORY_COUNTRY') or 'FR').upper()


def _cached(key, fn):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    value = fn()
    if value:                  # never cache a failure — retry on the next call
        _cache[key] = (time.time(), value)
    return value


def _get(url, params=None):
    r = requests.get(url, params=params, timeout=TIMEOUT,
                     headers={'User-Agent': USER_AGENT})
    r.raise_for_status()
    return r.json()


# ─── Podcasts ─────────────────────────────────────────────────────────────────

def podcast_genres(country=None):
    """Localized iTunes podcast genres: [{'id', 'name'}], alphabetical."""
    cc = (country or default_country()).upper()

    def fetch():
        try:
            data = _get(ITUNES_GENRES, {'id': PODCAST_ROOT_GENRE, 'cc': cc})
        except Exception as err:
            log.error(f'podcast_genres: {err}')
            return []
        subs = (data.get(PODCAST_ROOT_GENRE) or {}).get('subgenres') or {}
        out = [{'id': str(gid), 'name': g.get('name') or str(gid)}
               for gid, g in subs.items() if g.get('name')]
        out.sort(key=lambda g: g['name'].lower())
        return out

    return _cached(f'pgenres:{cc}', fetch)


def _itunes_rows(results):
    """iTunes lookup results → uniform rows (entries without a feed are dropped)."""
    rows = []
    for item in results or []:
        feed = item.get('feedUrl')
        name = item.get('collectionName')
        if not feed or not name:
            continue
        rows.append({
            'name': name,
            'uri': 'podcast+' + feed,
            'image': item.get('artworkUrl100') or item.get('artworkUrl60') or '',
            'sub': item.get('artistName') or '',
            'source': 'itunes',
        })
    return rows


def top_podcasts(genre_id=None, country=None, limit=25):
    """Top podcast channels for a genre (default: all podcasts)."""
    cc = (country or default_country()).upper()
    genre = str(genre_id or PODCAST_ROOT_GENRE)
    limit = max(1, min(int(limit or 25), 100))

    def fetch():
        try:
            charts = _get(ITUNES_CHARTS % (cc.lower(), limit, genre))
        except Exception as err:
            log.error(f'top_podcasts charts: {err}')
            return []
        ids = [e.get('id', {}).get('attributes', {}).get('im:id')
               for e in (charts.get('feed') or {}).get('entry') or []]
        ids = [i for i in ids if i]
        if not ids:
            return []
        try:
            # The charts feed has no feedUrl; only /lookup still returns it.
            found = _get(ITUNES_LOOKUP, {'id': ','.join(ids), 'cc': cc})
        except Exception as err:
            log.error(f'top_podcasts lookup: {err}')
            return []
        return _itunes_rows(found.get('results'))

    return _cached(f'ptop:{cc}:{genre}:{limit}', fetch)


def search_podcasts(query, limit=20):
    """Keyword search over the fyyd.de podcast directory."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    limit = max(1, min(int(limit or 20), 50))

    def fetch():
        try:
            data = _get(FYYD_SEARCH, {'title': q, 'count': limit})
        except Exception as err:
            log.error(f'search_podcasts: {err}')
            return []
        rows, seen = [], set()
        for p in data.get('data') or []:
            feed = p.get('xmlURL')
            name = p.get('title')
            if not feed or not name or feed in seen:
                continue
            seen.add(feed)
            rows.append({
                'name': name,
                'uri': 'podcast+' + feed,
                'image': p.get('imgURL') or '',
                'sub': p.get('author') or '',
                'source': 'fyyd',
            })
        return rows

    return _cached(f'psearch:{q.lower()}:{limit}', fetch)


# ─── Radios ───────────────────────────────────────────────────────────────────

def _radio_rows(stations):
    rows, seen = [], set()
    for s in stations or []:
        url = s.get('url_resolved') or s.get('url')
        name = (s.get('name') or '').strip()
        if not url or not name or url in seen:
            continue
        seen.add(url)
        bits = [b for b in (s.get('codec'), s.get('country'), s.get('tags', '').split(',')[0]) if b]
        rows.append({
            'name': name,
            'uri': url,
            'image': s.get('favicon') or '',
            'sub': ' · '.join(bits[:2]),
            'source': 'radio-browser',
        })
    return rows


def top_radios(country=None, limit=30):
    """Most-voted stations for a country — the no-query radio browse list."""
    cc = (country or default_country()).upper()
    limit = max(1, min(int(limit or 30), 100))

    def fetch():
        try:
            return _radio_rows(_get(RADIO_BROWSER + '/search', {
                'countrycode': cc, 'limit': limit, 'hidebroken': 'true',
                'order': 'votes', 'reverse': 'true',
            }))
        except Exception as err:
            log.error(f'top_radios: {err}')
            return []

    return _cached(f'rtop:{cc}:{limit}', fetch)


def search_radios(query, limit=30):
    """Keyword search over radio-browser station names (worldwide)."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    limit = max(1, min(int(limit or 30), 100))

    def fetch():
        try:
            return _radio_rows(_get(RADIO_BROWSER + '/search', {
                'name': q, 'limit': limit, 'hidebroken': 'true',
                'order': 'votes', 'reverse': 'true',
            }))
        except Exception as err:
            log.error(f'search_radios: {err}')
            return []

    return _cached(f'rsearch:{q.lower()}:{limit}', fetch)
