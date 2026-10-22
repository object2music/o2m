import unittest

from o2m_core import spotifyauth as sa


class TestRedirectUriProblem(unittest.TestCase):
    """The rule is a shape rule, so every case here is decidable offline."""

    def _ok(self, uri):
        self.assertIsNone(sa.redirect_uri_problem(uri), f'{uri!r} should be accepted')

    def _bad(self, uri, *, because=None):
        problem = sa.redirect_uri_problem(uri)
        self.assertIsInstance(problem, str, f'{uri!r} should be refused')
        self.assertTrue(problem.strip(), 'a refusal must say something')
        if because:
            self.assertIn(because, problem)

    # ── accepted ────────────────────────────────────────────────────────────
    def test_https_any_host(self):
        self._ok('https://o2m.site/api/spotipy_init')
        self._ok('https://pi.example.org:8443/api/spotipy_init')

    def test_http_loopback_literals(self):
        self._ok('http://127.0.0.1:6681/api/spotipy_init')
        self._ok('http://[::1]:6681/api/spotipy_init')

    def test_http_loopback_without_port(self):
        self._ok('http://127.0.0.1/api/spotipy_init')

    def test_shipped_default_is_accepted(self):
        """What samples/mopidy.conf now ships must pass its own check."""
        self._ok(sa.suggested_loopback())

    # ── refused ─────────────────────────────────────────────────────────────
    def test_localhost_is_refused_as_a_hostname(self):
        """The trap: it looks right, and it is what the sample config used to ship."""
        self._bad('http://localhost:6681/api/spotipy_init', because='localhost')

    def test_localhost_refusal_suggests_the_ip_literal(self):
        problem = sa.redirect_uri_problem('http://localhost:6681/api/spotipy_init')
        self.assertIn('http://127.0.0.1:6681/api/spotipy_init', problem)

    def test_plain_http_on_a_real_host(self):
        """The value this install actually carried, and the reason the login failed."""
        self._bad('http://pi.local:6681/api/spotipy_init', because='pi.local')

    def test_plain_http_on_a_public_ip(self):
        self._bad('http://109.7.238.172:6691/api/spotipy_init')

    def test_empty_and_blank(self):
        self._bad('', because='No redirect URI')
        self._bad(None, because='No redirect URI')
        self._bad('   ', because='No redirect URI')

    def test_other_scheme(self):
        self._bad('o2m://callback', because='o2m')

    def test_no_scheme(self):
        self._bad('/api/spotipy_init', because='No scheme')

    def test_whitespace_is_tolerated_around_a_good_value(self):
        self._ok('  http://127.0.0.1:6681/api/spotipy_init  ')


class TestSuggestedLoopback(unittest.TestCase):
    def test_default_shape(self):
        self.assertEqual(sa.suggested_loopback(),
                         'http://127.0.0.1:6681/api/spotipy_init')

    def test_keeps_a_given_port_and_path(self):
        self.assertEqual(sa.suggested_loopback(6691, '/api/spotipy_init'),
                         'http://127.0.0.1:6691/api/spotipy_init')

    def test_falls_back_to_our_path_when_empty(self):
        self.assertEqual(sa.suggested_loopback(6681, ''),
                         'http://127.0.0.1:6681/api/spotipy_init')

    def test_a_malformed_port_does_not_raise(self):
        """`urlsplit().port` raises on a bad port — the check must still answer."""
        problem = sa.redirect_uri_problem('http://pi.local:notaport/api/spotipy_init')
        self.assertIsInstance(problem, str)


if __name__ == '__main__':
    unittest.main()
