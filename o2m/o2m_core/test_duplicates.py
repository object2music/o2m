"""Duplicate tracks: grouping proposals and the merged counters."""
import unittest

from o2m_core import duplicates as dup


def row(uri, name='Rachid Ouiguini', artist='taha', ms=273949, rc=0, **kw):
    return dict(uri=uri, name=name, artist=artist, duration_ms=ms, read_count=rc, **kw)


class Normalize(unittest.TestCase):
    def test_release_decorations_go(self):
        for n in ('You Never Give Me Your Money - Remastered 2009',
                  'You Never Give Me Your Money (2009 Remaster)',
                  'You never give me your money - 2011 Remaster - Single Version'):
            self.assertEqual(dup.normalize_title(n), 'you never give me your money', n)

    def test_other_suffixes_stay(self):
        self.assertNotEqual(dup.normalize_title('Voilà Voilà'),
                            dup.normalize_title('Voilà Voilà - Justin Robertson Vocal Edit'))
        self.assertNotEqual(dup.normalize_title('Yamess'), dup.normalize_title('Yamess - Instrumental'))


class Groups(unittest.TestCase):
    def test_same_title_artist_and_length(self):
        g = dup.find_groups([row('a', rc=13), row('b', rc=57), row('c', name='Other', rc=3)])
        self.assertEqual([[m['uri'] for m in x] for x in g], [['b', 'a']])   # most read first

    def test_a_different_length_is_another_recording(self):
        self.assertEqual(dup.find_groups([row('a', rc=1), row('b', ms=273949 + 40000, rc=1)]), [])

    def test_another_artist_is_another_song(self):
        self.assertEqual(dup.find_groups([row('a', rc=1), row('b', artist='x', rc=1)]), [])

    def test_never_played_groups_are_not_proposed(self):
        self.assertEqual(dup.find_groups([row('a'), row('b')]), [])

    def test_merged_and_dismissed_are_left_out(self):
        rows = [row('a', rc=1), row('b', rc=1)]
        self.assertEqual(dup.find_groups(rows, aliased={'b'}), [])
        self.assertEqual(dup.find_groups(rows, dismissed={dup.group_key(['b', 'a'])}), [])

    def test_a_third_version_proposes_a_dismissed_pair_again(self):
        rows = [row('a', rc=1), row('b', rc=1), row('c')]
        self.assertEqual(len(dup.find_groups(rows, dismissed={dup.group_key(['a', 'b'])})), 1)


class Merge(unittest.TestCase):
    def test_counts_add_dates_take_the_latest(self):
        keep = dict(read_count=57, read_count_end=50, skipped_count=7, last_read_date=10,
                    last_play_seq=500, read_end=.9, liked=0)
        other = dict(read_count=13, read_count_end=10, skipped_count=3, last_read_date=20,
                     last_play_seq=400, read_end=.5, liked=1)
        m = dup.merged_counters(keep, [other])
        self.assertEqual((m['read_count'], m['read_count_end'], m['skipped_count']), (70, 60, 10))
        self.assertEqual((m['last_read_date'], m['last_play_seq']), (20, 500))
        self.assertAlmostEqual(m['read_end'], (.9 * 57 + .5 * 13) / 70)
        self.assertEqual(m['liked'], 1)

    def test_like_beats_dislike(self):
        m = dup.merged_counters(dict(liked=1), [dict(disliked=1)])
        self.assertEqual((m['liked'], m['disliked']), (1, 0))


class Certain(unittest.TestCase):
    def test_same_isrc_merges_into_the_most_read(self):
        g = dup.find_groups([row('a', rc=13), row('b', rc=57)])
        self.assertEqual(dup.certain_merges(g, {'a': 'GBBGU1487003', 'b': 'gbbgu1487003'}),
                         [('b', ['a'])])

    def test_different_or_unknown_isrc_is_left_to_a_person(self):
        g = dup.find_groups([row('a', rc=1), row('b', rc=1), row('c', rc=1)])
        self.assertEqual(dup.certain_merges(g, {'a': 'X1', 'b': 'X2', 'c': ''}), [])

    def test_only_the_matching_subset_merges(self):
        g = dup.find_groups([row('a', rc=3), row('b', rc=2), row('c', rc=1)])
        self.assertEqual(dup.certain_merges(g, {'a': 'X1', 'b': 'X2', 'c': 'X1'}), [('a', ['c'])])


if __name__ == '__main__':
    unittest.main()
