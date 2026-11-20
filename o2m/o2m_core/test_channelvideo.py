"""A YouTube playlist's settings reach the videos it holds, beside their channel's."""
import unittest

from peewee import SqliteDatabase

from o2m_core.dbhandler import DatabaseHandler
from o2m_core.o2mmodels import ChannelVideo, PodcastChannel, Track

PL = 'yt:playlist:PLabc'
UU = 'yt:playlist:UU' + 'x' * 22
VIDEO = 'yt:video:vid00000001'


class TestPlaylistSettings(unittest.TestCase):
    def setUp(self):
        self.mem = SqliteDatabase(':memory:')
        self.ctx = self.mem.bind_ctx([ChannelVideo, PodcastChannel, Track])
        self.ctx.__enter__()
        self.mem.create_tables([ChannelVideo, PodcastChannel, Track])
        self.db = DatabaseHandler.__new__(DatabaseHandler)
        # The real one writes MySQL's upsert, which SQLite refuses without a target.
        self.db.upsert_podcast_channel = lambda cid, kind, title='', url='': \
            PodcastChannel.create(id=cid, kind=kind, title=title, url=url)
        self.db.register_yt_channel(UU, 'Uploader')
        Track.insert(uri=VIDEO, channel_id=UU).execute()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.mem.close()

    def test_a_line_with_no_row_gets_one_when_set(self):
        self.assertEqual(self.db.set_channel_setting(PL, 'volume_boost_pct', 30, 'Mine'), [PL])
        self.assertEqual(self.db.get_channel_setting(PL, 'volume_boost_pct'), 30)

    def test_a_setting_reaches_a_linked_video_only(self):
        self.db.set_channel_setting(PL, 'ad_skip_s', 20)
        self.assertEqual(self.db.get_channel_setting(VIDEO, 'ad_skip_s'), 0)
        self.db.link_channel_videos(PL, [VIDEO])
        self.assertEqual(self.db.get_channel_setting(VIDEO, 'ad_skip_s'), 20)

    def test_the_channel_still_counts_and_the_largest_wins(self):
        self.db.set_channel_setting(PL, 'ad_skip_s', 20)
        self.db.set_channel_setting(UU, 'ad_skip_s', 45)
        self.db.link_channel_videos(PL, [VIDEO])
        self.assertEqual(self.db.get_channel_setting(VIDEO, 'ad_skip_s'), 45)

    def test_linking_twice_is_harmless(self):
        self.db.register_yt_channel(PL)
        self.db.link_channel_videos(PL, [VIDEO, ''])
        self.db.link_channel_videos(PL, [VIDEO])
        self.assertEqual(ChannelVideo.select().count(), 1)


if __name__ == '__main__':
    unittest.main()
