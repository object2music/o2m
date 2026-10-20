import unittest

from o2m_core import lyrics


class ParseLrcTest(unittest.TestCase):
    def test_lines_sorted_with_milliseconds(self):
        got = lyrics.parse_lrc("[ar:Someone]\n[00:12.50] second\n[00:01.05] first\n")
        self.assertEqual(got, [[1050, 'first'], [12500, 'second']])

    def test_several_stamps_on_one_line(self):
        got = lyrics.parse_lrc("[00:10.00][01:10.00] chorus")
        self.assertEqual(got, [[10000, 'chorus'], [70000, 'chorus']])

    def test_two_digit_fraction_is_hundredths(self):
        self.assertEqual(lyrics.parse_lrc("[00:00.5] x")[0][0], 500)


class CleanTest(unittest.TestCase):
    def test_release_decorations_dropped(self):
        self.assertEqual(lyrics.clean_title('Let It Be - Remastered 2009'), 'Let It Be')
        self.assertEqual(lyrics.clean_title('Song (feat. Someone)'), 'Song')
        self.assertEqual(lyrics.clean_title('Sit Down. Stand Up'), 'Sit Down. Stand Up')

    def test_main_artist(self):
        self.assertEqual(lyrics.main_artist('D-Pulse, Hot Toddy'), 'D-Pulse')
        self.assertEqual(lyrics.main_artist('Ben Harper'), 'Ben Harper')

class PickRowTest(unittest.TestCase):
    def test_synced_upload_wins(self):
        rows = [{'plainLyrics': 'a'}, {'syncedLyrics': '[00:01.00]a', 'plainLyrics': 'a'}]
        self.assertIn('syncedLyrics', lyrics.pick_row(rows))

    def test_plain_when_nothing_timed(self):
        self.assertEqual(lyrics.pick_row([{'plainLyrics': 'a'}]), {'plainLyrics': 'a'})
        self.assertIsNone(lyrics.pick_row([]))


if __name__ == '__main__':
    unittest.main()
