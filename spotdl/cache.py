#!/usr/bin/env python3
"""spotdl cache script: downloads Spotify tracks from pinned o2m boxes."""

import os
import sys
import time
import json
import subprocess
import threading
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

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
# On-demand queue: a listening device asked for a track offline and o2m has no
# file for it. Polled between the nightly runs, because the person is waiting.
QUEUE_POLL = int(os.environ.get('SPOTDL_QUEUE_POLL', '30'))
QUEUE_BATCH = int(os.environ.get('SPOTDL_QUEUE_BATCH', '5'))
ONDEMAND_DIRNAME = 'ondemand'
# Hard ceiling on the cache, in gigabytes. Override in .env (the service reads
# it through env_file); 0 or less disables the cap. A date-based expiry alone
# is not a limit: the day the downloader started working the cache went from
# 99 MB to 7.1 GB in a single nightly run, and nothing in CACHE_DAYS would have
# stopped it before the disk did.
CACHE_MAX_GB = float(os.environ.get('SPOTDL_CACHE_MAX_GB', '10'))
CACHE_MAX_BYTES = int(CACHE_MAX_GB * 1024 ** 3) if CACHE_MAX_GB > 0 else 0
AUDIO_EXT = ('.mp3', '.m4a', '.opus', '.ogg', '.flac', '.wav')
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


def sync_downloaded_files(output_dir):
    """Scan output_dir for mp3 files, read Spotify URI from ID3, register with o2m."""
    if not output_dir.exists():
        return 0
    count = 0
    for mp3_file in output_dir.glob('*.mp3'):
        spotify_uri = extract_spotify_uri_from_mp3(mp3_file)
        if not spotify_uri:
            continue
        local_uri = file_to_mopidy_uri(mp3_file)
        if register_local_track(spotify_uri, local_uri):
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


def run_spotdl(uri, output_dir):
    """Download a Spotify URI to output_dir. Returns True on success."""
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir) + '/{artists} - {title}.{ext}'
    cmd = [
        'spotdl', 'download', spotify_url(uri),
        '--output', template,
        '--format', 'mp3',
        '--bitrate', '192k',
        '--log-level', 'WARNING',
    ]
    print(f"  spotdl {uri}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def touch_files(directory):
    """Update mtime of all mp3 files to now (marks them active this run)."""
    now = time.time()
    for f in directory.rglob('*.mp3'):
        os.utime(f, (now, now))


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


def clean_old_files():
    """Delete audio files not touched in CACHE_DAYS days and unregister them."""
    cutoff = time.time() - CACHE_DAYS * 86400
    removed = 0
    with _prune_lock:
        for f, _size, mtime in cache_entries():
            if mtime < cutoff and drop_file(f):
                removed += 1
    if removed:
        print(f"Removed {removed} stale file(s) (>{CACHE_DAYS}d old)")


def enforce_cache_cap():
    """Delete the least recently wanted files until the cache fits the cap.

    Called after every box and every on-demand batch, not only at the end of a
    run: a nightly pass can add gigabytes, and a ceiling checked once at the
    end is a ceiling you go through first.
    """
    if not CACHE_MAX_BYTES:
        return 0
    with _prune_lock:
        entries = cache_entries()
        total = sum(e[1] for e in entries)
        if total <= CACHE_MAX_BYTES:
            return 0
        freed, removed = 0, 0
        for f, size, _mtime in sorted(entries, key=lambda e: e[2]):   # oldest first
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

    for box in boxes:
        uid = box.get('uid', '')
        desc = box.get('description') or uid
        uris = extract_spotify_uris(box)
        if not uris:
            continue

        print(f"Box {uid} ({desc}): {len(uris)} URI(s)")
        box_dir = CACHE_DIR / uid

        if box_dir.exists():
            touch_files(box_dir)

        for uri in uris:
            try:
                run_spotdl(uri, box_dir)
            except Exception as e:
                print(f"  spotdl error for {uri}: {e}")

        # Register all mp3 files in this box directory with the o2m API
        sync_downloaded_files(box_dir)
        enforce_cache_cap()

    clean_old_files()
    enforce_cache_cap()
    print(f"=== Done {datetime.now().strftime('%H:%M')} ===\n")


# ── On-demand queue (a device is waiting) ─────────────────────────────────────
# The nightly pass caches the pinned boxes, which is a guess about what will be
# wanted. This queue is the opposite: someone has armed offline on their phone
# and named the tracks. Same downloader, same registration path — only the
# trigger and the urgency differ.

def fetch_queue(limit=QUEUE_BATCH):
    try:
        r = requests.get(f"{O2M_URL}/api/offline/queue", params={'limit': limit}, timeout=10)
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
    out_dir = CACHE_DIR / ONDEMAND_DIRNAME
    print(f"On-demand queue: {len(items)} request(s)")
    for it in items:
        uri = it.get('uri')
        if not uri:
            continue
        try:
            run_spotdl(uri, out_dir)
        except Exception as e:
            print(f"  spotdl error for {uri}: {e}")
            queue_done(uri, ok=False, note=str(e)[:200])
            continue
        sync_downloaded_files(out_dir)
        ok = is_registered(uri)
        # A failure is recorded, not retried forever: the UI reads it to stop
        # showing the track as "on its way" when spotdl simply cannot find it.
        queue_done(uri, ok=ok, note=None if ok else 'not found or not registered')
        print(f"  {uri}: {'ok' if ok else 'FAILED'}")
    enforce_cache_cap()
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


def seconds_until_next_run():
    now = datetime.now()
    target = now.replace(hour=CACHE_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


if __name__ == '__main__':
    if not wait_for_o2m():
        sys.exit(1)

    threading.Thread(target=queue_worker, daemon=True, name='offline-queue').start()
    print(f"On-demand queue worker started (every {QUEUE_POLL}s)")
    print(f"Cache cap: {CACHE_MAX_GB:g} GB"
          if CACHE_MAX_BYTES else "Cache cap: disabled (SPOTDL_CACHE_MAX_GB<=0)")

    run_cache()

    while True:
        secs = seconds_until_next_run()
        h = int(secs) // 3600
        m = (int(secs) % 3600) // 60
        print(f"Next run in {h}h {m}m (at {CACHE_HOUR:02d}:00)")
        time.sleep(secs)
        run_cache()
