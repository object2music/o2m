"""HTTP app served by the extension itself, mounted by Mopidy under `/o2m/`.

This is what replaced the Iris integration: rather than copying `o2m.js` /
`o2m.css` over `mopidy_iris/static/` at image build time, the extension carries
its own assets inside the package and serves them. Those files, and the Mopidy 3
image that patched them in, are deleted. Nothing here may import or assume
Mopidy-Iris — the Mopidy 4 image does not install it.

Mopidy 4 note: `mopidy.http` is gone (the HTTP frontend moved to
`mopidy._exts.http`), but the extension-facing contract is unchanged — a factory
returning Tornado route tuples, registered as `http:app`. So no Mopidy import is
needed here at all; only tornado.
"""

from __future__ import annotations

import json
import pathlib

import tornado.web

STATIC_DIR = pathlib.Path(__file__).parent / "static"


class StatusHandler(tornado.web.RequestHandler):
    """`GET /o2m/status` — a small JSON probe.

    Exists so the extension is verifiable end to end from outside the
    container: it proves the package is installed, its config was read, and it
    holds a live handle on Mopidy's core.
    """

    def initialize(self, config, core):
        self.o2m_config = config
        self.core = core

    def get(self):
        from mopidy_o2m import __version__

        # CoreProxy calls are pykka futures. A short timeout keeps a wedged core
        # from blocking the Tornado IOLoop on what is only a status endpoint.
        try:
            uri_schemes = sorted(self.core.get_uri_schemes().get(timeout=5))
        except Exception as e:
            uri_schemes = None
            self.set_header("X-O2M-Core-Error", type(e).__name__)

        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps(
                {
                    "extension": "mopidy-o2m",
                    "version": __version__,
                    "api_url": self.o2m_config["o2m"]["api_url"],
                    "uri_schemes": uri_schemes,
                },
                indent=2,
            )
        )


def factory(config, core):
    """Routes for the app Mopidy mounts at `/o2m/`. Paths are relative to it."""
    return [
        (r"/status", StatusHandler, {"config": config, "core": core}),
        # Everything else is served from the package's own static directory.
        # Registered last: Tornado matches in order, so `/status` wins.
        (
            r"/(.*)",
            tornado.web.StaticFileHandler,
            {"path": str(STATIC_DIR), "default_filename": "index.html"},
        ),
    ]
