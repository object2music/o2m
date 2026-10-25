"""Tests for o2m_core.cachelayout — the offline cache's folders and file names.

Run from o2m/:  python3 -m unittest o2m_core.test_cachelayout
"""

import unittest

from o2m_core import cachelayout as cl


class TestNames(unittest.TestCase):

    def test_box_folder_is_name_then_uid(self):
        self.assertEqual(cl.box_folder('Auto music', '04463DD2204B80'),
                         'Auto music [04463DD2204B80]')

    def test_a_box_without_a_name_is_its_uid(self):
        """The layout before names: a folder of that shape is still the box's."""
        self.assertEqual(cl.box_folder('', 'box_news'), 'box_news')
        self.assertEqual(cl.box_folder('box_news', 'box_news'), 'box_news')

    def test_no_uid_is_no_box(self):
        self.assertEqual(cl.box_folder('x', ''), cl.NO_BOX)

    def test_reserved_characters_never_reach_a_path(self):
        """A virtual box's uid carries colons, refused by FAT/NTFS on a device."""
        f = cl.box_folder('AC/DC: Live?', 'obj:spotify:album:1x')
        self.assertNotIn('/', f)
        self.assertNotIn(':', f)
        self.assertNotIn('?', f)
        self.assertTrue(cl.folder_matches(f, 'obj:spotify:album:1x'))

    def test_folder_is_found_by_uid_whatever_its_name(self):
        self.assertTrue(cl.folder_matches('Auto music [04463DD2204B80]', '04463DD2204B80'))
        self.assertTrue(cl.folder_matches('Renamed since [04463DD2204B80]', '04463DD2204B80'))
        self.assertTrue(cl.folder_matches('04463DD2204B80', '04463DD2204B80'))
        self.assertFalse(cl.folder_matches('Other [04463DD2204B81]', '04463DD2204B80'))

    def test_music_file_is_title_then_album(self):
        self.assertEqual(cl.file_stem('Dans Un Camion', 'Le Vent'), 'Dans Un Camion - Le Vent')
        self.assertEqual(cl.file_stem('Solo', ''), 'Solo')
        self.assertEqual(cl.file_stem('', ''), 'track')

    def test_spoken_file_ends_with_its_tag(self):
        """One title every day for a news bulletin: the tag is what tells them
        apart, and what another instance sharing the disk finds the file by."""
        uri = 'podcast+https://feed/x.xml#guid-1'
        stem = cl.file_stem('Le journal de 8h', 'France Inter', uri)
        self.assertTrue(stem.startswith('Le journal de 8h - France Inter ['))
        self.assertEqual(cl.tag_of(stem), cl.spoken_tag(uri))
        self.assertNotEqual(cl.spoken_tag(uri), cl.spoken_tag(uri + '2'))

    def test_old_bare_tag_names_are_still_read(self):
        tag = cl.spoken_tag('podcast+x#y')
        self.assertEqual(cl.tag_of(tag), tag)
        self.assertEqual(cl.tag_of('Dans Un Camion - Le Vent'), '')


if __name__ == '__main__':
    unittest.main()
