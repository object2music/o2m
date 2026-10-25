"""Where a downloaded file lives in the offline cache, and how the boxes see it.

One file per item, filed by what it IS; the boxes are playlists over them:

    cache/
      Library/Brigitte Fontaine/Comme a la radio/03 Dans un camion.mp3
      Podcasts/France Inter - Le journal/2026-10-24 Le journal de 8h [3fa2c1d9e04b7a6c1f2e].mp3
      Videos/Arte/2026-10-20 Un film [9b1e…].m4a
      Boxes/Auto music [04AD43D2204B80]/All.m3u8
      Boxes/Auto music [04AD43D2204B80]/Favorites.m3u8
      Boxes/Auto music [04AD43D2204B80]/Chansons [04D444D2204B80]/All.m3u8
      Boxes/Auto music [04AD43D2204B80]/Chansons [04D444D2204B80]/Playlist X.m3u8

Why not a folder per box holding its files (tried first, 2026-10-25): which
boxes hold a track is a GRAPH — "Dans un camion" is in Favorites, in a
playlist, in an included box — and a tree can only put it in one place. Every
other place either copies the file or does not show it, and the file moves
whenever a box changes, each move a re-registration other databases on the
same disk do not see. Filed by artist and album the path never changes, and
the `.m3u8` views can go as deep as the boxes do: box › included box › source.

Both the server's cache and the device's folder copy follow this module: the
names are computed here and travel through the API, never re-derived.

Pure: no database, no filesystem.
"""

from __future__ import annotations

import hashlib
import posixpath
import re

LIBRARY = 'Library'
PODCASTS = 'Podcasts'
VIDEOS = 'Videos'
BOXES = 'Boxes'
ALL = 'All'                       # a box folder's playlist of everything below it
UNKNOWN_ARTIST = 'Unknown artist'
UNKNOWN_ALBUM = 'Unknown album'
UNKNOWN_CHANNEL = 'Unknown channel'

# Refused by at least one of the filesystems a copy lands on (ext4 refuses only
# '/', but the device folder may be FAT or NTFS, and a ':' is refused there).
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+')
_SPACES = re.compile(r'\s+')
_SPOKEN_TAG = re.compile(r'\[([0-9a-f]{20})\]$')


def safe_name(text, limit=100) -> str:
    """`text` as one path component: no separator, no reserved character, no
    leading/trailing dot or space (Windows drops them), at most `limit` chars."""
    s = _SPACES.sub(' ', _UNSAFE.sub(' ', str(text or ''))).strip().strip('.')
    return s[:limit].rstrip(' .')


# ── The files ─────────────────────────────────────────────────────────────────

def music_place(artist, album, number, title):
    """(folder, stem) of a music file: `Library/<album artist>/<album>`,
    `<NN> <title>` — the shape spotdl's own template gives a new download."""
    folder = posixpath.join(LIBRARY, safe_name(artist, 80) or UNKNOWN_ARTIST,
                            safe_name(album, 100) or UNKNOWN_ALBUM)
    title = safe_name(title, 150) or 'Track'
    try:
        n = int(number or 0)
    except (TypeError, ValueError):
        n = 0
    return folder, (f"{n:02d} {title}" if n > 0 else title)


def spoken_tag(uri) -> str:
    """The 20 hex digits a spoken file ends with. Deterministic, so an instance
    with its own database finds the file another instance fetched for the same
    item — and a daily bulletin has one title every day."""
    return hashlib.sha1(str(uri).encode('utf-8')).hexdigest()[:20]


def tag_of(stem) -> str:
    """The spoken tag a file name carries, '' for a music file. Accepts the old
    bare `<tag>` names too."""
    if re.fullmatch(r'[0-9a-f]{20}', stem or ''):
        return stem
    m = _SPOKEN_TAG.search(stem or '')
    return m.group(1) if m else ''


def spoken_place(uri, channel, published, title, video=False):
    """(folder, stem) of an episode (`Podcasts/<channel>`) or a video
    (`Videos/<channel>`), `<YYYY-MM-DD> <title> [tag]`."""
    folder = posixpath.join(VIDEOS if video else PODCASTS,
                            safe_name(channel, 100) or UNKNOWN_CHANNEL)
    day = (published or '')[:10] if re.match(r'\d{4}-\d\d-\d\d', published or '') else ''
    parts = [p for p in (day, safe_name(title, 150)) if p]
    base = ' '.join(parts)
    tag = spoken_tag(uri)
    return folder, (f"{base} [{tag}]" if base else tag)


# ── The box views ─────────────────────────────────────────────────────────────

def box_folder(name, uid) -> str:
    """`Name [uid]`, or the uid alone when the box has no name of its own. The
    uid makes two boxes of one name two folders."""
    tag = safe_name(uid, 80)
    if not tag:
        return ''
    label = safe_name(name, 80)
    return f"{label} [{tag}]" if label and label != tag else tag


# The AUTO mix's buckets, by the library_link its add_tracks calls pass.
_BUCKET_LINKS = {
    'o2m:favorites': 'Favorites', 'spotify:favorites': 'Favorites',
    'o2m:history': 'Habits', 'o2m:podcast': 'Podcasts',
    'spotify:album': 'Albums & artists', 'spotify:artist': 'Albums & artists',
}
_BUCKET_TYPES = {'favorites': 'Favorites', 'incoming': 'Incoming', 'new': 'New'}


def source_label(library_link, bucket='', display='') -> str:
    """The last level of a view: where in the box the item came from.

    An AUTO bucket by its name (Favorites, Incoming, New, Habits…), a tag as
    `Tag <name>`, a playlist, album or artist by the name the details panel
    already shows (`display`); a recommendation as Recommendations. '' when
    nothing names one — the item is then only in its box's All."""
    link = library_link or ''
    if display == 'Reco':
        return 'Recommendations'
    if link in _BUCKET_LINKS:
        return _BUCKET_LINKS[link]
    if bucket in _BUCKET_TYPES and not link.startswith('spotify:playlist:'):
        return _BUCKET_TYPES[bucket]
    if link.startswith('tag:'):
        return safe_name('Tag ' + link[4:], 100)
    name = display or ''
    # get_library_display may answer `playlist:<name>` or a bare id when Spotify
    # cannot name it: the type prefix is noise in a file name.
    name = re.sub(r'^(playlist|album|artist):', '', name).strip()
    if not name or name.startswith('spotify:'):
        return ''
    # A trailing [..] is how a BOX folder is told from a source (playlists()):
    # "Best of [2020]" must not read as a box.
    return safe_name(re.sub(r'\[([^\[\]]*)\]$', r'(\1)', name), 100)


def view_path(chain, source='') -> str:
    """Where a membership's playlist sits under Boxes/: the box chain as
    folders (outermost first, each `box_folder`), then the source. A chain
    with no source is the box itself — its All."""
    parts = [c for c in chain if c]
    if not parts:
        return ''
    if source and source != ALL:
        parts.append(safe_name(source, 100))
    return posixpath.join(*parts)


def playlists(memberships):
    """{playlist path under Boxes/ (no extension): [item keys]} for a set of
    (view_path, key) pairs, in the order given.

    A box folder's `All` lists everything at or below it, so a box that
    includes others lists their items too: All of Auto music is what Auto
    music played. A source path is its own playlist, and also feeds the All of
    each box above it. A box chain alone (no source) feeds only Alls.

    Whether the last part of a path is a box or a source is told by the uid in
    brackets — the one thing a source label cannot end with, since a box
    folder is the only place `box_folder` writes one."""
    out = {}

    def add(path, key):
        lst = out.setdefault(path, [])
        if key not in lst:
            lst.append(key)

    for path, key in memberships:
        parts = path.split('/')
        boxes = parts if _is_box(parts[-1]) else parts[:-1]
        if len(boxes) < len(parts):
            add(path, key)
        for i in range(1, len(boxes) + 1):
            add(posixpath.join(*boxes[:i], ALL), key)
    return out


def _is_box(part) -> bool:
    return bool(re.search(r"\[[^\[\]]+\]$", part or ""))
