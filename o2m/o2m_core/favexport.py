"""The favourite episodes outside the app: the export file and the public list.

Pure: the rows come from `DatabaseHandler.get_favorite_episodes`, the audio url
of a feed episode from the caller, so this touches neither database nor network.
"""
import csv
import hashlib
import hmac
import io
import re

FILENAME = 'o2m-favourite-episodes.csv'
COLUMNS = (('name', 'Title'), ('channel', 'Channel'), ('type', 'Type'),
           ('published', 'Published'), ('duration', 'Duration'), ('liked', 'Liked'),
           ('plays', 'Plays'), ('link', 'Link'), ('uri', 'URI'))


def duration_label(ms):
    """`1:02:05` / `4:05`, blank when the length is not known."""
    if not ms:
        return ''
    m, s = divmod(int(ms) // 1000, 60)
    h, m = divmod(m, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def media_link(uri, enclosure=None):
    """An address a person can open. A feed episode has none of its own: its
    audio url (`enclosure`) is the caller's to find, and may be gone from the feed."""
    u = str(uri or '')
    if u.startswith('podcast+'):
        return enclosure or ''
    video = re.match(r'(?:youtube|yt):video:([\w-]+)', u)
    if video:
        return f'https://www.youtube.com/watch?v={video.group(1)}'
    page = re.match(r'(?:web|xp|yt|youtube):(https?://.+)', u)
    return page.group(1) if page else ''


def _cell(value):
    """A title comes from someone else's feed: a leading `=` would run as a
    formula in the spreadsheet that opens this file."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def to_csv(rows):
    """UTF-8 with a BOM and `;`: what a French Excel opens as columns, accents
    included; LibreOffice and Sheets read it as well."""
    out = io.StringIO(newline='')
    w = csv.writer(out, delimiter=';', lineterminator='\r\n')
    w.writerow([label for _, label in COLUMNS])
    for r in rows:
        w.writerow([_cell(r.get(key)) for key, _ in COLUMNS])
    return '﻿' + out.getvalue()


def share_token(secret, generation):
    """The unguessable part of the public address. Derived rather than stored:
    CacheMeta holds integers, so a new generation is all a new link takes, and
    moving to it is what kills the old one."""
    msg = f'favourite-episodes:{generation}'.encode()
    return hmac.new(str(secret).encode(), msg, hashlib.sha256).hexdigest()


def share_token_ok(given, secret, generation):
    """No generation means nothing was ever shared: no token opens that."""
    if not generation:
        return False
    return hmac.compare_digest(str(given).encode(), share_token(secret, generation).encode())


def public_list(rows):
    """What the public address answers. It says what was liked and where to hear
    it, and nothing of the listening itself: no play count, no date of the like,
    no uri."""
    episodes = [{'title': r.get('name') or None, 'channel': r.get('channel') or None,
                 'type': r.get('type') or None,
                 'published': str(r['published']) if r.get('published') else None,
                 'duration': r.get('duration') or None, 'link': r.get('link') or None}
                for r in rows]
    return {'count': len(episodes), 'episodes': episodes}
