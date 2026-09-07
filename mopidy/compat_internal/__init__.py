"""Compat shim: `mopidy.internal` was removed in Mopidy 4.

Mopidy-TuneIn 1.1.0 (last released 2021, unmaintained) does
`from mopidy.internal import http, playlists`. Only those two helpers plus the
`validation` module they lean on are vendored here, verbatim from Mopidy 3.4.2 —
they are self-contained (requests, stdlib and `mopidy.httpclient`, which still
exists in 4). Drop this package if TuneIn is retired or gains a Mopidy 4 release.
"""
