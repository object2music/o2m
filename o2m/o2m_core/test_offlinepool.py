"""Which disk am I? — the cache pool that decides where a download belongs.

Only the pool RESOLUTION is covered here. The branches it drives live in
`DatabaseHandler`, and peewee is not installed where these tests run (which is
why every test in this directory is on a pure module), so the two new tables and
the queries against them are verified live on the instance that needs them
rather than imitated with a stub that would only restate the branch.
"""

import os
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


if __name__ == '__main__':
    unittest.main()
