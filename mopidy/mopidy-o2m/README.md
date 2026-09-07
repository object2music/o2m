# Mopidy-O2M

O2M's own Mopidy extension. Currently a working skeleton: it registers itself with
Mopidy and exposes an `[o2m]` config section, but adds no backend, frontend or HTTP
handler yet.

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
edits — `mopidy/o2m.js` and `mopidy/o2m.css` are copied over `mopidy_iris/static/` at
image build time, and `mopidy/mopidy_spotify_backend.py` is bind-mounted over
`mopidy_spotify/backend.py`. Those stay where they are, in the non-plugin code; they
are **not** to be reproduced here.

Consequence for design: anything this extension wants to expose to a browser it serves
itself, through its own `registry.add("http:app", ...)` handler under
`/o2m/`, with its own static assets inside the package. That keeps the extension
installable and useful on a Mopidy that has no Iris at all.

## Mopidy 3 today, Mopidy 4 is an open decision

Pinned to `mopidy >= 3.4, < 4` because that is what the image runs today: Mopidy 3.4.2 on
Python 3.10 (Ubuntu 22.04). **Mopidy 4 does exist** — 4.0.0 was released on 2026-04-24,
4.0.3 on 2026-09-06 — and requires **Python >= 3.13**. Beware: pip inside the 3.10 image
filters out every version whose `requires-python` it cannot satisfy, so `pip index
versions mopidy` there stops at 3.4.2 and looks as if 4 did not exist. Check PyPI
directly, not from the container.

Where the extensions O2M depends on stand (PyPI, 2026-09-07):

| Extension | Latest | Needs |
|---|---|---|
| Mopidy-Spotify | 5.0.0 (2026-04-25) | mopidy >= 4, py >= 3.13 — the image runs the **5.0.0a3 alpha**, the last pre-release that still ran on Mopidy 3 |
| Mopidy-Local | 4.0.1 | mopidy >= 4.0.2 |
| Mopidy-MPD | 4.0.1 | mopidy >= 4 |
| Mopidy-Podcast / -iTunes | 4.0.0 | mopidy >= 4 |
| Mopidy-Iris | 3.70.0 (2025-05-03) | mopidy >= 3, **no Mopidy 4 release** |
| Mopidy-YouTube | 4.0.2 (2026-05-04) | mopidy >= 3.1, no upper bound, untested on 4 |
| Mopidy-TuneIn | 1.1.0 (2021-01-12) | mopidy >= 3, unmaintained |

So the ecosystem has split: the actively maintained backends have all moved to Mopidy 4,
while the UI (Iris) has not. The skeleton itself only uses Extension API that is unchanged
in 4 (`ext.Extension`, `config.read`, `config.String`, `registry`), so lifting the pin is a
one-line change once the stack moves.

## Install

Not wired into the image yet. To install it, add to `mopidy/Dockerfile` after the
`pip install -r requirements.txt` line:

```dockerfile
COPY ./mopidy-o2m /app/mopidy-o2m
# setuptools 59.6.0 ships in the base image and predates PEP 621, so it ignores the
# [project] table in pyproject.toml: pip then silently builds and installs a package
# named UNKNOWN-0.0.0, and Mopidy finds no extension at all (no error anywhere).
# setuptools >= 61 is required; verified working on pip 26.2.1 / setuptools 84.0.0.
RUN python3 -m pip install --upgrade pip setuptools
RUN python3 -m pip install /app/mopidy-o2m
```

Then rebuild the mopidy image — a pull and restart will not pick it up, the extension
lives in the image.

## Verify

```bash
mopidy deps          # lists Mopidy-O2M 0.1.0
mopidy config        # shows the [o2m] section
```
