"""The shared box budget: each line a share of what is left, single items reserved."""
import unittest

from o2m_core.boxbudget import BoxBudget, is_single_item_line, split


def serve(total, lines, available):
    """Run a box through the budget; `available` says how much each line CAN give."""
    b = BoxBudget(total, lines)
    got = []
    for line in lines:
        share = b.take(line)
        n = 1 if share is None else min(share, available.get(line, share))
        b.spent(0 if share is None else n)
        got.append(n)
    return got


class Shares(unittest.TestCase):
    def test_three_playlists_split_the_box(self):
        # Used to be 15 + 15 + 15, cut to the first 15: playlist A took it all.
        self.assertEqual(serve(15, ['spotify:playlist:A', 'spotify:playlist:B',
                                    'spotify:playlist:C'], {}), [5, 5, 5])

    def test_a_cascade_fits_in_the_parent(self):
        got = serve(30, ['auto:library', 'box:1', 'box:2'], {})
        self.assertEqual(sum(got), 30)

    def test_a_shortfall_rolls_forward(self):
        got = serve(15, ['spotify:playlist:A', 'spotify:playlist:B', 'spotify:playlist:C'],
                    {'spotify:playlist:A': 2})
        self.assertEqual(got, [2, 6, 7])

    def test_a_single_item_reserves_its_place(self):
        lines = ['spotify:playlist:A', 'spotify:playlist:B', 'https://radio/stream.aac']
        self.assertEqual(serve(15, lines, {}), [7, 7, 1])

    def test_a_lone_line_gets_the_whole_box(self):
        self.assertEqual(serve(30, ['auto:library'], {}), [30])

    def test_more_lines_than_places(self):
        lines = ['spotify:playlist:%d' % i for i in range(5)]
        got = serve(3, lines, {})
        self.assertEqual(sum(got), 3)
        self.assertEqual(got[-2:], [0, 0])   # spent: skipped, never more than the box

    def test_single_items(self):
        for l in ('spotify:track:X', 'podcast+https://f/rss#g1', 'https://x/live.mp3',
                  'tunein:station:s1', 'yt:video:abc'):
            self.assertTrue(is_single_item_line(l), l)
        for l in ('spotify:playlist:X', 'podcast+https://f/rss', 'box:04A1',
                  'auto:library', 'web:https://page', 'tag:jazz', 'yt:playlist:UU1'):
            self.assertFalse(is_single_item_line(l), l)


def auto_weights(dl):
    """tracklistfill_auto's weights."""
    return {'favorites': -0.8 * dl + 10, 'common': -0.3 * dl + 8,
            'playlists': -0.3 * dl + 8, 'albums_artists': 0.1 * dl + 4,
            'incoming': 0.3 * dl, 'news': 1.0 * dl}


class Split(unittest.TestCase):
    def test_sum_is_exact_and_never_negative(self):
        for n in range(0, 40):
            for dl in range(11):
                got = split(auto_weights(dl), n)
                self.assertEqual(sum(got.values()), n, (n, dl))
                self.assertTrue(all(v >= 0 for v in got.values()))

    def test_a_small_mix_keeps_every_source(self):
        # 10 places at DL 5: incoming used to round to 0.
        got = split(auto_weights(5), 10)
        self.assertTrue(all(v >= 1 for v in got.values()), got)

    def test_weight_zero_stays_zero(self):
        # DL 0 asks for no news and no incoming: that is not rounding.
        got = split(auto_weights(0), 10)
        self.assertEqual((got['incoming'], got['news']), (0, 0))

    def test_fewer_places_than_sources_the_heaviest_win(self):
        got = split(auto_weights(10), 4)
        self.assertEqual(sum(got.values()), 4)
        self.assertEqual(got['news'], 1)   # the heaviest source at DL 10
        self.assertEqual(got['favorites'], 0)

    def test_large_mix_follows_the_weights(self):
        self.assertEqual(split(auto_weights(0), 30),
                         {'favorites': 10, 'common': 8, 'playlists': 8,
                          'albums_artists': 4, 'incoming': 0, 'news': 0})


if __name__ == '__main__':
    unittest.main()
