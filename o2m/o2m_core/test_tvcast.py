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
        self.box = SimpleNamespace(uid='04AB', data=f'tv:{URL}')

    def test_add_then_remove(self):
        paused = []
        with mock.patch.object(tv, 'play') as play, mock.patch.object(tv, 'stop') as stop:
            self.assertEqual(tv.box_action(self.box, 'add', _config(), lambda: paused.append(1)), 'TV added')
            play.assert_called_once_with('192.168.1.137', 'rwalpfPkQvk', 'PLM0sCcbvupIa3uPDa8lxDo6KgMnqcjajr')
            self.assertEqual(paused, [1])
            self.assertEqual(tv.box_action(self.box, 'add', _config()), 'No action')
            self.assertEqual(tv.box_action(self.box, 'remove', _config()), 'TV removed')
            stop.assert_called_once_with('192.168.1.137')
            self.assertEqual(tv.box_action(self.box, 'remove', _config()), 'No action')

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


if __name__ == '__main__':
    unittest.main()
