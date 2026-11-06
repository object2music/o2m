"""`tv:` box lines: a box that plays a video on a TV instead of the tracklist.

A box holding only `tv:` lines (labels, directives and windows aside) is a TV
trigger, like a box holding only `meta_all` is the ALL button: /api/box hands it
here instead of filling the tracklist. Putting the tag down casts the video to
the Cast receiver named in o2m.conf; taking it off closes the YouTube app.

    tv:https://www.youtube.com/watch?v=rwalpfPkQvk&list=PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr
    tv:https://www.youtube.com/playlist?list=UU...      (a channel's uploads)
    08:00-19:00 > tv:https://youtu.be/rwalpfPkQvk     (no TV after 7pm)

The box's `option_max_results` is a number of videos: past it, the watcher
closes YouTube (the playlist going on, or the app's autoplay). Unset = no limit.

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
    wake_fifo = /run/o2m-tv-remote.fifo   # the Bluetooth remote that wakes the box
    wake_key = wakeup            # `power` toggles: sent only when the box is off the network
    wake_wait = 30               # seconds to wait for it back on the network

A box in deep standby is OFF the network (no ping, no Cast), so no network
command reaches it; a key on its Bluetooth link wakes it, back on Cast ~6 s
later (measured on the Mi Box). That key comes from samples/tv-remote, a daemon
that makes the Pi a paired Bluetooth LE remote; here it is a word written to its
FIFO. Without `wake_fifo`, a sleeping box simply answers "unreachable".
"""

import os
import random
import re
import socket
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


_wake = {'fifo': '', 'key': 'wakeup', 'wait': 30}


def _configure(config):
    try:
        _wake['fifo'] = config.get('tv', 'wake_fifo', fallback='').strip()
        _wake['key'] = config.get('tv', 'wake_key', fallback='wakeup').strip() or 'wakeup'
        _wake['wait'] = config.getint('tv', 'wake_wait', fallback=30)
    except Exception as e:
        print(f"TV: [tv] wake settings unreadable: {e}")


def send_key(word):
    """Hand a key to the Bluetooth remote daemon. Non-blocking: with no daemon
    reading the FIFO, opening it fails (ENXIO) instead of hanging the request."""
    fifo = _wake['fifo']
    if not fifo:
        return False
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"TV: key {word} not sent, {fifo}: {e}")
        return False
    try:
        os.write(fd, (word + '\n').encode())
    finally:
        os.close(fd)
    return True


def _reachable(host, timeout=1.5):
    try:
        socket.create_connection((host, 8009), timeout=timeout).close()
        return True
    except OSError:
        return False


def _known_host(target):
    return target if _IP_RE.match(target) else _host_cache.get(target)


def _until(cond, seconds, step=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(step)
    return cond()


def _standby(cast):
    st = cast.status
    return bool(st is not None and st.is_stand_by)


def _connect_awake(target):
    """Connect to the receiver, waking it first when it sleeps.

    Two sleeps, two answers. Off the network (deep standby) the wake key is
    sent whatever it is: `power` then cannot be switching OFF a box that is on.
    On the network but in standby (Cast answers, the screen is off — launching
    an app there timed out, measured), only a key that never sleeps is sent:
    `is_stand_by` also reads true for a box left on another HDMI input.

    A key that never sleeps goes out FIRST, before anything is asked of the
    network: an awake box ignores it, and a sleeping one starts waking while
    the mDNS lookup of a name not yet known waits its 8 s for nothing (an o2m
    restart forgets the address: measured 12 s lost before the key, 38 s from
    the tag to the video)."""
    sent = _wake['key'] != 'power' and send_key(_wake['key'])
    host = _known_host(target)
    if host is None:
        try:
            host = _resolve_host(target)   # mDNS finds nothing while it sleeps
        except Exception:
            pass
    if host and _reachable(host):
        cast = _connect(target)
        if sent and _standby(cast):
            _until(lambda: not _standby(cast), 3)   # stuck true with the TV on, seen
        return cast
    if not (sent or send_key(_wake['key'])):
        return _connect(target)             # the usual "unreachable" error
    print(f"TV: receiver asleep, {_wake['key']} sent over Bluetooth")
    deadline = time.time() + _wake['wait']
    while time.time() < deadline:
        if host and _reachable(host):
            break
        if host is None:
            try:
                host = _resolve_host(target)
            except Exception:
                pass
        else:
            time.sleep(1)
    cast = _connect(target)
    _until(lambda: not _standby(cast), 10)
    return cast


SCREEN_ID_WAIT = 40            # s, from the launch to the app's screen id
_PLAYLIST_TTL = 6 * 3600       # a playlist changes over days
_PLAYLIST_FAIL_TTL = 3600       # an unreadable one is asked again within the hour
_playlists = {}                 # playlist id -> (expires, [video ids] or None)
_last_start = {}                # playlist id -> the video it last started at


def playable_entry(entry):
    """Can the TV play this flat playlist entry? A video deleted or made private
    by its uploader stays listed, with NO title (and no duration) — 26 of the 35
    of one playlist here, every one "Video unavailable". Started on one, the TV
    shows YouTube's error screen instead of the cartoon."""
    if not entry or not entry.get('id'):
        return False
    title = (entry.get('title') or '').strip()
    return bool(title) and title not in ('[Deleted video]', '[Private video]')


video_info = {}     # what a flat read says of a video, for what has no Track row yet


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
        entries = [e for e in (info.get('entries') or []) if playable_entry(e)]
        ids = [e['id'] for e in entries] or None
        video_info.update({e['id']: {'name': e.get('title') or '',
                                     'length': int((e.get('duration') or 0) * 1000)}
                           for e in entries})
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
            # Not the video it started at last time: 7 videos repeat one in 7.
            pool = [i for i in ids if i != _last_start.get(playlist_id)] or ids
            _last_start[playlist_id] = pick = rng.choice(pool)
            return pick
    if not video_id:
        raise RuntimeError(f"playlist {playlist_id} cannot be read and the line names no video")
    return video_id


def play(target, video_id, playlist_id=None, start_s=0):
    """Start a video (and the playlist after it) on the receiver's YouTube app,
    `start_s` seconds in. Returns the connected Chromecast, left open for the
    watcher."""
    cast = _connect_awake(target)
    try:
        yt = YouTubeController()
        cast.register_handler(yt)
        # The lounge session needs the app's screen id, which only a RUNNING app
        # reports: asked straight away, the pairing call fails with
        # "screen_ids parameter error" (measured on the Mi Box).
        # The app asks for it once, at launch; a cold start (the first after
        # the box woke) takes longer than that question waits, and the
        # answer never comes: ask again while the app comes up
        # (2026-11-01: YouTube up ~20 s after the launch).
        yt.launch()
        deadline = time.time() + SCREEN_ID_WAIT
        while not yt._screen_id and time.time() < deadline:
            if cast.app_id == YOUTUBE_APP_ID:
                yt.update_screen_id()       # blocks up to 10 s for the answer
            else:
                time.sleep(0.5)
        if not yt._screen_id:
            # Without it the pairing POSTs no body and YouTube answers a
            # baffling "411 Length Required" (2026-11-01, a box in standby
            # that no wake key reached).
            raise RuntimeError('the YouTube app did not start on the receiver'
                               + (' (in standby)' if _standby(cast) else ''))
        if start_s:
            # pychromecast's play_video has no start time; the lounge call
            # under it does (casttube's `_currentTime`).
            yt.start_session_if_none()
            yt._session.play_video(video_id, playlist_id or '', start_time=str(int(start_s)))
        else:
            yt.play_video(video_id, playlist_id=playlist_id)
    except Exception:
        cast.disconnect()
        raise
    return cast


def stop(target, cast=None):
    """Close the YouTube app, which brings the TV back to its home screen. Any
    other app is left alone: the tag only takes off what it put on."""
    own = cast is None
    if own:
        host = _known_host(target)
        if host and not _reachable(host):
            return False                    # asleep: nothing is playing
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
MIN_SHARE = 0.05                # update_stat_track's own artefact threshold
END_MARGIN_MS = 180000          # a film is over at its credits, not at 90%
BOOKMARK_S = 60                 # how often the position is saved while it plays
RESUME_BACK_S = 10              # a resume starts this much before the bookmark
RESUME_DAYS = 14                # an unfinished video older than this is not resumed


def video_finished(length_ms, position_ms):
    """Was this video watched to its end? update_stat_track's 90% is right for
    a song and wrong for a film: 90% of an hour-long one leaves six minutes. So
    the end is the last 3 minutes, or the last 10% of a video shorter than 30."""
    if not length_ms:
        return False
    return position_ms >= length_ms - min(END_MARGIN_MS, 0.1 * length_ms)


def resume_point(resume, video_id, playlist_id):
    """(video id, seconds) to resume at, or None. `resume(ids)` answers the
    unfinished video most recently watched among `ids` and its bookmark (ms):
    the ids of the line's playlist when it can be read, else its own video."""
    if not resume:
        return None
    ids = (playlist_entries(playlist_id) if playlist_id else None) or ([video_id] if video_id else [])
    if not ids:
        return None
    try:
        hit = resume(ids)
    except Exception as e:
        print(f"TV resume lookup error: {e}")
        return None
    if not hit:
        return None
    vid, pos_ms = hit
    return vid, max(0, int(pos_ms / 1000) - RESUME_BACK_S)


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
    # update_stat_track drops under 5% as an artefact — AFTER opening the row,
    # which left empty `new` rows behind (a 45 s look at an hour-long video).
    if length and pos < MIN_SHARE * length:
        return None
    return URI_PREFIX + video, title, length, pos


class _Watcher(threading.Thread):
    """Follows the receiver while the YouTube app runs, and reports each video
    when the next one starts, when the app closes, or when the tag is taken off.
    The receiver pushes its media status; this only reads the latest one."""

    def __init__(self, cast, on_play, limit=None, start=None, uid=None, on_bookmark=None):
        super().__init__(daemon=True)
        self.cast, self.on_play, self.limit, self.uid = cast, on_play, limit, uid
        # The position, saved while the video plays: until it is reported a
        # pause lives in memory only, and the Pi reboots every day.
        self.on_bookmark = on_bookmark
        # Until the video just cast shows up, the receiver may still report the
        # one it was playing before; counted, it would spend a limit of 1.
        self.start_id = start
        self._halt = threading.Event()
        self.cur = None
        self.seen = 0

    def run(self):
        try:
            while not self._halt.wait(POLL_S):
                if self.cast.app_id != YOUTUBE_APP_ID:
                    break
                if self._sample() == 'limit':
                    print(f"TV: {self.limit} video(s) played, closing YouTube")
                    self.cast.quit_app()
                    break
        except Exception as e:
            print(f"TV watcher error: {e}")
        finally:
            self._flush()
            if not self._halt.is_set():
                # Ended on its own (the app closed, the limit reached): the box
                # is no longer lit. Halted by box_action, that one decides.
                _active.pop(self.uid, None)
                self.cast.disconnect()

    def _sample(self):
        st = self.cast.media_controller.status
        vid = getattr(st, 'content_id', None)
        if not vid:
            return
        if self.start_id:
            if vid != self.start_id:
                return
            self.start_id = None
        if self.cur and self.cur['id'] != vid:
            self._flush()
        if not self.cur:
            # The box's max results is a number of VIDEOS: the one past it is
            # the playlist going on, or YouTube's autoplay once it ends.
            if self.limit and self.seen >= self.limit:
                return 'limit'
            self.seen += 1
            self.cur = {'id': vid, 'title': None, 'dur': None, 'pos': 0,
                        'marked': 0, 'mark_t': time.time()}
        self.cur['title'] = st.title or self.cur['title']
        self.cur['dur'] = st.duration or self.cur['dur']
        self.cur['pos'] = max(self.cur['pos'], st.adjusted_current_time or st.current_time or 0)
        self._bookmark(st)

    def _bookmark(self, st):
        """Save the position on a pause, and every BOOKMARK_S while it plays."""
        c = self.cur
        if not self.on_bookmark or c['pos'] == c['marked']:
            return
        if st.player_state != 'PAUSED' and time.time() - c['mark_t'] < BOOKMARK_S:
            return
        rec = play_record(c['id'], c['title'], c['dur'], c['pos'])
        if not rec:
            return
        c['marked'], c['mark_t'] = c['pos'], time.time()
        try:
            self.on_bookmark(*rec)
        except Exception as e:
            print(f"TV bookmark error ({rec[0]}): {e}")

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
_active = {}  # box uid -> {'ref', 'name', 'image'}: what it cast, how to draw it
_last = {}    # box uid -> the reference it cast last, on or off
_watcher = None


def is_active(uid):
    return uid in _active


def active_boxes():
    """uid -> {name, image} of the TV box on, for the Boxes column. A TV box
    never joins activeboxs (it owns no track), so this is how it lights."""
    return {uid: {'name': a['name'], 'image': a['image']} for uid, a in list(_active.items())}


def status():
    """What the TV is playing for a box, for the page: None when nothing is."""
    w = _watcher
    if not w or not w.is_alive() or w.uid not in _active:
        return None
    st = w.cast.media_controller.status
    vid = getattr(st, 'content_id', None)
    if not vid or (w.start_id and vid != w.start_id):
        vid = w.start_id   # just cast: the receiver still describes the previous one
        st = None
    return {
        'box_uid': w.uid,
        'box_name': _active[w.uid]['name'],
        'video': vid,
        'title': (st and st.title) or '',
        'duration': (st and st.duration) or None,
        'position': (st and (st.adjusted_current_time or st.current_time)) or 0,
        'state': (st and st.player_state) or 'BUFFERING',
        'thumb': f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg' if vid else '',
        'played': w.seen,
        'limit': w.limit,
    }


def next_video():
    """Skip to the next video of the playlist on the TV."""
    w = _watcher
    if not w or not w.is_alive():
        return False
    w.cast.media_controller.queue_next()
    return True


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


def box_action(box, mode, config, pause_music=None, on_play=None, on_bookmark=None,
               resume=None):
    """Toggle / add / remove a TV box, with the same truth table as a box.
    `on_play(uri, name, length_ms, position_ms)` records each video watched,
    `on_bookmark` (same arguments) saves its position while it plays, and
    `resume` finds an unfinished video to go back to (see resume_point).
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
    _configure(config)
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
            # The video left unfinished comes back first, where it stopped;
            # otherwise a random one of the playlist.
            back = resume_point(resume, video, playlist)
            start, at = back or (pick_start(video, playlist), 0)
            cast = play(target, start, playlist, at)
        except Exception as e:
            print(f"TV play error ({ref}): {e}")
            return f"TV: {e}"
        # One screen, one video: another TV box still marked on was replaced.
        _active.clear()
        _active[box.uid] = {'ref': ref,
                            'name': getattr(box, 'description', '') or box.uid,
                            'image': getattr(box, 'image_url', '') or ''}
        _last[box.uid] = ref
        _watcher = _Watcher(cast, on_play, getattr(box, 'option_max_results', None) or None,
                            start, box.uid, on_bookmark)
        _watcher.start()
        print(f"TV: {box.uid} cast {start}" + (f" at {at} s" if at else '') + f" from {ref}")
        try:
            if pause_music and config.getboolean('tv', 'pause_music', fallback=True):
                pause_music()
        except Exception as e:
            print(f"TV pause_music error: {e}")
        return "TV added"
