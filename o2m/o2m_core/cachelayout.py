"""Where a downloaded file lives in the offline cache, and what it is called.

The server's cache (`<music>/cache`, filled by spotdl) and the device's folder
copy (Settings → Offline → Copy to a folder) are laid out by this one module,
so the two read the same:

    cache/
      Auto music [04463DD2204B80]/
        Dans Un Camion - Le Vent Dans Les Plaines.mp3
        Le journal de 8h - France Inter [3fa2c1d9e04b7a6c1f2e].mp3
      No box/
        …                      what a device asked for outside any box

* **A folder per box, named first, id last.** The name is what a person looks
  for; the uid is what the code finds the folder by (`folder_matches`), so a
  renamed box keeps its folder and two boxes of one name never share one. The
  folders used to be the bare uid (`04463DD2204B80`), plus `ondemand/` (music
  a device asked for) and `spoken/` (episodes and videos a device asked for):
  three ways of saying "what the cache holds" that only the code could read.
* **A file is `title - album` for music, `title - channel` for an episode or a
  video.** A spoken item also ends with a hash of its uri in brackets: the same
  name is the same file for every instance sharing the disk, each with its own
  database (`spoken_tag`), and a title alone does not identify an episode — a
  daily news bulletin has one title every day.

Pure: no database, no filesystem. The callers (main.py, spotdl/cache.py through
the API) supply the names.
"""

from __future__ import annotations

import hashlib
import re

NO_BOX = 'No box'

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


def box_folder(name, uid) -> str:
    """`Name [uid]`, or the uid alone when the box has no name of its own."""
    tag = safe_name(uid, 80)
    if not tag:
        return NO_BOX
    label = safe_name(name, 80)
    return f"{label} [{tag}]" if label and label != tag else tag


def folder_matches(folder, uid) -> bool:
    """Is `folder` the folder of this box, whatever name it carries? A bare uid
    is the layout before names were added, and still that box's folder."""
    tag = safe_name(uid, 80)
    return bool(tag) and (folder == tag or folder.endswith(f' [{tag}]'))


def spoken_tag(uri) -> str:
    """The 20 hex digits a spoken file ends with. Deterministic, so an instance
    with its own database finds the file another instance fetched for the same
    item. It was the whole file name before (`<tag>.mp3`)."""
    return hashlib.sha1(str(uri).encode('utf-8')).hexdigest()[:20]


def tag_of(stem) -> str:
    """The spoken tag a file name carries, '' for a music file. Accepts the old
    bare `<tag>` names too."""
    if re.fullmatch(r'[0-9a-f]{20}', stem or ''):
        return stem
    m = _SPOKEN_TAG.search(stem or '')
    return m.group(1) if m else ''


def file_stem(title, second, spoken_uri=None) -> str:
    """The file name without its extension: `title - album` for music,
    `title - channel [tag]` for a spoken item (pass its uri)."""
    parts = [p for p in (safe_name(title, 120), safe_name(second, 80)) if p]
    base = ' - '.join(parts)
    if spoken_uri:
        tag = spoken_tag(spoken_uri)
        return f"{base} [{tag}]" if base else tag
    return base or 'track'
