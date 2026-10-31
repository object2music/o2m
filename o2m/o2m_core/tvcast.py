"""`tv:` box lines: a box that plays a video on a TV instead of the tracklist.

A box holding only `tv:` lines (labels, directives and windows aside) is a TV
trigger, like a box holding only `meta_all` is the ALL button: /api/box hands it
here instead of filling the tracklist. Putting the tag down casts the video to
the Cast receiver named in o2m.conf; taking it off closes the YouTube app.

    tv:https://www.youtube.com/watch?v=rwalpfPkQvk&list=PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr
    tv:https://www.youtube.com/playlist?list=UU...      (a channel's uploads)
    08:00-19:00 > tv:https://youtu.be/rwalpfPkQvk     (no TV after 7pm)

Several lines → one drawn at random among those whose window applies now. When
none applies, the tag does nothing: that is how a time window says "not now".

The receiver is the YouTube app of the TV box, driven through its lounge API
(pychromecast's YouTubeController): the TV fetches the stream itself, so nothing
here resolves a video — catt's route through yt_dlp was refused by YouTube on
the first try. A playlist without a video is the one case that needs an id
first: the lounge API starts a playlist AT a video, so its first entry is read
with yt_dlp (flat extraction, no format resolution).

`pychromecast` is an OPTIONAL dependency, deliberately absent from
requirements.txt: Cast only reaches the local network, so only the instance
beside the TV can use it, and it requires Python >= 3.11 (Pi #2 runs 3.9).
Without it, a TV box answers so and nothing else changes.

Config, o2m.conf:

    [tv]
    cast_host = 192.168.1.137    # an IP, or the receiver's Cast name ("WunderFull")
    pause_music = true           # pause Mopidy when a video starts
"""

import random
import re
import threading
import time
import urllib.parse

from o2m_core import boxdirectives as bdir

try:
    import pychromecast
    from pychromecast.controllers.youtube import YouTubeController
except ImportError:  # optional, see the module docstring
    pychromecast = None

PREFIX = 'tv:'
YOUTUBE_APP_ID = '233637DE'

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_IP_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


def available():
    return pychromecast is not None


# ─── Parsing (pure) ──────────────────────────────────────────────────────────

def parse_youtube(ref):
    """(video_id, playlist_id) for a YouTube reference, either may be None;
    None when it is not one. Accepts watch / youtu.be / shorts / playlist urls,
    `yt:video:<id>`, `yt:playlist:<id>` and a bare 11-character id."""
    ref = (ref or '').strip()
    if not ref:
        return None
    for scheme in ('yt:', 'youtube:'):
        if ref.startswith(scheme):
            kind, _, rid = ref[len(scheme):].partition(':')
            if kind == 'video' and rid:
                return rid, None
            if kind == 'playlist' and rid:
                return None, rid
            return None
    if _ID_RE.match(ref):
        return ref, None
    u = urllib.parse.urlparse(ref if '://' in ref else 'https://' + ref)
    host = (u.hostname or '').lower()
    if host.startswith('www.') or host.startswith('m.'):
        host = host.split('.', 1)[1]
    q = urllib.parse.parse_qs(u.query)
    playlist = (q.get('list') or [None])[0]
    video = None
    if host == 'youtu.be':
        video = u.path.strip('/').split('/')[0] or None
    elif host in ('youtube.com', 'music.youtube.com'):
        if u.path == '/watch':
            video = (q.get('v') or [None])[0]
        elif u.path.startswith(('/shorts/', '/live/', '/embed/')):
            video = u.path.split('/')[2] or None
        elif u.path != '/playlist':
            return None
    else:
        return None
    if video and not _ID_RE.match(video):
        video = None
    if not video and not playlist:
        return None
    return video, playlist


def _content(data, now=None):
    """(applies_now, payload) for every line that is content: not a label, not
    a directive."""
    return [(ok, p) for ok, p in bdir.iter_lines(data or '', now)
            if p and not p.startswith('#') and not bdir.is_directive(p)]


def is_tv_box(data):
    """True when every content line of the box is a `tv:` line, whatever the
    hour: a TV box whose windows are all shut is still a TV box — it must not
    fall through to the tracklist path and activate as an empty music box."""
    lines = _content(data)
    return bool(lines) and all(p.startswith(PREFIX) for _, p in lines)


def tv_refs(data, now=None):
    """The `tv:` references that apply now, prefix stripped."""
    return [p[len(PREFIX):].strip() for ok, p in _content(data, now)
            if ok and p.startswith(PREFIX)]


# ─── The receiver ────────────────────────────────────────────────────────────

_host_cache = {}


def _resolve_host(target):
    """An IP is used as is; anything else is the receiver's Cast name, found by
    mDNS (a few seconds, remembered for the process)."""
    if _IP_RE.match(target):
        return target
    if target in _host_cache:
        return _host_cache[target]
    casts, browser = pychromecast.get_listed_chromecasts(friendly_names=[target], discovery_timeout=8)
    try:
        if not casts:
            raise RuntimeError(f"no Cast receiver named {target!r} on the network")
        host = casts[0].cast_info.host
    finally:
        pychromecast.discovery.stop_discovery(browser)
    _host_cache[target] = host
    return host


def _connect(target):
    host = _resolve_host(target)
    cast = pychromecast.get_chromecast_from_host((host, 8009, None, None, None))
    cast.wait(timeout=10)
    return cast


def _first_of_playlist(playlist_id):
    import yt_dlp
    opts = {'quiet': True, 'skip_download': True, 'extract_flat': 'in_playlist',
            'playlistend': 1, 'no_warnings': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}', download=False)
    entries = list(info.get('entries') or [])
    if not entries or not entries[0].get('id'):
        raise RuntimeError(f"playlist {playlist_id} has no readable entry")
    return entries[0]['id']


def play(target, video_id, playlist_id=None):
    """Start a video (and the playlist after it) on the receiver's YouTube app."""
    if not video_id:
        video_id = _first_of_playlist(playlist_id)
    cast = _connect(target)
    try:
        yt = YouTubeController()
        cast.register_handler(yt)
        # The lounge session needs the app's screen id, which only a RUNNING app
        # reports: asked straight away, the pairing call fails with
        # "screen_ids parameter error" (measured on the Mi Box).
        yt.launch()
        for _ in range(20):
            if yt._screen_id:
                break
            time.sleep(0.5)
        yt.play_video(video_id, playlist_id=playlist_id)
    finally:
        cast.disconnect()


def stop(target):
    """Close the YouTube app, which brings the TV back to its home screen. Any
    other app is left alone: the tag only takes off what it put on."""
    cast = _connect(target)
    try:
        if cast.app_id == YOUTUBE_APP_ID:
            cast.quit_app()
            return True
        return False
    finally:
        cast.disconnect()


# ─── The box action ──────────────────────────────────────────────────────────

_lock = threading.Lock()
_active = {}  # box uid -> the reference it cast


def is_active(uid):
    return uid in _active


def box_action(box, mode, config, pause_music=None):
    """Toggle / add / remove a TV box, with the same truth table as a box.
    Returns the sentence /api/box answers."""
    if not available():
        return "TV: pychromecast is not installed on this instance"
    target = ''
    try:
        target = config.get('tv', 'cast_host', fallback='').strip()
    except Exception:
        pass
    if not target:
        return "TV: no [tv] cast_host in o2m.conf"
    with _lock:
        on = box.uid in _active
        # A remove closes YouTube even when this box is not marked on: the mark
        # is in memory, so after an o2m restart a tag taken off would otherwise
        # leave the video playing. stop() touches YouTube only.
        if mode == 'remove' or (mode == 'toogle' and on):
            _active.pop(box.uid, None)
            try:
                closed = stop(target)
            except Exception as e:
                print(f"TV stop error: {e}")
                return f"TV: {e}"
            return "TV removed" if (closed or on) else "No action"
        # An `add` while already on casts again rather than answering "No
        # action": the TV may have been switched off or YouTube closed with the
        # remote since, and a tag put down means "the video, now".
        refs = [(r, parse_youtube(r)) for r in tv_refs(box.data)]
        refs = [(r, p) for r, p in refs if p]
        if not refs:
            return "TV: nothing to play at this hour"
        ref, (video, playlist) = random.choice(refs)
        try:
            play(target, video, playlist)
        except Exception as e:
            print(f"TV play error ({ref}): {e}")
            return f"TV: {e}"
        # One screen, one video: another TV box still marked on was replaced.
        _active.clear()
        _active[box.uid] = ref
        print(f"TV: {box.uid} cast {ref}")
        try:
            if pause_music and config.getboolean('tv', 'pause_music', fallback=True):
                pause_music()
        except Exception as e:
            print(f"TV pause_music error: {e}")
        return "TV added"
