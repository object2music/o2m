# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

O2M (Object 2 Music) is a system that uses physical objects (NFC tags) to control and mix music, auto-building data-driven playlists. It runs on a Raspberry Pi and wraps [Mopidy](https://mopidy.com/) (a music server) with an API layer, Spotify integration, and a web UI.

## Docker Architecture

The system is split into Docker services defined in `docker-compose.yml`:

- **`mopidy`** (prod+dev): Music playback server with Iris web UI. Exposes port `PORT_MOPIDY` (→6680) and `PORT_MPD` (→6600). Mounts music files from `./data/music`.
- **`o2m`** (prod only): Python/Flask API server on `PORT_O2M_API` (→6681). The core logic layer that bridges NFC tags → Mopidy. Depends on `mopidy` and `mysql`.
- **`snapserver`** (prod+dev): Multi-room audio streaming (Snapcast). Shares `/tmp` with mopidy via a volume.
- **`mysql`** (prod only): Persistent storage for boxes (NFC tag configs) and listening stats. Init data from `o2m/samples/mysql/`.
- **`phpmyadmin`** (prod only): DB admin UI on `PORT_PHPMYADMIN`.
- **`back`** (dev only): PocketBase backend on port 8090. Migrations in `backend/pb_migrations/`.
- **`front`** (dev only): SvelteKit frontend. Hot-reloads `frontend/src/`.

Run production stack: `docker compose --profile prod up`
Run dev stack: `docker compose --profile dev up`

## Running and Testing

### Start services
```bash
docker compose --profile prod up -d
docker compose --profile dev up -d
```

### Run the o2m Python tests
Tests live in `o2m/src/test_tracklistfill.py`. To run from the `o2m/` directory:
```bash
cd o2m/src
python3 -m unittest test_tracklistfill
```
The test file imports `o2mtomopidy` directly (not via package prefix), so it must be run from `o2m/src/`.

### Run o2m locally (outside Docker)
```bash
cd o2m
pip install -r requirements.txt
# Ensure /etc/mopidy/o2m.conf exists (see o2m/samples/o2m.conf)
python3 main.py
```

## Core Python Code (`o2m/`)

The main application is in `o2m/main.py` — it starts Flask on port 6681 and wires everything together.

### Key source files in `o2m/src/`:
- **`o2mtomopidy.py`** — Central logic class `O2mToMopidy`. Manages active NFC boxes, tracklist filling, Spotify recommendations, and stats tracking. This is where most business logic lives.
- **`o2mmodels.py`** — Peewee ORM models (`Box`, `Track`, `Stats_Raw`, `PlaylistLog`, `Artist`, `ArtistGenre`, etc.). Connects to MySQL or SQLite based on `o2m.conf`. Database connection is initialized at module import time. Schema migrations versioned via `CacheMeta` table (`SCHEMA_VERSION` + `_MIGRATIONS` list).
- **`dbhandler.py`** — `DatabaseHandler` class wrapping all DB queries for boxes and stats.
- **`spotifyhandler.py`** — `SpotifyHandler` class wrapping the Spotipy library for recommendations, library lookups, auth, and Last.fm enrichment.
- **`nfcreader.py`** — NFC/smartcard reader integration via `pyscard`. Fires events on card insert/remove.

### Configuration
Config is read from `/etc/mopidy/o2m.conf` (Linux) or `~/.config/mopidy/o2m.conf` (macOS). In Docker, `o2m/create_conf_files.sh` generates this file from environment variables at container start. Key sections: `[o2m]`, `[spotipy]`, `[spotify]`, `[local]`.

### Data flow
1. NFC card detected by `nfcreader.py` → triggers `O2mToMopidy.get_new_cards()`
2. Card UID looked up in `Box` table → retrieves media data (Spotify URI, M3U playlist path, podcast URL, etc.)
3. `box_action()` builds and fills the Mopidy tracklist based on box type and `option_type`
4. `discover_level` (0–10) controls the ratio of familiar vs. new tracks
5. Mopidy events (`track_playback_ended`, `track_playback_paused`) trigger stat updates and dynamic tracklist refilling

### Box `option_type` values
`normal`, `favorites`, `new`, `incoming`, `hidden`, `trash`, `podcast`, `info`

## Frontend (`frontend/`)

SvelteKit + TypeScript + Tailwind CSS app. Source in `frontend/src/`:
- Routes under `src/routes/` (library, flows, radios pages)
- Models in `src/lib/models/` (Box, Flow, Track, Tracklist, etc.)
- Snapcast stream control in `src/lib/utils/snapstream.ts` and `snapcontrol.js`

## Mopidy UI Extension (`mopidy/`)

`mopidy/o2m.js` and `mopidy/o2m.css` are injected into the Mopidy-Iris web UI. `o2m.js` adds O2M sidebar buttons (box toggles, backoffice link, Spotify auth) and displays per-track status badges by calling the O2M API at `base_url` (auto-detected as `<origin-host>:6681/api/`). `mopidy/app.js` is a large webpack bundle for the Iris extension — do not edit directly.

## Environment Variables

All service configuration is via `.env` file (not committed). Key variables:
- `PORT_MOPIDY`, `PORT_MPD`, `PORT_O2M_API`, `PORT_SNAPSERVER_*`, `PORT_MYSQL`, `PORT_PHPMYADMIN`
- `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_TYPE`
- `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI`
- `SPOTIFY_USERNAME`, `SPOTIFY_PASSWORD`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- `HOST_MOPIDY`, `O2M_DISCOVER_LEVEL`, `O2M_DEFAULT_VOLUME`, etc.
- `LASTFM_API_KEY` — Last.fm API key for genre and mood enrichment (injected into `o2m.conf` via `create_conf_files.sh`)

## External API status (2026)

- **Spotify `/audio-features`** — removed Nov 2024, `spotipy` marks it deprecated. No tempo/energy/valence from Spotify.
- **Spotify `/recommendations`** — removed Nov 2024.
- **Spotify artist genres** — no longer returned reliably (`sp.artist()` gives simplified objects, `sp.search()` returns empty arrays).
- **Last.fm** replaces all three: `artist.getTopTags` for genres (min count 10, noise-filtered), `artist.getSimilar` for recommendations, `track.getTopTags` for mood (min count 3, fallback to artist genre cache).

## Cache warmup & CacheMeta

`SpotifyHandler.warmup_cache()` runs at startup in a background thread. Sequence: `liked` → `albums` → `artists` → `playlist_tracks` → `genres` → `moods`. TTLs in `_WARMUP_TTL` (days). `should_warmup()` skips if cache is fresh AND fill rate > threshold derived from `discover_level`.

**Progressive population** — genres (30/run) and moods (50/run) don't set their TTL until all items are covered; each startup processes the next batch.

**CacheMeta corruption**: `updated_at` is stored as BIGINT Unix seconds. An older code path wrote a MySQL DATETIME integer (`YYYYMMDDHHMMSS`, e.g. `20260523060530`) into that column. Peewee then calls `utcfromtimestamp(20260523060530)` → `ValueError: year 644000 is out of range`, killing the warmup thread. `get_cache_meta()` now catches `ValueError`/`OverflowError` and resets the row.

## Peewee ORM conventions

- JOIN queries that alias columns from joined tables (e.g. `Artist.name.alias('artist_name')`) **must call `.namedtuples()`** on the queryset — plain model instances don't expose aliased join columns as attributes.
- `TimestampField(utc=True)` maps to `BIGINT` in MySQL. Always let Peewee convert via `db_value`/`python_value` — never store raw datetime integers.
- Migrations: add `_migration_vN(migrator)`, append to `_MIGRATIONS`, bump `SCHEMA_VERSION`. Use `_add_column_safe()` for `ADD COLUMN` (idempotent). `setup_database()` is safe to call at every startup.

## Mood UI (`o2m/static/mood.html`)

Mobile-first PWA served at `GET /mood`. Dark theme, 3 SVG circular potentiometers (Energy, Valence, Découverte). Architecture rules:
- **CORS**: All Mopidy JSON-RPC calls go through `POST /api/mopidy_rpc` (Flask proxy) — never call Mopidy port 6680 directly from the browser
- Album art fetched via `core.library.get_images` (not from `get_current_tl_track`) → proxied through `GET /api/mopidy_image?uri=...` for non-HTTP URIs
- Click-to-play uses `core.playback.play({tlid})` with the `tlid` from `core.tracklist.get_tl_tracks`
- **Never reconstruct Mopidy URL from `.env` port variables** — those are external mapped ports. Use `mopidy.http_url` (already validated at startup)

## Mood / Energy / Valence enrichment

Track mood features come from Last.fm `_TAG_FEATURES` dict → averaged (energy, valence) from matching tags.

- `warmup_track_moods(batch_size, max_batches)` in `spotifyhandler.py` — called at startup (5 batches of 50) and via `GET /api/warmup_moods` (20 batches async, resets rate-limit sentinel first)
- Tracks with no Last.fm data get `mood='_'` sentinel to avoid endless retries
- `dbhandler.count_tracks_without_mood()` excludes the `'_'` sentinel (only truly NULL moods)
- Deferred enrichment in `o2mtomopidy.update_stat_track()`: if a played track has no mood, a daemon thread calls Last.fm in background without blocking the playback event

## Server topology

Two working directories on the server (`o2m@maudus`):
- `~/o2m_0` → branch `develop_pv` (main prod instance, external port 6681)
- `~/o2m_1` → branch `feature/mood-interface` (secondary instance, external port 6691)

**`docker-compose.yml` on o2m_1 was modified directly on server** — never overwrite it via git pull. All other files: commit → push → pull on server (never edit directly).

Deploy workflow:
```bash
git push
ssh o2m-server 'chmod 600 /home/o2m/o2m_0/.ssh/id_github && git -C /home/o2m/o2m_0 pull'
ssh o2m-server 'docker compose --profile prod -f /home/o2m/o2m_0/docker-compose.yml up -d --force-recreate o2m'
```
`up -d` without `--force-recreate` **does not restart a running container**. `docker restart` reuses existing env — use `up -d` to reload `.env` variables.

## SSH access for automation (`claude-o2m` user)

Restricted user on server for remote docker operations:
- Shell: `rbash` — PATH is restricted, use full paths (`/usr/bin/sudo`, `/usr/bin/docker`)
- sudoers: `/etc/sudoers.d/claude-o2m` — NOPASSWD for `docker compose restart`, `docker ps`, `docker logs`, `docker inspect`
- `Defaults:claude-o2m !use_pty` is required to allow passwordless sudo over non-PTY SSH connections
- `ForceCommand internal-sftp` and `ChrootDirectory` are commented out in `/etc/ssh/sshd_config` (they blocked all command execution)
- `docker exec` and `docker run` are intentionally NOT in sudoers

## Instructions pour Claude
- En fin de session ou avant /compact, propose une mise à jour de ce fichier
  avec les décisions architecturales et conventions découvertes.