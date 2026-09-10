"""The player port: what o2m_core needs from a music player, and nothing more.

Why this exists
---------------
`o2mtomopidy.py` drives playback through 119 calls on an object it receives as
`mopidyHandler` — in practice a `mopidyapi.MopidyAPI` websocket client. That made
the core structurally dependent on Mopidy *and* on that transport, even though
the surface it actually uses is narrow: **31 methods over 5 namespaces**.

This module states that surface explicitly, as protocols that **import nothing
from Mopidy**. The core can then say what it needs ("a player") instead of what
it happens to be given ("a MopidyAPI"), which is what allows a second
implementation — the Mopidy-O2M extension talking to core in-process, or another
player entirely — without touching the 119 call sites.

Deliberately namespaced
-----------------------
The protocols mirror the `player.tracklist.get_length()` shape rather than
flattening to `player.tracklist_get_length()`. Flattening would be tidier but
would rewrite every one of the 119 call sites for no functional gain, on the
largest file in the project. Keeping the shape means `MopidyAPI` already
satisfies this port as-is: nothing changes operationally today, and the contract
becomes explicit and testable straight away.

Types are structural on purpose: `Any` where a Mopidy model would appear, so
this file never imports `mopidy`. Signatures otherwise mirror Mopidy 4's core
controllers verbatim (checked against `mopidy.core` 4.0.3), so an adapter can be
written against them without guessing.

Keeping it honest
-----------------
`test_player_port.py` re-derives the call surface from the source and fails if a
call is not declared here. The port cannot silently drift from what the code
actually does.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TracklistPort(Protocol):
    def add(
        self,
        tracks: Iterable[Any] | None = None,
        *,
        at_position: int | None = None,
        uris: Iterable[str] | None = None,
    ) -> list[Any]: ...
    def clear(self) -> None: ...
    def filter(self, criteria: Any) -> list[Any]: ...
    def get_length(self) -> int: ...
    def get_tl_tracks(self) -> list[Any]: ...
    def get_tracks(self) -> list[Any]: ...
    def index(self, tl_track: Any | None = None, tlid: int | None = None) -> int | None: ...
    def move(self, start: int, end: int, to_position: int) -> None: ...
    def remove(self, criteria: Any) -> list[Any]: ...
    def set_random(self, value: bool) -> None: ...
    def shuffle(self, start: int | None = None, end: int | None = None) -> None: ...
    def slice(self, start: int, end: int) -> list[Any]: ...


@runtime_checkable
class PlaybackPort(Protocol):
    def get_current_tl_track(self) -> Any | None: ...
    def get_current_tlid(self) -> int | None: ...
    def get_current_track(self) -> Any | None: ...
    def get_state(self) -> str: ...
    def get_stream_title(self) -> str | None: ...
    def get_time_position(self) -> int: ...
    def next(self) -> None: ...
    def pause(self) -> None: ...
    def play(self, tlid: int | None = None) -> None: ...
    def resume(self) -> None: ...
    def seek(self, time_position: int) -> bool: ...
    def stop(self) -> None: ...


@runtime_checkable
class MixerPort(Protocol):
    def get_volume(self) -> int | None: ...
    def set_mute(self, mute: bool) -> bool: ...
    def set_volume(self, volume: int) -> bool: ...


@runtime_checkable
class PlaylistsPort(Protocol):
    def lookup(self, uri: str) -> Any | None: ...


@runtime_checkable
class LibraryPort(Protocol):
    def get_distinct(self, field: str, query: Any | None = None) -> set[Any]: ...
    def search(
        self,
        query: Any,
        uris: Iterable[str] | None = None,
        exact: bool = False,
    ) -> list[Any]: ...


class PlayerPort(Protocol):
    """What o2m_core drives. `MopidyAPI` satisfies this as-is."""

    tracklist: TracklistPort
    playback: PlaybackPort
    mixer: MixerPort
    playlists: PlaylistsPort
    library: LibraryPort

    # Not part of Mopidy's core API: it is the JSON-RPC endpoint of the client
    # object, which main.py proxies for the browser (/api/mopidy_rpc, to avoid
    # CORS). An in-process implementation has no URL to give and should expose
    # an empty string — callers must tolerate that rather than assume a URL.
    http_url: str


# Machine-readable mirror of the protocols above, for conformance checks and for
# the drift test. Keep in step with the classes — the test enforces that the
# surface covers the code, and _surface_matches_protocols() that it matches these
# declarations.
PORT_SURFACE: dict[str, frozenset[str]] = {
    "tracklist": frozenset(
        {
            "add", "clear", "filter", "get_length", "get_tl_tracks", "get_tracks",
            "index", "move", "remove", "set_random", "shuffle", "slice",
        }
    ),
    "playback": frozenset(
        {
            "get_current_tl_track", "get_current_tlid", "get_current_track",
            "get_state", "get_stream_title", "get_time_position", "next",
            "pause", "play", "resume", "seek", "stop",
        }
    ),
    "mixer": frozenset({"get_volume", "set_mute", "set_volume"}),
    "playlists": frozenset({"lookup"}),
    "library": frozenset({"get_distinct", "search"}),
}

PORT_ATTRIBUTES: frozenset[str] = frozenset({"http_url"})


def check_conformance(player: Any) -> list[str]:
    """Return the parts of the port `player` fails to provide, as dotted names.

    An empty list means it satisfies the port. Useful at startup to fail loudly
    on an incomplete adapter rather than at the first call, hours later, on a
    code path nobody exercised.
    """
    missing: list[str] = []
    for attr in sorted(PORT_ATTRIBUTES):
        if not hasattr(player, attr):
            missing.append(attr)
    for namespace, methods in sorted(PORT_SURFACE.items()):
        ns = getattr(player, namespace, None)
        if ns is None:
            missing.append(namespace)
            continue
        missing.extend(
            f"{namespace}.{m}" for m in sorted(methods) if not callable(getattr(ns, m, None))
        )
    return missing


class InertPlayer:
    """A player that accepts everything and does nothing, for read-only resolution.

    Resolving a box (`O2mToMopidy.resolve_box_uris`) runs the real fill logic
    with the mutation captured. But the fill also *reads* the player —
    `tracklist.get_length()` as a budget check, `library.get_distinct()` — and
    those reads are what made the Mopidy extension deadlock: its backend actor
    asked o2m to resolve, o2m called back into Mopidy's core, and core was
    already blocked waiting for that same backend to return from `browse()`.

    Swapping the player for this during resolution removes the re-entry
    entirely. It is also arguably more correct: what a box *would* play should
    not depend on what happens to be queued right now.

    It satisfies PlayerPort — `check_conformance(InertPlayer())` returns [] —
    which is precisely what the port was declared for.
    """

    http_url = ""

    class _Tracklist:
        def add(self, tracks=None, *, at_position=None, uris=None): return []
        def clear(self): return None
        def filter(self, criteria): return []
        def get_length(self): return 0
        def get_tl_tracks(self): return []
        def get_tracks(self): return []
        def index(self, tl_track=None, tlid=None): return None
        def move(self, start, end, to_position): return None
        def remove(self, criteria): return []
        def set_random(self, value): return None
        def shuffle(self, start=None, end=None): return None
        def slice(self, start, end): return []

    class _Playback:
        def get_current_tl_track(self): return None
        def get_current_tlid(self): return None
        def get_current_track(self): return None
        def get_state(self): return "stopped"
        def get_stream_title(self): return None
        def get_time_position(self): return 0
        def next(self): return None
        def pause(self): return None
        def play(self, tlid=None): return None
        def resume(self): return None
        def seek(self, time_position): return False
        def stop(self): return None

    class _Mixer:
        def get_volume(self): return None
        def set_mute(self, mute): return False
        def set_volume(self, volume): return False

    class _Playlists:
        def lookup(self, uri): return None

    class _Library:
        def get_distinct(self, field, query=None): return set()
        def search(self, query, uris=None, exact=False): return []

    def __init__(self) -> None:
        self.tracklist = self._Tracklist()
        self.playback = self._Playback()
        self.mixer = self._Mixer()
        self.playlists = self._Playlists()
        self.library = self._Library()
