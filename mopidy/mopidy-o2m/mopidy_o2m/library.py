"""Browse and search O2M's catalogue from any Mopidy client.

What this is for
----------------
O2M knows things no Mopidy backend does: a 76k-track catalogue with playback
history, popularity and mood, the podcast channels a box references, the radio
stations hidden in box data. All of it was reachable only from O2M's own web UI.

This provider exposes it through Mopidy's own library API, so an MPD app on a
phone, a car head unit or any web client can browse and search it.

It returns references into **other** backends — `spotify:`, `podcast+`, plain
http streams — because those are what actually plays. The `o2m:` scheme is
therefore browse-only: there is no playback provider, and nothing here decodes
audio. That is the same shape mopidy-podcast-itunes uses.

Boxes
-----
Browsing a box lists what it *would* play. That is served by
`/api/box_tracks`, the read-only counterpart of `/api/box` (which activates).
The resolution runs the real fill logic with the tracklist mutation captured and
thrown away, under the box lock — so listing a box neither plays it nor
interleaves with a real fill. All of that lives in the service; this file only
asks for the result.
"""

from __future__ import annotations

import logging
from typing import Any

from mopidy import backend, models

logger = logging.getLogger(__name__)

ROOT_URI = "o2m:root"
PLAYLISTS_URI = "o2m:playlists"
PODCASTS_URI = "o2m:podcasts"
GENRES_URI = "o2m:genres"
GENRE_PREFIX = "o2m:genre:"
BOXES_URI = "o2m:boxes"
BOXES_CAT_PREFIX = "o2m:boxes:"
BOX_PREFIX = "o2m:box:"

# The four categories /api/basic_boxes groups pinned boxes into.
BOX_CATEGORIES = (("music", "Music"), ("podcast", "Podcasts"),
                  ("info", "News"), ("radio", "Radios"))

# Resolving a box runs the real fill logic (minus the mutation), so it can hit
# Spotify and the DB exactly as a playback would. Keep the ask modest: browsing
# is meant to be a look, not a warmup.
BOX_LIMIT = 30

# A genre browse is a search behind the scenes; keep it to one screenful.
GENRE_LIMIT = 50
SEARCH_LIMIT = 50


class O2mLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(uri=ROOT_URI, name="O2M")

    def __init__(self, backend: Any, api: Any) -> None:
        super().__init__(backend)
        self._api = api

    # --- browse -------------------------------------------------------------

    def browse(self, uri: str) -> list[models.Ref]:
        if uri == ROOT_URI:
            return [
                models.Ref.directory(uri=PLAYLISTS_URI, name="Playlists"),
                models.Ref.directory(uri=PODCASTS_URI, name="Podcast channels"),
                models.Ref.directory(uri=GENRES_URI, name="Genres"),
                models.Ref.directory(uri=BOXES_URI, name="Boxes"),
            ]
        if uri == PLAYLISTS_URI:
            return self._browse_playlists()
        if uri == PODCASTS_URI:
            return self._browse_podcast_channels()
        if uri == GENRES_URI:
            return self._browse_genres()
        if uri.startswith(GENRE_PREFIX):
            return self._browse_genre(uri[len(GENRE_PREFIX) :])
        if uri == BOXES_URI:
            return self._browse_box_categories()
        if uri.startswith(BOXES_CAT_PREFIX):
            return self._browse_box_category(uri[len(BOXES_CAT_PREFIX) :])
        if uri.startswith(BOX_PREFIX):
            return self._browse_box(uri[len(BOX_PREFIX) :])
        logger.debug("O2M: nothing to browse at %r", uri)
        return []

    def _browse_playlists(self) -> list[models.Ref]:
        rows = self._api.get("playlists") or []
        # The uri is already a spotify:playlist: — mopidy-spotify resolves it.
        return [
            models.Ref.playlist(uri=r["uri"], name=r.get("name") or r["uri"])
            for r in rows
            if r.get("uri")
        ]

    def _browse_podcast_channels(self) -> list[models.Ref]:
        rows = self._api.get("podcast_channels") or []
        out = []
        for r in rows:
            uri = r.get("uri") or ""
            # `rf:show:…` is an O2M box pattern, not a playable uri: it means
            # "this Radio France show", which only the service can expand. Skip
            # it rather than hand Mopidy something no backend can browse.
            if not uri.startswith("podcast+"):
                continue
            name = r.get("name") or uri
            if r.get("sub"):
                name = f"{name} ({r['sub']})"
            out.append(models.Ref.directory(uri=uri, name=name))
        return out

    def _browse_genres(self) -> list[models.Ref]:
        rows = self._api.get("genres") or []
        return [
            models.Ref.directory(
                uri=GENRE_PREFIX + r["name"],
                name=f"{r['name']} ({r['count']})" if r.get("count") else r["name"],
            )
            for r in rows
            if r.get("name")
        ]

    def _browse_genre(self, genre: str) -> list[models.Ref]:
        # O2M has no "tracks of a genre" endpoint; its content search covers it,
        # and the genre name is exactly what the tag buckets match on.
        data = self._api.get("search", q=genre, limit=GENRE_LIMIT) or {}
        return [
            models.Ref.track(uri=t["uri"], name=t.get("name") or t["uri"])
            for t in (data.get("tracks") or [])
            if t.get("uri")
        ]

    def _browse_box_categories(self) -> list[models.Ref]:
        data = self._api.get("basic_boxes") or {}
        out = []
        for key, label in BOX_CATEGORIES:
            rows = data.get(key) or []
            if rows:
                out.append(
                    models.Ref.directory(
                        uri=BOXES_CAT_PREFIX + key, name=f"{label} ({len(rows)})"
                    )
                )
        return out

    def _browse_box_category(self, category: str) -> list[models.Ref]:
        data = self._api.get("basic_boxes") or {}
        return [
            models.Ref.directory(
                uri=BOX_PREFIX + b["uid"],
                # The active marker is what a client cannot know otherwise, and
                # it is the one piece of O2M state worth surfacing while browsing.
                name=(b.get("description") or b["uid"]) + (" •" if b.get("active") else ""),
            )
            for b in (data.get(category) or [])
            if b.get("uid")
        ]

    def _browse_box(self, uid: str) -> list[models.Ref]:
        data = self._api.get("box_tracks", uid=uid, limit=BOX_LIMIT) or {}
        return [
            models.Ref.track(uri=u, name=u.rsplit(":", 1)[-1] if ":" in u else u)
            for u in (data.get("uris") or [])
        ]

    # --- search -------------------------------------------------------------

    def search(
        self,
        query: dict[str, Any] | None = None,
        uris: list[str] | None = None,
        exact: bool = False,  # noqa: ARG002 — O2M's search is always fuzzy
    ) -> models.SearchResult | None:
        # Mopidy searches every backend and merges. When it restricts the search
        # to given roots, only answer if one of them is ours.
        if uris and not any(u == ROOT_URI or u.startswith("o2m:") for u in uris):
            return None
        terms = _flatten_query(query)
        if len(terms) < 2:
            return None
        data = self._api.get("search", q=terms, limit=SEARCH_LIMIT)
        if not data:
            return None
        return models.SearchResult(
            uri=f"o2m:search:{terms}",
            tracks=tuple(_tracks(data.get("tracks"))),
            artists=tuple(_artists(data.get("artists"))),
            albums=tuple(_albums(data.get("albums"))),
        )


def _flatten_query(query: dict[str, Any] | None) -> str:
    """Mopidy hands a field->values mapping; O2M's search takes one string."""
    if not query:
        return ""
    parts: list[str] = []
    for values in query.values():
        if isinstance(values, str):
            parts.append(values)
        else:
            parts.extend(str(v) for v in values or [])
    return " ".join(p.strip() for p in parts if p and p.strip()).strip()


def _tracks(rows: list[dict[str, Any]] | None) -> list[models.Track]:
    out = []
    for r in rows or []:
        if not r.get("uri"):
            continue
        out.append(
            models.Track(
                uri=r["uri"],
                name=r.get("name") or r["uri"],
                artists=tuple(
                    models.Artist(name=a) for a in (r.get("artists") or []) if a
                ),
                length=r.get("length"),
            )
        )
    return out


def _artists(rows: list[dict[str, Any]] | None) -> list[models.Artist]:
    return [
        models.Artist(uri=r["uri"], name=r.get("name") or r["uri"])
        for r in rows or []
        if r.get("uri")
    ]


def _albums(rows: list[dict[str, Any]] | None) -> list[models.Album]:
    out = []
    for r in rows or []:
        if not r.get("uri"):
            continue
        artist = r.get("artist")
        out.append(
            models.Album(
                uri=r["uri"],
                name=r.get("name") or r["uri"],
                artists=tuple([models.Artist(name=artist)] if artist else []),
            )
        )
    return out
