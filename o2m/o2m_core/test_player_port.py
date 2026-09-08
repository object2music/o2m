"""Keeps player.py honest.

A hand-written interface rots the moment someone adds a call the interface does
not know about — and it rots silently, because the code keeps working against
the concrete object. These tests re-derive the surface from the source, so the
port cannot drift from what o2m_core actually does.

Run from the o2m/ directory:  python3 -m unittest o2m_core.test_player_port
"""

from __future__ import annotations

import pathlib
import re
import unittest

from o2m_core.player import (
    PORT_ATTRIBUTES,
    PORT_SURFACE,
    LibraryPort,
    MixerPort,
    PlaybackPort,
    PlaylistsPort,
    TracklistPort,
    check_conformance,
)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
# The two files that drive the player: the core logic and the Flask shell.
_SOURCES = (_ROOT / "main.py", _ROOT / "o2m_core" / "o2mtomopidy.py")

# `mopidyHandler.<ns>.<method>` in the core, `mopidy.<ns>.<method>(` in main.py.
# The second needs the trailing paren: `mopidy.<something>` also matches module
# attributes that are not player calls.
_PATTERNS = (
    re.compile(r"mopidyHandler\.([a-z_]+)\.([a-z_]+)"),
    re.compile(r"(?<!mopidyHandler\.)\bmopidy\.([a-z_]+)\.([a-z_]+)\("),
)


def _calls_in_source() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in _SOURCES:
        src = path.read_text()
        for pattern in _PATTERNS:
            found.update((m.group(1), m.group(2)) for m in pattern.finditer(src))
    # `mopidy.http_url.replace(...)` is a string method on the attribute, not a
    # player namespace; the attribute itself is asserted separately.
    return {(ns, meth) for ns, meth in found if ns not in PORT_ATTRIBUTES}


class _Complete:
    """A minimal object that satisfies the whole port."""

    def __init__(self) -> None:
        self.http_url = ""
        for namespace, methods in PORT_SURFACE.items():
            setattr(self, namespace, type("NS", (), {m: (lambda *a, **k: None) for m in methods})())


class PlayerPortSurfaceTest(unittest.TestCase):
    def test_port_covers_every_call_in_the_source(self):
        """Every player call the code makes must be declared in the port."""
        undeclared = sorted(
            f"{ns}.{meth}"
            for ns, meth in _calls_in_source()
            if meth not in PORT_SURFACE.get(ns, frozenset())
        )
        self.assertEqual(
            undeclared,
            [],
            "these player calls exist in the source but are not declared in "
            f"o2m_core/player.py: {undeclared}. Add them to the protocol AND to "
            "PORT_SURFACE, or stop calling them.",
        )

    def test_the_source_still_makes_calls(self):
        """Guard against the regexes silently matching nothing."""
        calls = _calls_in_source()
        self.assertGreater(len(calls), 25, f"only found {len(calls)} player calls — regex broken?")

    def test_surface_matches_the_protocols(self):
        """PORT_SURFACE and the Protocol classes must not disagree."""
        protocols = {
            "tracklist": TracklistPort,
            "playback": PlaybackPort,
            "mixer": MixerPort,
            "playlists": PlaylistsPort,
            "library": LibraryPort,
        }
        self.assertEqual(set(protocols), set(PORT_SURFACE))
        for namespace, proto in protocols.items():
            declared = {
                n for n in vars(proto) if not n.startswith("_") and callable(vars(proto)[n])
            }
            self.assertEqual(
                declared,
                set(PORT_SURFACE[namespace]),
                f"{namespace}: protocol and PORT_SURFACE disagree",
            )


class ConformanceTest(unittest.TestCase):
    def test_complete_object_conforms(self):
        self.assertEqual(check_conformance(_Complete()), [])

    def test_missing_method_is_reported(self):
        player = _Complete()
        del type(player.playback).seek
        self.assertIn("playback.seek", check_conformance(player))

    def test_missing_namespace_is_reported(self):
        player = _Complete()
        del player.mixer
        self.assertIn("mixer", check_conformance(player))

    def test_missing_attribute_is_reported(self):
        player = _Complete()
        del player.http_url
        self.assertIn("http_url", check_conformance(player))


if __name__ == "__main__":
    unittest.main()
