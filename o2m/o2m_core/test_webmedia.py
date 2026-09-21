"""Tests for the 'web:<url>' page reader.

The fixtures are cut from the three pages the feature was written against, and
they are three different shapes on purpose — an <iframe> embed, plain <a> links,
and a page that refuses to be read at all. Those three are the whole problem.

No network: `_parse` and `classify` are pure, and they are where the routing
rule lives, which is what silently drifts.
"""

import unittest

from o2m_core import webmedia as wm


# enquetedesens-lefilm.com — the film's own site: one Vimeo player iframe.
# The '&circ;' is verbatim from the page, and is the reason a page label is
# only ever provisional (the extractor's own title replaces it).
PAGE_IFRAME = '''<html><head><title>Visionnez En Qu&ecirc;te de Sens</title></head><body>
<iframe src="https://player.vimeo.com/video/211902079?h=c0b9892ec8&amp;badge=0"
        title="En Qu&circ;te De Sens | Le Film | Multisubs" allowfullscreen></iframe>
<a href="http://www.youtube.com/channel/UCiMKsI5wafDMyQiQNJtslMQ">Notre cha&icirc;ne</a>
<script src="https://player.vimeo.com/api/player.js"></script></body></html>'''

# innovation-transformations.ecologie.gouv.fr — no embed at all: the replays are
# ordinary links, and what names them is the `title` attribute.
PAGE_LINKS = '''<html><head><title>[Replay] Cycle 8 : Syst&eacute;mique</title></head><body>
<ul class="fr-btns-group">
<li><a href="https://www.dailymotion.com/video/xa8g6ck" class="fr-btn" target="_blank"
       title="Lire le replay &quot;Probl&egrave;me syst&eacute;mique&quot; - nouvelle fen&ecirc;tre"
    >Lire le replay</a></li>
<li><a href="https://dai.ly/xamdswq" title="Lire le replay strat&eacute;gie">Lire</a></li>
<li><a href="/boite-a-outils/autre-page">Une autre fiche</a></li>
<li><a href="https://www.linkedin.com/company/whatever">Suivez-nous</a></li>
</ul></body></html>'''

# uved.fr answers this to every client, with HTTP 200.
PAGE_CHALLENGE = '<html><head><title>CrowdSec Challenge</title></head><body></body></html>'

PAGE_MIXED = '''<html><head><title>Une page</title>
<link rel="alternate" type="application/rss+xml" title="Le flux" href="/feed.xml">
<meta property="og:audio" content="https://cdn.example.org/emission.mp3"></head>
<body><audio><source src="/local/extrait.ogg"></audio>
<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe></body></html>'''


class TestClassify(unittest.TestCase):
    """The routing rule: 'web:' is worn only by media no existing scheme carries."""

    def test_youtube_becomes_a_mopidy_youtube_uri(self):
        for url in ('https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                    'https://youtu.be/dQw4w9WgXcQ',
                    'https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0',
                    'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'):
            self.assertEqual(wm.classify(url), 'yt:video:dQw4w9WgXcQ', url)

    def test_direct_audio_file_stays_itself(self):
        url = 'https://cdn.example.org/ep/42.mp3'
        self.assertEqual(wm.classify(url), url)

    def test_platform_without_a_backend_wears_web(self):
        for url in ('https://www.dailymotion.com/video/xa8g6ck',
                    'https://player.vimeo.com/video/211902079',
                    'https://soundcloud.com/user/track'):
            self.assertEqual(wm.classify(url), 'web:' + url, url)

    def test_ordinary_links_are_not_media(self):
        for url in ('https://www.linkedin.com/company/whatever',
                    'https://example.org/a-propos',
                    'mailto:x@example.org', ''):
            self.assertEqual(wm.classify(url), '', url)

    def test_a_subdomain_of_a_platform_counts_but_a_lookalike_does_not(self):
        self.assertTrue(wm.classify('https://player.vimeo.com/video/1').startswith('web:'))
        self.assertEqual(wm.classify('https://notvimeo.com/video/1'), '')


class TestCanonicalUrl(unittest.TestCase):
    """One spelling per media: the uri is what carries the history."""

    def test_the_shortener_and_the_long_form_are_one_uri(self):
        self.assertEqual(wm.classify('https://dai.ly/xamdswq'),
                         wm.classify('https://www.dailymotion.com/video/xamdswq'))

    def test_player_chrome_and_campaign_tracking_are_dropped(self):
        self.assertEqual(
            wm.classify('https://player.vimeo.com/video/1?badge=0&autopause=0'
                        '&player_id=0&app_id=58479&utm_source=news'),
            'web:https://player.vimeo.com/video/1')

    def test_an_unlisted_hash_survives(self):
        # Vimeo's 'h=' is not decoration: without it the video does not exist.
        self.assertEqual(wm.classify('https://player.vimeo.com/video/1?h=c0b9892ec8&badge=0'),
                         'web:https://player.vimeo.com/video/1?h=c0b9892ec8')

    def test_an_unknown_parameter_is_kept(self):
        # A denylist, never an allowlist: an unrecognised parameter might be
        # load-bearing, and dropping it would silently change what plays.
        self.assertEqual(wm.classify('https://soundcloud.com/u/t?si=abc&utm_medium=x'),
                         'web:https://soundcloud.com/u/t?si=abc')

    def test_a_uri_too_long_to_store_is_not_offered(self):
        # Rather than let it blow up on insert inside a box fill.
        long_url = 'https://soundcloud.com/u/' + 'x' * 300
        self.assertEqual(wm.classify(long_url), '')

    def test_a_trailing_slash_is_not_a_different_video(self):
        self.assertEqual(wm.classify('https://www.dailymotion.com/video/xa8g6ck/'),
                         wm.classify('https://www.dailymotion.com/video/xa8g6ck'))


class TestParse(unittest.TestCase):

    def test_iframe_embed_is_found_and_labelled(self):
        out = wm._parse('https://enquetedesens-lefilm.com/index.html', PAGE_IFRAME, 12)
        uris = [i['uri'] for i in out['items']]
        # '&badge=0' is player chrome and is normalised away; 'h=' is the
        # unlisted hash and must survive.
        self.assertIn('web:https://player.vimeo.com/video/211902079?h=c0b9892ec8', uris)
        self.assertEqual(out['reason'], '')
        # A channel link is not an episode: there is no video id in it.
        self.assertNotIn('yt:video:', ' '.join(uris))

    def test_the_embedding_page_is_remembered_as_the_referer(self):
        page = 'https://enquetedesens-lefilm.com/index.html'
        out = wm._parse(page, PAGE_IFRAME, 12)
        vimeo = next(i['uri'] for i in out['items'] if 'vimeo' in i['uri'])
        # Without this an embed-only Vimeo is refused outright.
        self.assertEqual(wm.origin_of(vimeo), page)

    def test_plain_links_are_found_and_noise_is_not(self):
        out = wm._parse('https://www.innovation-transformations.ecologie.gouv.fr/x',
                        PAGE_LINKS, 12)
        uris = [i['uri'] for i in out['items']]
        # The page spells the second one with the shortener; both land on the
        # same canonical uri they would have had from the long form.
        self.assertEqual(uris, ['web:https://www.dailymotion.com/video/xa8g6ck',
                                'web:https://www.dailymotion.com/video/xamdswq'])
        self.assertIn('Probl', out['items'][0]['name'])

    def test_relative_urls_are_resolved_against_the_page(self):
        out = wm._parse('https://example.org/emissions/une', PAGE_MIXED, 12)
        uris = [i['uri'] for i in out['items']]
        self.assertIn('https://example.org/local/extrait.ogg', uris)
        self.assertIn('podcast+https://example.org/feed.xml', uris)

    def test_each_kind_routes_to_its_own_scheme(self):
        out = wm._parse('https://example.org/emissions/une', PAGE_MIXED, 12)
        kinds = {i['kind'] for i in out['items']}
        self.assertEqual(kinds, {'yt', 'stream', 'feed'})
        # Nothing here needs 'web:' — every item has a home already.
        self.assertFalse([i for i in out['items'] if i['kind'] == 'web'])

    def test_the_same_media_twice_on_a_page_is_one_item(self):
        doubled = PAGE_LINKS.replace('</ul>',
                                     '<a href="https://www.dailymotion.com/video/xa8g6ck">encore</a></ul>')
        out = wm._parse('https://example.org/x', doubled, 12)
        self.assertEqual(len([i for i in out['items'] if 'xa8g6ck' in i['uri']]), 1)

    def test_limit_is_honoured(self):
        self.assertLessEqual(len(wm._parse('https://example.org/x', PAGE_LINKS, 1)['items']), 1)


class TestRefusal(unittest.TestCase):
    """A refusal and an empty page are different answers and must not collapse."""

    def test_a_challenge_page_is_recognised(self):
        self.assertTrue(wm._CHALLENGE_RE.search(PAGE_CHALLENGE))
        for title in ('Just a moment...', 'Attention Required! | Cloudflare'):
            self.assertTrue(wm._CHALLENGE_RE.search(f'<title>{title}</title>'), title)

    def test_a_page_with_no_media_is_not_a_refusal(self):
        out = wm._parse('https://example.org/x', '<html><title>Rien</title></html>', 12)
        self.assertEqual(out['items'], [])
        self.assertEqual(out['reason'], '')   # read fine — it simply holds nothing


class TestStreamCache(unittest.TestCase):
    """The two caches age differently because what they hold does."""

    def setUp(self):
        wm._cache.clear()
        # _ORIGIN is module-global and every classify() writes to it, so a page
        # parsed by another test would silently hand this one a Referer — and
        # a Referer is exactly what changes the number of attempts here.
        wm._ORIGIN.clear()

    def tearDown(self):
        wm._cache.clear()
        wm._ORIGIN.clear()

    def test_a_refused_extraction_is_remembered_briefly(self):
        import time
        calls = []

        class Boom:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False):
                calls.append(url)
                raise RuntimeError('No video formats found!')

        import sys, types
        fake = types.ModuleType('yt_dlp'); fake.YoutubeDL = Boom
        sys.modules['yt_dlp'] = fake
        try:
            uri = 'web:https://www.dailymotion.com/video/xa8g6ck'
            self.assertIsNone(wm.resolve_stream(uri))
            self.assertIsNone(wm.resolve_stream(uri))
            # Asked once. A platform that is already throttling us must not be
            # re-asked on every box fill.
            self.assertEqual(len(calls), 1)
            # ...and it is forgotten soon enough to come back on its own.
            key = next(iter(wm._cache))
            wm._cache[key] = (time.time() - wm._TTL_FAILURE - 1, None)
            self.assertIsNone(wm.resolve_stream(uri))
            self.assertEqual(len(calls), 2)
        finally:
            del sys.modules['yt_dlp']

    def test_the_referer_is_a_second_attempt_not_the_first(self):
        """Vimeo requires it; Dailymotion refuses it. Both measured."""
        import sys, types
        seen = []

        class Picky:
            def __init__(self, *a, **k): self.ref = (k.get('params') or {}).get('_r')
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False):
                seen.append(self.ref)
                if self.ref:      # a Dailymotion-shaped refusal
                    raise RuntimeError('No video formats found!')
                return {'url': 'https://cdn/ok', 'title': 'T', 'duration': 60}

        def factory(opts):
            inst = Picky(params={'_r': (opts.get('http_headers') or {}).get('Referer')})
            return inst

        fake = types.ModuleType('yt_dlp'); fake.YoutubeDL = factory
        sys.modules['yt_dlp'] = fake
        try:
            out = wm.resolve_stream('web:https://www.dailymotion.com/video/x',
                                    referer='https://example.org/page')
            self.assertIsNotNone(out)
            # Asked plainly, and never needed the page at all.
            self.assertEqual(seen, [None])
        finally:
            del sys.modules['yt_dlp']

    def test_the_referer_is_used_when_the_plain_attempt_fails(self):
        import sys, types
        seen = []

        class EmbedOnly:
            def __init__(self, ref): self.ref = ref
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False):
                seen.append(self.ref)
                if not self.ref:   # a Vimeo-shaped refusal
                    raise RuntimeError('Cannot download embed-only video without embedding URL')
                return {'url': 'https://cdn/ok', 'title': 'Film', 'duration': 5273}

        fake = types.ModuleType('yt_dlp')
        fake.YoutubeDL = lambda opts: EmbedOnly((opts.get('http_headers') or {}).get('Referer'))
        sys.modules['yt_dlp'] = fake
        try:
            out = wm.resolve_stream('web:https://player.vimeo.com/video/1',
                                    referer='https://enquetedesens-lefilm.com/index.html')
            self.assertEqual(out['name'], 'Film')
            self.assertEqual(out['length'], 5273000)
            self.assertEqual(seen, [None, 'https://enquetedesens-lefilm.com/index.html'])
        finally:
            del sys.modules['yt_dlp']

    def test_a_url_near_its_own_expiry_is_not_served(self):
        import time
        uri = 'web:https://vimeo.com/1'
        key = 'web:stream:https://vimeo.com/1'
        entry = {'url': 'https://cdn/x', 'name': 'n', 'length': 1,
                 'expires_at': time.time() + wm._EXPIRY_MARGIN - 60}
        wm._cache[key] = (time.time(), entry)
        # Inside the margin: the cached url would very likely die mid-track, so
        # it is re-resolved rather than handed out.
        import sys, types
        fake = types.ModuleType('yt_dlp')
        class Nope:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False): return None
        fake.YoutubeDL = Nope
        sys.modules['yt_dlp'] = fake
        try:
            self.assertIsNone(wm.resolve_stream(uri))
        finally:
            del sys.modules['yt_dlp']


class TestUri(unittest.TestCase):

    def test_prefix_round_trips(self):
        url = 'https://www.dailymotion.com/video/xa8g6ck'
        self.assertEqual(wm.media_url(wm.as_uri(url)), url)
        self.assertEqual(wm.media_url(url), url)          # idempotent on a bare url
        self.assertTrue(wm.is_web_uri(wm.as_uri(url)))
        self.assertFalse(wm.is_web_uri(url))

    def test_a_media_url_pasted_directly_needs_no_page_read(self):
        out = wm.find_media('https://www.dailymotion.com/video/xa8g6ck')
        self.assertEqual([i['uri'] for i in out['items']],
                         ['web:https://www.dailymotion.com/video/xa8g6ck'])

    def test_expiry_is_read_out_of_a_signed_url(self):
        import time
        soon = int(time.time()) + 3600
        self.assertEqual(wm._expiry_of(f'https://skyfire.vimeocdn.com/{soon}-0x0a87/f.mp4'), soon)
        # A past or absurd timestamp is not an expiry, and neither is a video id.
        self.assertIsNone(wm._expiry_of('https://vod3.cf.dmcdn.net/sec2(abc)/video/1234567890x.m3u8'))
        self.assertIsNone(wm._expiry_of('https://example.org/none'))


if __name__ == '__main__':
    unittest.main()


class TestPublishedDay(unittest.TestCase):
    """The date the details panel shows. Extractors disagree about which field
    they fill, and the three cases below are the three that were measured:
    Dailymotion answers `upload_date` AND a `timestamp`, Vimeo's on-demand
    extractor answers `upload_date` alone, and Vimeo's embed extractor answers
    nothing at all."""

    def test_upload_date_is_reshaped_to_the_stored_form(self):
        self.assertEqual(wm._published_day({'upload_date': '20260507'}), '2026-05-07')

    def test_a_timestamp_answers_when_no_date_field_does(self):
        # 1778168916 is the Dailymotion replay's own timestamp.
        self.assertEqual(wm._published_day({'timestamp': 1778168916}), '2026-05-07')

    def test_a_date_field_wins_over_a_timestamp(self):
        # Both are present on Dailymotion; the explicit date is the publisher's
        # own, the timestamp only has to agree with it.
        self.assertEqual(
            wm._published_day({'upload_date': '20260507', 'timestamp': 1}), '2026-05-07')

    def test_no_date_stays_empty_rather_than_invented(self):
        # Vimeo's embed extractor. A wrong date is worse than a blank one in a
        # panel whose job is to say what is KNOWN about a track.
        self.assertIsNone(wm._published_day({'title': 'En Quête De Sens'}))

    def test_a_malformed_date_is_refused_not_reshaped(self):
        for bad in ('2026-05-07', '2026', 'soon', '', None):
            self.assertIsNone(wm._published_day({'upload_date': bad}), bad)


class TestLegacyPrefix(unittest.TestCase):
    """'xp:' was the prefix for a few days before the rename to 'web:'. It is
    still READ — a Track uri is a primary key and a box line is something a
    person typed — and never written again."""

    def test_the_old_prefix_is_still_recognised(self):
        self.assertTrue(wm.is_web_uri('xp:https://vimeo.com/1'))
        self.assertTrue(wm.is_web_uri('web:https://vimeo.com/1'))
        self.assertFalse(wm.is_web_uri('https://vimeo.com/1'))

    def test_the_url_is_read_out_of_either_spelling(self):
        for uri in ('xp:https://vimeo.com/1', 'web:https://vimeo.com/1'):
            self.assertEqual(wm.media_url(uri), 'https://vimeo.com/1', uri)

    def test_only_the_new_prefix_is_ever_written(self):
        self.assertTrue(wm.as_uri('https://vimeo.com/1').startswith('web:'))
        self.assertEqual(wm.classify('https://www.dailymotion.com/video/xa8g6ck'),
                         'web:https://www.dailymotion.com/video/xa8g6ck')
