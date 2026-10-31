"""`tv:` box lines: a box that plays a video on a TV instead of the tracklist.

A box holding only `tv:` lines (labels, directives and windows aside) is a TV
trigger, like a box holding only `meta_all` is the ALL button: /api/box hands it
here instead of filling the tracklist. Putting the tag down casts the video to
the Cast receiver named in o2m.conf; taking it off closes the YouTube app.

    tv:https://www.youtube.com/watch?v=rwalpfPkQvk&list=PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr
    tv:https://www.youtube.com/playlist?list=UU...      (a channel's uploads)
    08:00-19:00 > tv:https://youtu.be/rwalpfPkQvk     (no TV after 7pm)

Several lines → one drawn at random among those whose window applies now, never
the one the box played last. When none applies, the tag does nothing: that is
how a time window says "not now". A playlist starts at a random video when it
can be read (yt_dlp, flat extraction); a private one cannot, and starts at the
video the line names.

The receiver is the YouTube app of the TV box, driven through its lounge API
(pychromecast's YouTubeController): the TV fetches the stream itself, so nothing
here resolves a video — catt's route through yt_dlp was refused by YouTube on
the first try. While the app runs, a watcher follows its media status and
records each video watched as a `tv:yt:<id>` Track row (see play_record).

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


_PLAYLIST_TTL = 6 * 3600       # a playlist changes over days
_PLAYLIST_FAIL_TTL = 3600       # an unreadable one is asked again within the hour
_playlists = {}                 # playlist id -> (expires, [video ids] or None)


def playlist_entries(playlist_id):
    """The video ids of a playlist, or None when it cannot be read — a PRIVATE
    playlist answers "The playlist does not exist" to anyone but its owner, even
    though the TV, signed in, plays it. Flat extraction: no format resolution."""
    hit = _playlists.get(playlist_id)
    if hit and hit[0] > time.time():
        return hit[1]
    ids = None
    try:
        import yt_dlp
        opts = {'quiet': True, 'skip_download': True, 'extract_flat': 'in_playlist',
                'no_warnings': True, 'playlistend': 500}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}',
                                    download=False)
        ids = [e['id'] for e in (info.get('entries') or []) if e and e.get('id')] or None
    except Exception as e:
        print(f"TV: playlist {playlist_id} unreadable: {str(e)[:120]}")
    _playlists[playlist_id] = (time.time() + (_PLAYLIST_TTL if ids else _PLAYLIST_FAIL_TTL), ids)
    return ids


def pick_start(video_id, playlist_id, rng=random):
    """The video to start a playlist at: one drawn at random when the playlist
    can be read, else the one the line names. The lounge API starts a playlist
    AT a video and ignores an index (measured: `_currentIndex` 5 still played
    the named video), so randomness has to come from knowing the ids."""
    if playlist_id:
        ids = playlist_entries(playlist_id)
        if ids:
            return rng.choice(ids)
    if not video_id:
        raise RuntimeError(f"playlist {playlist_id} cannot be read and the line names no video")
    return video_id


def play(target, video_id, playlist_id=None):
    """Start a video (and the playlist after it) on the receiver's YouTube app.
    Returns the connected Chromecast, left open for the watcher."""
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
    except Exception:
        cast.disconnect()
        raise
    return cast


def stop(target, cast=None):
    """Close the YouTube app, which brings the TV back to its home screen. Any
    other app is left alone: the tag only takes off what it put on."""
    own = cast is None
    cast = cast or _connect(target)
    try:
        if cast.app_id == YOUTUBE_APP_ID:
            cast.quit_app()
            return True
        return False
    finally:
        if own:
            cast.disconnect()


# ─── What the TV played ──────────────────────────────────────────────────────

URI_PREFIX = 'tv:yt:'           # a Track row per video watched on the TV
POLL_S = 5
MIN_WATCH_MS = 20000            # less than this is a zap, not a viewing


def play_record(video, title, duration_s, position_s):
    """(uri, name, length_ms, position_ms) for one video seen on the TV, or None
    when it was barely on.

    The uri is `tv:yt:<id>`, NOT the `yt:video:<id>` Mopidy-YouTube uses: the
    pools match `yt:%` by prefix, and `podcasts:unfinished` takes any long
    YouTube video half-heard — a cartoon half-watched would come back as audio
    in a music box, on o2m_0's older code too (same database). Under its own
    prefix the row is indexed and served by nothing."""
    if not video:
        return None
    pos = int((position_s or 0) * 1000)
    length = int(duration_s * 1000) if duration_s else None
    if pos < MIN_WATCH_MS and not (length and pos >= 0.9 * length):
        return None
    return URI_PREFIX + video, title, length, pos


class _Watcher(threading.Thread):
    """Follows the receiver while the YouTube app runs, and reports each video
    when the next one starts, when the app closes, or when the tag is taken off.
    The receiver pushes its media status; this only reads the latest one."""

    def __init__(self, cast, on_play):
        super().__init__(daemon=True)
        self.cast, self.on_play = cast, on_play
        self._halt = threading.Event()
        self.cur = None

    def run(self):
        try:
            while not self._halt.wait(POLL_S):
                if self.cast.app_id != YOUTUBE_APP_ID:
                    break
                self._sample()
        except Exception as e:
            print(f"TV watcher error: {e}")
        finally:
            self._flush()
            if not self._halt.is_set():
                self.cast.disconnect()

    def _sample(self):
        st = self.cast.media_controller.status
        vid = getattr(st, 'content_id', None)
        if not vid:
            return
        if self.cur and self.cur['id'] != vid:
            self._flush()
        if not self.cur:
            self.cur = {'id': vid, 'title': None, 'dur': None, 'pos': 0}
        self.cur['title'] = st.title or self.cur['title']
        self.cur['dur'] = st.duration or self.cur['dur']
        self.cur['pos'] = max(self.cur['pos'], st.adjusted_current_time or st.current_time or 0)

    def _flush(self):
        c, self.cur = self.cur, None
        rec = c and play_record(c['id'], c['title'], c['dur'], c['pos'])
        if rec and self.on_play:
            try:
                self.on_play(*rec)
            except Exception as e:
                print(f"TV play record error ({rec[0]}): {e}")

    def halt(self):
        """Report what is on and stop following; the connection stays open for
        the caller (stop() quits the app through it)."""
        self._halt.set()
        self.join(timeout=POLL_S + 2)


# ─── The box action ──────────────────────────────────────────────────────────

_lock = threading.Lock()
_active = {}  # box uid -> the reference it cast
_last = {}    # box uid -> the reference it cast last, on or off
_watcher = None


def is_active(uid):
    return uid in _active


def pick_ref(uid, refs, rng=random):
    """One of a box's lines, never the one it played last when it has others:
    with two lines a fair draw repeats one half the time, and a tag put down
    again to change the programme read as the tag not working."""
    pool = [r for r in refs if r[0] != _last.get(uid)] or refs
    return rng.choice(pool)


def _halt_watcher():
    global _watcher
    w, _watcher = _watcher, None
    if w:
        w.halt()
    return w


def box_action(box, mode, config, pause_music=None, on_play=None):
    """Toggle / add / remove a TV box, with the same truth table as a box.
    `on_play(uri, name, length_ms, position_ms)` records each video watched.
    Returns the sentence /api/box answers."""
    global _watcher
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
            w = _halt_watcher()
            try:
                closed = stop(target, w.cast if w else None)
            except Exception as e:
                print(f"TV stop error: {e}")
                return f"TV: {e}"
            finally:
                if w:
                    w.cast.disconnect()
            return "TV removed" if (closed or on) else "No action"
        # An `add` while already on casts again rather than answering "No
        # action": the TV may have been switched off or YouTube closed with the
        # remote since, and a tag put down means "the video, now".
        refs = [(r, parse_youtube(r)) for r in tv_refs(box.data)]
        refs = [(r, p) for r, p in refs if p]
        if not refs:
            return "TV: nothing to play at this hour"
        ref, (video, playlist) = pick_ref(box.uid, refs)
        w = _halt_watcher()   # the video on now is reported before it is replaced
        if w:
            w.cast.disconnect()
        try:
            start = pick_start(video, playlist)
            cast = play(target, start, playlist)
        except Exception as e:
            print(f"TV play error ({ref}): {e}")
            return f"TV: {e}"
        # One screen, one video: another TV box still marked on was replaced.
        _active.clear()
        _active[box.uid] = ref
        _last[box.uid] = ref
        _watcher = _Watcher(cast, on_play)
        _watcher.start()
        print(f"TV: {box.uid} cast {start} from {ref}")
        try:
            if pause_music and config.getboolean('tv', 'pause_music', fallback=True):
                pause_music()
        except Exception as e:
            print(f"TV pause_music error: {e}")
        return "TV added"
