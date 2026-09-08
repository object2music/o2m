"""Radio France OpenAPI (developers.radiofrance.fr) — shows, episodes, subjects.

Radio France is the main podcast/info source of this install, but it is nearly
absent from the keyless directories `directory.py` uses (fyyd indexes a single
France Culture podcast), so a show like "L'Invité(e) des Matins" could never be
found by search. This module talks to the official GraphQL API instead, which
knows the whole catalogue.

Three things it provides:

* show catalogue — `list_shows` walks `shows(station:)` page by page so the
  titles can be indexed locally and searched (the API itself has NO keyword
  search over shows).
* show episodes  — `episodes_of_show`. RF's `Show.podcast { rss }` field is
  broken server-side (their internal `refreplay` service answers 400 for
  essentially every show), so a show CANNOT be expressed as a `podcast+<feed>`
  line: it is expanded through the API and yields direct mp3 URLs.
* subjects       — `list_taxonomies` (themes/tags) + `diffusions`, which powers
  the dynamic `rf:sujet:<keyword>` box: whatever was published on a subject
  over the last few days.

Episode `uri` is the plain https mp3 (proxycast.radiofrance.fr), which 302s to
media.radiofrance-podcast.net and is played directly by mopidy-stream.

Rows follow the same shape as `directory.py` so they drop into the same UI:
    {'name', 'uri', 'image', 'sub', 'source'}
episodes add {'length'}. The API key is always the first argument — this module
never reads the config. Network/API failures degrade to None/[]: Radio France
being down must never break search or a box fill.
"""

import logging
import datetime
import re
import time
import unicodedata

import requests

log = logging.getLogger(__name__)

GRAPHQL_URL = 'https://openapi.radiofrance.fr/v1/graphql'
USER_AGENT = 'o2m/1.0 (+https://github.com/o2m)'
TIMEOUT = 12
MAX_PAGE = 100          # server-side hard cap on `first`
MAX_WINDOW_DAYS = 7     # server-side hard cap on the diffusions start/end window

# Station slug (as used in o2m box data / RF page URLs) → StationsEnum value.
STATIONS = {
    'franceculture': 'FRANCECULTURE',
    'franceinter':   'FRANCEINTER',
    'franceinfo':    'FRANCEINFO',
    'francemusique': 'FRANCEMUSIQUE',
    'mouv':          'MOUV',
    'fip':           'FIP',
}
STATION_LABELS = {
    'FRANCECULTURE': 'France Culture', 'FRANCEINTER': 'France Inter',
    'FRANCEINFO': 'France Info', 'FRANCEMUSIQUE': 'France Musique',
    'MOUV': 'Mouv', 'FIP': 'FIP',
}
# Spoken-content stations, richest in podcasts — the default for `rf:sujet:`.
DEFAULT_STATIONS = ('FRANCECULTURE', 'FRANCEINTER')

_TTL_SHOWS = 6 * 3600      # the catalogue moves slowly
_TTL_EPISODES = 15 * 60    # a rolling window; 15 min is plenty
_cache = {}


def _cached(key, fn, ttl, cache_empty=False):
    """Memoise fn() for ttl seconds. A falsy value is not cached by default so a
    failure is retried — but with cache_empty the caller signals it can tell a
    real failure (None) from a legitimate empty answer ([]), and an empty answer
    IS worth caching: a subject with no recent episode would otherwise be
    re-queried on every single box activation."""
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    value = fn()
    if (value is not None) if cache_empty else bool(value):
        _cache[key] = (time.time(), value)
    return value


def normalize(text):
    """Fold a title for matching: lowercase, no accents, collapsed spaces."""
    s = unicodedata.normalize('NFKD', str(text or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).strip().lower()


def _gql(api_key, query, variables=None, timeout=None):
    """POST one GraphQL document with the X-Token header.

    Returns the `data` dict, KEEPING PARTIAL DATA: this API answers 200 with
    both `data` and `errors` when a non-nullable subfield faults (it does that
    routinely for Taxonomy.path and Show.podcast), and discarding the payload
    would throw away every good row alongside. None on transport/auth failure.
    """
    if not api_key:
        return None
    try:
        r = requests.post(GRAPHQL_URL,
                          json={'query': query, 'variables': variables or {}},
                          timeout=timeout or TIMEOUT,
                          headers={'User-Agent': USER_AGENT, 'X-Token': api_key})
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        log.error(f'radiofrance: request failed: {e}')
        return None
    errors = payload.get('errors')
    if errors:
        log.warning(f"radiofrance: partial errors: {(errors[0] or {}).get('message')}")
    return payload.get('data')


# ─── URL detection (a pasted radiofrance.fr page) ─────────────────────────────

# A show page is /{station}/podcasts/{slug}; an episode page adds one more
# segment whose tail is '-<digits>' (…/ia-dans-les-services-publics-…-3141912).
_RF_URL_RE = re.compile(
    r'https?://(?:www\.)?radiofrance\.fr/(?P<station>[a-z0-9-]+)/podcasts/'
    r'(?P<show>[^/?#\s]+)(?:/(?P<episode>[^/?#\s]+))?', re.I)


def is_rf_url(text):
    return bool(text) and bool(_RF_URL_RE.search(str(text)))


def parse_rf_url(text):
    """Recognize a radiofrance.fr podcast page inside free text.

    Returns {'kind': 'show'|'episode', 'station', 'show_url', 'url',
    'episode_id', 'episode_slug'} or None. `showByUrl` rejects an episode URL
    ("Not a show"), so an episode is resolved through its PARENT show url.
    """
    m = _RF_URL_RE.search(str(text or ''))
    if not m:
        return None
    station, show, episode = m.group('station'), m.group('show'), m.group('episode')
    show_url = f'https://www.radiofrance.fr/{station}/podcasts/{show}'
    out = {'kind': 'show', 'station': station.lower(), 'show_url': show_url,
           'url': m.group(0), 'episode_id': None, 'episode_slug': None}
    if episode:
        out['kind'] = 'episode'
        out['episode_slug'] = episode
        tail = re.search(r'-(\d+)$', episode)
        out['episode_id'] = tail.group(1) if tail else None
    return out


# ─── Rows ─────────────────────────────────────────────────────────────────────

def show_row(node, station=None):
    """A show as a channel row. `uri` is a box data line — NOT 'podcast+<feed>',
    because RF's rss field is unusable (see the module docstring)."""
    url = (node.get('url') or '').strip()
    return {
        'name': (node.get('title') or '').strip(),
        'uri': 'rf:show:' + url if url else '',
        'image': '',                      # the Show type exposes no image field
        'sub': STATION_LABELS.get(station or '', 'Radio France'),
        'source': 'radiofrance',
        'rf_id': node.get('id'),
        'station': station,
        'standfirst': (node.get('standFirst') or '').strip(),
        'url': url,
    }


_FEED_RE = re.compile(r'https?://[^"\']*radiofrance-podcast\.net/[^"\']*\.xml')


def discover_feed(show_url, timeout=None):
    """The RSS feed of a Radio France show, read from its own page.

    The OpenAPI exposes a `podcast { rss }` field but it faults server-side for
    essentially every show, so the page is the only source. No API key needed.
    This is what lets an API episode be expressed as 'podcast+<feed>#<guid>' —
    the same shape as every other podcast in the app — instead of a bare mp3
    link needing its own special cases everywhere.
    """
    if not show_url:
        return ''

    def fetch():
        try:
            r = requests.get(show_url, timeout=timeout or TIMEOUT,
                             headers={'User-Agent': USER_AGENT})
            r.raise_for_status()
            m = _FEED_RE.search(r.text)
            return m.group(0) if m else ''
        except Exception as e:
            log.error(f'discover_feed({show_url}): {e}')
            return ''

    return _cached('rffeed:' + show_url, fetch, _TTL_SHOWS) or ''


def episode_key(page_url):
    """Radio France's own id for an episode, taken from its page URL.

    The SAME broadcast reaches us twice — as an RSS item and as an API episode —
    under different audio files with different ITEMA ids, so there is no shared
    key in the media. But both point at the same episode PAGE: the feed's
    <link> and the API's url end with the same numeric id. That id is the join.
    """
    m = re.search(r'-(\d{5,})/?$', (page_url or '').strip().rstrip('/'))
    return m.group(1) if m else ''


def canonical_episode_url(url):
    """One URL per episode, always the same one.

    The API appends a '?project=<app id>' to every episode link. It is stable
    today, but it identifies the CALLER, not the episode — so the day it changes
    (new app, migration) the same episodes would come back under new URLs and be
    stored a second time, splitting their listening history in two. The bare
    file plays identically (verified: 206 audio/mpeg), so drop the query and key
    everything on the file itself. Scoped to media files: a live radio stream's
    query can be meaningful.
    """
    u = (url or '').strip()
    if '?' not in u:
        return u
    head = u.split('?', 1)[0]
    return head if head.lower().endswith(('.mp3', '.m4a', '.aac', '.ogg')) else u


def _day(ts):
    """RF publishes a unix timestamp; the feed path stores 'YYYY-MM-DD'."""
    try:
        return datetime.datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except Exception:
        return ''


def episode_row(node, show_title=''):
    """A diffusion as a playable episode row, or None when it carries no audio
    (news bulletins and some segments have no podcastEpisode)."""
    ep = node.get('podcastEpisode') or {}
    url = canonical_episode_url((ep.get('url') or '').strip())
    if not url:
        return None
    show = node.get('show') or {}
    duration = ep.get('duration')
    tx = [((e or {}).get('node') or {}).get('id')
          for e in ((node.get('taxonomiesConnection') or {}).get('edges') or [])]
    return {
        'name': (node.get('title') or '').strip(),
        'uri': url,
        'image': '',
        'sub': show_title or (show.get('title') or '').strip(),
        'source': 'radiofrance',
        'length': int(duration) * 1000 if duration else None,
        'published': node.get('published_date'),
        'day': _day(node.get('published_date')),
        'show_title': (show.get('title') or '').strip(),
        'show_url': (show.get('url') or '').strip(),
        'page_url': (node.get('url') or '').strip(),
        'key': episode_key(node.get('url')),
        'taxonomies': [t for t in tx if t],
    }


# ─── Queries ──────────────────────────────────────────────────────────────────

_Q_SHOWS = '''query Shows($station: StationsEnum!, $first: Int!, $after: String) {
  shows(station: $station, first: $first, after: $after) {
    edges { cursor node { id title url standFirst } }
  }
}'''

_Q_SHOW_BY_URL = '''query ShowByUrl($url: String!) {
  showByUrl(url: $url) { id title url standFirst }
}'''

_Q_EPISODES = '''query EpisodesOfShow($url: String!, $first: Int!) {
  diffusionsOfShowByUrl(url: $url, first: $first) {
    edges { node { id title url published_date podcastEpisode { url duration }
                   taxonomiesConnection { edges { node { id } } } } }
  }
}'''

# `path` is deliberately NOT requested: it is null for some tags and the API
# then raises "Cannot return null for non-nullable field Taxonomy.path".
_Q_TAXONOMIES = '''query Taxonomies($types: [TaxonomyTypeEnum!], $first: Int!, $after: String) {
  taxonomies(types: $types, first: $first, after: $after) {
    edges { cursor node { id type title } }
  }
}'''

# Themes carry a hierarchy path whose depth selects the diffusions() argument.
# Only asked for THEME: for some tags `path` is null and the API then raises
# "Cannot return null for non-nullable field Taxonomy.path".
_Q_TAXONOMIES_PATH = '''query Taxonomies($types: [TaxonomyTypeEnum!], $first: Int!, $after: String) {
  taxonomies(types: $types, first: $first, after: $after) {
    edges { cursor node { id type title path } }
  }
}'''

_Q_DIFFUSIONS = '''query Diffusions($station: StationsEnum!, $themes: [String!], $tags: [String!],
                  $subthemes: [String!], $subsubthemes: [String!],
                  $start: Int!, $end: Int!, $first: Int!) {
  diffusions(station: $station, themes: $themes, tags: $tags,
             subthemes: $subthemes, subsubthemes: $subsubthemes,
             start: $start, end: $end, first: $first) {
    edges { node { id title url published_date show { title url }
                   podcastEpisode { url duration }
                   taxonomiesConnection { edges { node { id } } } } }
  }
}'''


def _edges(data, field):
    return (((data or {}).get(field) or {}).get('edges')) or []


def list_shows(api_key, station, first=MAX_PAGE, after=None):
    """One page of a station's show catalogue → (rows, last_cursor).

    `Shows` exposes no pageInfo, so paging follows the last edge's cursor and
    stops when a page comes back short.
    """
    first = max(1, min(int(first or MAX_PAGE), MAX_PAGE))
    data = _gql(api_key, _Q_SHOWS, {'station': station, 'first': first, 'after': after})
    edges = _edges(data, 'shows')
    rows = [show_row(e['node'], station) for e in edges if e and e.get('node')]
    # A short RAW page means the end; `cursor` is None then so the caller can
    # simply page until it is falsy. Never base this on the FILTERED rows: one
    # show without a url would look like a short page and truncate the catalogue.
    cursor = edges[-1].get('cursor') if len(edges) >= first else None
    return [r for r in rows if r['uri']], cursor


def show_by_url(api_key, url):
    """Resolve a show page URL. An episode URL is retried against its parent."""
    if not url:
        return None
    info = parse_rf_url(url)
    target = info['show_url'] if info else url
    data = _gql(api_key, _Q_SHOW_BY_URL, {'url': target})
    node = (data or {}).get('showByUrl')
    if not node and info and info['url'] != target:
        data = _gql(api_key, _Q_SHOW_BY_URL, {'url': info['url']})
        node = (data or {}).get('showByUrl')
    if not node:
        return None
    slug = (info or {}).get('station') or ''
    return show_row(node, STATIONS.get(slug.replace('-', '')))


def episodes_of_show(api_key, show_url, first=20):
    """Latest episodes of a show, newest first, audio-bearing only."""
    if not show_url:
        return []
    info = parse_rf_url(show_url)
    target = info['show_url'] if info else show_url
    first = max(1, min(int(first or 20), MAX_PAGE))

    def fetch():
        data = _gql(api_key, _Q_EPISODES, {'url': target, 'first': first})
        rows = []
        for e in _edges(data, 'diffusionsOfShowByUrl'):
            row = episode_row((e or {}).get('node') or {})
            if row:
                row['page_url'] = ((e.get('node') or {}).get('url') or '')
                rows.append(row)
        return rows

    return _cached(f'rfep:{target}:{first}', fetch, _TTL_EPISODES) or []


def list_taxonomies(api_key, kinds=('THEME',), first=MAX_PAGE, after=None):
    """One page of themes/tags → (rows, last_cursor)."""
    first = max(1, min(int(first or MAX_PAGE), MAX_PAGE))
    want_path = all(str(k).upper() == 'THEME' for k in kinds)
    data = _gql(api_key, _Q_TAXONOMIES_PATH if want_path else _Q_TAXONOMIES,
                {'types': list(kinds), 'first': first, 'after': after})
    edges = _edges(data, 'taxonomies')
    rows = []
    for e in edges:
        n = (e or {}).get('node') or {}
        if n.get('id') and n.get('title'):
            rows.append({'id': n['id'], 'title': (n.get('title') or '').strip(),
                         'kind': (n.get('type') or '').strip(),
                         'path': (n.get('path') or '').strip()})
    cursor = edges[-1].get('cursor') if len(edges) >= first else None
    return rows, cursor


def diffusions(api_key, station, themes=None, tags=None, subthemes=None,
               subsubthemes=None, days=MAX_WINDOW_DAYS, first=50):
    """Episodes published on a station over the last `days` (≤7, server cap),
    optionally filtered by taxonomy IDs. Filters take IDs, never paths."""
    days = max(1, min(int(days or MAX_WINDOW_DAYS), MAX_WINDOW_DAYS))
    first = max(1, min(int(first or 50), MAX_PAGE))
    end = int(time.time())
    start = end - days * 86400
    themes = [t for t in (themes or []) if t]
    tags = [t for t in (tags or []) if t]
    subthemes = [t for t in (subthemes or []) if t]
    subsubthemes = [t for t in (subsubthemes or []) if t]

    def fetch():
        data = _gql(api_key, _Q_DIFFUSIONS, {
            'station': station, 'themes': themes or None, 'tags': tags or None,
            'subthemes': subthemes or None, 'subsubthemes': subsubthemes or None,
            'start': start, 'end': end, 'first': first})
        if data is None:
            return None            # transport/auth failure — retry next time
        rows = []
        for e in _edges(data, 'diffusions'):
            row = episode_row((e or {}).get('node') or {})
            if row:
                rows.append(row)
        return rows                # may legitimately be empty

    key = (f"rfdiff:{station}:{','.join(themes)}:{','.join(subthemes)}:"
           f"{','.join(subsubthemes)}:{','.join(tags)}:{days}:{first}")
    return _cached(key, fetch, _TTL_EPISODES, cache_empty=True) or []
