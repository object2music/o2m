"""Mopidy-O2M — the O2M extension for Mopidy.

Targets the Mopidy 4 extension API and is verified loading on 3.4.2 as well;
everything it uses (`ext.Extension`, `config.read`, `config.String`, the
registry, the `http:app` factory contract) is unchanged between the two.

What it does today:
  - a **backend** exposing the `o2m:` scheme, browse-only: O2M's catalogue
    (playlists, podcast channels, genres) and a search over it, returning
    references into other backends. No playback provider — see `backend.py`.
  - a **frontend** that pushes playback events to the O2M API in-process,
    replacing the websocket transport (see `frontend.py` for why)
  - an **HTTP app** under `/o2m/` — a status probe and the package's own assets

It is an adapter, never the seat of the logic — box semantics, discover level
and popularity stay in the o2m service, so a second facade can be a client of
the same API rather than a client of Mopidy.

It must never depend on Mopidy-Iris. The Mopidy 4 image does not install Iris at
all, and the legacy `o2m.js` / `o2m.css` that were copied into
`mopidy_iris/static/` have been deleted along with the Mopidy 3 image.
"""

import logging
import pathlib
from importlib.metadata import version

from mopidy import config, ext

# Single source of truth is pyproject.toml, read back from the installed
# distribution metadata — the same thing Mopidy-Local does.
__version__ = version("Mopidy-O2M")

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = "Mopidy-O2M"
    ext_name = "o2m"
    version = __version__

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()
        # Base URL of the O2M API. Inside the compose network this is the
        # service name, never a published port or a public IP.
        schema["api_url"] = config.String()
        # Off means the frontend actor starts and does nothing: the o2m service
        # keeps taking events over its websocket. Kept configurable so an
        # instance can be rolled back without rebuilding the image.
        schema["forward_events"] = config.Boolean()
        return schema

    def setup(self, registry):
        from .backend import O2mBackend  # noqa: PLC0415
        from .frontend import O2mFrontend  # noqa: PLC0415 — deferred like Mopidy-MPD's

        # Browse-only: the `o2m` scheme resolves to references into other
        # backends, so this registers no playback provider. See backend.py.
        registry.add("backend", O2mBackend)
        registry.add("frontend", O2mFrontend)
        # Mounted by Mopidy at /o2m/.
        registry.add("http:app", {"name": self.ext_name, "factory": self.webapp})
        logger.info("Mopidy-O2M %s loaded — HTTP app at /%s/", self.version, self.ext_name)

    def webapp(self, config, core):
        from .web import factory  # noqa: PLC0415 — deferred like Mopidy-Local's

        return factory(config, core)
