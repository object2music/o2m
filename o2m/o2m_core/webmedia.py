"""web:<url> — play the media a web page holds. Experimental.

Every other box line names something to play. `web:` names a PAGE and asks what
is playable inside it, which is a different act: the answer is not in the line,
it is on the other side of a fetch, and it changes when the page does.

Two steps, cached apart because they age at completely different rates:

1. DISCOVERY — the page, read once and parsed for media (`find_media`). A page
   changes over days, so it is memoised for hours.
2. RESOLUTION — one media reference turned into bytes a GStreamer pipeline can
   open (`resolve_stream`, via yt_dlp). Measured on Vimeo: the signed url handed
   back carried an expiry **5.8 hours out**, and these items run an hour each —
   a tracklist filled at six o'clock would hand a dead url to its fourth track.
   So resolution is late (at `tracklist.add`, through `_resolve_uri`) and its
   cache is minutes, not hours.

**The uri that lasts is not the url that plays.** `web:<media page>` is stable,
dedupes the same video found from two different pages, and is what carries the
resume position, the cooldown and the stats; the `https://…/sec2(…)` that comes
out of yt_dlp is valid for an afternoon. Everything durable keys on the former.

**Discovery routes to the existing schemes wherever one exists** — `web:` is only
worn by media nothing else in o2m can carry. A YouTube embed comes back as
`yt:video:<id>` (Mopidy-YouTube plays and caches it), an `<audio>` or a bare mp3
link as its plain https url (mopidy-stream), an RSS link as `podcast+<feed>`
(the whole podcast subsystem, with its episodes and its resume). Vimeo,
Dailymotion and the rest — no Mopidy backend, no file — are what `web:` is for.

**The embedding page is part of the extraction, and platforms disagree about
it.** Vimeo answers "Cannot download embed-only video without embedding URL" to
a request for its own player url and hands over the film when the same request
carries the page as `Referer`; Dailymotion resolves the identical url plain and
answers "No video formats found!" the moment one is attached. So the page
travels with the item — persistently in `Track.channel_id` (the page IS the
channel, the same field an episode uses to name its feed), and in `_ORIGIN` for
the fill that has just discovered it and has no row yet — but it is offered
SECOND, only after a plain attempt fails. See `resolve_stream`.

**A page can simply refuse.** uved.fr answers every client — plain, browser-UA,
Googlebot, facebookexternalhit alike — with a CrowdSec javascript challenge:
296 KB, HTTP 200, no media. That is not a bug to route around (solving it means
running a browser), it is an outcome to report: `find_media` returns an `error`
saying the page refused, rather than an empty list that reads as "nothing here".
"""

import datetime
import logging
import re
import time
from html import unescape
from urllib.parse import (urljoin, urlparse, parse_qs, parse_qsl,
                          urlencode, urlunparse)

import requests

log = logging.getLogger(__name__)

PREFIX = 'web:'
# The prefix this shipped under for a few days. Kept readable, never written:
# 'xp:' named a PHASE, not a thing, and a phase name in a primary key outlives
# the phase. Renamed while the footprint was still four rows and one box — the
# only moment it is free, since Track.uri IS the key and a later rename would be
# a non-additive migration on a database two instances share.
LEGACY_PREFIX = 'xp:'

# A browser's UA, deliberately. This is not evasion — a challenge page still
# wins, as uved.fr shows — but a good many sites serve a stripped page or a 403
# to an unknown agent, and the pages this feature exists for are ordinary public
# ones a person just opened in a tab.
USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
TIMEOUT = 15
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_URI = 255          # Track.uri is the primary key, varchar(255)

_TTL_PAGE = 6 * 3600        # a page's media list, in hours
_TTL_STREAM = 30 * 60       # a signed url, in minutes — see the expiry rule below
_EXPIRY_MARGIN = 10 * 60    # never hand out a url within this of its own expiry
_TTL_FAILURE = 5 * 60       # how long a refused extraction is remembered

# Platforms whose pages yt_dlp turns into a stream. yt_dlp supports some 1800
# sites; this list is not about what it CAN do, it is about what a page link is
# allowed to drag into a tracklist — without it, every share button and every
# footer link on a page becomes a candidate track.
_PLATFORMS = (
    'vimeo.com', 'dailymotion.com', 'dai.ly',
    'soundcloud.com', 'mixcloud.com', 'bandcamp.com',
    'canal-u.tv', 'ina.fr', 'arte.tv', 'ausha.co', 'acast.com',
    'podcloud.fr', 'spreaker.com', 'buzzsprout.com', 'megaphone.fm',
)
_YOUTUBE = ('youtube.com', 'youtu.be', 'youtube-nocookie.com')

# Extensions mopidy-stream opens directly, so they need no extractor at all.
_MEDIA_EXT = ('.mp3', '.m4a', '.aac', '.ogg', '.oga', '.opus', '.wav', '.flac',
              '.mp4', '.m4v', '.webm', '.m4b')

# Pages that answer with a challenge instead of themselves. All three of these
# return HTTP 200, so the status line cannot be the test — the title is.
_CHALLENGE_RE = re.compile(
    r'<title[^>]*>\s*(crowdsec|just a moment|attention required|checking your browser)',
    re.I)

_TAG_RE = re.compile(r'<(iframe|source|audio|video|link|meta|embed)\b([^>]*?)/?>', re.I)
_ANCHOR_RE = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.I | re.S)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"|'
                      r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*'([^']*)'")
_TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
_STRIP_RE = re.compile(r'<[^>]+>')
_YT_ID_RE = re.compile(r'(?:v=|/embed/|/shorts/|youtu\.be/|/v/)([A-Za-z0-9_-]{11})')

_cache = {}
# Discovered media -> the page it was found on, for the Referer. The DB copy in
# Track.channel_id is the durable one; this covers the window between a fill
# discovering an item and a row existing for it.
_ORIGIN = {}


def _cached(key, fn, ttl):
    """Memoise fn() for ttl seconds; a falsy answer is not cached, so a failed
    fetch is retried rather than remembered for six hours."""
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    value = fn()
    if value:
        _cache[key] = (time.time(), value)
    return value


def is_web_uri(uri):
    """True for a uri of this module — under either spelling, so rows and box
    lines written before the rename keep working without being rewritten."""
    return bool(uri) and str(uri).startswith((PREFIX, LEGACY_PREFIX))


is_xp = is_web_uri        # old name, kept so no call site breaks mid-rename


def media_url(uri):
    """The url inside a `web:` uri (or a legacy `xp:`). Idempotent on a bare url."""
    u = str(uri or '')
    for p in (PREFIX, LEGACY_PREFIX):
        if u.startswith(p):
            return u[len(p):]
    return u


def as_uri(url):
    return PREFIX + str(url or '')


def is_page_url(value):
    v = (value or '').strip()
    return v.startswith(('http://', 'https://')) and ' ' not in v


def origin_of(uri, fallback=None):
    """The page an item was found on — the Referer an extractor may need."""
    return _ORIGIN.get(media_url(uri)) or fallback or None


def remember_origin(uri, page):
    if page:
        _ORIGIN[media_url(uri)] = page


# ── 1. Discovery: what does this page hold? ───────────────────────────────────

def _attrs(blob):
    out = {}
    for m in _ATTR_RE.finditer(blob or ''):
        k = (m.group(1) or m.group(3) or '').lower()
        out[k] = unescape(m.group(2) if m.group(1) else (m.group(4) or ''))
    return out


def _clean_label(text, limit=160):
    s = unescape(_STRIP_RE.sub(' ', text or ''))
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:limit]


def _host(url):
    try:
        return (urlparse(url).hostname or '').lower()
    except Exception:
        return ''


def _on(url, hosts):
    h = _host(url)
    return any(h == d or h.endswith('.' + d) for d in hosts)


def _youtube_uri(url):
    """A YouTube link as Mopidy-YouTube's own uri — it plays and caches it, and
    `_is_spoken_uri` already knows the scheme."""
    m = _YT_ID_RE.search(url or '')
    if m:
        return 'yt:video:' + m.group(1)
    try:
        vid = parse_qs(urlparse(url).query).get('v', [''])[0]
        return 'yt:video:' + vid if len(vid) == 11 else ''
    except Exception:
        return ''


# Query parameters that say how a player should behave, not what it should
# play, plus the usual campaign tracking. They are what makes the SAME video
# arrive under two spellings from two pages.
_NOISE_PARAMS = {
    'autoplay', 'autopause', 'badge', 'player_id', 'app_id', 'muted', 'loop',
    'byline', 'portrait', 'title', 'dnt', 'controls', 'api', 'transparent',
    'fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'referrer', 'origin',
}


def canonical_media_url(url):
    """One spelling per media, because the uri IS the identity.

    `Track.uri` carries the resume position, the cooldown and the whole history,
    so two spellings of one video are two histories of half a listener each —
    and pages spell generously: the shortener (`dai.ly/x` for
    `dailymotion.com/video/x`, observed on the same page as its long form) and a
    trail of player parameters that differ per embed.

    What is NOT dropped matters as much: Vimeo's `h=` is the unlisted-video hash,
    without which the video does not exist. So this is a denylist of known noise,
    never an allowlist of known-good — an unrecognised parameter is kept, on the
    assumption that it might be load-bearing."""
    try:
        u = urlparse(url)
    except Exception:
        return url
    host, path = (u.hostname or '').lower(), u.path
    if host in ('dai.ly', 'www.dai.ly'):
        host, path = 'www.dailymotion.com', '/video' + path
    elif host == 'dailymotion.com':
        host = 'www.dailymotion.com'
    kept = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=False)
            if k.lower() not in _NOISE_PARAMS and not k.lower().startswith('utm_')]
    query = urlencode(kept)
    port = f':{u.port}' if u.port and u.port not in (80, 443) else ''
    return urlunparse((u.scheme.lower(), host + port, path.rstrip('/') or '/',
                       '', query, ''))


def classify(url, page=None):
    """One url -> the o2m uri that can play it, or '' for "not media".

    The whole routing rule lives here: the existing schemes first, `web:` only
    for what none of them carries."""
    url = (url or '').strip()
    if not url.startswith(('http://', 'https://')):
        return ''
    if _on(url, _YOUTUBE):
        # The id IS the canonical form here — Mopidy-YouTube's own uri, and the
        # same normalising instinct as canonical_media_url below.
        return _youtube_uri(url)
    path = urlparse(url).path.lower()
    if path.endswith(_MEDIA_EXT):
        return url                     # mopidy-stream opens it as-is
    if _on(url, _PLATFORMS):
        uri = as_uri(canonical_media_url(url))
        # `Track.uri` is the primary key, varchar(255). A uri that cannot be
        # stored is worse than an item not offered: the row would be refused at
        # insert and the item would vanish anyway, having first raised inside a
        # box fill. Normalisation above already removes the usual reason a media
        # url runs long.
        if len(uri) > MAX_URI:
            log.warning(f'web: uri too long to store ({len(uri)} chars): {uri[:80]}…')
            return ''
        remember_origin(uri, page)
        return uri
    return ''


def _fetch(url, timeout=None):
    r = requests.get(url, timeout=timeout or TIMEOUT, allow_redirects=True,
                     headers={'User-Agent': USER_AGENT,
                              'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                              'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'},
                     stream=True)
    r.raise_for_status()
    body = r.raw.read(MAX_PAGE_BYTES, decode_content=True) or b''
    enc = r.encoding or 'utf-8'
    return r.url, body.decode(enc, errors='replace')


def find_media(page_url, limit=12, timeout=None):
    """Read a page and return what o2m could play from it.

    -> {'page', 'title', 'items': [{'uri','name','url','kind'}], 'reason', 'error'}

    A failure comes back twice over, because two different readers need it:
    `reason` is a code to branch on ('challenge' | 'unreachable' | 'not-a-url'),
    `error` the sentence to show. Both empty means the page WAS read — and then
    an empty `items` honestly means it holds nothing playable, which is a
    different answer from a refusal and must not be reported as the same one."""
    page_url = (page_url or '').strip()
    if not is_page_url(page_url):
        return {'page': page_url, 'title': '', 'items': [],
                'reason': 'not-a-url', 'error': 'not a url'}

    # The pasted url may itself BE the media (a Dailymotion video, an mp3): then
    # there is no page to read and nothing to discover.
    direct = classify(page_url, page=page_url)
    if direct:
        return {'page': page_url, 'title': '', 'reason': '', 'error': '',
                'items': [{'uri': direct, 'name': '', 'url': page_url,
                           'kind': _kind_of(direct)}]}

    key = 'web:page:' + page_url
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _TTL_PAGE:
        return hit[1]

    try:
        final_url, html = _fetch(page_url, timeout)
    except Exception as e:
        # NOT cached, deliberately. A timeout or a 502 is an accident of the
        # minute; remembering it for six hours would turn one bad moment into an
        # afternoon of a box silently missing its page. The two outcomes below
        # are the opposite — a challenge and a parsed page are both stable facts
        # about the page, and re-fetching either on every box activation is the
        # waste this cache exists to avoid.
        log.error(f'find_media({page_url}): {e}')
        return {'page': page_url, 'title': '', 'items': [],
                'reason': 'unreachable', 'error': f'page unreachable: {e}'}

    if _CHALLENGE_RE.search(html[:4000]):
        out = {'page': page_url, 'title': '', 'items': [],
               'reason': 'challenge',
               'error': 'the page answered with an anti-bot challenge, '
                        'not with its content'}
    else:
        out = _parse(final_url, html, limit)
    _cache[key] = (time.time(), out)
    return out


def _kind_of(uri):
    if uri.startswith((PREFIX, LEGACY_PREFIX)):
        return 'web'
    if uri.startswith(('yt:', 'youtube:')):
        return 'yt'
    if uri.startswith('podcast+'):
        return 'feed'
    return 'stream'


def _parse(page_url, html, limit):
    title = _clean_label(_TITLE_RE.search(html).group(1)) if _TITLE_RE.search(html) else ''
    items, seen = [], set()

    def offer(url, label=''):
        if len(items) >= limit or not url:
            return
        url = urljoin(page_url, unescape(url.strip()))
        uri = classify(url, page=page_url)
        if not uri or uri in seen:
            return
        seen.add(uri)
        items.append({'uri': uri, 'name': _clean_label(label), 'url': url,
                      'kind': _kind_of(uri)})

    # Tags that declare media outright. <link rel=alternate type=rss> is kept
    # apart: a feed is a whole channel, not one item, so it is offered as
    # 'podcast+' and left to the podcast subsystem.
    feeds = []
    for tag, blob in _TAG_RE.findall(html):
        a = _attrs(blob)
        tag = tag.lower()
        if tag == 'link':
            if 'rss' in (a.get('type') or '') or 'atom' in (a.get('type') or ''):
                feeds.append((urljoin(page_url, a.get('href', '')), a.get('title') or title))
            continue
        if tag == 'meta':
            prop = (a.get('property') or a.get('name') or '').lower()
            if prop in ('og:video', 'og:video:url', 'og:video:secure_url',
                        'og:audio', 'og:audio:url', 'twitter:player'):
                offer(a.get('content', ''), title)
            continue
        offer(a.get('src') or a.get('data-src') or a.get('href') or '',
              a.get('title') or a.get('data-title') or title)

    # Plain links. The label is what the page calls it ("Lire le replay …") and
    # is PROVISIONAL: it is good enough for a search result, but the real title
    # comes from the extractor at resolution time and is what gets stored.
    for blob, inner in _ANCHOR_RE.findall(html):
        a = _attrs(blob)
        offer(a.get('href', ''), a.get('title') or inner)

    for feed_url, label in feeds:
        if len(items) >= limit or not feed_url:
            continue
        uri = 'podcast+' + feed_url
        if uri in seen:
            continue
        seen.add(uri)
        items.append({'uri': uri, 'name': _clean_label(label), 'url': feed_url,
                      'kind': 'feed'})

    return {'page': page_url, 'title': title, 'items': items,
            'reason': '', 'error': ''}


# ── 2. Resolution: one media reference -> bytes GStreamer can open ────────────

def _expiry_of(url):
    """When a signed url stops working, read out of the url itself.

    Every CDN signs differently, but they nearly all park a ten-digit epoch in
    the path or the query (Vimeo: `1789510922-0x…`; measured 5.8 h out). Take the
    earliest plausible one — guessing too SHORT only costs a re-resolution,
    guessing too long costs a track that dies mid-play."""
    now = time.time()
    best = None
    for m in re.finditer(r'\b(1[0-9]{9})\b', url or ''):
        v = int(m.group(1))
        if now < v < now + 7 * 86400:
            best = v if best is None else min(best, v)
    return best


def _extract(url, referer, timeout):
    """One yt_dlp attempt. Raises — the caller decides what a failure means."""
    import yt_dlp
    opts = {'quiet': True, 'no_warnings': True, 'skip_download': True,
            'noplaylist': True, 'socket_timeout': timeout or TIMEOUT,
            # bestaudio first: Dailymotion answers an audio-only HLS rendition
            # (hls-0_aac_q2), which is the whole point. Vimeo publishes no
            # audio-only format, so `best` there is a progressive mp4 whose
            # video track GStreamer decodes and drops — correct, just wasteful.
            'format': 'bestaudio/best'}
    if referer:
        opts['http_headers'] = {'Referer': referer}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _published_day(info):
    """When this was published, as the 'YYYY-MM-DD' the rest of the app stores.

    Three sources because extractors disagree about which they fill, measured on
    the pages this was built against: Dailymotion answers `upload_date` and a
    `timestamp`, Vimeo's on-demand extractor answers `upload_date`, and Vimeo's
    embed extractor answers **neither** — for that one there is genuinely no date
    anywhere, the embedding page carrying none either. It stays empty rather than
    being invented: a wrong date is worse than a blank one in a panel whose job
    is to say what is known about a track.
    """
    for key in ('upload_date', 'release_date'):
        raw = str(info.get(key) or '')
        if len(raw) == 8 and raw.isdigit():
            return f'{raw[:4]}-{raw[4:6]}-{raw[6:]}'
    for key in ('release_timestamp', 'timestamp'):
        ts = info.get(key)
        if ts:
            try:
                return datetime.datetime.fromtimestamp(
                    int(ts), datetime.timezone.utc).strftime('%Y-%m-%d')
            except Exception:
                pass
    return None


def resolve_stream(uri, referer=None, timeout=None):
    """`web:<media page>` -> {'url','name','length','day','expires_at'} or None.

    yt_dlp lives here rather than in the Mopidy image on purpose: this is the
    core deciding what to play, and the adapter is never the seat of that.

    **The Referer is tried second, not first.** Both halves of that were
    measured on this install, alternating on the same two videos:

      * Vimeo REQUIRES it. An embed-only video — what a film's own site uses —
        answers "Cannot download embed-only video without embedding URL" to
        every direct request, and hands over the film when the embedding page
        comes along as Referer.
      * Dailymotion REFUSES it. The identical canonical url resolves plain and
        answers "No video formats found!" the moment a Referer is attached.
        Reproduced three times in a row, alternating.

    So neither "always send it" nor "never" is right, and a per-host table of
    who wants one would just be wrong about the next platform. Asking plainly
    and retrying with the page costs one wasted request on embed-only videos,
    once, and is the only version that does not have to be told.
    """
    url = media_url(uri)
    if not url:
        return None
    referer = referer or origin_of(uri)
    key = 'web:stream:' + url

    hit = _cache.get(key)
    if hit:
        age, entry = time.time() - hit[0], hit[1]
        if entry is None:                      # a remembered failure, see below
            if age < _TTL_FAILURE:
                return None
        else:
            exp = entry.get('expires_at')
            if age < _TTL_STREAM and (not exp or time.time() < exp - _EXPIRY_MARGIN):
                return entry

    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        log.error('resolve_stream: yt_dlp is not installed in this image')
        return None

    info, first_error = None, None
    for attempt_referer in ((None, referer) if referer else (None,)):
        try:
            info = _extract(url, attempt_referer, timeout)
            if info and info.get('url'):
                break
            info = None
        except Exception as e:
            first_error = first_error or e
            info = None

    if not info or not info.get('url'):
        # A failure is remembered, briefly. Not to spare the platform — it is
        # to spare the BOX: without this, an item nothing can extract is asked
        # for again on every single fill, and each ask is a live network round
        # trip on the path that is filling a tracklist someone is waiting for.
        # Short, because the usual causes (a geo-block, a video pulled for an
        # hour, a bad minute) pass, and the item should come back by itself.
        log.error(f'resolve_stream({url}): {str(first_error or "no format")[:200]}')
        _cache[key] = (time.time(), None)
        return None

    length = info.get('duration')
    entry = {'url': info['url'],
             'name': (info.get('title') or '').strip()[:512],
             'length': int(length * 1000) if length else None,
             'day': _published_day(info),
             'expires_at': _expiry_of(info['url'])}
    _cache[key] = (time.time(), entry)
    return entry
