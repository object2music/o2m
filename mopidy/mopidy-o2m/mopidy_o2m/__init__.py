"""Mopidy-O2M — the O2M extension for Mopidy.

Targets the Mopidy 4 extension API and is verified loading on 3.4.2 as well;
everything it uses (`ext.Extension`, `config.read`, `config.String`, the
registry, the `http:app` factory contract) is unchanged between the two.

What it does today: serves its own HTTP app under `/o2m/` — a status probe and
the package's own static assets. It registers no backend yet.

It must never depend on Mopidy-Iris. The Mopidy 4 image does not install Iris at
all; the legacy `o2m.js` / `o2m.css` copies into `mopidy_iris/static/` stay in
the non-plugin code and are not to be reproduced here.
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
        return schema

    def setup(self, registry):
        # Mounted by Mopidy at /o2m/. No backend registered yet — that is where
        # a backend (registry.add("backend", ...)) or a frontend will go.
        registry.add("http:app", {"name": self.ext_name, "factory": self.webapp})
        logger.info("Mopidy-O2M %s loaded — HTTP app at /%s/", self.version, self.ext_name)

    def webapp(self, config, core):
        from .web import factory  # noqa: PLC0415 — deferred like Mopidy-Local's

        return factory(config, core)
