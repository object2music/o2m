import os
import tempfile
import unittest
from unittest import mock

from o2m_core import offline


class _Db:
    """The one method `local_file_for` asks of a database."""

    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get_local_uri(self, uri):
        return self._m.get(uri)


class TestFilePresent(unittest.TestCase):
    """`local_uri` is one global column over several disks, so "registered"
    and "here" are two different questions. This is the second one."""

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.mount = self.root.name
        # What Mopidy writes into local_uri, and what this instance sees instead.
        self.media = '/app/Music'
        self._patches = [
            mock.patch.object(offline, 'MUSIC_MOUNT', self.mount),
            mock.patch.dict(os.environ, {'LOCAL_MEDIA_DIR': self.media}),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self.root.cleanup)
        for p in self._patches:
            self.addCleanup(p.stop)

    def _make(self, rel):
        path = os.path.join(self.mount, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(b'0')
        return path

    def test_present_when_the_file_is_there(self):
        self._make('cache/ondemand/song.mp3')
        self.assertTrue(offline.file_present('file:///app/Music/cache/ondemand/song.mp3'))

    def test_absent_when_the_row_outlives_its_file(self):
        """The case that left a device waiting for ever: a row, and no bytes."""
        self.assertFalse(offline.file_present('file:///app/Music/cache/ondemand/gone.mp3'))

    def test_absent_for_another_instance_path(self):
        """A path outside this instance's namespace is not ours to claim."""
        self.assertFalse(offline.file_present('file:///home/pi/Music/cache/x.mp3'))

    def test_percent_encoded_name(self):
        """spotdl registers the path percent-encoded; the file has real spaces."""
        self._make('cache/The Strokes - The Adults Are Talking.mp3')
        self.assertTrue(offline.file_present(
            'file:///app/Music/cache/The%20Strokes%20-%20The%20Adults%20Are%20Talking.mp3'))

    def test_spotify_uri_resolves_through_the_database(self):
        self._make('cache/ondemand/song.mp3')
        db = _Db({'spotify:track:abc': 'file:///app/Music/cache/ondemand/song.mp3'})
        self.assertTrue(offline.file_present('spotify:track:abc', db=db))
        self.assertFalse(offline.file_present('spotify:track:nope', db=db))

    def test_no_mount_trusts_the_database(self):
        """An instance that never added the music mount must keep its behaviour:
        answering 'absent' there would re-queue a whole cache it really holds."""
        with mock.patch.object(offline, 'MUSIC_MOUNT', os.path.join(self.mount, 'nope')):
            self.assertTrue(offline.file_present('file:///app/Music/cache/gone.mp3'))

    def test_a_directory_is_not_a_file(self):
        os.makedirs(os.path.join(self.mount, 'cache', 'adir'))
        self.assertFalse(offline.file_present('file:///app/Music/cache/adir'))

    def test_escaping_the_mount_is_refused(self):
        self.assertFalse(offline.file_present('file:///app/Music/../../etc/passwd'))

    def test_empty_and_unknown_shapes(self):
        self.assertFalse(offline.file_present(''))
        self.assertFalse(offline.file_present('spotify:track:abc'))   # no db to ask
        self.assertFalse(offline.file_present('podcast+https://x/f.xml#g'))


if __name__ == '__main__':
    unittest.main()
