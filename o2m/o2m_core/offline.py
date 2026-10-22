"""Handing audio bytes to a listening device, so it can play without the server.

O2M already had an offline path, and it is the OTHER one: `spotdl/cache.py`
downloads the Spotify tracks of the pinned boxes into the music volume and
registers each file on `Track.local_uri`, which `_resolve_uri` then substitutes
at fill time. That cache lives on the server and only ever fed Mopidy. This
module is what lets a browser take a copy of it.

Three constraints shape everything here, and none of them is negotiable:

* **Spotify cannot be downloaded.** librespot decrypts into GStreamer, never
  into a file, so a phone can only ever receive a track the server holds as an
  actual file — i.e. one spotdl has fetched. Every music uri therefore resolves
  through `Track.local_uri`; a track without one is `pending` (queued for
  spotdl), not `ready`, and never `unavailable` unless it cannot be fetched at
  all.

* **The paths in the database are Mopidy's, not ours.** spotdl writes
  `local_uri` as `file:///app/Music/…` — the path as the MOPIDY container sees
  it. This container mounts the same volume elsewhere, so every path is rebased
  from `media_dir` onto `MUSIC_MOUNT`. It is the same translation spotdl does in
  the other direction (`file_to_mopidy_uri`), and the reason the o2m service
  mounts `./data/music` read-only.

* **Spoken content is a remote URL, and the browser may not fetch it itself.**
  A podcast CDN rarely sends `Access-Control-Allow-Origin`, so a cross-origin
  fetch from the page fails with nothing to catch. Episodes are therefore
  streamed back through this server like everything else: one shape for the
  client, `/api/audio?uri=…`, whatever sits behind it.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.request

# Where THIS container sees the music volume, and where MOPIDY sees it (the
# prefix `local_uri` carries). Kept separate on purpose: they are two mounts of
# one volume, and assuming they are equal is what silently breaks file lookup.
MUSIC_MOUNT = os.environ.get('O2M_MUSIC_MOUNT', '/music')
_FEED_UA = 'o2m/1.0'

# Extension → what the browser is told it is receiving. A wrong type makes
# <audio> refuse the blob, so an unknown one falls back to a generic stream
# rather than to a guess.
_MIME = {
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.mp4': 'audio/mp4',
    '.aac': 'audio/aac', '.ogg': 'audio/ogg', '.oga': 'audio/ogg',
    '.opus': 'audio/ogg', '.flac': 'audio/flac', '.wav': 'audio/wav',
    '.wma': 'audio/x-ms-wma', '.aiff': 'audio/aiff', '.m4b': 'audio/mp4',
    '.webm': 'audio/webm',
}


def media_dir(config=None) -> str:
    """The music root as Mopidy writes it into `local_uri` — `[local] media_dir`."""
    try:
        if config is not None and 'local' in config and 'media_dir' in config['local']:
            return (config['local']['media_dir'] or '').rstrip('/') or '/app/Music'
    except Exception:
        pass
    return (os.environ.get('LOCAL_MEDIA_DIR') or '/app/Music').rstrip('/')


def mime_for(path: str) -> str:
    return _MIME.get(os.path.splitext(path)[1].lower(), 'application/octet-stream')


def is_music_uri(uri: str) -> bool:
    return bool(uri) and uri.startswith(('spotify:track:', 'local:track:', 'file://'))


def is_spoken_uri(uri: str) -> bool:
    return bool(uri) and uri.startswith('podcast+')


def is_youtube_uri(uri: str) -> bool:
    """A single YouTube VIDEO — not a playlist or a channel, which hold many."""
    if not uri or not uri.startswith(('yt:', 'youtube:')):
        return False
    from o2m_core.webmedia import youtube_video_id
    return bool(youtube_video_id(uri)) and ':playlist:' not in uri and ':channel:' not in uri


# ── Files the server holds ────────────────────────────────────────────────────

def _rebase(path: str, config=None) -> str | None:
    """Translate a Mopidy-side absolute path onto this container's mount.

    Also the security boundary: the result must stay under MUSIC_MOUNT. The uri
    reaches us from a query string, so `..` in it is a given, not a worry —
    `realpath` collapses it and the prefix check rejects whatever escaped.
    """
    root = media_dir(config)
    if path.startswith(root + '/'):
        path = MUSIC_MOUNT + path[len(root):]
    elif not path.startswith(MUSIC_MOUNT + '/'):
        return None
    real = os.path.realpath(path)
    mount = os.path.realpath(MUSIC_MOUNT)
    if real != mount and not real.startswith(mount + os.sep):
        return None
    return real


def local_file_for(uri: str, db=None, config=None) -> str | None:
    """Absolute path of the file backing this uri here, or None.

    Resolves one indirection: a Spotify uri has no file of its own, only the one
    spotdl fetched for it and recorded on `Track.local_uri`.
    """
    if not uri:
        return None
    if uri.startswith('spotify:track:') or is_spoken_uri(uri) or is_youtube_uri(uri):
        # An episode or a video too, once the server keeps a copy (spotdl's
        # spoken queue): same column, same indirection.
        if db is None:
            return None
        try:
            local = db.get_local_uri(uri)
        except Exception:
            local = None
        return local_file_for(local, db=None, config=config) if local else None
    if uri.startswith('file://'):
        return _rebase(urllib.parse.unquote(uri[len('file://'):]), config)
    if uri.startswith('local:track:'):
        rel = urllib.parse.unquote(uri[len('local:track:'):])
        return _rebase(os.path.join(media_dir(config), rel.lstrip('/')), config)
    return None


def file_present(uri: str, db=None, config=None) -> bool:
    """Whether the bytes behind `uri` are on THIS instance's disk.

    A `local_uri` says a file was registered; it does not say the file is here.
    The column is global and the disks are not: several instances share one
    database, the numbered ones share one music volume and the Raspberry Pi
    shares neither — so a row written by one instance names a path another
    cannot open. The cache cleaner leaves dangling rows too: it swallows the
    error if its unregister call fails, and the instance that prunes a shared
    tree is not always the one holding the row.

    True when the volume is not mounted here at all, which is the same answer
    `_resolve_uri` trusts: without the mount we cannot tell a missing file from
    a missing mount, and reading that as "absent" would make every instance
    that never added the mount re-queue the whole cache it already holds.
    """
    try:
        if not os.path.isdir(MUSIC_MOUNT):
            return True                      # no mount: trust the database
        path = local_file_for(uri, db=db, config=config)
        return bool(path) and os.path.isfile(path)
    except Exception:
        return True


# ── Episodes the server can fetch on the device's behalf ──────────────────────

_enclosures: dict[str, tuple[float, dict[str, tuple[str, int]]]] = {}
_ENCLOSURE_TTL = 900   # seconds; a feed's audio urls are stable, its item list is not


def feed_enclosures(feed_url: str) -> dict[str, tuple[str, int]]:
    """`guid -> (audio url, declared bytes)` for one feed.

    Parsed with the same regex reading as `_feed_index` in o2mtomopidy rather
    than a parser dependency: the two fields wanted here are attributes of a
    single tag, and podcast feeds are too irregular to reward strictness.
    """
    hit = _enclosures.get(feed_url)
    if hit and (time.time() - hit[0]) < _ENCLOSURE_TTL:
        return hit[1]
    out: dict[str, tuple[str, int]] = {}
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': _FEED_UA})
        raw = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
        for item in re.findall(r'<item>(.*?)</item>', raw, re.S):
            g = re.search(r'<guid[^>]*>([^<]+)</guid>', item)
            e = re.search(r'<enclosure\b([^>]*)>', item, re.I)
            if not g or not e:
                continue
            attrs = e.group(1)
            u = re.search(r'\burl\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
            if not u:
                continue
            ln = re.search(r'\blength\s*=\s*["\'](\d+)["\']', attrs, re.I)
            out[g.group(1).strip()] = (u.group(1).strip(), int(ln.group(1)) if ln else 0)
    except Exception as exc:
        print(f"offline.feed_enclosures({feed_url}): {exc}")
        return hit[1] if hit else {}
    _enclosures[feed_url] = (time.time(), out)
    return out


def episode_media_url(uri: str) -> tuple[str | None, int]:
    """`(audio url, declared bytes)` behind a `podcast+<feed>#<guid>` uri."""
    if not is_spoken_uri(uri):
        return None, 0
    rest = uri[len('podcast+'):]
    feed, _, guid = rest.partition('#')
    if not feed or not guid:
        return None, 0
    return feed_enclosures(feed).get(guid, (None, 0))


# ── What the device is told about a uri ───────────────────────────────────────

def describe(uri: str, db=None, config=None) -> dict:
    """One uri's offline availability, as the UI's download pass reads it.

    `ready`       — bytes are servable now, at `/api/audio?uri=…`.
    `pending`     — a music track with no file yet; spotdl has to fetch it first.
    `unavailable` — nothing can make this downloadable (a live radio has no end,
                    an episode dropped from its feed).

    A YouTube video is `ready` without being resolved: resolving costs ~2 s per
    item and its url expires, so `/api/audio` does it when the bytes are asked
    for (`webmedia.youtube_audio`). It is spoken content, as the server files it
    (`_SPOKEN_URI_RE`): it resumes, and a finished one is not downloaded.

    `held` says the SERVER has the file. A spoken item it does not hold is still
    `ready` — relayed from its source — and is queued for the server to keep, so
    the next device (and Mopidy) read it from disk instead of the network.
    """
    if is_spoken_uri(uri) or is_youtube_uri(uri):
        path = local_file_for(uri, db=db, config=config)
        if path and os.path.isfile(path):
            return {'uri': uri, 'kind': 'spoken', 'state': 'ready', 'held': True,
                    'bytes': os.path.getsize(path), 'mime': mime_for(path)}
    if is_youtube_uri(uri):
        return {'uri': uri, 'kind': 'spoken', 'state': 'ready', 'held': False,
                'bytes': 0, 'mime': 'audio/mp4'}
    kind = 'music' if is_music_uri(uri) else ('spoken' if is_spoken_uri(uri) else 'other')
    if kind == 'music':
        path = local_file_for(uri, db=db, config=config)
        if path and os.path.isfile(path):
            return {'uri': uri, 'kind': kind, 'state': 'ready', 'held': True,
                    'bytes': os.path.getsize(path), 'mime': mime_for(path)}
        if uri.startswith('spotify:track:'):
            return {'uri': uri, 'kind': kind, 'state': 'pending', 'bytes': 0,
                    'reason': 'no local file yet'}
        # A local: or file: uri whose file is gone is a stale row, not a wait.
        return {'uri': uri, 'kind': kind, 'state': 'unavailable', 'bytes': 0,
                'reason': 'file missing'}
    if kind == 'spoken':
        url, size = episode_media_url(uri)
        if url:
            return {'uri': uri, 'kind': kind, 'state': 'ready', 'held': False,
                    'bytes': size, 'mime': mime_for(urllib.parse.urlparse(url).path)}
        return {'uri': uri, 'kind': kind, 'state': 'unavailable', 'bytes': 0,
                'reason': 'no enclosure in feed'}
    return {'uri': uri, 'kind': kind, 'state': 'unavailable', 'bytes': 0,
            'reason': 'not downloadable'}
