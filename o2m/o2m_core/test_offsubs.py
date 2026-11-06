import threading
import types
import unittest

from o2m_core import offsubs
from o2m_core.o2mtomopidy import O2mToMopidy


class Expand(unittest.TestCase):
    def test_a_youtube_playlist_gives_its_videos_either_spelling(self):
        read = lambda kind, key: [f'{kind}/{key}/{i}' for i in range(3)]
        got = offsubs.expand(['yt:playlist:UUabc', 'yt:https://www.youtube.com/playlist?list=PLx'],
                             read, 10)
        self.assertIn('yt_playlist/UUabc/0', got)
        self.assertIn('yt_playlist/PLx/2', got)

    def test_a_long_playlist_leaves_room_for_the_next_line(self):
        read = lambda kind, key: [f'{key}{i}' for i in range(100)]
        got = offsubs.expand(['yt:playlist:A', 'yt:playlist:B'], read, 10)
        self.assertEqual(sum(u.startswith('B') for u in got), 5)

    def reader(self, kind, key):
        return {('album', 'A'): ['t1', 't2'], ('playlist', 'P'): ['t2', 't3']}.get((kind, key))

    def test_a_container_becomes_its_tracks_in_place(self):
        got = offsubs.expand(['t0', 'spotify:album:A', 'podcast+f#g'], self.reader, 10)
        self.assertEqual(got, ['t0', 't1', 't2', 'podcast+f#g'])

    def test_an_item_held_by_two_lines_comes_once(self):
        got = offsubs.expand(['spotify:album:A', 'spotify:user:u:playlist:P'], self.reader, 10)
        self.assertEqual(got, ['t1', 't2', 't3'])

    def test_what_is_not_cached_is_left_out(self):
        self.assertEqual(offsubs.expand(['spotify:artist:X'], self.reader, 10), [])

    def test_the_limit_holds_inside_a_container(self):
        self.assertEqual(offsubs.expand(['spotify:album:A', 't9'], self.reader, 1), ['t1'])


class CaptureLeavesNoTrace(unittest.TestCase):
    """A `box:` line runs a real box_action on the child while resolving."""

    def fill(self, stub):
        with O2mToMopidy.capture_fill(stub):
            stub.activeboxs.append('child')
            stub._cascade_owned.add('child')
            stub._box_parent['child'] = 'parent'
            stub._box_share['child'] = 10
            stub.update_stat_raw('box:child')

    def stub(self):
        logged = []
        return types.SimpleNamespace(
            _box_lock=threading.RLock(), _capture_lock_timeout=1, add_tracks=None,
            mopidyHandler='real', update_stat_raw=logged.append, logged=logged,
            activeboxs=['on'], _cascade_owned=set(), _box_parent={}, _box_share={})

    def test_the_child_is_not_switched_on(self):
        s = self.stub()
        self.fill(s)
        self.assertEqual(s.activeboxs, ['on'])
        self.assertEqual((s._cascade_owned, s._box_parent, s._box_share), (set(), {}, {}))
        self.assertEqual(s.mopidyHandler, 'real')

    def test_no_play_is_logged(self):
        s = self.stub()
        self.fill(s)
        self.assertEqual(s.logged, [])
