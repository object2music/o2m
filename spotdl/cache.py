#!/usr/bin/env python3
"""spotdl cache script: downloads Spotify tracks from pinned o2m boxes."""

import os
import sys
import time
import json
import subprocess
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


def extract_spotify_uri_from_mp3(filepath):
    """Read the Spotify track URI from ID3 comment tag written by spotdl."""
    try:
        from mutagen.id3 import ID3
        tags = ID3(str(filepath))
        for key in tags:
            if key.startswith('COMM'):
                try:
                    text = str(tags[key].text[0]) if tags[key].text else ''
                except Exception:
                    text = ''
                if 'open.spotify.com/track/' in text:
                    track_id = text.split('/track/')[1].split('?')[0].strip()
                    return f'spotify:track:{track_id}'
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


def run_spotdl(uri, output_dir):
    """Download a Spotify URI to output_dir. Returns True on success."""
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir) + '/{artists} - {title}.{ext}'
    cmd = [
        'spotdl', 'download', uri,
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


def clean_old_files():
    """Delete mp3 files not touched in CACHE_DAYS days and unregister from o2m."""
    cutoff = time.time() - CACHE_DAYS * 86400
    removed = 0
    for f in CACHE_DIR.rglob('*.mp3'):
        if f.stat().st_mtime < cutoff:
            local_uri = file_to_mopidy_uri(f)
            clear_local_track(local_uri)
            f.unlink()
            removed += 1
    if removed:
        print(f"Removed {removed} stale file(s) (>{CACHE_DAYS}d old)")


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

    clean_old_files()
    print(f"=== Done {datetime.now().strftime('%H:%M')} ===\n")


def seconds_until_next_run():
    now = datetime.now()
    target = now.replace(hour=CACHE_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


if __name__ == '__main__':
    if not wait_for_o2m():
        sys.exit(1)

    run_cache()

    while True:
        secs = seconds_until_next_run()
        h = int(secs) // 3600
        m = (int(secs) % 3600) // 60
        print(f"Next run in {h}h {m}m (at {CACHE_HOUR:02d}:00)")
        time.sleep(secs)
        run_cache()
