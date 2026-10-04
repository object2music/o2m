"""A picture for a box, stored in the database.

`Box.image_url` could only point at a picture hosted somewhere else, which is
little use to someone holding a photo on their phone. This stores the picture
itself, and the place is chosen by who has to read it: o2m_0, o2m_1 and the
Raspberry Pi share one database but not one disk (each instance has its own
`./o2m`, the Pi has no volume at all), so a file written beside one instance
would show on that one only.

The server does no image work. The browser downscales and re-encodes before
sending (`_bxImageEncode` in mood.html), which also drops the EXIF — GPS
included — and leaves the server a plain check: is it really one of three
raster formats, and is it small. SVG is refused on purpose: it is a document
that can carry script, served from our own origin.

Pictures are addressed by the sha1 of their bytes, so the same upload twice is
one row and a url never changes meaning — which is what lets it be served as
`immutable`. A box points at one through its ordinary `image_url`
(`/api/box_image/<sha1>`), so no column was added to `box`, external urls keep
working, and an older image that never heard of this simply shows the picture.

DB-free: the queries are in DatabaseHandler, the routes in main.py.
"""
import hashlib
import re

MAX_BYTES = 300 * 1024          # a 640px WebP is 30-80 KB; this is the ceiling, not the target
URL_PREFIX = '/api/box_image/'

# An uploaded picture no box points at is kept this long before the sweep takes
# it: the editor uploads on pick, before Save, and the creation wizard before the
# box even exists.
ORPHAN_GRACE_HOURS = 24

_SHA1_RE = re.compile(r'^[0-9a-f]{40}$')
_REF_RE = re.compile(r'/api/box_image/([0-9a-f]{40})')


def sniff(data):
    """The mime type of `data` read from its first bytes, or None when it is not
    a JPEG, PNG or WebP. The Content-Type a client sends is not looked at."""
    if not data or len(data) < 12:
        return None
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def check(data):
    """(mime, None) when `data` may be stored, else (None, reason)."""
    if not data:
        return None, 'empty'
    if len(data) > MAX_BYTES:
        return None, 'too_large'
    mime = sniff(data)
    if mime is None:
        return None, 'not_an_image'
    return mime, None


def digest(data):
    return hashlib.sha1(data).hexdigest()


def url_for(sha1):
    return URL_PREFIX + sha1


def is_sha1(s):
    return bool(s) and bool(_SHA1_RE.match(s))


def referenced(image_urls):
    """The set of stored pictures a list of `image_url` values points at.
    Matched anywhere in the value, so an absolute spelling
    (https://host/api/box_image/<sha1>) counts too."""
    out = set()
    for u in image_urls:
        if u:
            out.update(_REF_RE.findall(u))
    return out
