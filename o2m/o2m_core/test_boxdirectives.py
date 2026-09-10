import datetime
import unittest

from o2m_core import boxdirectives as bd


def at(h, m=0):
    return datetime.datetime(2026, 9, 10, h, m)


class TestSplitCondition(unittest.TestCase):
    def test_plain_line_is_untouched(self):
        self.assertEqual(bd.split_condition('auto:library'), (None, 'auto:library'))

    def test_window_is_stripped(self):
        self.assertEqual(bd.split_condition('08:00-10:00 > infos:library'),
                         ((480, 600), 'infos:library'))

    def test_a_uri_containing_a_colon_is_not_mistaken_for_a_window(self):
        # The payload itself is full of colons; only a leading hh:mm-hh:mm > counts.
        line = 'podcast+https://example.org/rss.xml#guid:1'
        self.assertEqual(bd.split_condition(line), (None, line))

    def test_nonsense_window_falls_back_to_plain_text(self):
        self.assertEqual(bd.split_condition('99:00-10:00 > x'), (None, '99:00-10:00 > x'))


class TestWindowMatches(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(bd.window_matches((480, 600), at(9)))

    def test_start_inclusive_end_exclusive(self):
        self.assertTrue(bd.window_matches((480, 600), at(8, 0)))
        self.assertFalse(bd.window_matches((480, 600), at(10, 0)))

    def test_wraps_midnight(self):
        w = (22 * 60, 2 * 60)
        self.assertTrue(bd.window_matches(w, at(23)))
        self.assertTrue(bd.window_matches(w, at(1)))
        self.assertFalse(bd.window_matches(w, at(12)))

    def test_no_window_always_matches(self):
        self.assertTrue(bd.window_matches(None, at(3)))


class TestParseMood(unittest.TestCase):
    def test_named(self):
        self.assertEqual(bd.parse_mood('calm'), bd.MOOD_NAMES['calm'])
        self.assertEqual(bd.parse_mood('  ENERGETIC '), bd.MOOD_NAMES['energetic'])

    def test_pair(self):
        self.assertEqual(bd.parse_mood('0.3,0.8'), (0.3, 0.8))

    def test_out_of_range_and_garbage_are_refused(self):
        self.assertIsNone(bd.parse_mood('1.5,0.2'))
        self.assertIsNone(bd.parse_mood('sombre'))
        self.assertIsNone(bd.parse_mood(''))


class TestReadDirectives(unittest.TestCase):
    def test_nothing_set(self):
        self.assertEqual(bd.read_directives('auto:library\nbox:ABC'),
                         {'energy': None, 'valence': None, 'dl': None})

    def test_unconditional(self):
        d = bd.read_directives('dl:7\nmood:calm\nauto:library')
        self.assertEqual(d['dl'], 7)
        self.assertEqual((d['energy'], d['valence']), bd.MOOD_NAMES['calm'])

    def test_window_outside_is_ignored(self):
        d = bd.read_directives('08:00-10:00 > dl:2', now=at(15))
        self.assertIsNone(d['dl'])

    def test_window_inside_applies(self):
        d = bd.read_directives('08:00-10:00 > dl:2', now=at(9))
        self.assertEqual(d['dl'], 2)

    def test_conditional_beats_unconditional_whatever_the_order(self):
        # The more specific statement wins even when typed first.
        early = bd.read_directives('08:00-10:00 > dl:2\ndl:9', now=at(9))
        late = bd.read_directives('dl:9\n08:00-10:00 > dl:2', now=at(9))
        self.assertEqual(early['dl'], 2)
        self.assertEqual(late['dl'], 2)

    def test_outside_the_window_the_unconditional_value_stands(self):
        d = bd.read_directives('08:00-10:00 > dl:2\ndl:9', now=at(15))
        self.assertEqual(d['dl'], 9)

    def test_comments_are_skipped(self):
        self.assertIsNone(bd.read_directives('#dl:7').get('dl'))


class TestIsDirective(unittest.TestCase):
    def test_recognises_its_own(self):
        self.assertTrue(bd.is_directive('dl:5'))
        self.assertTrue(bd.is_directive('mood:calm'))

    def test_leaves_content_alone(self):
        self.assertFalse(bd.is_directive('auto:library'))
        self.assertFalse(bd.is_directive('meta_radios'))


if __name__ == '__main__':
    unittest.main()
