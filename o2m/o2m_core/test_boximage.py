import unittest

from o2m_core import boximage

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 20
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
WEBP = b'RIFF\x10\x00\x00\x00WEBPVP8 ' + b'\x00' * 20
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


class SniffTest(unittest.TestCase):
    def test_three_raster_formats(self):
        self.assertEqual(boximage.sniff(JPEG), 'image/jpeg')
        self.assertEqual(boximage.sniff(PNG), 'image/png')
        self.assertEqual(boximage.sniff(WEBP), 'image/webp')

    def test_svg_and_other_riff_refused(self):
        self.assertIsNone(boximage.sniff(SVG))
        self.assertIsNone(boximage.sniff(b'RIFF\x10\x00\x00\x00WAVEfmt ' + b'\x00' * 8))
        self.assertIsNone(boximage.sniff(b'\xff\xd8'))


class CheckTest(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(boximage.check(b''), (None, 'empty'))
        self.assertEqual(boximage.check(SVG), (None, 'not_an_image'))
        big = JPEG + b'\x00' * boximage.MAX_BYTES
        self.assertEqual(boximage.check(big), (None, 'too_large'))
        self.assertEqual(boximage.check(WEBP), ('image/webp', None))


class ReferenceTest(unittest.TestCase):
    def test_url_round_trip(self):
        h = boximage.digest(JPEG)
        self.assertTrue(boximage.is_sha1(h))
        self.assertEqual(boximage.referenced([boximage.url_for(h)]), {h})

    def test_absolute_spelling_and_external_urls(self):
        h = 'a' * 40
        urls = [f'https://home.o2m.site/api/box_image/{h}', 'https://example.com/x.jpg', None, '']
        self.assertEqual(boximage.referenced(urls), {h})

    def test_is_sha1_rejects_paths(self):
        self.assertFalse(boximage.is_sha1('../../etc/passwd'))
        self.assertFalse(boximage.is_sha1('A' * 40))


if __name__ == '__main__':
    unittest.main()
