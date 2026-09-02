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
Tests live in `o2m/src/test_popularity.py` (popularity scoring). Run from the repo root
(package-prefixed, since it imports `src.popularity`):
```bash
cd o2m
python3 -m unittest src.test_popularity
```

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
- **`o2mmodels.py`** — Peewee ORM models. Connects to MySQL or SQLite based on `o2m.conf`; the connection is initialized at module import time. Current models:
  - **Core**: `Box` (an NFC object: content + settings), `Track` (one row per uri — stats AND cached metadata, the central table), `Stats_Raw` (one row per play: the raw log behind hourly habits), `PlaylistLog`.
  - **Catalogue**: `Album`, `Artist`, `Genre`, `Playlist`, `TagFeature`, `CacheMeta`, and the N:N links `TrackArtist`, `AlbumArtist`, `ArtistGenre`, `TrackGenre`, `AlbumGenre`, `PlaylistTrack`, `AlbumTrack`.
  - **Spoken content**: `PodcastChannel` (one row per show or feed — see the spoken-content section), `RfTaxonomy` (Radio France subject vocabulary), `EpisodeTaxonomy` (episode ↔ subject pivot).

  **Schema migrations**: `SCHEMA_VERSION` (currently **21**) plus an ordered `_MIGRATIONS` list, applied at startup by `ensure_schema`. **Migrations must be additive only** — o2m_0 (prod) and o2m_1 (dev) share the same database, so an older image must keep running against a newer schema. Use `_add_column_safe`; never drop or retype a column a released version reads.
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
`library`, `favorites`, `new`, `incoming`, `hidden`, `trash`, `podcast`, `info`.

The same field on `Track` means something different — it is the track's **lifecycle**
state, not a box type, and is what the UI shows as STATUS. Observed in prod: `new` 54,100 ·
`library` 8,841 · `info` 7,110 · `podcast` 2,199 · `favorites` 765 · `hidden` 753 ·
`incoming` 405 · `trash` 177 (plus 2,456 empty, i.e. never classified).

## Popularity Algorithm (`o2m/src/popularity.py`)

`compute_popularity(...)` → a single float in **[0, 1]**, pure/DB-free, recomputed in
batch by `DatabaseHandler.recompute_popularity` and persisted on `Track.popularity`.
It is the core ranking signal for selection (see below). Components (tunables at the
top of the module):

1. **Completion quality** — Bayesian shrinkage of `read_end` toward the cohort
   completion mean (`prior_completion`, ~0.55): `q = (n·R + M·prior)/(n + M)` with
   `n = read_count_end`, `M = PRIOR_M = 3`. Never-finished tracks collapse to the
   neutral prior (explorable, not 0.5-arbitrary).
2. **Volume** — saturating `log1p(read_count_end)/log1p(VOLUME_REF=20)`, capped at 1.
3. **Base** = `QUALITY_W·quality + VOLUME_W·volume` (0.65 / 0.35).
4. **Skip penalty** — `base ·= 1 − SKIP_W·skip_rate` (`SKIP_W=0.5`, `skip_rate =
   skipped_count/read_count`).
5. **Recency** — soft multiplier in `[REC_FLOOR=0.6, 1]`, half-life 120 days (old
   favourites keep ≥60%).
6. **Explicit / novelty / endorsement** — `+LIKE_BONUS(0.10)` if liked; a fading
   first-play **novelty** boost (`NOVELTY_W=0.15`, 30-day half-life, ÷(1+completions));
   a **playlist** endorsement boost (`+PLAYLIST_W=0.10 · min(playlist_count/4, 1)`).

`option_type` stays OUT of the score (favourites already correlate with quality/volume),
**except `trash` → forced 0**. Non-music (`podcast`/`info`, streams) is left unscored
(`popularity = NULL`, `is_scorable` guard) and ignored by selection.

## Auto-Selection Algorithm (`o2m/src/o2mtomopidy.py`)

`tracklistfill_auto` composes the AUTO mix from sources whose **proportions vary with
`discover_level` (DL)**. Each source gets a linear weight in DL; the weights are then
normalised, so they always sum to the requested track count:

| Source | Weight | DL0 → DL10 |
|---|---|---|
| `favorites` | `−0.8·DL + 10` | 10 → 2 |
| `common` | `−0.3·DL + 8` | 8 → 5 |
| `playlists` | `−0.3·DL + 8` | 8 → 5 |
| `albums_artists` | `0.1·DL + 4` | 4 → 5 |
| `incoming` | `0.3·DL` | 0 → 3 |
| `news` | `1.0·DL` | 0 → 10 |
| `podcasts` (when the box mixes them in) | `0.9·DL` | 0 → 9 |

So DL0 is almost entirely favourites/common (the known), DL10 is dominated by news and
incoming (the unknown). Within each source, tracks are drawn
by one of two weighted samplers (Efraimidis-Spirakis, `_sample_by_weight`). Both realise
the same principle: **DL0 → popularity-dominant, DL10 → pure random.**

### `_mood_pick` (library sources: common/favorites/playlists/albums_artists/incoming/news)
- **Concentric mood weighting** (single weighted draw, no hard band): a DL-scaled
  **Gaussian** around the `(energy, valence)` target, `σ = radius = DL/20 + 0.05` (tight at
  DL0 → broad at DL10). `mood_w = max(exp(−d²/2σ²), floor)` with Euclidean `d`;
  `floor = 0.05 + 0.95·DL/10` rises with DL so mood stops mattering at DL10 (discovery).
  Unknown-mood (NULL energy/valence) tracks sit at `floor` as low-weight fillers, so the
  pool is never empty despite sparse coverage (~1.6% of tracks carry energy/valence).
  Replaced the old hard ±radius in-mood/rest split (`rest_pop_factor` now unused).
- Weight = `popularity^k × mood_w × cooldown`, temperature **`k = (10 − DL)/5`**: DL0→k=2
  (favours popular), DL5→1 (proportional), DL10→0 (uniform / pure random).

### `_expand_pick` (tapped box/playlist/album `option_sort='smart'` + live recos)
Variant = `expand_pick_mode`: **`hybrid` (P0, default)** | `temp` (P1) | `band` (P2).
- **P0 hybrid**: `n_explore = round(n·DL/10)` picks are uniform (cooldown-only, no
  popularity); the rest are exploit, sampled ∝ `affinity^exploit_sharpness(1.3)` where
  `affinity = popularity + 0.15 mood-bonus`. DL0 → all exploit, DL10 → all explore.
- P1 `temp`: one sample ∝ `affinity^k`, `k=(5−DL)/2.5`. P2 `band`: Gaussian around a DL-set
  popularity target (p90 at DL0 → p10 at DL10).

### Anti-repeat cooldown (`_cooldown_factor`, shared by both)
Down-weight in (0,1], multiplicative:
- **Played (multi-day, graduated)**: a just-played track sits at `cooldown_mult=0.05` and
  eases **linearly back to 1.0 over `cooldown_days=2`**, stretched up to ~2× for
  heavy-rotation tracks (`read_count → cooldown_rc_ref=20`) so comfort favourites don't
  recur every session. (Replaced the old hard 8h step — `cooldown_hours` kept for reference.)
- **Served (intra-session)**: just-selected tracks ×`served_mult=0.1` for `served_cooldown_min=30`min.

### Known bias & mitigations
- **Comfort-track over-recurrence**: a high-popularity favourite that's been played a lot
  hits favorites + common + high-pop weighting simultaneously → recurs often. Two guards:
  the multi-day cooldown above, and `get_stat_raw_by_hour` returns **DISTINCT** uris (the
  raw play log has one row per play → a 14×-played track otherwise gets 14 draw tickets).
- **Deep-library under-exposure**: unplayed library tracks surface only via `newrecent`
  (uniform 1/pool, see the novelty section) and the tiny albums bucket; per-fill P is low.
  `newrecent` is scoped to the library (`liked=1 OR album saved=1`) — browsed/lazy-filled
  albums are excluded.

## Spoken Content: Podcasts, News, Radio France

Spoken items (podcast episodes, news flashes) are `Track` rows like any other, but they
carry their own metadata, their own selection rules and their own caching. `option_type`
is `podcast` or `info`; music scoring does not apply (`popularity` stays NULL).

### URI convention — one shape for everything
Every episode is a **mopidy-podcast uri**: `podcast+<feed_url>#<guid>`. This is the single
most important invariant of the subsystem: resume, publication date, duration and channel
all come from that shape. Radio France episodes used to be bare mp3 links
(`proxycast.radiofrance.fr/…mp3`), which forced RF hosts into `_is_spoken_uri`, the
unfinished pool, the volume ducking and the client's stream test. They are now converted
to the `podcast+` shape (see below); the mp3 form survives only as a fallback.

### Radio France (`o2m/src/radiofrance.py`)
Two unrelated APIs, both used:
- **livemeta** (`api.radiofrance.fr/livemeta/pull/<id>`) — what is playing *right now* on a
  live stream. No key.
- **OpenAPI GraphQL** (`openapi.radiofrance.fr/v1/graphql`, header `X-Token`, key in
  `radiofrance_api_key` / `RADIOFRANCE_API_KEY`) — show catalogue, episodes, taxonomies.

Hard-won constraints of the OpenAPI, all verified against the live API — do not
re-derive them:
- `first <= 100`; `Shows` exposes only `edges` (cursor paging, **no** `pageInfo`).
- `showByUrl` rejects episode urls ("Not a show").
- `diffusions` accepts a window of **7 days maximum**.
- Taxonomy filters take **ids**, not names, and are **INTERSECTED** (AND, never OR).
- `taxonomies` needs a non-null inner type: `[TaxonomyTypeEnum!]`, `[String!]`.
- `path` is null for tags and raises if selected on them — themes only.
- `Show.podcast { rss }` is broken server-side. The feed is discovered from the **show
  page** instead (`discover_feed`, no key needed).
- A diffusion may have a page url but **no** `podcastEpisode` — those episodes are not
  playable from the API, yet are usually present in the RSS feed.

### Joining the two sources — `Track.episode_key`
The same broadcast reaches us twice: as an RSS item and as an API episode. The audio files
differ (different `ITEMA` ids), so **there is no key in the media**. Both, however, point
at the same **episode page**, whose trailing numeric id is an exact join — the feed's
`<link>` and the API's `url` end with it. That id is `Track.episode_key`, and it is what:
1. converts an API episode into `podcast+<feed>#<guid>` (`_rf_as_podcast_uri`), and
2. makes cross-source duplicates impossible rather than merged after the fact.

### Catalogue and warmup
- `PodcastChannel` is the **single channel table** (a previous `RfShow` table described RF
  shows a second time and was merged into it, migration v21). `kind` is `rf` or `rss`;
  `feed_url` is the feed backing the channel — discovered once per RF show and cached;
  `rf_id` keeps the API uuid.
- `warmup_podcast_catalogue` refreshes the episodes of every **box-referenced** source
  (feeds, shows, subjects) into `Track`, so a box fills from the DB instead of hitting the
  network on the critical path. `warmup_radiofrance` refreshes the RF show catalogue
  (TTL 7 days) and the taxonomies (TTL 30 days).
- Episodes are purged beyond ~1 year (`purge_old_episodes`).
- Non-RF RSS boxes still query their feed live at fill time — that is intended.

### Box patterns for spoken content
`podcasts:unfinished` (resume what was started) · `podcasts:channel` (the box's own feeds) ·
`infos:library` (scheduled news flash) · `meta_podcasts` / `meta_infos` / `meta_radios`
(all sources of a category) · `rf:show:<url>` (one Radio France show) · `rf:sujet:<keyword>`
(episodes matching a Radio France theme or tag, refilled dynamically).

Note there is **no `meta_music`**: `meta_fill` handles the `music` category, but
`_META_PATTERNS` has no entry for it, so it cannot be written in a box. The BASIC view's
ALL button is a UI action over the four categories, not a pattern.

### Behaviours to know
- **Classification** (`_spoken_type_for_uri`): box heritage first (`info` beats `podcast`),
  then duration (< 20 min → `info`), then `podcast`. It accepts a `podcast+…` uri **or** a
  bare feed url — the catalogue warmup classifies a whole feed at once and passes the
  latter.
- **Budget sharing**: a box mixing several feeds shares its `max_results` between them in a
  rolling fashion, so one prolific feed cannot crowd out the others.
- **Resume**: any spoken item resumes at its saved position (minus 10s).
- **Pre-roll ads**: a fixed skip per host (30s for Radio France and BBC hosts, overridable
  with `podcast_ad_skip = host:ms`), applied only on a fresh start. It cannot be detected:
  no feed exposes chapters or ad markers, and `itunes:duration` already includes the ad.

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

### Four filling paths

**1. Warmup at startup** (`warmup_cache` → `warmup_track_moods`, `spotifyhandler.py`)
- Up to 250 tracks/startup (5 batches × 50), ordered by `read_count_end` DESC
- TTL = 30 days, but **only activated when all tracks are covered** → re-runs every startup until complete
- Controlled by `should_warmup('moods', discover_level)`

**2. Manual trigger** `GET /api/warmup_moods`
- Resets TTL to 0, runs up to 1000 tracks (20 × 50) in background thread

**3. Deferred enrichment on playback end** (`o2mtomopidy.py`, `track_playback_ended`)
- Triggers when `stat.energy is None AND stat.mood is None` after a track ends
- Fires a background thread calling `_lastfm_get_track_mood`

**4. Preemptive enrichment at fill time** (`o2mtomopidy.py`, `add_tracks`)
- Every track added to the tracklist that is feature-less (`mood` NULL or `_`, or
  `energy` NULL) **and unlocked** (`mood_edited_at IS NULL`) is queued in `_enrich_items`
  and enriched in the background, before it plays.
- This is what turned the mood coverage around: enrichment follows actual listening
  instead of waiting for a warmup to reach a track by `read_count_end` rank.

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

### Prod DB fill rates (shared o2m_0/o2m_1 database, measured 2026-09-02)

| Entity | Total | With name | Mood filled | Mood sentinel `_` | Energy/valence |
|--------|-------|-----------|-------------|-------------------|----------------|
| Tracks | 76,815 | 52,187 | **40,941** | 7,709 | **40,229** |

Artists: 1,285, of which **1,247 carry genres (97%)**. Albums 7,880 · Genres 694 ·
Playlists 53 (10,406 memberships) · Boxes 150 · Stats_Raw 102,542 plays.
Mood distribution: happy 21,123 · calm 13,153 · energetic 5,482 · dark 1,183.

**This replaces the May 2026 figures, which described a pipeline that barely worked**
(108 tracks with mood, 1.1%; 57 artists with genres, 24%). Two things fixed it, and both
matter when reasoning about the engine:
- the **genre pipeline reaching near-full coverage** (24% → 97% of artists), which makes
  the artist-genre fallback in `_lastfm_get_track_mood` productive instead of anecdotal;
- **preemptive enrichment at fill time** (path 4 above), which follows real listening.

The old "50 tracks stuck in an infinite warmup loop" bug (energy set, mood NULL) is
**effectively closed**: 3 rows remain. 4,479 named tracks still have no mood and no
sentinel — these are simply not yet reached, not stuck.

`mood_edited_at` is set on 23,768 rows. It is a **lock**, not a claim of hand-editing:
any write through `update_track_features_manual` stamps it so a later warmup cannot
overwrite the value. Treat it as "authoritative", not "curated by a human".

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
- `RADIOFRANCE_API_KEY` — Radio France OpenAPI token (show catalogue, episodes, subjects).
  Without it the RF features degrade silently: livemeta (now-playing on live streams) and
  plain RSS feeds keep working, `rf:show:` / `rf:sujet:` do not.

Note: `.env` changes need `docker compose up -d` to be injected — a `restart` reuses the
old environment.
