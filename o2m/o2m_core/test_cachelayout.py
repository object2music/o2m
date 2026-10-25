"""Tests for o2m_core.cachelayout — the offline cache's files and box views.

Run from o2m/:  python3 -m unittest o2m_core.test_cachelayout
"""

import unittest

from o2m_core import cachelayout as cl


class TestFiles(unittest.TestCase):

    def test_music_is_filed_by_artist_and_album(self):
        self.assertEqual(cl.music_place('Brigitte Fontaine', 'Comme à la radio', 3, 'Dans un camion'),
                         ('Library/Brigitte Fontaine/Comme à la radio', '03 Dans un camion'))

    def test_missing_facts_have_a_name_not_a_hole(self):
        self.assertEqual(cl.music_place('', '', None, 'Solo'),
                         ('Library/Unknown artist/Unknown album', 'Solo'))

    def test_reserved_characters_never_reach_a_path(self):
        folder, stem = cl.music_place('AC/DC', 'Live: 1992?', 1, 'T.N.T.')
        self.assertEqual(folder, 'Library/AC DC/Live 1992')
        self.assertEqual(stem, '01 T.N.T')

    def test_spoken_item_by_channel_date_and_tag(self):
        """One title every day for a bulletin: the date orders them, the tag is
        what tells them apart and what another instance finds the file by."""
        uri = 'podcast+https://feed/x.xml#guid-1'
        folder, stem = cl.spoken_place(uri, 'France Inter', '2026-10-24', 'Le journal de 8h')
        self.assertEqual(folder, 'Podcasts/France Inter')
        self.assertEqual(stem, f'2026-10-24 Le journal de 8h [{cl.spoken_tag(uri)}]')
        self.assertEqual(cl.tag_of(stem), cl.spoken_tag(uri))
        self.assertEqual(cl.spoken_place(uri, '', '', '', video=True)[0], 'Videos/Unknown channel')

    def test_old_bare_tag_names_are_still_read(self):
        tag = cl.spoken_tag('podcast+x#y')
        self.assertEqual(cl.tag_of(tag), tag)
        self.assertEqual(cl.tag_of('03 Dans un camion'), '')


class TestViews(unittest.TestCase):

    A = cl.box_folder('Auto music', '04AD43D2204B80')
    C = cl.box_folder('Chansons', '04D444D2204B80')

    def test_box_folder_is_name_then_uid(self):
        self.assertEqual(self.A, 'Auto music [04AD43D2204B80]')
        self.assertEqual(cl.box_folder('', 'box_news'), 'box_news')
        self.assertNotIn(':', cl.box_folder('Album', 'obj:spotify:album:1x'))

    def test_auto_buckets_are_named(self):
        self.assertEqual(cl.source_label('o2m:favorites', 'favorites'), 'Favorites')
        self.assertEqual(cl.source_label('o2m:history', 'library'), 'Habits')
        self.assertEqual(cl.source_label('spotify:playlist:x', 'incoming', 'playlist:Incoming'), 'Incoming')
        self.assertEqual(cl.source_label('', 'incoming'), 'Incoming')
        self.assertEqual(cl.source_label('spotify:album', 'library'), 'Albums & artists')
        self.assertEqual(cl.source_label('tag:jazz'), 'Tag jazz')
        self.assertEqual(cl.source_label('x', 'new', 'Reco'), 'Recommendations')

    def test_named_sources_lose_their_type_prefix(self):
        self.assertEqual(cl.source_label('spotify:playlist:1', 'library', 'playlist:Vava'), 'Vava')
        self.assertEqual(cl.source_label('spotify:playlist:1', 'library', 'spotify:playlist:1'), '')

    def test_a_source_never_reads_as_a_box(self):
        label = cl.source_label('spotify:playlist:1', 'library', 'playlist:Best of [2020]')
        self.assertEqual(label, 'Best of (2020)')
        lists = cl.playlists([(cl.view_path([self.A], label), 'u')])
        self.assertIn(f'{self.A}/Best of (2020)', lists)

    def test_an_included_box_nests_and_feeds_every_all_above_it(self):
        lists = cl.playlists([
            (cl.view_path([self.A, self.C], 'Playlist X'), 'u1'),
            (cl.view_path([self.A], 'Favorites'), 'u2'),
            (cl.view_path([self.A], ''), 'u3'),
        ])
        self.assertEqual(lists[f'{self.A}/{self.C}/Playlist X'], ['u1'])
        self.assertEqual(lists[f'{self.A}/{self.C}/All'], ['u1'])
        self.assertEqual(lists[f'{self.A}/Favorites'], ['u2'])
        self.assertEqual(lists[f'{self.A}/All'], ['u1', 'u2', 'u3'])
        self.assertNotIn(self.A, lists, "a box with no source is only in its All")

    def test_a_track_in_two_sources_is_listed_once_per_playlist(self):
        lists = cl.playlists([(f'{self.A}/Favorites', 'u'), (f'{self.A}/Habits', 'u')])
        self.assertEqual(lists[f'{self.A}/All'], ['u'])
        self.assertEqual(lists[f'{self.A}/Favorites'], ['u'])
        self.assertEqual(lists[f'{self.A}/Habits'], ['u'])


if __name__ == '__main__':
    unittest.main()
