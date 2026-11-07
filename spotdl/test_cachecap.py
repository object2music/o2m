"""The cap's choice of files. Run from the repo root: python3 spotdl/test_cachecap.py"""

import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location(
    'spotdl_cache', pathlib.Path(__file__).with_name('cache.py'))
cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cache)


def names(victims):
    return [f for f, _size in victims]


class CapVictims(unittest.TestCase):
    def test_under_the_cap_nothing_goes(self):
        self.assertEqual(cache.cap_victims([('m', 10, 1)], set(), set(), 10, 0.25), [])

    def test_unheard_episode_outlives_newer_music(self):
        # The 2026-10-29 case: older than every music file, and still wanted.
        entries = [('ep', 20, 1), ('m1', 40, 5), ('m2', 60, 6)]
        self.assertEqual(names(cache.cap_victims(entries, set(), {'ep'}, 100, 0.25)), ['m1'])

    def test_heard_episode_goes_first(self):
        entries = [('m', 60, 1), ('ep', 60, 9)]
        self.assertEqual(names(cache.cap_victims(entries, {'ep'}, {'ep'}, 100, 0.25)), ['ep'])

    def test_past_its_share_the_oldest_episode_ages_like_the_rest(self):
        entries = [('old', 20, 1), ('new', 20, 2), ('m', 70, 3)]
        got = cache.cap_victims(entries, set(), {'old', 'new'}, 100, 0.25)
        self.assertEqual(names(got), ['old'])

    def test_share_zero_is_the_previous_order(self):
        entries = [('ep', 20, 1), ('m', 90, 5)]
        self.assertEqual(names(cache.cap_victims(entries, set(), {'ep'}, 100, 0)), ['ep'])

    def test_the_cap_holds_whatever_the_share(self):
        entries = [('a', 60, 1), ('b', 60, 2)]
        got = cache.cap_victims(entries, set(), {'a', 'b'}, 100, 5)
        self.assertLessEqual(sum(e[1] for e in entries) - sum(s for _f, s in got), 100)


if __name__ == '__main__':
    unittest.main()
