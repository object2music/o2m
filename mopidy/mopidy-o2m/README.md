# Mopidy-O2M

O2M's own Mopidy extension. It registers itself with Mopidy, exposes an `[o2m]` config
section and serves its own HTTP app under `/o2m/`. It registers no backend yet.

## Why it lives in this repo

The extension is coupled to O2M's own code (Peewee models, the
`podcast+<feed_url>#<guid>` URI convention, the API on port 6681), so it ships in the
same repo rather than a separate one. It sits inside `mopidy/`, which is the Docker
build context of the mopidy image, so the Dockerfile can install it with a relative
`COPY`. If it is ever published to PyPI, `git subtree split` extracts this directory
with its history into a standalone repo.

## Boundaries: no Iris dependency

The extension must **never depend on Mopidy-Iris**, neither as a package dependency
nor by reaching into its files. The existing Iris integration is a set of hard-coded
edits — on the legacy Mopidy 3 image `mopidy/o2m.js` and `mopidy/o2m.css` are copied over
`mopidy_iris/static/`, and `mopidy/mopidy_spotify_backend5.py` is bind-mounted over
`mopidy_spotify/backend.py`. Those stay where they are, in the non-plugin code; they are
**not** to be reproduced here. The Mopidy 4 image does not install Iris at all, so the
question is settled there.

Consequence for design: anything this extension wants to expose to a browser it serves
itself, through its own `registry.add("http:app", ...)` handler under
`/o2m/`, with its own static assets inside the package. That keeps the extension
installable and useful on a Mopidy that has no Iris at all.

## Targets Mopidy 4

Declared as `mopidy >= 3.4`, **with no upper bound on purpose**, and verified loading on
both 3.4.2 and 4.0.3. A `< 4` pin is not merely conservative here, it is harmful: pip
honours it while building the Mopidy 4 image and silently downgrades mopidy 4.0.3 to
3.4.2, leaving every other extension unsatisfied — the build succeeds and the stack is
quietly wrong.

Mopidy 4.0.0 was released 2026-04-24, 4.0.3 on 2026-09-06, and requires **Python >= 3.13**.
Beware when checking versions: pip inside a Python 3.10 image filters out every release
whose `requires-python` it cannot satisfy, so `pip index versions mopidy` there stops at
3.4.2 and looks as if Mopidy 4 did not exist. Check PyPI directly, never from the old
container.

Where the extensions O2M depends on stand (PyPI, 2026-09-08):

| Extension | Latest | Needs |
|---|---|---|
| Mopidy-Spotify | 5.0.0 (2026-04-25) | mopidy >= 4, py >= 3.13 — **now installed**; the Mopidy 3 image ran the 5.0.0a3 alpha |
| Mopidy-Local | 4.0.1 | mopidy >= 4.0.2 |
| Mopidy-MPD | 4.0.1 | mopidy >= 4 |
| Mopidy-Podcast / -iTunes | 4.0.0 | mopidy >= 4 |
| Mopidy-Iris | 3.70.0 (2025-05-03) | mopidy >= 3, **no Mopidy 4 release** |
| Mopidy-YouTube | 4.0.2 (2026-05-04) | mopidy >= 3.1, no upper bound, untested on 4 |
| Mopidy-TuneIn | 1.1.0 (2021-01-12) | mopidy >= 3, unmaintained |

The ecosystem had split — the maintained backends all moved to Mopidy 4, the UI (Iris)
never did. That is why the Mopidy 4 image **drops Iris entirely** and O2M serves its own
UI: the one blocker was a UI we had already decided to replace.

## Install

Installed by `mopidy/Dockerfile4` (the Mopidy 4 image) — nothing to do by hand:

```dockerfile
COPY ./mopidy-o2m /app/mopidy-o2m
RUN pip install --break-system-packages --root-user-action=ignore -q /app/mopidy-o2m
```

The extension lives **in the image**, so a `git pull` and a restart will not pick up a
change to it — the image has to be rebuilt.

It is *not* installed in the legacy Mopidy 3 image (`mopidy/Dockerfile`), which is still
what un-migrated instances run. If you ever add it there, note that the Ubuntu 22.04 base
ships setuptools 59.6.0, which predates PEP 621 and ignores the `[project]` table: pip
then silently builds and installs a package named `UNKNOWN-0.0.0` and Mopidy finds no
extension at all, with no error anywhere. `pip install --upgrade setuptools` (>= 61)
first. The trixie base of `Dockerfile4` is new enough not to need this.

## The HTTP app

Mopidy mounts the extension's own app at **`/o2m/`** — `registry.add("http:app", ...)`,
the same contract Mopidy-Local uses, unchanged between Mopidy 3 and 4. (Mopidy 4 did move
the HTTP frontend itself from `mopidy.http` to `mopidy._exts.http`, so `from mopidy import
http` no longer resolves — but an extension never needs it: the factory only returns
Tornado route tuples.)

| Route | What it is |
|---|---|
| `GET /o2m/status` | JSON probe: extension version, configured `api_url`, and Mopidy's live URI schemes read off `core` |
| `GET /o2m/` | the package's own static assets (`mopidy_o2m/static/`), currently a placeholder page |

This is the alternative to the legacy Iris integration: assets live inside the package and
are served by the extension, instead of being copied over `mopidy_iris/static/` at image
build time.

`/o2m/status` is worth keeping: it is what caught `api_url` pointing at the host-side port
(`http://o2m:6691/api/`) instead of the port o2m listens on inside the compose network
(`6681`) — a URL that is simply unreachable from the mopidy container.

## Verify

```bash
mopidy deps                              # lists mopidy-o2m 0.2.0
mopidy config                            # shows the [o2m] section
curl http://<host>:<PORT_MOPIDY>/o2m/status
```
