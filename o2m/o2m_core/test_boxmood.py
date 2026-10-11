"""The mood of a box's content: line reading, line-weighted average, distances."""
import random
import unittest

from o2m_core import boxmood


class Reader:
    def __init__(self, sets=None, feats=None):
        self.sets, self.feats = sets or {}, feats or {}

    def track_uris(self, kind, key):
        return self.sets.get((kind, key), [])

    def features(self, uris):
        return {u: self.feats[u] for u in uris if u in self.feats}


def f(e, v, name=''):
    return {'energy': e, 'valence': v, 'name': name, 'artist': ''}


class Classify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(boxmood.classify('spotify:playlist:abc'), ('playlist', 'abc'))
        self.assertEqual(boxmood.classify('spotify:user:me:playlist:abc'), ('playlist', 'abc'))
        self.assertEqual(boxmood.classify('spotify:album:A1'), ('album', 'A1'))
        self.assertEqual(boxmood.classify('tag:new wave'), ('tag', 'new wave'))

    def test_rules_name_no_fixed_set(self):
        for line in ('auto:library', 'now:library', 'https://x/stream.aac',
                     'podcast+https://f/rss', 'spotify:library', 'box:12ab'):
            self.assertEqual(boxmood.classify(line), (None, None), line)

    def test_every_hour_counts_and_directives_do_not(self):
        data = '#Morning\nmood:calm\n08:00-10:00 > spotify:album:A\n#spotify:album:B\ndl:3'
        self.assertEqual(boxmood.content_lines(data), ['spotify:album:A'])


class Average(unittest.TestCase):
    def test_each_line_weighs_the_same(self):
        # One track at (1,1) against a 3-track artist at (0,0): a per-track mean
        # would say .25, the box plays both lines equally, so .5.
        r = Reader(sets={('track', 'T'): ['t'], ('artist', 'A'): ['a1', 'a2', 'a3']},
                   feats={'t': f(1, 1), 'a1': f(0, 0), 'a2': f(0, 0), 'a3': f(0, 0)})
        pts, lines = boxmood.measure('spotify:track:T\nspotify:artist:A', r)
        s = boxmood.summarize(pts)
        self.assertAlmostEqual(s['energy'], .5)
        self.assertAlmostEqual(s['valence'], .5)
        self.assertEqual([l['measured'] for l in lines], [1, 3])

    def test_unmeasured_tracks_and_rules_are_reported_not_counted(self):
        r = Reader(sets={('playlist', 'P'): ['x', 'y']}, feats={'x': f(.2, .4)})
        pts, lines = boxmood.measure('spotify:playlist:P\nauto:library', r)
        self.assertEqual(lines[0]['tracks'], 2)
        self.assertEqual(lines[0]['measured'], 1)
        self.assertIsNone(lines[1]['kind'])
        self.assertAlmostEqual(boxmood.summarize(pts)['energy'], .2)

    def test_an_included_box_is_not_followed(self):
        r = Reader(sets={('track', 'a'): ['a']}, feats={'a': f(.3, .3)})
        pts, lines = boxmood.measure('spotify:track:a\nbox:kid', r)
        self.assertEqual(len(pts), 1)
        self.assertIsNone(lines[1]['kind'])

    def test_sorted_most_divergent_first(self):
        r = Reader(sets={('playlist', 'P'): ['n', 'm', 'far']},
                   feats={'n': f(.5, .5, 'near'), 'm': f(.5, .5, 'mid'), 'far': f(1, 1, 'far')})
        s = boxmood.summarize(boxmood.measure('spotify:playlist:P', r)[0])
        self.assertEqual(s['tracks'][0]['uri'], 'far')
        self.assertTrue(s['tracks'][0]['distance'] >= s['tracks'][-1]['distance'])
        self.assertTrue(0 < s['inside'] < 1)

    def test_a_large_line_is_sampled(self):
        uris = [f'u{i}' for i in range(boxmood.MAX_PER_LINE + 50)]
        r = Reader(sets={('tag', 'jazz'): uris}, feats={u: f(.5, .5) for u in uris})
        pts, lines = boxmood.measure('tag:jazz', r, rng=random.Random(1))
        self.assertEqual(len(pts), boxmood.MAX_PER_LINE)
        self.assertEqual(lines[0]['tracks'], len(uris))

    def test_nothing_measured(self):
        self.assertIsNone(boxmood.summarize([]))


if __name__ == '__main__':
    unittest.main()
