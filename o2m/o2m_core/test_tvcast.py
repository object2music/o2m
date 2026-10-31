import configparser
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

from o2m_core import tvcast as tv

URL = 'https://www.youtube.com/watch?v=rwalpfPkQvk&list=PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr'


class TestParseYoutube(unittest.TestCase):
    def test_watch_with_playlist(self):
        self.assertEqual(tv.parse_youtube(URL),
                         ('rwalpfPkQvk', 'PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr'))

    def test_short_link_and_bare_id(self):
        self.assertEqual(tv.parse_youtube('https://youtu.be/rwalpfPkQvk?t=3'), ('rwalpfPkQvk', None))
        self.assertEqual(tv.parse_youtube('rwalpfPkQvk'), ('rwalpfPkQvk', None))

    def test_playlist_alone(self):
        self.assertEqual(tv.parse_youtube('https://www.youtube.com/playlist?list=UUabc'), (None, 'UUabc'))
        self.assertEqual(tv.parse_youtube('yt:playlist:UUabc'), (None, 'UUabc'))

    def test_shorts_and_mopidy_spelling(self):
        self.assertEqual(tv.parse_youtube('https://m.youtube.com/shorts/rwalpfPkQvk'), ('rwalpfPkQvk', None))
        self.assertEqual(tv.parse_youtube('yt:video:rwalpfPkQvk'), ('rwalpfPkQvk', None))

    def test_not_youtube(self):
        for ref in ('', 'https://vimeo.com/123', 'https://www.youtube.com/@channel',
                    'https://www.youtube.com/watch?v=short'):
            self.assertIsNone(tv.parse_youtube(ref), ref)


class TestTvBox(unittest.TestCase):
    def test_only_tv_lines_with_labels_and_directives(self):
        self.assertTrue(tv.is_tv_box(f'# Octonauts\ntv:{URL}\ndl:3'))

    def test_mixed_box_is_not_a_tv_box(self):
        self.assertFalse(tv.is_tv_box(f'tv:{URL}\nauto:library'))
        self.assertFalse(tv.is_tv_box('# only a label'))
        self.assertFalse(tv.is_tv_box(''))

    def test_shut_window_is_still_a_tv_box(self):
        data = f'08:00-19:00 > tv:{URL}'
        self.assertTrue(tv.is_tv_box(data))
        self.assertEqual(tv.tv_refs(data, datetime.datetime(2026, 10, 31, 20)), [])
        self.assertEqual(tv.tv_refs(data, datetime.datetime(2026, 10, 31, 10)), [URL])

    def test_block_window(self):
        data = f'08:00-19:00 > {{\ntv:{URL}\n}}'
        self.assertTrue(tv.is_tv_box(data))
        self.assertEqual(tv.tv_refs(data, datetime.datetime(2026, 10, 31, 20)), [])


def _config(host='192.168.1.137', pause='true'):
    c = configparser.ConfigParser()
    c['tv'] = {'cast_host': host, 'pause_music': pause}
    return c


@mock.patch.object(tv, 'pychromecast', object())
class TestBoxAction(unittest.TestCase):
    def setUp(self):
        tv._active.clear()
        tv._last.clear()
        tv._watcher = None
        self.box = SimpleNamespace(uid='04AB', data=f'tv:{URL}')
        # No network: the playlist is unreadable, so the named video starts, and
        # the watcher is a no-op.
        for name, kw in (('playlist_entries', {'return_value': None}),
                         ('_Watcher', {})):
            p = mock.patch.object(tv, name, **kw)
            p.start()
            self.addCleanup(p.stop)

    def test_add_then_remove(self):
        paused = []
        with mock.patch.object(tv, 'play') as play, mock.patch.object(tv, 'stop') as stop:
            self.assertEqual(tv.box_action(self.box, 'add', _config(), lambda: paused.append(1)), 'TV added')
            play.assert_called_once_with('192.168.1.137', 'rwalpfPkQvk', 'PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr')
            self.assertEqual(paused, [1])
            # Put down again: cast again — the TV may have been closed meanwhile.
            self.assertEqual(tv.box_action(self.box, 'add', _config()), 'TV added')
            self.assertEqual(play.call_count, 2)
            self.assertEqual(tv.box_action(self.box, 'remove', _config()), 'TV removed')
            stop.assert_called_once()
            # Not marked on (e.g. after an o2m restart): YouTube is still closed.
            stop.return_value = True
            self.assertEqual(tv.box_action(self.box, 'remove', _config()), 'TV removed')
            stop.return_value = False
            self.assertEqual(tv.box_action(self.box, 'remove', _config()), 'No action')
            self.assertEqual(stop.call_count, 3)
            stop.assert_called_with('192.168.1.137', None)

    def test_toggle(self):
        with mock.patch.object(tv, 'play'), mock.patch.object(tv, 'stop') as stop:
            self.assertEqual(tv.box_action(self.box, 'toogle', _config()), 'TV added')
            self.assertEqual(tv.box_action(self.box, 'toogle', _config()), 'TV removed')
            stop.assert_called_once()

    def test_music_left_alone_when_asked(self):
        paused = []
        with mock.patch.object(tv, 'play'):
            tv.box_action(self.box, 'add', _config(pause='false'), lambda: paused.append(1))
        self.assertEqual(paused, [])

    def test_failed_cast_leaves_the_box_off(self):
        with mock.patch.object(tv, 'play', side_effect=RuntimeError('unreachable')):
            self.assertEqual(tv.box_action(self.box, 'add', _config()), 'TV: unreachable')
        self.assertFalse(tv.is_active('04AB'))

    def test_no_host_and_no_package(self):
        self.assertIn('cast_host', tv.box_action(self.box, 'add', _config(host='')))
        with mock.patch.object(tv, 'pychromecast', None):
            self.assertIn('not installed', tv.box_action(self.box, 'add', _config()))


class TestPicking(unittest.TestCase):
    def setUp(self):
        tv._last.clear()

    def test_never_the_same_line_twice_in_a_row(self):
        refs = [('a', ('v1', None)), ('b', ('v2', None))]
        seen = []
        for _ in range(10):
            r = tv.pick_ref('U', refs)
            tv._last['U'] = r[0]
            seen.append(r[0])
        self.assertTrue(all(x != y for x, y in zip(seen, seen[1:])), seen)

    def test_a_single_line_is_still_played(self):
        tv._last['U'] = 'a'
        self.assertEqual(tv.pick_ref('U', [('a', ('v1', None))])[0], 'a')

    def test_start_drawn_from_a_readable_playlist(self):
        with mock.patch.object(tv, 'playlist_entries', return_value=['x1', 'x2', 'x3']):
            rng = mock.Mock(choice=lambda ids: ids[-1])
            self.assertEqual(tv.pick_start('v', 'PL', rng), 'x3')

    def test_start_never_repeats_the_last_one(self):
        tv._last_start.clear()
        with mock.patch.object(tv, 'playlist_entries', return_value=['x1', 'x2']):
            starts = [tv.pick_start(None, 'PL') for _ in range(8)]
        self.assertTrue(all(a != b for a, b in zip(starts, starts[1:])), starts)

    def test_unavailable_entries_are_never_drawn(self):
        # Flat entries as yt_dlp returns them for a playlist holding dead videos.
        self.assertTrue(tv.playable_entry({'id': 'YY3MvhTNO38', 'title': "L'Etoile Mysterieuse"}))
        for e in ({'id': 'ebGSyc0VBBU', 'title': None}, {'id': 'x', 'title': ''},
                  {'id': 'x', 'title': '[Private video]'}, {'title': 'no id'}, None):
            self.assertFalse(tv.playable_entry(e), e)

    def test_unreadable_playlist_starts_at_the_named_video(self):
        with mock.patch.object(tv, 'playlist_entries', return_value=None):
            self.assertEqual(tv.pick_start('v', 'PL'), 'v')
            with self.assertRaises(RuntimeError):
                tv.pick_start(None, 'PL')


class TestPlayRecord(unittest.TestCase):
    def test_a_viewing_is_recorded_under_its_own_prefix(self):
        self.assertEqual(tv.play_record('abc', 'Tintin', 1500.0, 600.5),
                         ('tv:yt:abc', 'Tintin', 1500000, 600500))

    def test_a_zap_is_not(self):
        self.assertIsNone(tv.play_record('abc', 'Tintin', 1500.0, 5))
        # 45 s of an hour: under update_stat_track's 5% artefact threshold.
        self.assertIsNone(tv.play_record('abc', 'Octonauts', 3600.0, 45))
        self.assertIsNone(tv.play_record(None, None, None, 100))

    def test_a_short_video_seen_to_the_end_is(self):
        self.assertIsNotNone(tv.play_record('abc', 'jingle', 15.0, 14.5))

    def test_the_prefix_stays_out_of_the_yt_pools(self):
        # The pools match 'yt:%' / 'youtube:%' by PREFIX (dbhandler).
        self.assertFalse(tv.URI_PREFIX.startswith(('yt:', 'youtube:', 'podcast+', 'web:')))


class TestWatcherLimit(unittest.TestCase):
    def _watcher(self, limit, start=None):
        st = SimpleNamespace(content_id=None, title='t', duration=600.0,
                             adjusted_current_time=300.0, current_time=300.0)
        cast = SimpleNamespace(media_controller=SimpleNamespace(status=st))
        recs = []
        return tv._Watcher(cast, lambda *r: recs.append(r), limit, start), st, recs

    def test_the_video_past_the_limit_stops_it(self):
        w, st, recs = self._watcher(1)
        st.content_id = 'v1'
        self.assertIsNone(w._sample())
        st.content_id = 'v2'                    # playlist goes on / autoplay
        self.assertEqual(w._sample(), 'limit')
        self.assertEqual([r[0] for r in recs], ['tv:yt:v1'])   # v1 still recorded

    def test_the_previous_video_is_not_counted(self):
        w, st, recs = self._watcher(1, start='v1')
        st.content_id = 'old'                   # still reported just after the cast
        self.assertIsNone(w._sample())
        st.content_id = 'v1'
        self.assertIsNone(w._sample())
        st.content_id = 'v2'
        self.assertEqual(w._sample(), 'limit')
        self.assertEqual([r[0] for r in recs], ['tv:yt:v1'])

    def test_no_limit(self):
        w, st, _ = self._watcher(None)
        for v in ('v1', 'v2', 'v3'):
            st.content_id = v
            self.assertIsNone(w._sample())


if __name__ == '__main__':
    unittest.main()
