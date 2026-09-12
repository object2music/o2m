import datetime
import os
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


class TestLocalNow(unittest.TestCase):
    """The feature must mean local hours even where the deployment sets no TZ."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ('TZ', 'O2M_TIMEZONE')}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_falls_back_to_a_real_timezone_when_the_container_sets_none(self):
        os.environ.pop('TZ', None)
        os.environ.pop('O2M_TIMEZONE', None)
        local = bd.local_now()
        utc = datetime.datetime.utcnow()
        # Paris is one or two hours ahead of UTC; the point is that it is NOT UTC.
        delta = round((local - utc).total_seconds() / 3600)
        self.assertIn(delta, (1, 2))

    def test_o2m_timezone_overrides(self):
        os.environ['O2M_TIMEZONE'] = 'UTC'
        delta = round((bd.local_now() - datetime.datetime.utcnow()).total_seconds() / 3600)
        self.assertEqual(delta, 0)

    def test_result_is_naive_so_it_compares_with_plain_datetimes(self):
        self.assertIsNone(bd.local_now().tzinfo)


BLOCK_BOX = """\
#Matin
08:00-10:00 > {
  infos:library
  mood:calm
}
auto:library
18:00-23:00 > meta_radios
"""


class TestBlocks(unittest.TestCase):
    def _payloads(self, data, now):
        return [p for ok, p in bd.iter_lines(data, now) if ok and p]

    def test_inside_the_block_window(self):
        got = self._payloads(BLOCK_BOX, at(9))
        self.assertIn('infos:library', got)
        self.assertIn('mood:calm', got)
        self.assertIn('auto:library', got)          # outside the block, always on
        self.assertNotIn('meta_radios', got)        # its own window, not matching

    def test_outside_the_block_window(self):
        got = self._payloads(BLOCK_BOX, at(12))
        self.assertNotIn('infos:library', got)
        self.assertNotIn('mood:calm', got)
        self.assertIn('auto:library', got)          # the block must not swallow it

    def test_a_block_directive_is_read_only_in_its_window(self):
        self.assertEqual(bd.read_directives(BLOCK_BOX, now=at(9))['energy'],
                         bd.MOOD_NAMES['calm'][0])
        self.assertIsNone(bd.read_directives(BLOCK_BOX, now=at(12))['energy'])

    def test_an_inline_window_inside_a_block_wins_for_that_line(self):
        data = "08:00-10:00 > {\n  20:00-22:00 > meta_radios\n  infos:library\n}\n"
        at9 = self._payloads(data, at(9))
        self.assertIn('infos:library', at9)
        self.assertNotIn('meta_radios', at9)        # its own window says no
        self.assertIn('meta_radios', self._payloads(data, at(21)))

    def test_a_label_does_not_close_a_block(self):
        data = "08:00-10:00 > {\n  #Bulletin\n  infos:library\n}\nauto:library\n"
        self.assertIn('infos:library', self._payloads(data, at(9)))
        self.assertNotIn('infos:library', self._payloads(data, at(15)))

    def test_indentation_is_decoration_only(self):
        """The box editor trims every line; a block must survive that."""
        flat = "08:00-10:00 > {\ninfos:library\nmood:calm\n}\nauto:library\n"
        got = self._payloads(flat, at(9))
        self.assertIn('infos:library', got)
        self.assertNotIn('infos:library', self._payloads(flat, at(15)))

    def test_an_unclosed_block_runs_to_the_end(self):
        data = "08:00-10:00 > {\n  infos:library\n  meta_radios\n"
        self.assertEqual(self._payloads(data, at(9)), ['infos:library', 'meta_radios'])
        self.assertEqual(self._payloads(data, at(15)), [])

    def test_lines_after_the_closing_brace_are_free_again(self):
        data = "08:00-10:00 > {\n  infos:library\n}\nauto:library\nmeta_radios\n"
        self.assertEqual(self._payloads(data, at(15)), ['auto:library', 'meta_radios'])

    def test_the_per_line_form_still_works(self):
        self.assertIn('infos:library',
                      self._payloads('08:00-10:00 > infos:library\n', at(9)))
        self.assertNotIn('infos:library',
                         self._payloads('08:00-10:00 > infos:library\n', at(15)))
