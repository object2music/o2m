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
- **`o2mmodels.py`** — Peewee ORM models (`Box`, `Stats`, `Stats_Raw`). Connects to MySQL or SQLite based on `o2m.conf`. Database connection is initialized at module import time.
- **`dbhandler.py`** — `DatabaseHandler` class wrapping all DB queries for boxes and stats.
- **`spotifyhandler.py`** — `SpotifyHandler` class wrapping the Spotipy library for recommendations, library lookups, and auth.
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
`library`, `favorites`, `new`, `incoming`, `hidden`, `trash`, `podcast`, `info`

## Frontend (`frontend/`)

SvelteKit + TypeScript + Tailwind CSS app. Source in `frontend/src/`:
- Routes under `src/routes/` (library, flows, radios pages)
- Models in `src/lib/models/` (Box, Flow, Track, Tracklist, etc.)
- Snapcast stream control in `src/lib/utils/snapstream.ts` and `snapcontrol.js`

## Mopidy UI Extension (`mopidy/`)

`mopidy/o2m.js` and `mopidy/o2m.css` are injected into the Mopidy-Iris web UI. `o2m.js` adds O2M sidebar buttons (box toggles, backoffice link, Spotify auth) and displays per-track status badges by calling the O2M API at `base_url` (auto-detected as `<origin-host>:6681/api/`). `mopidy/app.js` is a large webpack bundle for the Iris extension — do not edit directly.

## Mood / Energy / Valence Pipeline

Tracks carry three enrichment fields (added via DB migrations v5/v6):
- `mood` TEXT — categorical: `calm`, `energetic`, `dark`, `happy`, or `_` (sentinel = tried, no data)
- `energy` FLOAT — 0.0 (sleep/ambient) → 1.0 (metal/hardcore)
- `valence` FLOAT — 0.0 (dark/grief) → 1.0 (joyful/euphoric)

### Three filling paths

**1. Warmup at startup** (`warmup_cache` → `warmup_track_moods`, `spotifyhandler.py`)
- Up to 250 tracks/startup (5 batches × 50), ordered by `read_count_end` DESC
- TTL = 30 days, but **only activated when all tracks are covered** → re-runs every startup until complete
- Controlled by `should_warmup('moods', discover_level)`

**2. Manual trigger** `GET /api/warmup_moods`
- Resets TTL to 0, runs up to 1000 tracks (20 × 50) in background thread

**3. Deferred enrichment on playback end** (`o2mtomopidy.py`, `track_playback_ended`)
- Triggers when `stat.energy is None AND stat.mood is None` after a track ends
- Fires a background thread calling `_lastfm_get_track_mood`

### Scoring logic (`spotifyhandler.py`)

`_lastfm_get_track_mood(artist, track)`:
1. **Primary**: `track.getTopTags` (Last.fm) — tags with `count >= 3` only
2. **Fallback**: artist genres from `ArtistGenre` cache (no API call, `allow_api=False`)

Scoring uses:
- `_MOOD_TAGS` — 4 categories (calm/energetic/dark/happy) → ~70 tag strings
- `_GENRE_MOOD` — genre name → mood category (narrower set than `_MOOD_TAGS`)
- `_TAG_FEATURES` — 50+ tags → `(energy, valence)` numeric tuple, averaged across matches

Returns `(mood, energy, valence)`. If only energy/valence found (mood=None), `update_track_features`
sets energy/valence but leaves mood=NULL — **these tracks are picked up again by the next warmup**
(known issue: should be given a derived mood or a different sentinel to break the loop).

### Genre pipeline

`warmup_artist_genres` (`spotifyhandler.py`) — called inside `warmup_cache`:
- 30 artists per run, 0.3s/call via Last.fm `artist.getTopTags`
- Fallback: Spotify `search()` if no Last.fm key
- TTL = 14 days, **only set when all artists are covered**
- Note: the function's docstring incorrectly says "not run automatically" — it IS in `warmup_cache`

### Prod DB fill rates (o2m_0, measured 2026-05-30)

| Entity | Total | With name | With name+artist | Mood filled | Mood '\_' | Pending |
|--------|-------|-----------|-----------------|-------------|-----------|---------|
| Tracks | 45,744 | 20,864 | 9,797 | 108 (1.1%) | 481 | 9,208 |
| Energy/valence | — | — | 9,797 | 158 (1.6%) | — | — |

**50 tracks have energy set but mood=NULL** — these are stuck in an infinite warmup loop (see bug above).

Artists: 234 with names, 57 with genres (24%). Top genres: jazz (26), rock (13), alternative (10), piano (7), folk (5), chanson française (5).

**Root cause of low fill rate**: many niche/French tracks (Alain Bashung, Têtes Raides…) have no
`track.getTopTags` data on Last.fm (→ 81% of attempted tracks get sentinel `_`). The artist-genre
fallback partially helps for energy/valence but `_GENRE_MOOD` doesn't cover tags like
`chanson francaise`, `jazz fusion`, `african`, so mood stays NULL.

### API endpoints

- `GET /api/warmup_moods` — trigger background mood warmup (up to 1000 tracks)
- `GET /api/warmup_genres` — trigger background genre warmup
- `GET /api/diag/genres` — synchronous genre diagnostic, returns JSON
- `GET /api/mood` — current mood state + energy/valence distribution + pending count
- `POST /api/mood` — set `energy`, `valence`, `genres` → triggers `apply_mood_settings()`
- `GET /api/genres` — genre list with track counts
- `GET /mood` — mood UI (served from `o2m/static/mood.html`)

## UI Language Convention

**All user-facing UI text is English by default** (labels, buttons, feedback messages,
tooltips, placeholders). This applies across the whole project — the mood UI
(`o2m/static/mood.html`), the SvelteKit frontend (`frontend/`), and any new interface.
Write new strings in English; translate existing French strings to English when you
touch surrounding code. Some user-facing concepts are
renamed for clarity (e.g. the *valence* control is labelled **Ambiance**).

**Code and code comments are also English by default.** Write all new code,
identifiers and comments in English. When editing a file that still has French
comments, translate the ones you touch. (Chat/explanations to the user stay in the
language the user writes in — this rule is about what lands in the codebase.)

## Icon Convention

**Never use emoji as icons.** Use the project's chosen B&W icon set:
**Feather / Lucide-style inline SVG** — stroke-based, `viewBox="0 0 24 24"`,
`fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
stroke-linejoin="round"`, sized via CSS (`width/height`). They inherit `currentColor`
so they adapt to every theme automatically. This applies everywhere (mood UI, frontend,
new interfaces): playback controls, footer links, the details-panel lock/heart, status
glyphs, etc. When you touch code that still has emoji icons (e.g. 🔒 ♥ ⚡), replace them
with the equivalent Feather/Lucide SVG.

## Environment Variables

All service configuration is via `.env` file (not committed). Key variables:
- `PORT_MOPIDY`, `PORT_MPD`, `PORT_O2M_API`, `PORT_SNAPSERVER_*`, `PORT_MYSQL`, `PORT_PHPMYADMIN`
- `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_TYPE`
- `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI`
- `SPOTIFY_USERNAME`, `SPOTIFY_PASSWORD`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- `HOST_MOPIDY`, `O2M_DISCOVER_LEVEL`, `O2M_DEFAULT_VOLUME`, etc.
- `LASTFM_API_KEY` — required for mood/genre enrichment via Last.fm
