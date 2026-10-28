"""Tests for o2m_core.mopidywatch — a Mopidy that came up without Spotify.

The journals below are the real ones, copied from pi1 on 2026-10-28: the failing
start of the night before, and the successful one after the restart.

Run from o2m/:  python3 -m unittest o2m_core.test_mopidywatch
"""

import unittest

from o2m_core import mopidywatch as mw

DEAD = """\
oct. 27 23:49:18 pi mopidy[671]: INFO [MainThread] mopidy.__main__ Enabled extensions: iris, file, podcast, mpd, http, softwaremixer, tunein, spotify, podcast-itunes, stream, m3u, youtube
oct. 27 23:49:20 pi mopidy[671]: ERROR [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.web Retrying https://auth.mopidy.com/spotify/token in 0.500 seconds.
oct. 27 23:49:22 pi mopidy[671]: ERROR [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.web Retrying https://auth.mopidy.com/spotify/token in 1.000 seconds.
oct. 27 23:49:23 pi mopidy[671]: ERROR [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.web OAuth token refresh failed: Unknown error.
oct. 27 23:49:23 pi mopidy[671]: ERROR [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.web Failed to load Spotify user profile
oct. 27 23:49:23 pi mopidy[671]: INFO [MainThread] mopidy.commands Starting Mopidy core
"""

ALIVE = """\
oct. 28 22:06:23 pi mopidy[24441]: INFO [MainThread] mopidy.commands Starting Mopidy backends: SpotifyBackend, TuneInBackend, YouTubeBackend
oct. 28 22:06:25 pi mopidy[24441]: INFO [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.web Logged into Spotify Web API as 1181464119
oct. 28 22:06:25 pi mopidy[24441]: INFO [SpotifyBackend-3 (_actor_loop)] mopidy_spotify.playlists Refreshing 41 Spotify playlists in background
"""


class TestTheVerdictComesFromMopidysOwnWords(unittest.TestCase):

    def test_the_failing_start_measured_on_pi1(self):
        self.assertEqual(mw.spotify_verdict(DEAD), 'dead')

    def test_the_working_start_measured_on_pi1(self):
        self.assertEqual(mw.spotify_verdict(ALIVE), 'alive')

    def test_a_retry_that_then_succeeds_is_alive(self):
        """The last decisive line wins, not the first: mopidy-spotify retries
        its token around startup, and a success after a failure means it has an
        account. Reading the first line would restart a healthy Mopidy."""
        self.assertEqual(mw.spotify_verdict(
            "ERROR mopidy_spotify.web Retrying https://auth.mopidy.com/spotify/token in 0.500 seconds.\n"
            "INFO mopidy_spotify.web Logged into Spotify Web API as 1181464119\n"), 'alive')

    def test_a_failure_after_a_success_is_dead(self):
        self.assertEqual(mw.spotify_verdict(
            "INFO mopidy_spotify.web Logged into Spotify Web API as 118\n"
            "INFO mopidy_spotify.search Spotify search aborted: Spotify is offline\n"), 'dead')

    def test_a_log_that_says_nothing_is_unknown(self):
        """The common answer, and it must lead to doing nothing: the extension
        disabled, a version wording it differently, a journal already rotated."""
        for text in ('', None, "INFO mopidy.commands Starting Mopidy core\n"):
            self.assertEqual(mw.spotify_verdict(text), 'unknown')


class TestWhatItDecidesToDo(unittest.TestCase):

    def act(self, verdict='dead', uptime=600, net=True, attempts=0):
        return mw.decide(verdict, uptime, net, attempts)[0]

    def test_a_latched_backend_on_a_reachable_network_is_restarted(self):
        self.assertEqual(self.act(), 'restart')

    def test_nothing_is_done_unless_the_log_says_dead(self):
        """`unknown` must never act. A watchdog that restarts on 'I could not
        tell' is worse than none: it cuts the music for its own blind spot."""
        self.assertEqual(self.act(verdict='alive'), 'none')
        self.assertEqual(self.act(verdict='unknown'), 'none')

    def test_a_mopidy_that_just_started_is_left_alone(self):
        """What keeps it out of a restart loop: each restart makes a young
        Mopidy, and acting on one would make the next, for ever."""
        self.assertEqual(self.act(uptime=5), 'wait')
        self.assertEqual(self.act(uptime=119), 'wait')
        self.assertEqual(self.act(uptime=121), 'restart')

    def test_it_does_not_restart_into_the_same_outage(self):
        """The ordinary cause IS the network. Restarting while it is still down
        cuts whatever is playing for nothing and spends an attempt on a cause
        that has not gone away."""
        self.assertEqual(self.act(net=False), 'wait')

    def test_waiting_for_the_network_never_spends_an_attempt(self):
        """A week-long outage must leave all three attempts for the moment the
        link comes back."""
        action, _ = mw.decide('dead', 9999, False, 0)
        self.assertEqual(action, 'wait')
        self.assertEqual(self.act(net=True, attempts=0), 'restart')

    def test_it_gives_up_rather_than_cut_the_music_for_ever(self):
        """A revoked token looks exactly like a network blip from here and no
        restart cures it."""
        self.assertEqual(self.act(attempts=2), 'restart')
        self.assertEqual(self.act(attempts=3), 'give-up')
        self.assertEqual(self.act(attempts=99), 'give-up')

    def test_every_branch_says_why(self):
        """The reason is the whole value of the log line: four ways to be wrong,
        told apart."""
        seen = set()
        for kw in (dict(verdict='alive'), dict(uptime=5), dict(net=False),
                   dict(attempts=9), {}):
            args = dict(verdict='dead', uptime=600, net=True, attempts=0)
            args.update(kw)
            action, why = mw.decide(args['verdict'], args['uptime'],
                                    args['net'], args['attempts'])
            self.assertTrue(why and why.strip(), action)
            seen.add(action)
        self.assertEqual(seen, {'none', 'wait', 'give-up', 'restart'})


if __name__ == '__main__':
    unittest.main()
