"""Activating an OBJECT — an album, an artist — the way a box is activated.

A box is a durable thing: an NFC uid and a row in `box`. An album is not; it has
only its uri. But nothing that happens after an activation is driven by that row.
The fill, the mood and discover-level ladder, the anti-repeat cooldown, the
ownership tag that lets a deactivation remove exactly the tracks it added — all
of it is driven by a `Box` OBJECT. So an object is activated by building that
object and nothing else: a Box that is never saved.

The pattern is not new here. `apply_mood_settings` already fills from an unsaved
`Box(uid='auto_sim', data='auto:library')` when no box is active; this module
only makes it a first-class, addressable thing.

**The uid is namespaced (`obj:<uri>`) and that is load-bearing.**
`DatabaseHandler.get_box_by_uid` CREATES a box for any uid it does not find —
which is right for an unknown NFC tag and wrong for everything else. A virtual
uid reaching one of the uid-keyed paths would open a junk row per activation, and
there is a non-obvious one: `/api/track_info` resolves the name of the box that
owns the playing track. The namespace is what the guard there recognises.

No database, no clock, no player: the caller passes the name it already has (the
mosaic read it from the library listing), the model is imported only inside
`build`. That is what makes the policy below testable on a host with no peewee.
"""

PREFIX = 'obj:'

# Which uris can be activated as an object. Deliberately a short list rather than
# "anything with a scheme": the tracklist is filled by a box, and a box line that
# resolves to nothing would activate an object that plays silence.
_KINDS = {'album': 'album', 'artist': 'artist', 'playlist': 'playlist'}

# How each kind fills, and the two answers differ on purpose.
#
# An ALBUM is asked for by name: tapping its cover means "play this record", so it
# goes down the basic path — the raw uri, which Mopidy resolves whole, in order.
# 'asc' rather than any other non-smart value because one_box_changed re-shuffles
# everything except 'asc'/'desc'.
#
# An ARTIST is not a record but a body of work (87 cached tracks on average here,
# up to 314). Served whole it would BE the tracklist, so it goes through the smart
# path — `_expand_pick`, i.e. popularity, mood and cooldown, exactly like a box
# line pointing at the same artist.
_SORTS = {'album': 'asc', 'artist': 'smart', 'playlist': 'smart'}


def kind_of(uri):
    """'spotify:album:7vEJ…' → 'album'. None when it is not activable."""
    parts = (uri or '').split(':')
    if len(parts) < 3 or parts[0] != 'spotify' or not parts[2]:
        return None
    return _KINDS.get(parts[1])


def is_activable(uri):
    return kind_of(uri) is not None


def uid_for(uri):
    return PREFIX + (uri or '')


def uri_of(uid):
    """The uri behind a virtual uid, or None when the uid is a real box's."""
    u = uid or ''
    return u[len(PREFIX):] if u.startswith(PREFIX) else None


def is_virtual(uid):
    return bool(uid) and uid.startswith(PREFIX)


def spec(uri, name=''):
    """The Box field values for this object, or None when it is not activable.

    Separate from `build` so the policy — uid, sort, option_type — can be read and
    tested without a database driver.
    """
    kind = kind_of(uri)
    if kind is None:
        return None
    return {
        'uid': uid_for(uri),
        'data': uri,
        # The name the mosaic already had. Falls back to the uri so the tracklist's
        # Source line and the box-removal log are never blank.
        'description': (name or '').strip() or uri,
        # 'library' is the neutral lifecycle: it neither restricts the fill to
        # unheard tracks ('new') nor excludes it from the stats ('hidden').
        'option_type': 'library',
        'option_sort': _SORTS[kind],
        # No budget of its own: the session's max_results applies, as it does for a
        # box that leaves the field empty.
        'option_max_results': None,
    }


def build(uri, name=''):
    """An unsaved Box for this object, or None when it is not activable."""
    s = spec(uri, name)
    if s is None:
        return None
    from o2m_core.o2mmodels import Box   # lazy: importing the models opens the DB
    return Box(**s)


def find_active(handler, uri):
    """The live Box instance for this object among the active ones, if any."""
    uid = uid_for(uri)
    for b in (getattr(handler, 'activeboxs', None) or []):
        if getattr(b, 'uid', None) == uid:
            return b
    return None


def active_objects(handler):
    """Every currently-active object, for the mosaic's state. One call for the
    whole grid: 248 tiles polling their own state is 248 requests per refresh."""
    out = []
    for b in (getattr(handler, 'activeboxs', None) or []):
        uri = uri_of(getattr(b, 'uid', None))
        if not uri:
            continue
        out.append({'uri': uri, 'kind': kind_of(uri),
                    'name': getattr(b, 'description', '') or uri})
    return out


def toggle(handler, uri, mode='toogle', name=''):
    """Activate or deactivate an object, by the same truth table as a box.

    Mirrors `api_box_action` rather than calling it: that one is uid-keyed, and
    reaching it with a virtual uid is exactly what the namespace exists to
    prevent. Everything after the decision IS the box path — `box_action` and
    `box_action_remove`, unchanged.
    """
    kind = kind_of(uri)
    if kind is None:
        return {'ok': False, 'error': 'uri not activable', 'uri': uri}

    box = find_active(handler, uri)
    active = box is not None
    if mode == 'remove' or (mode == 'toogle' and active):
        if not active:
            return {'ok': True, 'active': False, 'kind': kind, 'uri': uri, 'action': 'none'}
        handler.activeboxs.remove(box)
        handler.box_action_remove(box, box)
        return {'ok': True, 'active': False, 'kind': kind, 'uri': uri, 'action': 'removed'}

    if mode == 'add' or mode == 'toogle':
        if active:
            return {'ok': True, 'active': True, 'kind': kind, 'uri': uri, 'action': 'none'}
        box = build(uri, name)
        handler.activeboxs.append(box)
        # An object put down is a fresh intent, exactly as a box is: it hands
        # precedence back from the dials (see note_box_activation).
        handler.note_box_activation()
        handler.box_action(box)
        return {'ok': True, 'active': True, 'kind': kind, 'uri': uri, 'action': 'added'}

    return {'ok': False, 'error': f'unknown mode {mode}', 'uri': uri}
