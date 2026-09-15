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
Tests live beside the code they cover, in `o2m/o2m_core/`: `test_popularity.py`
(popularity scoring), `test_boxdirectives.py` (time windows, mood/dl directives),
`test_player_port.py` (the player port's anti-drift check) and `test_webmedia.py`
(the `xp:` page reader). Run from the repo root (package-prefixed, since they import
`o2m_core.*`):
```bash
cd o2m
python3 -m unittest discover -s o2m_core -p 'test_*.py' -t .
python3 -m unittest o2m_core.test_popularity      # or one at a time
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

### Key source files in `o2m/o2m_core/`:
- **`o2mtomopidy.py`** — Central logic class `O2mToMopidy`. Manages active NFC boxes, tracklist filling, Spotify recommendations, and stats tracking. This is where most business logic lives.
- **`o2mmodels.py`** — Peewee ORM models. Connects to MySQL or SQLite based on `o2m.conf`; the connection is initialized at module import time. Current models:
  - **Core**: `Box` (an NFC object: content + settings), `Track` (one row per uri — stats AND cached metadata, the central table), `Stats_Raw` (one row per play: the raw log behind hourly habits), `PlaylistLog`.
  - **Catalogue**: `Album`, `Artist`, `Genre`, `Playlist`, `TagFeature`, `CacheMeta`, and the N:N links `TrackArtist`, `AlbumArtist`, `ArtistGenre`, `TrackGenre`, `AlbumGenre`, `PlaylistTrack`, `AlbumTrack`.
  - **Spoken content**: `PodcastChannel` (one row per show or feed — see the spoken-content section), `RfTaxonomy` (Radio France subject vocabulary), `EpisodeTaxonomy` (episode ↔ subject pivot).
  - **Offline**: `OfflineRequest` (a track a device wants and the server has no file for — the hand-off to spotdl; see the offline section).

  **Schema migrations**: `SCHEMA_VERSION` (currently **23**) plus an ordered `_MIGRATIONS` list, applied at startup by `ensure_schema`. **Migrations must be additive only** — o2m_0 (prod) and o2m_1 (dev) share the same database, so an older image must keep running against a newer schema. Use `_add_column_safe`; never drop or retype a column a released version reads.
- **`dbhandler.py`** — `DatabaseHandler` class wrapping all DB queries for boxes and stats.
- **`webmedia.py`** — the `xp:<url>` page reader: fetch a web page, find what o2m can
  play in it, and resolve it to a stream (yt_dlp). Experimental; see its own section.
- **`spotifyhandler.py`** — `SpotifyHandler` class wrapping the Spotipy library for recommendations, library lookups, and auth.

### Configuration
Config is read from `/etc/mopidy/o2m.conf` (Linux) or `~/.config/mopidy/o2m.conf` (macOS). In Docker, `o2m/create_conf_files.sh` generates this file from environment variables at container start. Key sections: `[o2m]`, `[spotipy]`, `[spotify]`, `[local]`.

### Data flow
1. NFC card detected by the **separate** reader project
   ([object2music/o2m_nfc](https://github.com/object2music/o2m_nfc)), which activates
   the box through the O2M API — it is not part of this repo. The old in-tree
   `nfcreader.py` was dead since 2023 (it still called a `get_new_cards()` that no
   longer existed) and has been removed.
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

## Popularity Algorithm (`o2m/o2m_core/popularity.py`)

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

## Auto-Selection Algorithm (`o2m/o2m_core/o2mtomopidy.py`)

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
Down-weight in (0,1]. **Two clocks measure "recently", and the stricter one wins** —
`min()`, not a product: each is a full-strength constraint, and multiplying would demote a
track twice for one offence.

- **Elapsed time**, graduated: a just-played track sits at `cooldown_mult=0.05` and eases
  linearly back to 1.0 over `cooldown_days=3`, stretched up to ~2× for heavy-rotation
  tracks (`read_count → cooldown_rc_ref=20`) — so up to 6 days. (Replaced the old hard 8h
  step — `cooldown_hours` kept for reference.)
- **Rotation depth**: how much OTHER music has played since, over `cooldown_plays=80`
  (up to 160 stretched). `Track.last_play_seq` records the `stats_raw.id` of a track's last
  play; `recent_music_play_seq` reads the last `cooldown_seq_window` music-play ids once
  per fill, and a bisect per candidate gives the count. That window is **derived**, not
  set: `max(200, cooldown_plays × 2 × 1.25)`. A ruler shorter than the widest depth window
  would silently cap the rule — every track older than the tail looks infinitely far away
  and goes free.

Both were doubled from `cooldown_days=2` / `cooldown_plays=40` after a 24-play favourite
came back at 4.6 days and 115 intervening plays, i.e. just past both windows. Simulated
before applying: that track goes from factor 1.000 to 0.733, and the braked population of
the sequence window from 98 to 159 tracks (29 → 45 strongly). A fill still returns 59
distinct tracks with no empty-pool warning, so the pool is not starved.
- **Served (intra-session)**: just-selected tracks ×`served_mult=0.1` for
  `served_cooldown_min=30`min. This one multiplies — it answers a different question.

**What a `stats_raw` row means.** A play is only logged when `position / length > 0.9` —
a skipped or interrupted track never enters. Measured: 47,343 rows against 79,688 starts
(0.59) but 55,360 completions (0.86). So rotation depth counts music actually LISTENED to,
not served. Weighting partial plays by their completion was considered and rejected: it
would advance the depth ~32% faster, i.e. free tracks *sooner*, the opposite of the intent
— and the same rows feed the hourly habits, which must not learn from what was skipped.

**Why depth and not time alone.** Measured on this install: **80% of the intervals between
two plays of the same track exceed four days**, i.e. past every time window, so a popular
track could be picked again and again as long as the calendar moved, however little music
had actually gone by. Depth is what a listener perceives as repetition; time is only a
proxy, and a poor one when listening is sporadic. (The observed rotation is nonetheless
healthy — median gap 288 plays / 11.8 days — so this hardens the mechanism rather than
fixing a fire.)

Depth counts **music only**: 55% of `stats_raw` rows are podcasts, radios and box
activations, and an evening of podcasts is not other music having gone by — counting them
would inflate the depth and lift the cooldown early, which is the failure it exists to
prevent. A track with no `last_play_seq` falls back to time alone.

**`backfill_last_play_seq` runs once at startup**, and it has to. `last_play_seq` is only
written when a track ENDS, so on the day the column was added the depth rule protected
**25 tracks out of 22,733 already played — 0.1%**, while `stats_raw` held the position of
the last play for 15,138 of them. Letting it "fill in as tracks play" would have left the
rule meaningless for weeks, on exactly the popular tracks it exists to slow down. One
statement, guarded by a CacheMeta flag: 158ms the first time, 0.7ms after.

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

### Radio France (`o2m/o2m_core/radiofrance.py`)
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
`podcasts:unfinished`, `podcasts:channel`, `infos:library`, `meta_podcasts` / `meta_infos` /
`meta_radios`, `rf:show:` and `rf:sujet:` — all defined once in **Box Data: the complete
line reference** below, with every other line type. Kept in one place on purpose: two
lists of the same patterns drift.

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

## Box Data: the complete line reference

A box's `data` is a list of lines. Each is one of four things, and the dispatcher in
`tracklistappend_box` is the authority — `BOX_KEYWORDS` in `mood.html` is the picker's
copy of the same list, and the two are currently in parity (verified by comparing the
dispatch branches against the picker).

### 1. Sources — a literal thing to play
| Line | What it adds |
|---|---|
| `spotify:track:…` · `spotify:album:…` · `spotify:artist:…` · `spotify:playlist:…` | that object |
| `podcast+<feed_url>` | the feed's episodes (`?max_results=N` caps it) |
| `podcast+<feed_url>#<guid>` | one episode |
| `rf:show:<url>` | one Radio France show |
| `http(s)://…` · `tunein:…` | a radio stream |
| `local:…` · `m3u:…` · `file:…` | local files |
| `yt:…` · `youtube:…` | YouTube |
| `box:<uid>` | **another box**, included whole (cascade) |
| `xp:<page url>` | **whatever media that web page holds** — experimental, see below |

### 2. Smart patterns — a rule that resolves to tracks at fill time
| Pattern | What it draws |
|---|---|
| `auto:library` | the full AUTO mix (all sources, DL-weighted — see the selection section) |
| `auto_simple:library` | the AUTO mix, reduced set of sources |
| `auto_podcast:library` | the AUTO mix with podcasts mixed in |
| `spotify:library` | saved albums + artists |
| `spotify:library2` | saved albums + artists + liked tracks |
| `o2m:favorites` | O2M favourites (`spotify:favorites` is the legacy spelling, still honoured) |
| `newrecent:library` | recent library additions, drawn uniformly |
| `newnotcompleted:library` | started but never finished |
| `now:library` | what is usually played at this hour |
| `herenow:library` | daily habits (hour + library extract) |
| `albums:spotify` | a random saved album or artist |
| `albums:local` | a random local album |
| `podcasts:unfinished` | episodes already started, most recent first |
| `podcasts:channel` | the episodes of this box's own feeds |
| `infos:library` | the scheduled news bulletin (see the two-clocks note below) |
| `rf:sujet:<keyword>` | Radio France episodes matching a theme or tag, refilled dynamically |
| `meta_podcasts` · `meta_infos` · `meta_radios` | every source of that category, across all boxes |
| `recommendation:…` | live Spotify recommendations (legacy; the API has since been restricted) |

There is **no `meta_music`**: `meta_fill` handles the `music` category, but
`_META_PATTERNS` has no entry for it, so it cannot be written in a box. The BASIC view's
ALL button is a UI action over the four categories, not a pattern.

### 3. Settings — read BEFORE the box is filled
These force what the dials would otherwise decide (`o2m_core/boxdirectives.py`):

| Line | Effect |
|---|---|
| `mood:calm` | one of `intense` · `calm` · `normy` · `happy` · `energetic` — the BASIC detents |
| `mood:0.3,0.8` | the precise `energy,valence` pair |
| `dl:7` | discover level, 0-10 |

They are read in a **pre-pass**, never in the dispatch loop: the fill settles its mood and
DL before serving any entry, so a `mood:` line placed after `auto:library` would otherwise
have had no effect on it and the order inside the box would silently change the result.

**Precedence**, ordered in time rather than ranked (`effective_mood` / `effective_dl`):
a dial gesture newer than the activation → a box directive (a matching time window beats an
unconditional line, whatever the order typed) → the box column (`option_energy` /
`option_valence` / `option_discover_level`) → the session default. Putting an object down is
itself a fresh intent and hands precedence back to the box, which is why the activation is
stamped at the API entry point and **not** in `box_action` — eight internal paths go through
that one (cascade includes, every reload, applying a mood).

**Cascades inherit.** An included box (`box:<uid>`) is part of the object you put down, so
it plays under that object's mood and discover level unless it states its own — the child's
directive or column still wins, inheritance only fills what it leaves unsaid. The lineage
is a durable map (`_box_parent`, child uid → parent uid), not a stack around the fill: the
question is asked again long after, when the dials refresh and when the end-of-track
recommendations pick what to add next to a track belonging to the child. It is resolved on
demand, so a parent whose mood sits under a time window that has since turned hands down
the new value; and it is forgotten when either box is deactivated.

**With several boxes active, "in effect" is only defined relative to a track** — the one
being played. `ambient_settings(track_uri, tlid)` resolves the box that owns it and returns
its effective `(energy, valence, dl)`; `GET /api/mood` reports the same box in
`effective_energy` / `effective_valence` / `effective_dl` / `forced_by`, falling back to the
first active box when nothing plays. So the dials show what the next additions will follow,
not an average of boxes that would describe none of them.

**End-of-track recommendations use that same ladder.** They used to disagree with the fill:
the DL came from the owning box's *column* while the mood came from the *session*, so a box
forcing `calm` filled calm and then had neutral tracks appended to it.

### 4. Labels and disabling
A `#` line immediately before a directive is its **human label**; a `#` in front of a
directive **disables** it. Anything unrecognised is kept verbatim as a raw line —
`parseBoxData` / `serializeBoxData` round-trip losslessly, verified.

### Time windows — any line can be gated
Inline, one line at a time:

    08:00-10:00 > infos:library
    18:00-23:00 > meta_radios
    22:00-02:00 > dl:2

Or as a **block**, opened by a window followed by a brace and closed by one:

    08:00-10:00 > {
      infos:library
      mood:calm
    }
    auto:library          <- outside the block again

Repeating the same window on six lines is where a typo lives, and the lines of a morning
belong together. An inline window on a line *inside* a block wins for that line, and an
unclosed block runs to the end of the data — the forgiving reading.

**The delimiters are explicit, and that is the whole point.** A first version used
indentation and it was wrong: `parseBoxData` trims every line, so opening a box in the
editor and saving it flattened the block and turned its gated lines into permanent ones —
worse than not working. Indentation is now decoration; braces survive a trim. Neither
character starts a line anywhere in the 150 existing boxes, so nothing can collide.

`iter_lines` resolves both shapes once, at the top of `tracklistappend_box`, so the
prefetch pools and the dispatch both work on plain stripped payloads — no prefix and no
block indentation left to trip a `startswith()`.

Start inclusive, end exclusive; a window whose end is not after its start **wraps midnight**.
The prefix is generic on purpose: gating the morning news is as useful as gating a mood.

**A cascade multiplies content, and that is not a bug.** Each included box fills with its
own `max_results`, added to the parent's: measured 11 → 17 → 21 tracks for one, two and
three sources. A box gating two includes to the morning therefore serves noticeably more
before 9am than after. Checked for accumulation across a mood change (remove-then-refill
could have doubled a cascade): it does not — 17 → 17 → 17 over two successive changes.

**Two clocks, and they must not be confused.** Windows and the `infos:library` bulletin
grid are read in LOCAL time (`boxdirectives.local_now`: the process timezone when the
deployment sets TZ, else `Europe/Paris` explicitly — every instance's compose is its own
file and cannot be relied on). Listening HABITS (`now:library`, `herenow:library`, the
`common` bucket, `day_time_average`) are read in UTC via `O2mToMopidy.stats_hour`, because
`read_hour` is written in UTC across 100k+ rows. They agreed only by accident while the
containers ran on UTC; setting a timezone without splitting them would have offset every
habit query by two hours. Anything DISPLAYED from a stored timestamp goes through
`boxdirectives.to_local` — the database keeps UTC, the reader reads local — rather than
growing a third definition of local time next to those two.

Window-aware scanning matters elsewhere too: a window says WHEN a line plays, not whether
the box refers to it, so the catalogue warmup and the directory listings strip the prefix
before matching — otherwise a gated feed would stop being pre-cached.

## `xp:<url>` — the media a web page holds (experimental)

Every other box line names something to play. `xp:` names a **page** and asks what is
playable inside it, which is a different act: the answer is not in the line, it is on
the other side of a fetch, and it changes when the page does. It exists because a great
deal of what one wants to listen to is not published as a podcast — a film on its own
site, a replay listing from a ministry, a conference buried in a resource page.

All of it lives in **`o2m/o2m_core/webmedia.py`**, with `test_webmedia.py` beside it.

### Two steps, cached apart, because they age at completely different rates
1. **Discovery** (`find_media`) — the page, fetched once and parsed. A page changes over
   days: memoised **6 h**.
2. **Resolution** (`resolve_stream`, yt_dlp) — one media reference turned into bytes a
   GStreamer pipeline can open. Memoised **30 min**, and less when the url says so.

That split is not tidiness. The signed url Vimeo hands back carried an expiry **5.8 hours
out** (measured), and these items run an hour each — a tracklist filled at six o'clock
would hand a dead url to its fourth track. So resolution is **late**: it happens in
`_resolve_uri`, at `tracklist.add`, the same choke point that substitutes `local_uri`.
`_expiry_of` reads the epoch most CDNs park in their signature and refuses to serve a url
within `_EXPIRY_MARGIN` (10 min) of it — guessing too short costs a re-resolution,
guessing too long costs a track that dies mid-play.

### The uri that lasts is not the url that plays
`xp:<media page>` is stable and is what carries the resume position, the cooldown and the
stats; `https://skyfire.vimeocdn.com/1789511813-0x…` is valid for an afternoon.
`_played_to_canonical` maps one back to the other — the same dict a downloaded Spotify
track already needed, for the same reason: Mopidy reports playback against the uri it was
handed, and stats must land on the stable one. (It was `_local_to_spotify`; the name
described half of what it now holds.)

**One spelling per media** (`canonical_media_url`), because the uri IS the identity: a
page was observed carrying `dai.ly/xamdswq` and `dailymotion.com/video/xamdswq` for the
same video, which would have been two histories of half a listener each. Player chrome
and campaign parameters are dropped — but by **denylist, never allowlist**: Vimeo's `h=`
is the unlisted-video hash, and without it the video does not exist.

### Discovery routes to the existing schemes; `xp:` is what nothing else can carry
| Found on the page | Comes back as | Played by |
|---|---|---|
| a YouTube link or embed | `yt:video:<id>` | Mopidy-YouTube (which has its own cache) |
| an `<audio>`, a bare `.mp3`/`.m4a`/… | its own https url | mopidy-stream |
| `<link rel=alternate type=rss>` | `podcast+<feed>` | the whole podcast subsystem |
| Vimeo, Dailymotion, SoundCloud… | `xp:<url>` | o2m, via yt_dlp |

`_PLATFORMS` is not a statement about what yt_dlp can do (some 1800 sites) — it is about
what a page link is allowed to drag into a tracklist. Without it, every share button and
footer link becomes a candidate track.

The page is registered as a **`PodcastChannel` with `kind='web'`** and each item points at
it through `Track.channel_id`. That is not bookkeeping: it is where the Referer lives.

### The Referer is tried SECOND, and both halves of that were measured
* **Vimeo requires it.** An embed-only video — what a film's own site uses — answers
  *"Cannot download embed-only video without embedding URL"* to every direct request, and
  hands over the film when the embedding page arrives as `Referer`.
* **Dailymotion refuses it.** The identical canonical url resolves plain and answers
  *"No video formats found!"* the moment one is attached. Reproduced three times running,
  alternating on the same video.

So neither "always" nor "never" is right, and a per-host table of who wants one would
simply be wrong about the next platform. `resolve_stream` asks plainly and retries with
the page: one wasted request on embed-only videos, once, and nothing to keep updated.
**This cost half a day of misreading it as rate-limiting** — the failures looked like
throttling because they followed successes.

### A page can simply refuse, and that is an answer, not an absence
uved.fr answers every client — plain, browser-UA, Googlebot, `facebookexternalhit` alike —
with a CrowdSec javascript challenge: HTTP 200, 296 KB, no media. Solving that means
running a browser, so `find_media` reports it instead: `reason` is a code to branch on
(`challenge` | `unreachable` | `not-a-url`) and `error` the sentence to show. **Both empty
means the page was read**, and an empty `items` then honestly means it holds nothing
playable — a different answer from a refusal, which must never be reported as the same
thing.

The cache follows that distinction: a challenge and a parsed page are stable facts about
the page and are cached; a timeout or a 502 is an accident of the minute and is **not** —
remembering it for six hours would turn one bad moment into an afternoon of a box silently
missing its page. A refused *extraction* is remembered for 5 min (`_TTL_FAILURE`), not to
spare the platform but to spare the box: without it, an unextractable item is re-asked on
every fill, each ask a live round trip on the path filling a tracklist someone is waiting for.

### Where it plugs in
* **Box line** — `xp:<url>`, dispatched in `tracklistappend_box`, sharing the box budget
  between several pages exactly as podcast feeds do (one replay listing holding three
  hour-long conferences must not crowd out the rest of the box). `xp_page_tracks` filters
  through `_unread_spoken_uris`, so a replay watched to the end does not come back.
* **Search** — pasting any page url into `/api/search` shows what is in it, the same
  gesture `rf_resolve_url` already offered for radiofrance.fr, generalised. A refusal comes
  back as `results['web_page']`.
* **Classification** — items are spoken content: `_SPOKEN_URI_RE` matches `^xp:`, so they
  resume at their position, are eligible for `podcasts:unfinished`, and stay out of music
  scoring (`popularity` NULL). The page, not the item, is what
  `_spoken_type_for_uri` classifies — as a feed is classified whole.
* **Names** — the row is opened **without** one. What a page calls a link ("Lire le replay
  …") is a button label, not a title, and `upsert_episodes` never overwrites a name once
  set, so writing the provisional one would lock the real title out for good. The
  extractor supplies it a moment later, at resolution.
* **Unresolvable items are dropped** in `_resolve_uris` rather than handed to Mopidy, which
  has no backend for `xp:` and would lose them silently.

### Dependencies, and one that is not obvious
`yt_dlp` **and `curl_cffi`** in `o2m/requirements.txt`. The second is not a hard dependency
of the first and is not optional here: Dailymotion demands a TLS fingerprint it recognises,
*intermittently*. It resolved fine in the mopidy container, which has no `curl_cffi`
either, and then answered *"attempting impersonation, but none of these impersonate
targets are available: firefox"* in the o2m one. A missing `curl_cffi` is a feature that
works until the day it does not. Wheels exist for musl, so the alpine image needs no
toolchain.

### Known limits
* **No offline.** `/api/audio` does not serve `xp:` yet — the signed url expires, so a
  download would have to re-resolve at fetch time.
* **Video bytes.** Vimeo publishes no audio-only format, so `bestaudio/best` falls back to
  a progressive mp4 whose video track GStreamer decodes and drops. Correct, just wasteful.
  Dailymotion does answer audio-only HLS (`hls-0_aac_q2`).
* **Javascript-rendered pages** yield nothing: the parser reads HTML, not a DOM.

## Offline: the device holds the audio and plays it itself

Everywhere else the browser is a remote control — Mopidy plays, Snapcast streams the
result to the phone, every button is an RPC. Offline inverts that: the device keeps its
own copies and plays them through a plain `<audio>` element, server out of the loop.
The control answers "do I still need a network", not "is there one" — which is why
the network reading was folded INTO it rather than kept beside it.

**One control, three states.** Where the audio comes out is a single question with three
answers, so it is one button (`#btn-snapcast`, `cyclePlaybackTarget`) cycling through
them: **remote** (the server plays, this device is only a remote) → **snapcast** (the
server plays and this device is a speaker) → **offline** (this device plays its own
files) → remote. They are mutually exclusive in fact — `offStart` stops the Snapcast
stream — and two separate toggles made that exclusivity something the user had to know
rather than something the control expressed. Where Snapcast is not configured the cycle
has two stops rather than a dead button: offline must stay reachable, which is why the
button is no longer removed when `snap_ws_url` is absent.

**The glyph also carries network health, and the separate dot is gone.** One latency probe
still publishes `html[data-net]` (green/orange/red, `netProbe`), but it now paints the
button instead of a dot beside the status badge. The health of the link and where the audio
comes out are the same question asked twice, and two indicators made the reader correlate
them. Connected takes the colour outright — the web stream holds ~1s of buffer, so red is
about to be audible. **Remote** stays grey while all is well and colours only on orange/red:
grey there means "this device is not a speaker", and a green tick would answer a question
nobody asked. **Offline** is never tinted, the network being irrelevant to it by definition.
The millisecond reading moved to the button's tooltip, under the state line. The probe also
stopped being silenceable: it used to open with `if (!el) return;` on that dot, so any view
without one killed the measurement outright.

**The switch is manual** (`offStart` / `offStop` in `mood.html`). Two players exist and
you always know which one has the hand; losing the network is not a reason for the page
to start playing something else behind your back. Turning it on pauses the server, stops
the Snapcast stream, stops the silent media anchor (a real `<audio>` has its own OS media
session, and two of them fight over the notification), then builds a queue and starts.

### What can be held, which is the whole constraint
**Spotify cannot be downloaded** — librespot decrypts into GStreamer, never into a file.
A device can therefore only hold what the server holds as an actual *file*:

| Kind | Available | How |
|---|---|---|
| Podcast / news episode | always | the enclosure url in the feed, streamed back through `/api/audio` (a CDN sends no CORS header, so the browser cannot fetch it itself) |
| Local file (`local:` / `file:`) | always | served from the music volume |
| Spotify track | only once spotdl has fetched it | `Track.local_uri`, else queued (`pending`) |
| Radio, YouTube | never | a live stream has no end, and there is no file |

This is why **the pre-existing server-side cache is the foundation, not a parallel
feature**: `spotdl/cache.py` already downloaded the pinned boxes into `data/music` and
registered `Track.local_uri`, which `_resolve_uri` substitutes at fill time. That cache
only ever fed Mopidy. Offline lets a browser take a copy of it — and extends it: a track
the device wants and the server lacks is queued in `OfflineRequest`, spotdl polls that
queue between (and during) its nightly runs, and `local_uri` is what says the bytes
landed. One downloader, one registration path; only the trigger and the urgency differ.

**Two defects in that cache, found by tracing the chain end to end (2026-09-13), that had
made it silently useless since it was written** — both fixed, both worth knowing:

- **spotdl takes URLs, not URIs.** Handed `spotify:track:<id>` it falls into
  `Song.from_search_term` and *searches* Spotify for that literal string, downloading
  whatever comes back; three different ids returned one identical unrelated track.
  Handed `https://open.spotify.com/track/<id>` it resolves the id. `spotify_url()` now
  converts. The nightly box cache had been doing this too, which is why `data/music`
  held two dozen files matching no box.
- **The Spotify id lives in the `WOAS` ID3 frame**, not `COMM` — current spotdl puts the
  YouTube url in `COMM`. Registration read `COMM` only, found nothing, and registered
  zero tracks for months.

They interact, and the order matters: fixing the tag without fixing the query would have
started writing *wrong* `local_uri` mappings, and `_resolve_uri` would then have played
the wrong song on the SERVER, not merely offline. The guard that makes this safe is
`is_registered`: an on-demand request closes as done only when the uri it asked for is
the one that actually landed, so a mis-resolved download fails honestly instead of being
served as the track someone wanted.

**The cache has a ceiling, and it needs one.** `SPOTDL_CACHE_MAX_GB` (default **10**,
settable in `.env`, `0` disables) is enforced by `enforce_cache_cap()` after every box and
every on-demand batch — not only at the end of a run, because a nightly pass adds
gigabytes and a ceiling checked once at the end is a ceiling you go through first. It
deletes least-recently-wanted first (`mtime`, which `touch_files` stamps per box, so it
orders by relevance rather than by download date) and **unregisters every file it
removes**: `local_uri` is substituted into the Mopidy tracklist by `_resolve_uri`, so a row
left pointing at a deleted file makes the SERVER fail to play a track it would otherwise
have streamed. `CACHE_DAYS` is an expiry, not a limit — the day the downloader started
working the cache went from 99 MB to **7.1 GB in a single nightly run**, and nothing in the
date rule would have stopped it before the disk did. Both the main thread and the queue
worker delete, so every deletion is under one lock.

**Giving up has to be reachable.** The first version re-queued every `failed` row on each
`plan` call — and a client polls `plan` while it waits, so the same unfetchable tracks
were re-downloaded every 30s for ever, the tries counter climbing and the UI reporting
"being fetched by the server" with no end. `plan` now reads the queue state *before*
touching it, `request_offline(retry_failed=False)` is the default, and even a deliberate
retry stops at `OFFLINE_MAX_TRIES = 3`.

### Server side
- **`o2m_core/offline.py`** — `describe(uri)` → `ready` | `pending` | `unavailable`;
  `local_file_for(uri)` resolves the file and is the security boundary (`realpath` +
  prefix check, so `..` in a query string escapes nothing); `feed_enclosures(feed)` parses
  `<enclosure>` with the same regex reading as `_feed_index` (15 min memo).
- **`GET /api/audio?uri=…`** — one shape for the client whatever is behind it. Files go
  through `send_file(conditional=True)` because a media element asks for a Range before it
  will accept a stream at all; remote episodes are a passthrough of the CDN's own response,
  Range header included.
- **`POST /api/offline/plan`** — per-uri availability, **and** the moment the queue is fed:
  "tell me what you have" and "then go and get the rest" are one intent, and splitting
  them let a client ask and never queue.
- **`GET /api/offline/queue`** / **`POST /api/offline/queue_done`** — what spotdl polls.
- **`POST /api/offline/plays`** — deliberately **not** `/api/event`: that path also runs
  `add_reco_after_track_read`, so replaying an evening of offline listening through it
  would push a dozen recommendations into whatever is playing now. Stats are the only
  thing an offline play can honestly report, so stats are the only thing this writes —
  each play carrying **its own timestamp**, because the hourly habits read
  `stats_raw.read_hour` and crediting the flush would teach the selector that you listen
  on the commute home rather than on the train.

The o2m service mounts the music volume at `/music:ro` — like spotdl, **not** under
`/app`, which is itself a bind mount of `./o2m` and would grow an `o2m/Music` directory on
the host. `local_uri` holds Mopidy's path (`/app/Music/…`), so every path is rebased from
`[local] media_dir` onto that mount — the same translation spotdl does in reverse.
**`docker-compose.yml` is skip-worktree (one per instance), so this line has to be added
by hand on every instance that wants the feature.**

### One cache for every instance
`MUSIC_DIR` (`.env`, default `./data/music`) is the HOST directory behind the three
mounts; the numbered instances all point it at **`/home/o2m/music`** so one download
serves them all. `o2m_claire` is deliberately left out — it runs on its own Spotify
account, and sharing would mix two libraries.

**No database migration was needed, and that is structural rather than lucky.**
`local_uri` records the path as MOPIDY sees it (`/app/Music/…`), and every instance
already mounted its volume at that same container path. Swapping the host directory
behind it therefore leaves every row valid. Verified on o2m_1 across the move: same
track, same 5,725,908 bytes, before and after; 1282 files relocated.

Two consequences to keep in mind:
- **Exactly one instance may prune a shared cache.** The expiry and the size cap delete
  files and unregister them through the *local* API, so a pruner removes files other
  instances still hold `local_uri` rows for. `SPOTDL_PRUNE` (default `1`) is set to `0`
  everywhere but the owner.
- **A dangling `local_uri` is survivable anyway.** `_resolve_uri` checks the file is
  really there before substituting it, whenever the volume is visible to this container
  (`_local_file_present`; with no mount it trusts the database, so an instance without
  the `:ro` line keeps its old behaviour). Without that check a row outliving its file
  turns a track that would have streamed from Spotify into a playback failure — and rows
  could already outlive their files before any of this, since `clear_local_track`
  swallows its own errors.

### Device side (`o2m/static/mood.html`)
- **Quota** in Settings, per device (`localStorage`), default 1 GB. Eviction is LRU and
  protects both what is queued to play and what the pass in progress just downloaded —
  freeing space by deleting the track fetched a second ago is a loop, not a saving.
- **Blobs in IndexedDB, not the Cache API**: Cache needs a secure context and the dev
  instances are served over plain HTTP, so the feature would have been untestable exactly
  where it is developed. Metadata (the inventory) sits in `localStorage`.
- **Where the bytes actually are**, shown in Settings → Offline → *Where it is stored*
  (`offFillStorage`, `GET /api/offline/storage`). On the device: IndexedDB `o2m-offline`,
  store `audio`, plus the browser's own `storage.estimate()`. A page **cannot choose or
  move** that location, so the UI says so instead of offering a path picker; the two real
  levers are the quota above and `storage.persist()` ("Keep when storage runs low"), which
  asks the browser not to evict the store and reports whether it agreed. On the server:
  `./data/music/cache` on the host, `/music/cache` in the o2m container, `/app/Music/cache`
  in mopidy's paths — all three reported, because matching a shell listing to a `local_uri`
  otherwise means guessing which of the three a number refers to. The o2m mount is
  read-only by design, and the endpoint reports that too.
- **The queue rule**: the local subset of the current tracklist; if that is empty, or the
  tracklist is, everything on the device, newest first. Downloads that land mid-session
  are appended live. "Full" here is about the tracklist, never about the quota.
- **Where "local" is shown**: on the device, as a badge on the tracklist row (the row's
  number takes the accent colour) — *not* in `Track.local_uri`. That column means "the
  SERVER has this file" and is what the fill substitutes; writing a phone's copy into it
  would make the server believe it can play something it does not have.
- Plays are logged locally (same `> 0.05` artefact rule as the server) and flushed on
  reconnection. `'ended'` records the play and then skips, so the skip must not record the
  same index a second time — one index, one record (`OFF.loggedAt`).
- The transport, the seek bar, the tracklist rows and the Mopidy event stream all check
  `OFF.on` and route to the local player; `refreshNowPlaying` returns early, since the
  server's state then describes a room nobody is listening to.

**Stats travel both ways, and the two kinds of record are not the same thing.** Online,
`track_playback_paused` is wired to the *same* handler as `ended`: a pause is a play
reported at its position, and that is what writes `read_position`, which
`track_started_event` then reads to resume a spoken item ten seconds earlier (or, on a
genuinely fresh start, to skip the pre-roll). Offline mirrors all of it:

- **A completed play is an event and appends**; **a position is state and replaces**.
  They live in two stores (`o2m-offline-plays`, `o2m-offline-pos`) precisely because
  merging them would have inflated `read_count` by one per checkpoint — the server counts
  a read on every record it receives, and `read_count` feeds popularity and the cooldown.
- **The bookmark is written on pause, on seek, on leaving a track, on `pagehide` and
  `visibilitychange`, and on a 10s-throttled tick.** The position that matters most is the
  one from the session nobody ended cleanly — a phone in a pocket, a tab killed by the OS.
- **Finishing retires the bookmark**, or the episode would resume ten seconds before its
  own end for ever.
- **Server → device**: `plan` returns each uri's `position`, `length` and `ad_skip`, and a
  download seeds the bookmark from them — marked as already synced, so it is not echoed
  straight back as a fresh read. A local bookmark is never overwritten: it is the newer one.
- **Device → server**: only bookmarks that MOVED since the last successful flush are sent
  (`at !== syncedAt`). Re-sending an unchanged position on every reconnection would quietly
  inflate `read_count`.
- **They are readable.** Both stores are plain `localStorage`, which is nowhere a person
  can look, so Settings → Offline lists them: how many plays are waiting, how many
  bookmarks exist and how many are unsent, and — under *What is waiting to be sent* — the
  records themselves, each with its track, its position as a percentage and its timestamp.
- **Resume is spoken-only**, like `_is_spoken_uri` guards it on the server. Measured on a
  real row: a music track played to the end carries `read_position == its own duration`, so
  honouring it for music would restart every favourite ten seconds before its last note.

**Headset and notification controls route to whichever player has the hand.** The Media
Session handlers called `rpc('core.playback.next')` unconditionally, so a Bluetooth "next"
while offline reached Mopidy — unreachable with no network, and worse with one, since it
skipped a track in a room nobody was listening to while the phone carried on. `play`,
`pause`, `previoustrack`, `nexttrack` and `seekto` all check `OFF.on` first; `seekbackward`,
`seekforward` and `stop` are wired for the local player only, the server transport having
never exposed them.

**Known limits.** Reloading the page while offline needs the service worker, which only
registers over HTTPS — in prod (Caddy) the shell is cached on first visit and it works;
on an HTTP dev instance offline lives only as long as the tab stays open. Covers are not
cached: the generated (local) cover is used instead.

## Frontend (`frontend/`)

SvelteKit + TypeScript + Tailwind CSS app. Source in `frontend/src/`:
- Routes under `src/routes/` (library, flows, radios pages)
- Models in `src/lib/models/` (Box, Flow, Track, Tracklist, etc.)
- Snapcast stream control in `src/lib/utils/snapstream.ts` and `snapcontrol.js`

## Mopidy image and extension (`mopidy/`)

The image is built from **`mopidy/Dockerfile4`** — Mopidy 4 on Debian trixie, Python 3.13,
and **no Iris**. Every instance runs it, and it is the default in `docker-compose.yml`, so
no `-f` overlay is needed.

O2M's own Mopidy extension lives in **`mopidy/mopidy-o2m/`** (distribution `Mopidy-O2M`,
module `mopidy_o2m`). It registers a browse-only `o2m:` backend, a frontend that pushes
playback events to the O2M API in-process, and its own HTTP app under `/o2m/`. See its
README.

`mopidy/mopidy_spotify_backend5.py` is bind-mounted over `mopidy_spotify/backend.py` to
carry O2M's streaming identity and a resilient login.

**The Iris integration is gone.** `o2m.js` / `o2m.css` used to be copied into
`mopidy_iris/static/` at image build time, alongside a 7.5 MB `app.js`; Iris was never
ported to Mopidy 4, the UI is now O2M's own, and all of it — with the Mopidy 3 image that
copied it — was deleted. Git history has it if ever needed.

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
- `MUSIC_DIR` — host directory behind the music volume (default `./data/music`). The
  numbered instances share `/home/o2m/music`; see the offline section.
- `SPOTDL_CACHE_MAX_GB` — ceiling on the server-side download cache (default 10, `0` = no
  cap). See the offline section: the 30-day `SPOTDL_CACHE_DAYS` expiry is not a limit.
- `SPOTDL_PRUNE` — may this instance delete from the cache (default `1`). Set `0` on every
  instance but one when the cache is shared.
- `LASTFM_API_KEY` — required for mood/genre enrichment via Last.fm
- `RADIOFRANCE_API_KEY` — Radio France OpenAPI token (show catalogue, episodes, subjects).
  Without it the RF features degrade silently: livemeta (now-playing on live streams) and
  plain RSS feeds keep working, `rf:show:` / `rf:sujet:` do not.

Note: `.env` changes need `docker compose up -d` to be injected — a `restart` reuses the
old environment.
