import csv
import io
import json
import unittest

from unittest import mock

from o2m_core import favexport, radiofrance


class MediaLink(unittest.TestCase):
    def test_a_feed_episode_is_its_enclosure_or_nothing(self):
        uri = 'podcast+https://f.example/rss#g1'
        self.assertEqual(favexport.media_link(uri, 'https://cdn.example/a.mp3'),
                         'https://cdn.example/a.mp3')
        self.assertEqual(favexport.media_link(uri), '')

    def test_a_video_opens_on_youtube(self):
        for uri in ('youtube:video:O2h-qA9_VSA', 'yt:video:O2h-qA9_VSA'):
            self.assertEqual(favexport.media_link(uri),
                             'https://www.youtube.com/watch?v=O2h-qA9_VSA')

    def test_a_page_item_is_its_page(self):
        for prefix in ('web:', 'xp:', 'yt:'):
            self.assertEqual(favexport.media_link(prefix + 'https://v.example/x?h=1'),
                             'https://v.example/x?h=1')


class Duration(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(favexport.duration_label(245000), '4:05')
        self.assertEqual(favexport.duration_label(3725000), '1:02:05')
        self.assertEqual(favexport.duration_label(None), '')


class ToCsv(unittest.TestCase):
    def parse(self, text):
        return list(csv.reader(io.StringIO(text.lstrip('﻿')), delimiter=';'))

    def test_opens_with_a_bom_and_a_header(self):
        text = favexport.to_csv([])
        self.assertTrue(text.startswith('﻿Title;Channel;'))

    def test_separators_and_quotes_in_a_title_survive(self):
        rows = self.parse(favexport.to_csv([{'name': 'Été; "vous" dites', 'plays': 0}]))
        self.assertEqual(rows[1][0], 'Été; "vous" dites')
        self.assertEqual(rows[1][6], '0')

    def test_a_title_cannot_be_a_formula(self):
        rows = self.parse(favexport.to_csv([{'name': '=HYPERLINK("http://x")'}]))
        self.assertEqual(rows[1][0], '\'=HYPERLINK("http://x")')


class EpisodePages(unittest.TestCase):
    FEED = ('<link>https://www.radiofrance.fr</link>'
            '<link>https://www.radiofrance.fr/fi/podcasts/old/a-1000001</link>'
            '<link>https://www.radiofrance.fr/fi/podcasts/new/b-1000002</link>'
            '<link>https://www.radiofrance.fr/fi/podcasts/new/c-1000003</link>')

    def setUp(self):
        radiofrance._episode_pages.clear()

    def test_the_most_frequent_show_comes_first(self):
        self.assertEqual(radiofrance.show_pages(self.FEED),
                         ['https://www.radiofrance.fr/fi/podcasts/new',
                          'https://www.radiofrance.fr/fi/podcasts/old'])

    def test_found_on_a_second_show_then_remembered(self):
        def gql(key, query, variables, timeout):
            if variables['url'].endswith('/new'):
                return None
            return {'diffusionsOfShowByUrl': {'edges': [
                {'node': {'url': 'https://x.example/old/ep-5203940'}}]}}
        feed = mock.Mock(text=self.FEED)
        with mock.patch.object(radiofrance.requests, 'get', return_value=feed), \
             mock.patch.object(radiofrance, '_gql', side_effect=gql) as api:
            want = {'https://f.example/rss': {'5203940'}}
            self.assertEqual(radiofrance.episode_pages('k', want),
                             {'5203940': 'https://x.example/old/ep-5203940'})
            calls = api.call_count
            self.assertEqual(radiofrance.episode_pages('k', want),
                             {'5203940': 'https://x.example/old/ep-5203940'})
            self.assertEqual(api.call_count, calls)

    def test_no_key_asks_nothing(self):
        with mock.patch.object(radiofrance.requests, 'get') as get:
            self.assertEqual(radiofrance.episode_pages(None, {'f': {'1'}}), {})
        get.assert_not_called()


class PublicPage(unittest.TestCase):
    def test_a_token_needs_its_secret_and_its_generation(self):
        token = favexport.share_token('s', 3)
        self.assertGreaterEqual(len(token), 64)
        self.assertTrue(favexport.share_token_ok(token, 's', 3))
        self.assertFalse(favexport.share_token_ok(token, 's', 4))
        self.assertFalse(favexport.share_token_ok(token, 'other', 3))

    def test_nothing_shared_opens_with_no_token(self):
        self.assertFalse(favexport.share_token_ok(favexport.share_token('s', None), 's', None))
        self.assertFalse(favexport.share_token_ok(favexport.share_token('s', 0), 's', 0))

    def test_an_episode_says_what_it_is_and_where_to_hear_it(self):
        got = favexport.public_list([{'name': 'n', 'channel': 'c', 'type': 'podcast',
                                      'published': '2026-10-01', 'duration': '4:05',
                                      'link': 'https://a.example/x'}])
        self.assertEqual(got, {'count': 1, 'episodes': [
            {'title': 'n', 'channel': 'c', 'type': 'podcast', 'published': '2026-10-01',
             'duration': '4:05', 'link': 'https://a.example/x'}]})

    def test_what_is_not_known_is_null(self):
        self.assertIsNone(favexport.public_list([{'name': 'n', 'link': ''}])['episodes'][0]['link'])

    def test_the_listening_stays_private(self):
        page = json.dumps(favexport.public_list([
            {'name': 'n', 'uri': 'podcast+https://secret.example/rss#g',
             'plays': 4321, 'liked': '2026-11-06 08:00'}]))
        for private in ('secret.example', '4321', '2026-11-06'):
            self.assertNotIn(private, page)


if __name__ == '__main__':
    unittest.main()
