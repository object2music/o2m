"""Mopidy-O2M — the O2M extension for Mopidy.

Deliberately a no-op for now: it registers itself, reads its config and adds
nothing to the registry. That is enough for `mopidy deps` to list it and for
`[o2m]` to appear in `mopidy config`, which is what we want to verify before
wiring any behaviour in.

Targets the Mopidy 3.x extension API because that is what the image runs;
everything used here is unchanged in Mopidy 4 (see pyproject.toml, README).
"""

import logging
import pathlib

from mopidy import config, ext

__version__ = "0.1.0"

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
        return schema

    def setup(self, registry):
        # Nothing registered yet. This is where a backend
        # (registry.add("backend", ...)), a frontend or an HTTP handler
        # (registry.add("http:app", ...)) will go.
        #
        # Never depend on Mopidy-Iris here, nor write into its files: the o2m.js /
        # o2m.css edits stay in the non-plugin code. Anything this extension needs
        # to show in a browser it serves itself under /o2m/. See README.
        logger.info("Mopidy-O2M %s loaded (no components registered yet)", self.version)
