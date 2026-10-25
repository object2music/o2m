#!/usr/bin/env python3
"""spotdl cache script: downloads Spotify tracks from pinned o2m boxes, and keeps
the podcast episodes and YouTube videos a device asked for."""

import hashlib
import os
import re
import sys
import time
import json
import subprocess
import threading
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote

O2M_URL = os.environ.get('O2M_URL', 'http://o2m:6681')
CACHE_DIR = Path(os.environ.get('SPOTDL_CACHE_DIR', '/music/cache'))
CACHE_DAYS = int(os.environ.get('SPOTDL_CACHE_DAYS', '30'))
CACHE_HOUR = int(os.environ.get('SPOTDL_CACHE_HOUR', '3'))
# Mopidy music root as seen inside the mopidy container
MOPIDY_MUSIC_DIR = os.environ.get('MOPIDY_MUSIC_DIR', '/app/Music')
# /music in this container maps to MOPIDY_MUSIC_DIR in mopidy container
SPOTDL_MUSIC_MOUNT = os.environ.get('SPOTDL_MUSIC_MOUNT', '/music')
# Comma-separated box UIDs to cache; empty = all pinned boxes
BOX_UIDS = [u.strip() for u in os.environ.get('SPOTDL_BOX_UIDS', '').split(',') if u.strip()]
# May the nightly pass prefetch the pinned boxes at all? It is a GUESS about
# what will be wanted, and on a small disk the guess is the problem: 28 pinned
# boxes against a 2 GB ceiling only thrash the cache, evicting what a device
# actually asked for. `SPOTDL_BOX_UIDS` restricts WHICH boxes and can never say
# none — naming a uid that does not exist leaves `run_cache` returning before
# `run_maintenance`, so the nightly expiry would go with it.
BOX_PASS = (os.environ.get('SPOTDL_BOX_PASS', '1').strip().lower()
            not in ('0', 'false', 'no', 'off'))
# On-demand queue: a listening device asked for a track offline and o2m has no
# file for it. Polled between the nightly runs, because the person is waiting.
QUEUE_POLL = int(os.environ.get('SPOTDL_QUEUE_POLL', '30'))
QUEUE_BATCH = int(os.environ.get('SPOTDL_QUEUE_BATCH', '5'))
# One on-demand track, at most. A hung spotdl used to hold the whole queue —
# and, since o2m only knows a downloader is there because it keeps asking and
# reporting, it also made o2m tell every device there was none.
QUEUE_TRACK_TIMEOUT = int(os.environ.get('SPOTDL_QUEUE_TIMEOUT', '300'))
# Between two on-demand tracks, and after YouTube has refused us. Every spotdl
# invocation opens a YouTube Music session and searches it twice (its own
# liveness check, then the track), so a queue served flat out is a burst of
# requests from one address: on the Pi, 30 tracks armed on a phone brought back
# `403 Sorry...` for 32 of 33 attempts, each recorded as "this track cannot be
# found". Pacing is the fix; the backoff is what makes a refusal cost minutes
# instead of a trackload of rows.
QUEUE_TRACK_PAUSE = int(os.environ.get('SPOTDL_QUEUE_PAUSE', '10'))
QUEUE_THROTTLE_WAIT = int(os.environ.get('SPOTDL_THROTTLE_WAIT', '300'))
# One file per item, filed by what it is; the boxes are playlists over them
# (o2m_core/cachelayout.py):
#   Library/<album artist>/<album>/<NN> <title>.mp3   music, spotdl's template
#   Podcasts|Videos/<channel>/<date> <title> [tag]     named by o2m (queue rows)
#   Boxes/<box>/[<included box>/]<source>.m3u8, All.m3u8   write_views()
# Folders per box holding their files were tried first and given up: a track is
# in several boxes, a tree can put it in one. The box folders of that layout,
# `ondemand/` and `spoken/` are what reorganize_cache() empties.
LIBRARY_DIR = CACHE_DIR / 'Library'
BOXES_DIR = CACHE_DIR / 'Boxes'
LIBRARY_TEMPLATE = '{album-artist}/{album}/{track-number} {title}.{output-ext}'
# Hard ceiling on the cache, in gigabytes. Override in .env (the service reads
# it through env_file); 0 or less disables the cap. A date-based expiry alone
# is not a limit: the day the downloader started working the cache went from
# 99 MB to 7.1 GB in a single nightly run, and nothing in CACHE_DAYS would have
# stopped it before the disk did.
# Whether THIS instance may delete from the cache. Several instances can share
# one cache directory, and each unregisters only in its OWN database — so a
# pruner deletes files other instances still have rows for. Exactly one
# instance should prune a shared tree; the others set SPOTDL_PRUNE=0. (The
# rows left behind are survivable either way: `_resolve_uri` checks the file
# exists before substituting it. This keeps the churn down and the ownership
# clear.) Default 1, which is right for a lone instance.
PRUNE = (os.environ.get('SPOTDL_PRUNE', '1').strip().lower()
         not in ('0', 'false', 'no', 'off'))
CACHE_MAX_GB = float(os.environ.get('SPOTDL_CACHE_MAX_GB', '10'))
CACHE_MAX_BYTES = int(CACHE_MAX_GB * 1024 ** 3) if CACHE_MAX_GB > 0 else 0
AUDIO_EXT = ('.mp3', '.m4a', '.opus', '.ogg', '.flac', '.wav', '.webm', '.aac', '.mp4')
# Podcast episodes and YouTube videos a device asked for, kept so the next device
# and Mopidy read them from disk. Fetched through o2m's own /api/audio, which
# already knows how to reach both (feed enclosure, yt_dlp) — nothing here
# resolves anything, and this image needs no yt_dlp of its own.
# A native install — a Raspberry Pi — has no spotdl: the package is not there,
# and an armv7l with 923 MB of RAM is not where a per-track ffmpeg conversion
# belongs. Its devices still want the podcasts and the videos, and those need no
# spotdl at all: the spoken queue is an HTTP fetch of o2m's own /api/audio into a
# file, then a registration. So this script has two shapes and this flag says
# which — the full downloader beside a Docker instance, or the spoken half plus
# the pruner beside an o2m that owns its disk (O2M_CACHE_POOL, see CLAUDE.md).
#
# Running the same file in both is deliberate. One downloader, one naming
# scheme, one registration path and one pruner: a second implementation for the
# Pi would be a second set of the two defects this one took a day to find
# (spotdl takes URLs not URIs, the id lives in WOAS not COMM).
SPOKEN_ONLY = (os.environ.get('SPOTDL_SPOKEN_ONLY', '0').strip().lower()
               in ('1', 'true', 'yes', 'on'))
SPOKEN_BATCH = int(os.environ.get('SPOTDL_SPOKEN_BATCH', '3'))
_SPOKEN_EXT = {'audio/mpeg': '.mp3', 'audio/mp3': '.mp3', 'audio/mp4': '.m4a',
               'audio/x-m4a': '.m4a', 'audio/m4a': '.m4a', 'audio/aac': '.aac',
               'audio/ogg': '.ogg', 'audio/webm': '.webm', 'video/mp4': '.mp4'}
# run_cache (main thread) and the queue worker both delete. One lock over every
# deletion, so neither can pull a file out from under the other's stat().
_prune_lock = threading.Lock()


def wait_for_o2m(timeout=300):
    print(f"Waiting for o2m API at {O2M_URL}...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{O2M_URL}/health", timeout=5)
            if r.status_code == 200:
                print("o2m API ready")
                return True
        except Exception:
            pass
        time.sleep(10)
    print("Timed out waiting for o2m API")
    return False


def get_pinned_boxes():
    r = requests.get(f"{O2M_URL}/api/box_favorites", timeout=10)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def get_box_info(uid):
    r = requests.get(f"{O2M_URL}/api/box_info", params={'uid': uid}, timeout=10)
    if r.status_code == 404:
        print(f"Box {uid} not found")
        return None
    r.raise_for_status()
    return r.json()


def extract_spotify_uris(box):
    """Extract cacheable Spotify URIs from a box data field."""
    data = (box.get('data') or '').strip()
    if not data:
        return []
    uris = []
    for line in data.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and line.startswith('spotify:'):
            uris.append(line)
    return uris


def _spotify_uri_from_text(text):
    if text and 'open.spotify.com/track/' in text:
        return 'spotify:track:' + text.split('/track/')[1].split('?')[0].strip()
    return None


def extract_spotify_uri_from_mp3(filepath):
    """Read the Spotify track URI spotdl wrote into the file's ID3 tags.

    WOAS (Official Audio Source Webpage) first: current spotdl puts the Spotify
    track url there and the YOUTUBE url in COMM. Reading COMM alone — which this
    did — therefore found nothing at all, which is why the cache had been
    downloading files for months and registering none of them. COMM is kept as a
    fallback for files written by older versions.
    """
    try:
        from mutagen.id3 import ID3
        tags = ID3(str(filepath))
        for frame in tags.getall('WOAS'):
            uri = _spotify_uri_from_text(getattr(frame, 'url', ''))
            if uri:
                return uri
        for key in tags:
            if key.startswith('COMM'):
                try:
                    text = str(tags[key].text[0]) if tags[key].text else ''
                except Exception:
                    text = ''
                uri = _spotify_uri_from_text(text)
                if uri:
                    return uri
    except Exception as e:
        print(f"  mutagen error ({filepath.name}): {e}")
    return None


def file_to_mopidy_uri(filepath):
    """Convert a local file path to the file:// URI that Mopidy uses."""
    rel = filepath.relative_to(Path(SPOTDL_MUSIC_MOUNT))
    mopidy_abs = str(Path(MOPIDY_MUSIC_DIR) / rel)
    return 'file://' + quote(mopidy_abs, safe='/')


def register_local_track(spotify_uri, local_uri):
    try:
        r = requests.post(
            f"{O2M_URL}/api/register_local_track",
            json={'spotify_uri': spotify_uri, 'local_uri': local_uri},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  register error: {e}")
        return False


def clear_local_track(local_uri):
    try:
        requests.post(
            f"{O2M_URL}/api/clear_local_track",
            json={'local_uri': local_uri},
            timeout=10,
        )
    except Exception:
        pass


# Files this process registered already. The library is one tree for every box,
# so a box pass that re-registered all of it would make ~2,000 calls per box.
_registered = set()


def sync_downloaded_files(output_dir=None):
    """Register with o2m every mp3 of the library not registered yet by this
    process: the Spotify uri from its ID3 tags, the file as Mopidy sees it."""
    output_dir = output_dir or LIBRARY_DIR
    if not output_dir.exists():
        return 0
    count = 0
    for mp3_file in output_dir.rglob('*.mp3'):
        if mp3_file in _registered:
            continue
        spotify_uri = extract_spotify_uri_from_mp3(mp3_file)
        if not spotify_uri:
            continue
        local_uri = file_to_mopidy_uri(mp3_file)
        if register_local_track(spotify_uri, local_uri):
            _registered.add(mp3_file)
            count += 1
    if count:
        print(f"  registered {count} track(s)")
    return count


def spotify_url(uri):
    """`spotify:track:<id>` -> `https://open.spotify.com/track/<id>`.

    This is not cosmetic, it is the difference between a lookup and a search.
    spotdl dispatches on the shape of its argument: given a URI it falls into
    `Song.from_search_term`, i.e. it SEARCHES Spotify for the literal string
    "spotify:track:0Brzu8…" and downloads whatever comes back — which is why
    three different ids all resolved to one unrelated track, and why the
    nightly box cache had been filling data/music with songs nobody asked for.
    Given a URL it resolves the id. Verified on both forms, same container,
    same credentials.
    """
    if not uri or not uri.startswith('spotify:'):
        return uri
    parts = uri.split(':')
    if len(parts) < 3:
        return uri
    return f"https://open.spotify.com/{parts[1]}/{parts[2]}"


class Throttled(Exception):
    """YouTube refused US, which says nothing about the track asked for.

    The same distinction the `web:` reader draws between a page that declined
    and a page that holds nothing: reported as a failure, the track's row goes
    to `failed` and the device is told it cannot be downloaded — a verdict on
    a song over a rate limit that will be gone in a minute.
    """


# Spotdl means its YouTube Music check to be advisory ("without stopping
# downloads", entry_point.py) but lets the exception out, so one non-JSON
# answer — Google's `Sorry...` page — kills the run before it looks at the
# track. These are the markers of that answer, none of which a real
# "no match for this song" carries.
_THROTTLE_MARKERS = (
    'check_ytmusic_connection',
    'JSONDecodeError',
    'Expecting value: line 1 column 1',
    'HTTP Error 429',
    'Sign in to confirm',
)


def _is_throttled(output):
    return any(m in output for m in _THROTTLE_MARKERS)


def run_spotdl(uri, output_dir, timeout=None):
    """Download a Spotify URI to output_dir. Returns True on success.

    `timeout` (seconds) raises subprocess.TimeoutExpired once spent, the child
    killed. The nightly pass leaves it unset — a playlist may legitimately take
    an hour — but a single on-demand track has no such excuse."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # {output-ext} is spotdl's own placeholder; {ext} is not one of them and
    # stays in the name literally, so every file was "Title.{ext}.mp3".
    template = str(output_dir) + '/' + LIBRARY_TEMPLATE
    cmd = [
        'spotdl', 'download', spotify_url(uri),
        '--output', template,
        '--format', 'mp3',
        '--bitrate', '192k',
        # A file already in the folder is recognised by the Spotify url in its
        # tags, not by its name: renaming the cache (reorganize_cache) or a
        # change of naming must not download a whole box again.
        '--scan-for-songs', '--overwrite', 'skip',
        '--log-level', 'WARNING',
    ]
    print(f"  spotdl {uri}")
    result = subprocess.run(cmd, timeout=timeout, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors='replace')
    out = result.stdout or ''
    if result.returncode == 0:
        return True
    if _is_throttled(out):
        raise Throttled('YouTube Music answered 403 (too many requests from here)')
    for line in [l.strip() for l in out.splitlines() if l.strip()][-3:]:
        print(f"    {line[:200]}")
    return False


def touch_files(paths):
    """Update the mtime of these files to now (marks them wanted this run)."""
    now = time.time()
    for f in paths:
        try:
            os.utime(f, (now, now))
        except OSError:
            pass


def human_size(n):
    for unit, step in (('GB', 1024 ** 3), ('MB', 1024 ** 2), ('kB', 1024)):
        if n >= step:
            return f"{n / step:.2f} {unit}"
    return f"{n} B"


def cache_entries():
    """(path, size, mtime) for every audio file in the cache.

    mtime is not "when it was downloaded" but "when a cache run last wanted
    it" — touch_files stamps a whole box at the start of its pass. So ordering
    by it is ordering by relevance, which is what both the expiry and the cap
    below want.
    """
    out = []
    for f in CACHE_DIR.rglob('*'):
        if f.is_file() and f.suffix.lower() in AUDIO_EXT:
            try:
                st = f.stat()
            except OSError:
                continue
            out.append((f, st.st_size, st.st_mtime))
    return out


def drop_file(path):
    """Delete one cached file and unregister it.

    Unregistering is not tidiness. `local_uri` is substituted into the Mopidy
    tracklist by `_resolve_uri`, so a row left pointing at a deleted file makes
    the SERVER fail to play a track it would otherwise have streamed — and
    makes /api/audio 404 for a device that asked for it.
    """
    try:
        clear_local_track(file_to_mopidy_uri(path))
        path.unlink()
        return True
    except OSError:
        return False


def finished_files(entries):
    """The cached files o2m says are spoken items heard to the end.

    Asked of THIS instance's database: a file another instance (with its own
    database) asked for is unknown here and simply ages like the rest."""
    spoken = [f for f, _s, _m in entries if spoken_tag_of(f)]
    if not spoken:
        return set()
    by_uri = {file_to_mopidy_uri(f): f for f in spoken}
    try:
        r = requests.post(f"{O2M_URL}/api/offline/finished",
                          json={'local_uris': list(by_uri)}, timeout=30)
        r.raise_for_status()
        return {by_uri[u] for u in (r.json() or {}).get('finished') or [] if u in by_uri}
    except Exception as e:
        print(f"finished check error: {e}")
        return set()


def clean_old_files():
    """Delete audio files not touched in CACHE_DAYS days, and every episode or
    video already heard to the end, and unregister them."""
    if not PRUNE:
        return
    cutoff = time.time() - CACHE_DAYS * 86400
    removed, heard = 0, 0
    with _prune_lock:
        entries = cache_entries()
        done = finished_files(entries)
        for f, _size, mtime in entries:
            if (mtime < cutoff or f in done) and drop_file(f):
                removed += 1
                heard += f in done
    if removed:
        print(f"Removed {removed} file(s): {heard} heard to the end, "
              f"{removed - heard} stale (>{CACHE_DAYS}d old)")


def enforce_cache_cap():
    """Delete files until the cache fits the cap: the episodes and videos
    already heard first, then the least recently wanted.

    Called after every box and every on-demand batch, not only at the end of a
    run: a nightly pass can add gigabytes, and a ceiling checked once at the
    end is a ceiling you go through first.
    """
    if not CACHE_MAX_BYTES or not PRUNE:
        return 0
    with _prune_lock:
        entries = cache_entries()
        total = sum(e[1] for e in entries)
        if total <= CACHE_MAX_BYTES:
            return 0
        done = finished_files(entries)
        freed, removed = 0, 0
        # Heard first, then oldest. mtime is "last wanted" for a box's music
        # (touch_files) and the download time for a spoken file.
        for f, size, _mtime in sorted(entries, key=lambda e: (e[0] not in done, e[2])):
            if total - freed <= CACHE_MAX_BYTES:
                break
            if drop_file(f):
                freed += size
                removed += 1
    print(f"Cache over {CACHE_MAX_GB:g} GB: removed {removed} file(s), "
          f"freed {human_size(freed)} (now {human_size(total - freed)})")
    return freed


def run_cache():
    print(f"\n=== Cache run {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    if BOX_UIDS:
        boxes = [b for uid in BOX_UIDS if (b := get_box_info(uid)) is not None]
    else:
        try:
            boxes = get_pinned_boxes()
        except Exception as e:
            print(f"Failed to fetch pinned boxes: {e}")
            return

    if not boxes:
        print("No boxes to cache")
        return

    # What the pinned boxes name outright is still wanted: stamped, so the
    # expiry (by mtime) keeps it. One library for every box, so this is asked
    # of o2m rather than read off a folder.
    views = fetch_views(static=True)
    touch_files(view_files(views))

    for box in boxes:
        uid = box.get('uid', '')
        desc = box.get('description') or uid
        uris = extract_spotify_uris(box)
        if not uris:
            continue

        print(f"Box {uid} ({desc}): {len(uris)} URI(s)")
        for uri in uris:
            try:
                run_spotdl(uri, LIBRARY_DIR)
            except Throttled as e:
                print(f"  throttled ({e}); backing off {QUEUE_THROTTLE_WAIT}s")
                time.sleep(QUEUE_THROTTLE_WAIT)
            except Exception as e:
                print(f"  spotdl error for {uri}: {e}")

        sync_downloaded_files()
        enforce_cache_cap()

    run_maintenance()
    print(f"=== Done {datetime.now().strftime('%H:%M')} ===\n")


def run_maintenance():
    """The expiry and the ceiling — the half of a nightly run that needs no
    downloader, so the spoken-only shape runs exactly this and nothing else."""
    clean_old_files()
    enforce_cache_cap()
    write_views()
    remove_empty_dirs()


# ── Layout: one file per item, a playlist per box ─────────────────────────────

def relocate(src, dst, uri):
    """Move one cached file and register it where it now is. False, and the
    file left where it was, when the name is taken or the move fails."""
    if dst == src or dst.exists():
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    except OSError as e:
        print(f"  move {src.name}: {e}")
        return False
    if uri and not register_local_track(uri, file_to_mopidy_uri(dst)):
        print(f"  {dst.name}: moved but not registered")
    return True


def mopidy_uri_to_file(local_uri):
    """The reverse of file_to_mopidy_uri: the file behind a registered uri."""
    if not (local_uri or '').startswith('file://'):
        return None
    path = unquote(local_uri[len('file://'):])
    root = MOPIDY_MUSIC_DIR.rstrip('/') + '/'
    if not path.startswith(root):
        return None
    return Path(SPOTDL_MUSIC_MOUNT) / path[len(root):]


def fetch_views(static=False):
    try:
        r = requests.get(f"{O2M_URL}/api/offline/views",
                         params={'static': 1} if static else {}, timeout=60)
        r.raise_for_status()
        return r.json() or {}
    except Exception as e:
        print(f"views fetch error: {e}")
        return {}


def view_files(views):
    """The files a set of views lists, those present on this disk."""
    out = []
    for it in (views.get('items') or {}).values():
        f = mopidy_uri_to_file(it.get('local_uri'))
        if f is not None and f.is_file():
            out.append(f)
    return out


_views_lock = threading.Lock()


def write_views():
    """Write the box playlists under Boxes/ and delete those no box has any
    more. A playlist lists only what is on this disk, by a path relative to
    itself, so the same file plays from any machine the folder is copied to.
    Rewritten only when its content moved. The pruner only: it is the one
    instance that changes this tree."""
    if not PRUNE or not CACHE_DIR.exists():
        return
    with _views_lock:     # three threads end a batch with this
        _write_views(fetch_views())


def _write_views(views):
    if 'playlists' not in views:       # o2m did not answer: delete nothing
        return
    items = views.get('items') or {}
    wanted, written = set(), 0
    for path, uris in views['playlists'].items():
        target = BOXES_DIR / (path + '.m3u8')
        lines = ['#EXTM3U']
        for u in uris:
            it = items.get(u) or {}
            f = mopidy_uri_to_file(it.get('local_uri'))
            if f is None or not f.is_file():
                continue
            lines.append(f"#EXTINF:{int(it.get('seconds') or 0) or -1},{it.get('title') or f.stem}")
            lines.append(os.path.relpath(f, target.parent))
        if len(lines) == 1:
            continue
        wanted.add(target)
        text = '\n'.join(lines) + '\n'
        try:
            if target.is_file() and target.read_text(encoding='utf-8') == text:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
            written += 1
        except OSError as e:
            print(f"  view {path}: {e}")
    removed = 0
    if BOXES_DIR.exists():
        for f in BOXES_DIR.rglob('*.m3u8'):
            if f not in wanted:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    if written or removed:
        print(f"Box views: {written} written, {removed} removed, {len(wanted)} in all")


def placements(files):
    """o2m's answer for these cached files: {path: {uri, file, box_folder}}."""
    out = {}
    files = list(files)
    for i in range(0, len(files), 200):
        by_uri = {file_to_mopidy_uri(f): f for f in files[i:i + 200]}
        try:
            r = requests.post(f"{O2M_URL}/api/offline/placement",
                              json={'local_uris': list(by_uri)}, timeout=60)
            r.raise_for_status()
            for lu, p in ((r.json() or {}).get('items') or {}).items():
                if lu in by_uri:
                    out[by_uri[lu]] = p
        except Exception as e:
            print(f"placement error: {e}")
    return out


def reorganize_cache():
    """Bring a cache laid out another way to the current one, once per start.

    Every file this database knows is moved to its place (`Library/...`,
    `Podcasts/...`, `Videos/...`) through POST /api/offline/placement and
    registered there; the box folders, `ondemand/` and `spoken/` of the
    earlier layouts empty out and go. Idempotent: a file in place is not
    touched. A file o2m does not know (another instance's database) stays
    where it is and ages out with the expiry. The pruner only, like every
    other change to a shared tree."""
    if not PRUNE or not CACHE_DIR.exists():
        return
    files = [f for f, _s, _m in cache_entries()]
    moved = 0
    with _prune_lock:
        for f, p in placements(files).items():
            if not p.get('folder') or not p.get('file'):
                continue
            moved += relocate(f, CACHE_DIR / p['folder'] / (p['file'] + f.suffix.lower()),
                              p.get('uri'))
    print(f"Reorganized the cache: {moved} of {len(files)} file(s) moved or renamed")
    write_views()
    remove_empty_dirs(min_age=0)


def remove_empty_dirs(min_age=600):
    """Delete the folders left with nothing in them — a box emptied by the
    expiry, the old `ondemand/` and `spoken/`. Bottom-up, never the cache root,
    and only when untouched for `min_age` seconds: spotdl creates its output
    folder before it writes the first file into it."""
    if not PRUNE or not CACHE_DIR.exists():
        return
    now, removed = time.time(), 0
    with _prune_lock:
        for d in sorted((p for p in CACHE_DIR.rglob('*') if p.is_dir()),
                        key=lambda p: len(p.parts), reverse=True):
            try:
                if not any(d.iterdir()) and now - d.stat().st_mtime >= min_age:
                    d.rmdir()
                    removed += 1
            except OSError:
                pass
    if removed:
        print(f"Removed {removed} empty folder(s)")


# ── On-demand queue (a device is waiting) ─────────────────────────────────────
# The nightly pass caches the pinned boxes, which is a guess about what will be
# wanted. This queue is the opposite: someone has armed offline on their phone
# and named the tracks. Same downloader, same registration path — only the
# trigger and the urgency differ.

def fetch_queue(limit=QUEUE_BATCH, kind=None):
    try:
        params = {'limit': limit}
        if kind:
            params['kind'] = kind
        r = requests.get(f"{O2M_URL}/api/offline/queue", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"queue fetch error: {e}")
        return []


def queue_done(uri, ok=True, note=None):
    try:
        requests.post(f"{O2M_URL}/api/offline/queue_done",
                      json={'uri': uri, 'ok': ok, 'note': note}, timeout=10)
    except Exception as e:
        print(f"queue_done error: {e}")


def is_registered(uri):
    """Ask o2m whether the track now resolves to a file.

    This is load-bearing, not a formality. Registration maps a file to the
    Spotify id written in its own tags, so if spotdl resolved the query to a
    DIFFERENT track (which it currently does — see the note in run_queue) the
    file lands under its true id and this check still says no. That is what
    keeps a mis-resolved download from being served to a device as the track it
    asked for: an honest failure instead of the wrong song.

    Asking the server also beats inspecting our own output directory: spotdl
    names files from metadata, so the database is the only reliable answer.
    `fetch_missing=False` so a status check never re-queues what it is checking.
    """
    try:
        r = requests.post(f"{O2M_URL}/api/offline/plan",
                          json={'uris': [uri], 'fetch_missing': False}, timeout=15)
        r.raise_for_status()
        items = (r.json() or {}).get('items') or []
        return bool(items) and items[0].get('state') == 'ready'
    except Exception as e:
        print(f"  plan check error: {e}")
        return False


def run_queue():
    """Download one batch of on-demand requests. Returns how many were handled.

    A request only closes as done when the track it asked for is actually
    registered (see is_registered). A download that resolved to some other
    song therefore fails honestly instead of being served to a device as the
    track it wanted.
    """
    items = fetch_queue()
    if not items:
        return 0
    print(f"On-demand queue: {len(items)} request(s)")
    for n, it in enumerate(items):
        uri = it.get('uri')
        if not uri:
            continue
        if n and QUEUE_TRACK_PAUSE > 0:
            time.sleep(QUEUE_TRACK_PAUSE)
        out_dir = LIBRARY_DIR
        try:
            run_spotdl(uri, out_dir, timeout=QUEUE_TRACK_TIMEOUT)
        except Throttled as e:
            # The row is left exactly as it was — still pending, its tries
            # untouched — and the batch stops: asking again at once is how the
            # refusal was earned.
            print(f"  {uri}: throttled ({e}); backing off {QUEUE_THROTTLE_WAIT}s")
            time.sleep(QUEUE_THROTTLE_WAIT)
            break
        except Exception as e:
            print(f"  spotdl error for {uri}: {e}")
            queue_done(uri, ok=False, note=str(e)[:200])
            continue
        sync_downloaded_files()
        ok = is_registered(uri)
        # A failure is recorded, not retried forever: the UI reads it to stop
        # showing the track as "on its way" when spotdl simply cannot find it.
        queue_done(uri, ok=ok, note=None if ok else 'not found or not registered')
        print(f"  {uri}: {'ok' if ok else 'FAILED'}")
    enforce_cache_cap()
    write_views()
    return len(items)


def queue_worker():
    """Serve the on-demand queue forever, on its own thread.

    It must not share the nightly run's loop. The two are different jobs with
    different urgencies: the nightly pass refreshes a guess about what will be
    wanted and may run for an hour on a single box of eighteen playlists, while
    a queue entry means a person has armed offline on their phone and is
    waiting now. Interleaving the two — between boxes, then between sources —
    was tried and still left the queue behind one playlist download. Concurrent
    spotdl processes are fine: separate processes, separate output directories.
    """
    while True:
        try:
            run_queue()
        except Exception as e:
            print(f"queue run error: {e}")
        time.sleep(QUEUE_POLL)


# ── Spoken queue: episodes and videos ─────────────────────────────────────────

def spoken_stem(uri):
    """The file name of one item, from its uri alone. Deterministic, so an
    instance with its own database finds a file another instance fetched for the
    same item and only registers it."""
    return hashlib.sha1(uri.encode('utf-8')).hexdigest()[:20]


_TAG = re.compile(r'(?:^|\[)([0-9a-f]{20})\]?$')


def spoken_tag_of(path):
    """The uri hash a spoken file carries: `… [<tag>].mp3`, or the old bare
    `<tag>.mp3`. '' for a music file."""
    m = _TAG.search(path.stem)
    return m.group(1) if m else ''


def existing_spoken(uri):
    """The file already held for this item, wherever it sits in the cache."""
    tag = spoken_stem(uri)
    for f, _s, _m in cache_entries():
        if spoken_tag_of(f) == tag:
            return f
    return None


def download_spoken(uri, out_dir, stem=None):
    """Fetch one item through o2m's /api/audio. Returns the file, or None."""
    stem = stem or spoken_stem(uri)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / (stem + '.part')
    try:
        with requests.get(f"{O2M_URL}/api/audio", params={'uri': uri},
                          stream=True, timeout=(10, 120)) as r:
            if r.status_code != 200:
                print(f"  {uri}: HTTP {r.status_code}")
                return None
            ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            ext = _SPOKEN_EXT.get(ctype)
            if not ext:
                print(f"  {uri}: not audio ({ctype or 'no type'})")
                return None
            with open(tmp, 'wb') as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
        if tmp.stat().st_size < 1024:
            tmp.unlink()
            return None
        path = out_dir / (stem + ext)
        tmp.rename(path)
        return path
    except Exception as e:
        print(f"  {uri}: {e}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return None


def is_held(uri):
    """Does o2m now serve this item from its own file? (`held`, see describe)."""
    try:
        r = requests.post(f"{O2M_URL}/api/offline/plan",
                          json={'uris': [uri], 'fetch_missing': False}, timeout=15)
        r.raise_for_status()
        items = (r.json() or {}).get('items') or []
        return bool(items) and items[0].get('held') is True
    except Exception as e:
        print(f"  plan check error: {e}")
        return False


def run_spoken_queue():
    items = fetch_queue(SPOKEN_BATCH, kind='spoken')
    if not items:
        return 0
    print(f"Spoken queue: {len(items)} request(s)")
    for it in items:
        uri = it.get('uri')
        if not uri:
            continue
        # `Podcasts/<channel>/<date> <title> [tag]`, as o2m names it.
        path = existing_spoken(uri) or download_spoken(
            uri, CACHE_DIR / (it.get('folder') or 'Podcasts'), it.get('file') or None)
        ok = bool(path) and register_local_track(uri, file_to_mopidy_uri(path)) and is_held(uri)
        queue_done(uri, ok=ok, note=None if ok else 'download or registration failed')
        print(f"  {uri[:100]}: {'ok ' + human_size(path.stat().st_size) if ok else 'FAILED'}")
    enforce_cache_cap()
    write_views()
    return len(items)


def spoken_worker():
    """Its own thread: a music request may hold run_queue for minutes."""
    while True:
        try:
            run_spoken_queue()
        except Exception as e:
            print(f"spoken queue error: {e}")
        time.sleep(QUEUE_POLL)


def seconds_until_next_run():
    now = datetime.now()
    target = now.replace(hour=CACHE_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


if __name__ == '__main__':
    if not wait_for_o2m():
        sys.exit(1)
    try:
        reorganize_cache()
    except Exception as e:
        print(f"reorganize error: {e}")

    if not SPOKEN_ONLY:
        threading.Thread(target=queue_worker, daemon=True, name='offline-queue').start()
    threading.Thread(target=spoken_worker, daemon=True, name='spoken-queue').start()
    print("Spoken queue worker started (every %ds)" % QUEUE_POLL if SPOKEN_ONLY else
          f"On-demand queue workers started, music and spoken (every {QUEUE_POLL}s)")
    print(f"Cache cap: {CACHE_MAX_GB:g} GB" if CACHE_MAX_BYTES
          else "Cache cap: disabled (SPOTDL_CACHE_MAX_GB<=0)")
    if not PRUNE:
        print("Pruning disabled here (SPOTDL_PRUNE=0) — another instance owns "
              f"the cleanup of {CACHE_DIR}")

    if SPOKEN_ONLY or not BOX_PASS:
        # Nothing to prefetch, so the nightly run is the maintenance alone. The
        # ceiling does not wait for it — it is enforced after every batch, music
        # (run_queue) and spoken (run_spoken_queue) alike, exactly as it is
        # beside a Docker instance; this loop only adds the nightly expiry.
        if SPOKEN_ONLY:
            # No music queue and no box pass: both go through spotdl.
            print(f"Spoken only: no spotdl here. Cache {CACHE_DIR}, "
                  f"cap {CACHE_MAX_GB:g} GB, expiry {CACHE_DAYS} days.")
        else:
            print(f"Box pass off (SPOTDL_BOX_PASS=0): on-demand only. "
                  f"Cache {CACHE_DIR}, cap {CACHE_MAX_GB:g} GB, "
                  f"expiry {CACHE_DAYS} days.")
        run_maintenance()
        while True:
            time.sleep(seconds_until_next_run())
            run_maintenance()

    run_cache()

    while True:
        secs = seconds_until_next_run()
        h = int(secs) // 3600
        m = (int(secs) % 3600) // 60
        print(f"Next run in {h}h {m}m (at {CACHE_HOUR:02d}:00)")
        time.sleep(secs)
        run_cache()
