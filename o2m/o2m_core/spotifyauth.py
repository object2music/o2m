"""What Spotify will accept as an OAuth redirect URI — a pure, offline check.

Spotify stopped registering plain `http://` redirects for anything but a **loopback
IP literal**: `https://` for a real host, or `http://127.0.0.1:PORT` / `http://[::1]:PORT`.
`localhost` is refused *as a hostname* — the literal IP is required. That last rule is
the whole trap, because `http://localhost:6681/api/spotipy_init` looks exactly like
something that should work, and it is what `samples/mopidy.conf` shipped: every native
install started from a redirect that could not be registered at all, and the operator
only found out at the end of the round trip, from a Spotify error page naming the
redirect while the real cause sat in the service log.

**For a Raspberry Pi the loopback form is not a fallback, it is THE answer.** A Pi on
someone's LAN has no public hostname and no certificate, so there is nothing to put in
an `https://` redirect; the operator reaches the callback through an SSH tunnel
(`ssh -L 6681:localhost:6681`) or a browser on the Pi itself, and Spotify never has to
resolve the name — it only hands the code back to the browser, which is already on the
right side of the tunnel.

`redirect_uri_problem` is deliberately **offline**. The dashboard's allowlist cannot be
read from here: `accounts.spotify.com/authorize` sends an anonymous caller to its login
page *before* it validates the redirect, so there is no way to probe what is registered
without an authenticated session. The shape is therefore the only thing checkable ahead
of the round trip — and the shape is what fails.
"""

from urllib.parse import urlsplit

# Loopback literals Spotify accepts over plain http. `urlsplit().hostname` strips the
# brackets of an IPv6 literal, so '::1' is the form seen here, never '[::1]'.
LOOPBACK_HOSTS = frozenset({'127.0.0.1', '::1'})

DEFAULT_PORT = 6681
DEFAULT_PATH = '/api/spotipy_init'


def suggested_loopback(port=DEFAULT_PORT, path=DEFAULT_PATH):
    """The redirect to ship, and to suggest when a configured one cannot be registered."""
    return f'http://127.0.0.1:{port}{path or DEFAULT_PATH}'


def _port_of(parts):
    """`parts.port` raises on a malformed port; a missing or bad one falls back to ours."""
    try:
        return parts.port or DEFAULT_PORT
    except ValueError:
        return DEFAULT_PORT


def redirect_uri_problem(uri):
    """None when Spotify can register `uri` and o2m can serve its callback, else one
    sentence saying why it cannot — what the onboarding endpoint reports to the operator."""
    raw = (uri or '').strip()
    if not raw:
        return 'No redirect URI is configured.'

    parts = urlsplit(raw)
    scheme = (parts.scheme or '').lower()
    if not scheme:
        return 'No scheme in the redirect URI — it must start with http:// or https://.'
    if scheme not in ('http', 'https'):
        return (f"Scheme '{scheme}' cannot receive the callback — o2m serves it over "
                'http or https.')

    try:
        host = (parts.hostname or '').lower()
    except ValueError:          # malformed IPv6 literal
        host = ''
    if not host:
        return 'No host in the redirect URI.'

    # https is accepted for any host; only the plain-http case is restricted.
    if scheme == 'https':
        return None
    if host in LOOPBACK_HOSTS:
        return None

    loopback = suggested_loopback(_port_of(parts), parts.path)
    if host == 'localhost':
        return ("Spotify refuses 'localhost' as a hostname: the loopback form must use "
                f'the IP literal. Use {loopback} instead.')
    return (f"Spotify no longer registers a plain http:// redirect for '{host}'. Use "
            f'https:// with a real hostname, or the loopback form {loopback} (reachable '
            'through an SSH tunnel or a browser on the machine itself).')
