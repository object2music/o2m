"""The `o2m:` backend — browse-only, no playback provider.

It registers the `o2m` uri scheme so Mopidy routes `o2m:…` browse and lookup
calls here, and it answers searches against O2M's catalogue. It deliberately
provides **no playback**: everything it returns is a reference into another
backend (`spotify:`, `podcast+`, an http stream), which is what actually
decodes audio. Mopidy never asks us to play an `o2m:` uri because we never
hand one out as a playable track.

No playlists provider either: O2M's playlists are Spotify's, and mopidy-spotify
already owns them. Duplicating them here would show every playlist twice.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import pykka
from mopidy import backend
from mopidy.types import UriScheme

from mopidy_o2m.api import O2mApi
from mopidy_o2m.library import O2mLibraryProvider

logger = logging.getLogger(__name__)


class O2mBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes: ClassVar[list[UriScheme]] = [UriScheme("o2m")]

    def __init__(self, config: Any, audio: Any) -> None:  # noqa: ARG002 — no audio needed
        super().__init__()
        api = O2mApi(config["o2m"]["api_url"])
        self.library = O2mLibraryProvider(backend=self, api=api)
        # Left unset on purpose: see the module docstring.
        self.playback = None
        self.playlists = None
