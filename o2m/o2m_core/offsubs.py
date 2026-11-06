"""What a device may keep of a box it subscribes to.

A subscription is the device's own business (see `static/offsubs.js`): the server
only answers what a box holds, as items a device can download. Pure, the caller
hands the cache lookups, so the tests run without a database.
"""
import re

_CONTAINER = re.compile(r'^spotify:(?:(album|artist)|(?:user:[^:]+:)?(playlist)):([A-Za-z0-9]+)$')
_YT_PLAYLIST = re.compile(r'^(?:yt|youtube):(?:playlist:|https?://\S*[?&]list=)([\w-]+)')


def _container(uri):
    """(kind, key) of a uri standing for many items, or None."""
    m = _YT_PLAYLIST.match(uri or '')
    if m:
        return 'yt_playlist', m.group(1)
    m = _CONTAINER.match(uri or '')
    return (m.group(1) or m.group(2), m.group(3)) if m else None


def expand(uris, reader, limit):
    """One downloadable uri per item, in order. A fill may hand over an album or a
    playlist whole, which Mopidy would expand; a device needs its tracks. Read from
    the cache: what is not cached is left for a later pass, not fetched here. A
    YouTube playlist is read from YouTube, the cache holding none. Containers share
    the limit: a channel's 200 videos must not leave the next line nothing."""
    seen, out = set(), []
    share = max(1, limit // max(1, sum(1 for u in uris if _container(u))))
    for uri in uris:
        found = _container(uri)
        items = (reader(*found) or [])[:share] if found else [uri]
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
            if len(out) >= limit:
                return out
    return out
