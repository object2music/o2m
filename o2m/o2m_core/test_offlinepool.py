"""Which disk am I? — the cache pool that decides where a download belongs.

Only the pool RESOLUTION is covered here. The branches it drives live in
`DatabaseHandler`, and peewee is not installed where these tests run (which is
why every test in this directory is on a pure module), so the two new tables and
the queries against them are verified live on the instance that needs them
rather than imitated with a stub that would only restate the branch.
"""

import os
import time
import unittest

from o2m_core import offline


class CachePoolTest(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get('O2M_CACHE_POOL')
        os.environ.pop('O2M_CACHE_POOL', None)

    def tearDown(self):
        os.environ.pop('O2M_CACHE_POOL', None)
        if self._saved is not None:
            os.environ['O2M_CACHE_POOL'] = self._saved

    def test_default_is_shared(self):
        """Saying nothing must keep today's behaviour, on every instance.

        This is the whole safety of the change: o2m_0 runs an older image
        against the same database, and an instance that has not been told it
        owns a disk keeps using `Track.local_uri` and `OfflineRequest`.
        """
        self.assertEqual(offline.cache_pool(), 'shared')
        self.assertTrue(offline.is_shared_pool())

    def test_named_pool(self):
        os.environ['O2M_CACHE_POOL'] = 'pi2'
        self.assertEqual(offline.cache_pool(), 'pi2')
        self.assertFalse(offline.is_shared_pool())

    def test_whitespace_is_stripped(self):
        """A systemd drop-in is edited by hand; a trailing space must not make
        'pi2 ' a different pool from 'pi2' and orphan every row already filed."""
        os.environ['O2M_CACHE_POOL'] = '  pi2  '
        self.assertEqual(offline.cache_pool(), 'pi2')

    def test_empty_falls_back_to_shared(self):
        """An unset variable written as empty is not a pool named ''."""
        for value in ('', '   '):
            os.environ['O2M_CACHE_POOL'] = value
            self.assertEqual(offline.cache_pool(), 'shared')
            self.assertTrue(offline.is_shared_pool())

    def test_shared_may_be_named_explicitly(self):
        """Writing the default out is allowed and means the same thing — an
        instance sharing the volume may say so rather than stay silent."""
        os.environ['O2M_CACHE_POOL'] = 'shared'
        self.assertTrue(offline.is_shared_pool())

    def test_read_at_each_call_not_frozen_at_import(self):
        """The pool is consulted on the path of a database lookup, so it is read
        when asked. Frozen at import it could not be set by a drop-in applied
        after the module was loaded, nor exercised the way an operator sets it."""
        os.environ['O2M_CACHE_POOL'] = 'first'
        self.assertEqual(offline.cache_pool(), 'first')
        os.environ['O2M_CACHE_POOL'] = 'second'
        self.assertEqual(offline.cache_pool(), 'second')


class MusicDownloaderPresentTest(unittest.TestCase):
    """Is anything serving this instance's music queue?

    Nothing registers a downloader: spotdl announces itself by polling the queue
    endpoint. These tests pin the asymmetry that makes the answer safe — not
    knowing counts as yes.
    """

    def setUp(self):
        self._polled = dict(offline._queue_polled_at)
        self._started = offline._started_at

    def tearDown(self):
        offline._queue_polled_at.clear()
        offline._queue_polled_at.update(self._polled)
        offline._started_at = self._started

    def _fresh(self, age_s):
        """A process up for `age_s` seconds with nothing ever polled."""
        offline._queue_polled_at.clear()
        offline._started_at = time.monotonic() - age_s

    def test_just_started_counts_as_present(self):
        """The optimistic answer inside the grace, and it is load-bearing.

        Right after a restart nothing has polled yet on ANY instance, including
        the ones whose spotdl is healthy and will poll within 30 s. Answering no
        there would refuse music downloads on the instances that work.
        """
        self._fresh(5)
        self.assertTrue(offline.music_downloader_present())

    def test_never_polled_past_the_grace_is_absent(self):
        """Up long enough with the music queue never once asked for: nobody."""
        self._fresh(offline._MUSIC_POLL_GRACE + 60)
        self.assertFalse(offline.music_downloader_present())

    def test_a_poll_makes_it_present_however_old_the_process(self):
        self._fresh(offline._MUSIC_POLL_GRACE * 10)
        offline.note_queue_poll(spoken=False)
        self.assertTrue(offline.music_downloader_present())

    def test_a_downloader_gone_quiet_is_absent(self):
        """It polled, then stopped — spotdl crashed, or its container is down."""
        self._fresh(offline._MUSIC_POLL_GRACE * 10)
        offline._queue_polled_at['music'] = (
            time.monotonic() - offline._MUSIC_POLL_GRACE - 60)
        self.assertFalse(offline.music_downloader_present())

    def test_the_spoken_queue_does_not_answer_for_music(self):
        """The two queues have two downloaders, and on a native install only the
        spoken one runs — that must not read as a music downloader, or the Pi
        would go back to queueing Spotify tracks to nobody."""
        self._fresh(offline._MUSIC_POLL_GRACE + 60)
        offline.note_queue_poll(spoken=True)
        self.assertFalse(offline.music_downloader_present())

    def test_the_grace_is_well_above_the_poll_interval(self):
        """spotdl polls every 30 s by default (SPOTDL_QUEUE_POLL). A grace near
        that would flip to 'absent' on one slow poll."""
        self.assertGreaterEqual(offline._MUSIC_POLL_GRACE, 300)


if __name__ == '__main__':
    unittest.main()
