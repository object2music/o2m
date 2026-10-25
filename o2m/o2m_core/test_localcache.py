"""Reading the offline cache with no database — o2m_core/localcache.py.

Every test builds a real cache tree in a temporary directory, because what is
being tested IS the reading of a tree: a fake filesystem would only prove the
fake agrees with itself.
"""

import json
import os
import random
import shutil
import tempfile
import unittest

from o2m_core import cachelayout, localcache


class _Tree(unittest.TestCase):
    """A cache root with a box, an included box, a source and four files."""

    AUTO = 'Auto music [04AD43D2204B80]'
    INNER = 'Chansons [04D444D2204B80]'

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='o2m-cache-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.files = {}
        self._file('Library/Brigitte Fontaine/Comme a la radio/03 Dans un camion.mp3')
        self._file('Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3')
        self._file('Podcasts/France Inter/2026-10-24 Le journal de 8h [3fa2c1d9e04b7a6c1f2e].mp3')
        self._file('Podcasts/France Inter/2026-10-23 Le journal de 8h [aaaabbbbccccddddeeee].mp3')

    def _file(self, rel, body=b'\0'):
        path = os.path.join(self.root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(body)
        self.files[rel] = path
        return path

    def _view(self, rel, lines):
        """Write a `.m3u8` under Boxes/, its paths relative to itself."""
        path = os.path.join(self.root, cachelayout.BOXES, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = ['#EXTM3U']
        for target, title, secs in lines:
            out.append(f"#EXTINF:{secs},{title}")
            out.append(os.path.relpath(os.path.join(self.root, *target.split('/')),
                                       os.path.dirname(path)))
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out) + '\n')
        return path

    def _index(self, items):
        with open(os.path.join(self.root, localcache.INDEX_NAME), 'w',
                  encoding='utf-8') as f:
            json.dump({'items': items}, f)

    def cache(self, seed=1):
        return localcache.LocalCache(self.root, rng=random.Random(seed))


class TestBoxFolderNames(unittest.TestCase):
    """The uid in the folder name is the whole reason a tag can be answered
    from the disk, so the inverse of `box_folder` has to hold both ways."""

    def test_round_trip(self):
        for name, uid in [('Auto music', '04AD43D2204B80'),
                          ('', '04AD43D2204B80'),
                          ('Chansons', '04D444D2204B80')]:
            folder = cachelayout.box_folder(name, uid)
            label, parsed = cachelayout.parse_box_folder(folder)
            self.assertEqual(parsed, uid, folder)
            self.assertEqual(label, name if name and name != uid else '', folder)

    def test_a_source_label_is_not_a_box(self):
        # source_label rewrites a trailing [x] to (x) precisely so that a
        # playlist called "Best of [2020]" cannot read as a box folder.
        self.assertEqual(cachelayout.source_label('', display='Best of [2020]'),
                         'Best of (2020)')
        label, uid = cachelayout.parse_box_folder('Best of (2020)')
        self.assertEqual((label, uid), ('', 'Best of (2020)'))

    def test_nothing_is_not_a_box(self):
        self.assertIsNone(cachelayout.parse_box_folder(''))
        self.assertIsNone(cachelayout.parse_box_folder('   '))


class TestBoxes(_Tree):

    def test_a_tag_finds_its_box_from_the_disk_alone(self):
        self._view(f'{self.AUTO}/All.m3u8',
                   [('Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3',
                     'Bohemian Rhapsody', 355)])
        c = self.cache()
        box = c.box('04AD43D2204B80')
        self.assertIsNotNone(box)
        self.assertEqual(box.uid, '04AD43D2204B80')
        self.assertEqual(box.label, 'Auto music')
        self.assertEqual(box.name, 'Auto music')

    def test_the_uid_is_matched_whatever_its_case(self):
        self._view(f'{self.AUTO}/All.m3u8', [])
        self.assertIsNotNone(self.cache().box('04ad43d2204b80'))

    def test_an_included_box_is_found_too(self):
        self._view(f'{self.AUTO}/{self.INNER}/All.m3u8',
                   [('Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3',
                     'Bohemian Rhapsody', 355)])
        c = self.cache()
        self.assertEqual({b.uid for b in c.boxes()},
                         {'04AD43D2204B80', '04D444D2204B80'})
        inner = c.box('04D444D2204B80')
        self.assertEqual(inner.rel, f'{self.AUTO}/{self.INNER}')

    def test_an_unknown_tag_is_no_box_and_no_crash(self):
        self.assertIsNone(self.cache().box('DEADBEEF'))
        self.assertIsNone(self.cache().box(''))
        self.assertEqual(self.cache().queue('DEADBEEF'), [])

    def test_an_empty_cache_answers_nothing(self):
        c = localcache.LocalCache(os.path.join(self.root, 'nope'))
        self.assertEqual(c.boxes(), [])
        self.assertEqual(c.index(), {})


class TestEntries(_Tree):

    def test_a_view_plays_without_any_index(self):
        """The degraded mode must not depend on the index, or it would depend
        on the freshness it exists to do without."""
        self._view(f'{self.AUTO}/All.m3u8', [
            ('Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3',
             'Bohemian Rhapsody', 355),
        ])
        got = self.cache().entries(f'{self.AUTO}/All.m3u8')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].title, 'Bohemian Rhapsody')   # from the #EXTINF
        self.assertEqual(got[0].seconds, 355)
        self.assertEqual(got[0].uri, '')                      # nothing names it
        self.assertEqual(got[0].kind, 'music')
        self.assertTrue(os.path.isfile(got[0].file))

    def test_the_index_names_the_item_and_wins_on_the_title(self):
        rel = 'Podcasts/France Inter/2026-10-24 Le journal de 8h [3fa2c1d9e04b7a6c1f2e].mp3'
        self._view(f'{self.AUTO}/All.m3u8', [(rel, 'a stale title', 600)])
        self._index({'podcast+https://f.fr/rss#guid-1': {
            'path': rel, 'title': 'Le journal de 8h', 'seconds': 612,
            'kind': 'spoken', 'cat': 'info', 'position': 120000,
            'ad_skip': 30000, 'volume_boost': 50, 'finished': False,
            'liked': True}})
        e = self.cache().entries(f'{self.AUTO}/All.m3u8')[0]
        self.assertEqual(e.uri, 'podcast+https://f.fr/rss#guid-1')
        self.assertEqual(e.title, 'Le journal de 8h')
        self.assertEqual(e.seconds, 612)
        self.assertEqual(e.cat, 'info')
        self.assertTrue(e.spoken)
        self.assertEqual(e.volume_boost, 50)
        self.assertTrue(e.liked)

    def test_a_line_whose_file_is_gone_is_dropped(self):
        """A view is rewritten only when its content moves, so it can outlive
        a file the expiry took."""
        keep = 'Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3'
        gone = 'Library/Queen/A Night at the Opera/99 Deleted.mp3'
        self._view(f'{self.AUTO}/All.m3u8',
                   [(gone, 'Deleted', 100), (keep, 'Bohemian Rhapsody', 355)])
        got = self.cache().entries(f'{self.AUTO}/All.m3u8')
        self.assertEqual([e.title for e in got], ['Bohemian Rhapsody'])

    def test_a_dropped_line_does_not_lend_its_title_to_the_next(self):
        """The #EXTINF is read before the path it describes, so skipping a
        missing file must clear it or the next line inherits it."""
        gone = 'Library/Queen/A Night at the Opera/99 Deleted.mp3'
        keep = 'Library/Brigitte Fontaine/Comme a la radio/03 Dans un camion.mp3'
        self._view(f'{self.AUTO}/All.m3u8',
                   [(gone, 'Deleted', 111), (keep, '', 0)])
        got = self.cache().entries(f'{self.AUTO}/All.m3u8')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].title, '')
        self.assertEqual(got[0].seconds, 0)

    def test_a_broken_index_is_an_empty_one(self):
        rel = 'Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3'
        self._view(f'{self.AUTO}/All.m3u8', [(rel, 'Bohemian Rhapsody', 355)])
        with open(os.path.join(self.root, localcache.INDEX_NAME), 'w') as f:
            f.write('{not json at all')
        c = self.cache()
        self.assertEqual(c.index(), {})
        self.assertEqual(len(c.entries(f'{self.AUTO}/All.m3u8')), 1)

    def test_the_index_is_re_read_when_it_moves(self):
        rel = 'Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3'
        self._view(f'{self.AUTO}/All.m3u8', [(rel, 'x', 1)])
        self._index({'spotify:track:a': {'path': rel, 'title': 'First'}})
        c = self.cache()
        self.assertEqual(c.entries(f'{self.AUTO}/All.m3u8')[0].title, 'First')
        os.utime(os.path.join(self.root, localcache.INDEX_NAME), (0, 0))
        self._index({'spotify:track:a': {'path': rel, 'title': 'Second'}})
        self.assertEqual(c.entries(f'{self.AUTO}/All.m3u8')[0].title, 'Second')


class TestWherePlaybackStarts(unittest.TestCase):
    """The server's rule, and its two halves are not symmetrical."""

    def test_music_always_starts_at_zero(self):
        # A music track played to the end carries read_position == its own
        # duration, so honouring it would restart every favourite at its last
        # note. The server does not resume music; neither does this.
        e = localcache.Entry('/f.mp3', kind='music', position=355_000,
                             ad_skip=30_000)
        self.assertEqual(e.start_ms(), 0)

    def test_a_started_spoken_item_resumes_a_little_before(self):
        e = localcache.Entry('/f.mp3', kind='spoken', position=120_000)
        self.assertEqual(e.start_ms(), 120_000 - localcache.RESUME_LEAD_MS)

    def test_a_resume_near_the_start_does_not_go_negative(self):
        e = localcache.Entry('/f.mp3', kind='spoken', position=2_000)
        self.assertEqual(e.start_ms(), 0)

    def test_a_fresh_spoken_item_skips_the_pre_roll_instead(self):
        e = localcache.Entry('/f.mp3', kind='spoken', position=0, ad_skip=30_000)
        self.assertEqual(e.start_ms(), 30_000)

    def test_a_resume_wins_over_the_pre_roll(self):
        # The ad is before the bookmark by definition: skipping it again would
        # rewind a listener who is already past it.
        e = localcache.Entry('/f.mp3', kind='spoken', position=600_000,
                             ad_skip=30_000)
        self.assertEqual(e.start_ms(), 590_000)


class TestQueue(_Tree):

    THREE = [
        ('Library/Queen/A Night at the Opera/11 Bohemian Rhapsody.mp3', 'B', 355),
        ('Library/Brigitte Fontaine/Comme a la radio/03 Dans un camion.mp3', 'D', 200),
        ('Podcasts/France Inter/2026-10-24 Le journal de 8h [3fa2c1d9e04b7a6c1f2e].mp3',
         'J', 600),
    ]

    def test_asc_keeps_the_order_written(self):
        self._view(f'{self.AUTO}/All.m3u8', self.THREE)
        got = self.cache().queue('04AD43D2204B80', sort='asc')
        self.assertEqual([e.title for e in got], ['B', 'D', 'J'])

    def test_desc_reverses_it(self):
        self._view(f'{self.AUTO}/All.m3u8', self.THREE)
        got = self.cache().queue('04AD43D2204B80', sort='desc')
        self.assertEqual([e.title for e in got], ['J', 'D', 'B'])

    def test_no_sort_shuffles_and_keeps_everything(self):
        """A view with no stated order is an accumulation: replayed as written
        it would give the same sequence every time."""
        self._view(f'{self.AUTO}/All.m3u8', self.THREE)
        got = self.cache().queue('04AD43D2204B80', sort='')
        self.assertEqual(sorted(e.title for e in got), ['B', 'D', 'J'])
        # Reproducible under a seed, which is what makes this assertable at all.
        again = self.cache().queue('04AD43D2204B80', sort='')
        self.assertEqual([e.title for e in got], [e.title for e in again])

    def test_a_finished_episode_is_left_out_but_music_never_is(self):
        self._view(f'{self.AUTO}/All.m3u8', self.THREE)
        self._index({
            'podcast+https://f.fr/rss#g': {
                'path': self.THREE[2][0], 'kind': 'spoken', 'finished': True},
            'spotify:track:q': {
                'path': self.THREE[0][0], 'kind': 'music', 'finished': True},
        })
        got = self.cache().queue('04AD43D2204B80', sort='asc')
        self.assertEqual([e.title for e in got], ['B', 'D'])
        # ...unless the caller asks for everything.
        every = self.cache().queue('04AD43D2204B80', sort='asc',
                                   include_finished=True)
        self.assertEqual(len(every), 3)

    def test_with_no_All_a_source_is_played_instead(self):
        self._view(f'{self.AUTO}/Favorites.m3u8', self.THREE[:1])
        got = self.cache().queue('04AD43D2204B80', sort='asc')
        self.assertEqual([e.title for e in got], ['B'])

    def test_All_comes_first_among_the_views(self):
        self._view(f'{self.AUTO}/Favorites.m3u8', self.THREE[:1])
        self._view(f'{self.AUTO}/All.m3u8', self.THREE)
        c = self.cache()
        views = c.views(c.box('04AD43D2204B80'))
        self.assertTrue(views[0].endswith('All.m3u8'), views)
        self.assertEqual(len(views), 2)


if __name__ == '__main__':
    unittest.main()
