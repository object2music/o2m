# Offline cache on a native (non-Docker) instance

How to give a Raspberry Pi running o2m natively its **own** offline cache: its own
download queue, its own files, its own ceiling. Written from the deployment done on
Pi #2 on 2026-10-23; every figure below was measured, not estimated.

Read §0 and §2's warning before typing anything. One setting in §2 can delete a music
library.

---

## 0. What you are fixing, and what you cannot

`Track.local_uri` is one column on a row **every instance shares**, and
`OfflineRequest` is keyed on the uri alone — one queue row per track in the whole
installation. The numbered Docker instances point `MUSIC_DIR` at `/home/o2m/music`, so
sharing is correct for them. A Pi shares no disk, and that broke both ways:

* a track the server downloaded read as held by **everyone**, so the Pi answered
  `ready` and then could not open the file;
* a request the Pi queued was drained by the **server's** spotdl (it polls its own API,
  which returned every `pending` row), so the file landed on the server's disk and the
  Pi was left with `state=done` on a path it cannot read.

A **cache pool** fixes both. It names the **disk**, not the machine.

What a native instance can hold afterwards:

| Content | Works | Needs |
|---|---|---|
| Podcast / news episode | yes | §1 + §2 |
| YouTube video | yes | §1 + §2 (`yt_dlp` in the o2m process) |
| Local file (`local:` / `file:`) | yes | §1 only |
| **Spotify track** | **only on Python ≥ 3.10** | §3 — read it before hoping |
| Radio, YouTube playlist | never | a live stream has no end |

**Check this first — it decides whether §3 is possible at all:**

```bash
python3 -V                                   # < 3.10  ->  §3 is a dead end, see why
uname -m ; free -m | awk '/Mem:/{print $2" MB RAM"}' ; df -h /
grep -E '^media_dir' /etc/mopidy/o2m.conf    # the music root; §2 depends on it
```

---

## 1. Declare the cache pool

Required, and it is the whole foundation. `O2M_CACHE_POOL` defaults to `shared`, which
reproduces the previous behaviour bit for bit — so an instance that says nothing is
unaffected, including a Docker instance running an older image. **Isolation is opt-in**,
exactly like `SPOTDL_PRUNE`.

An environment variable rather than an `o2m.conf` key, so it sits beside
`O2M_MUSIC_MOUNT`, whose other half it is.

```bash
sudo mkdir -p /etc/systemd/system/o2m.service.d
sudo tee /etc/systemd/system/o2m.service.d/music-mount.conf >/dev/null <<'CONF'
[Service]
# Where THIS instance sees the music volume. On a native install it is a plain
# directory, not a mount, but offline.MUSIC_MOUNT is the same question.
Environment=O2M_MUSIC_MOUNT=/home/pi/Music
# This instance shares no music volume with the Docker ones, so its downloads and
# its download queue are its own. Pick a name unique to this machine.
Environment=O2M_CACHE_POOL=pi2
CONF
sudo systemctl daemon-reload
sudo systemctl restart o2m
```

`O2M_MUSIC_MOUNT` must equal Mopidy's `media_dir` on a native install (both are the same
real directory). `[local] media_dir` lives in `/etc/mopidy/o2m.conf`, and Mopidy's
`[file] enabled` must be `true` or no substituted path can ever play.

**Verify** — `/health` should answer within ~15 s, and the schema reach v36:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:6681/health
sudo journalctl -u o2m --since '3 min ago' | grep -E 'migration v36|schema version is now'
```

Migration **v36** creates two tables, additively. An older image cannot see them, which
is the property wanted: it keeps polling `OfflineRequest`, keeps serving the shared pool,
and stops draining anyone else.

| Shared pool (default) | Named pool |
|---|---|
| `OfflineRequest` (key: `uri`) | `OfflineClaim` (key: `pool`,`uri`) |
| `Track.local_uri` | `LocalFile` (`pool`,`uri`,`path`) |

---

## 2. The spoken cache — episodes, news, YouTube

> ### ⚠️ `SPOTDL_CACHE_DIR` is the one setting that can destroy data
>
> The pruner walks `CACHE_DIR.rglob('*')` **and nothing above it**. Point it at
> `<media_dir>/cache` and a hand-filled library sitting in `<media_dir>` is out of its
> reach. Point it at `<media_dir>` itself and it will delete that library.
> On Pi #2 that is 5.8 GB of ripped discs with no other copy. Check the value twice,
> then verify with the count in the test below.

Nothing is reimplemented for a native install: `spotdl/cache.py` imports no spotdl
package at module level, so the half that needs none — the spoken queue, the expiry and
the ceiling — runs natively. `SPOTDL_SPOKEN_ONLY=1` selects that shape. One downloader,
one naming scheme (a sha1 stem, so a file one instance fetched is found and merely
registered by another), one registration path, one pruner.

Only `requests` is needed, and o2m already depends on it.

```bash
sudo tee /etc/systemd/system/o2m-spoken-cache.service >/dev/null <<'UNIT'
[Unit]
Description=o2m spoken cache (episodes and videos a device asked for)
After=network-online.target o2m.service
Wants=o2m.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/o2m
Environment=PYTHONUNBUFFERED=1
Environment=O2M_URL=http://localhost:6681
Environment=SPOTDL_SPOKEN_ONLY=1
# See the warning above. <media_dir>/cache, NEVER <media_dir>.
Environment=SPOTDL_CACHE_DIR=/home/pi/Music/cache
# Both are the same real directory here, so the path translation is the identity.
Environment=MOPIDY_MUSIC_DIR=/home/pi/Music
Environment=SPOTDL_MUSIC_MOUNT=/home/pi/Music
# 2 GB, not the Docker instances' 10: this is a 29 GB SD card.
Environment=SPOTDL_CACHE_MAX_GB=2
Environment=SPOTDL_CACHE_DAYS=30
# This pool is this machine's own disk, so it prunes it — and unregisters only its
# own rows, LocalFile being keyed by pool.
Environment=SPOTDL_PRUNE=1
ExecStart=/usr/bin/python3 /home/pi/o2m/spotdl/cache.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now o2m-spoken-cache
sudo journalctl -u o2m-spoken-cache -n 10 --no-pager
```

Expected last line: `Spoken only: no spotdl here. Cache /home/pi/Music/cache, cap 2 GB,
expiry 30 days.`

### Verify, including the pruner's reach

Arm offline on a device for a tracklist holding **at least one podcast or video** (an
all-Spotify tracklist will queue and wait for §3), then:

```bash
# how many files live OUTSIDE the cache — must be identical before and after
find /home/pi/Music -type f -not -path '*/cache/*' | wc -l
ls -la /home/pi/Music/cache/spoken/
sudo journalctl -u o2m-spoken-cache --since '20 min ago' | tail -5
```

A success line reads `  podcast+https://…: ok 17.44 MB`. Measured on Pi #2: queued at
13:01, registered at 13:02, 17.44 MB over a 4G link.

Then confirm the registration went to **this pool only** (adjust the pool name):

```bash
cd /home/pi/o2m/o2m && sudo O2M_CACHE_POOL=pi2 O2M_MUSIC_MOUNT=/home/pi/Music python3 - <<'PY'
import sys, collections
sys.path.insert(0, '/home/pi/o2m/o2m')
from o2m_core.o2mmodels import OfflineClaim, OfflineRequest, LocalFile, Track
from o2m_core import offline
P = offline.cache_pool()
print('pool               :', P, '| shared =', offline.is_shared_pool())
print('queue, this pool   :', dict(collections.Counter(
    r.state for r in OfflineClaim.select().where(OfflineClaim.pool == P))))
print('files held here    :', LocalFile.select().where(LocalFile.pool == P).count())
for r in LocalFile.select().where(LocalFile.pool == P).limit(3):
    print('   ', r.path)
print('shared queue       :', dict(collections.Counter(r.state for r in OfflineRequest.select())))
PY
```

What a correct deployment looks like: `LocalFile` rows under your pool, paths under
**your** `media_dir`, and `Track.local_uri` left `None` for those tracks — the shared
column untouched, so the Docker instances see nothing of what this machine holds.

Forced-eviction test (safe: the cache holds only what you just fetched):

```bash
cd /home/pi/o2m && sudo -u pi env O2M_URL=http://localhost:6681 \
  SPOTDL_CACHE_DIR=/home/pi/Music/cache MOPIDY_MUSIC_DIR=/home/pi/Music \
  SPOTDL_MUSIC_MOUNT=/home/pi/Music SPOTDL_CACHE_MAX_GB=0.001 SPOTDL_PRUNE=1 \
  python3 -c "
import sys; sys.path.insert(0,'/home/pi/o2m/spotdl'); import cache
print('before:', len(cache.cache_entries()), 'file(s)')
cache.enforce_cache_cap()
print('after :', len(cache.cache_entries()), 'file(s)')"
find /home/pi/Music -type f -not -path '*/cache/*' | wc -l   # must not have moved
```

The file must disappear, its `LocalFile` row must disappear with it (a row outliving its
file makes `_resolve_uri` substitute a path that is not there), and the count outside the
cache must be unchanged. Measured on Pi #2: 17.44 MB freed, 1036 files outside the cache
before and after.

---

## 3. Spotify music — a wall, not a to-do

**Spotify cannot be captured from playback**: librespot decrypts into GStreamer, never
into a file. A file exists only if a downloader re-finds the track elsewhere, which is
what spotdl does. The Docker image runs it on `python:3.11-slim`.

On **Python 3.9 (Raspberry Pi OS bullseye) this is not achievable.** Four blockers, each
measured on 2026-10-23, and the fourth has no way round:

1. **spotdl ≥ 4.4 requires Python ≥ 3.10.** Newest usable: **4.3.1**.
2. `soundcloud-v2` 1.7 pulls `curl_cffi`, whose piwheels wheel demands `GLIBC_2.33`
   while bullseye is below it → pin **`soundcloud-v2==1.6.2`** (satisfies spotdl's
   `>=1.6.0,<2`, uses `requests`). *piwheels now builds on a newer Debian, so its recent
   wheels no longer run on bullseye — this trap will recur.*
3. yt-dlp emits `Support for Python version 3.9 has been deprecated` as a warning, and
   spotdl routes yt-dlp's logger to an `error` that **raises** (`providers/audio/base.py:57`),
   so a warning becomes fatal → pin **`yt-dlp==2025.07.21`**, the last release whose
   `_get_system_deprecation` has `MIN_RECOMMENDED = (3, 9)`. From 2025.08.27 it is
   `(3, 10)` and every download dies.
4. **`ytmusicapi` 1.10.3 is the newest release supporting Python 3.9, and it is already
   too old for today's YouTube Music responses** — `KeyError: "Unable to find 'header'"`.
   Every version that fixes that parsing requires ≥ 3.10. **There is no pin that works.**

Everything up to (3) installs cleanly, for the record: piwheels supplies every armv7l
wheel including `pydantic-core` and `rapidfuzz`, **nothing compiles**, and the venv is
128 MB. `spotdl --version` answers `4.3.1`. It simply cannot talk to YouTube any more.

### The ways out, in order of sanity

1. **Reinstall the machine on a current Raspberry Pi OS (trixie, Python 3.13).** Fixes
   the root cause and the piwheels/glibc trap with it. Then §3 is a plain
   `pip install spotdl` in a venv and `SPOTDL_SPOKEN_ONLY=0`.
2. **Install Docker on the Pi** and run the repo's existing `spotdl/Dockerfile`
   (`python:3.11-slim`, which publishes a `linux/arm/v7` variant), pointed at
   `O2M_URL=http://localhost:6681` with this machine's cache paths. No Python change.
3. **Leave it.** §1 and §2 already cover podcasts, news, YouTube and local files. Only
   Spotify music stays server-side.

Do **not** compile Python 3.11+ from source on an armv7l with under 1 GB of RAM to get
there — hours of build, and 99 MB of swap.

### If your Python is ≥ 3.10

```bash
python3 -m venv /home/pi/spotdl-venv
/home/pi/spotdl-venv/bin/pip install --upgrade pip
/home/pi/spotdl-venv/bin/pip install spotdl
/home/pi/spotdl-venv/bin/spotdl --version
```

Then in the unit of §2: `SPOTDL_SPOKEN_ONLY=0`, and add the venv to the unit's PATH so
`run_spotdl`'s bare `spotdl` call resolves —
`Environment=PATH=/home/pi/spotdl-venv/bin:/usr/local/bin:/usr/bin:/bin`.

**Leave the nightly box pass off** unless the disk is large: it prefetches every pinned
box's Spotify tracks — 28 boxes on Pi #1 — which against a 2 GB ceiling only thrashes the
cache, evicting what a device actually asked for. `SPOTDL_BOX_PASS=0` says that:

```
Environment=SPOTDL_BOX_PASS=0
```

The on-demand queues and the pruner stay on; only the guess goes. Do **not** reach for
`SPOTDL_BOX_UIDS` instead — it restricts WHICH boxes and can never say none, and a uid
that does not exist makes `run_cache` return *before* `run_maintenance`, so the nightly
expiry would go with the pass.

---

## Appendix — rolling back

```bash
sudo systemctl disable --now o2m-spoken-cache
sudo rm /etc/systemd/system/o2m-spoken-cache.service
# drop the two Environment= lines from o2m.service.d/music-mount.conf, then:
sudo systemctl daemon-reload && sudo systemctl restart o2m
```

With `O2M_CACHE_POOL` gone the instance is back on the shared pool and behaves exactly as
before. The `OfflineClaim` / `LocalFile` rows it wrote are simply never read again; delete
them if you want (`DELETE FROM offlineclaim WHERE pool='pi2'`). The v36 tables stay —
migrations here are additive only and an older image ignores them.

Files cached under `<media_dir>/cache/spoken/` keep playing for nothing: no row points at
them any more. Remove that directory by hand if you are done with it.
