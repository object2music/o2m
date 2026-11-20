"""The last box to arrive decides whether an unfinished item leads the queue."""
import types
import unittest

from o2m_core.o2mtomopidy import O2mToMopidy


def box(uid, data='', option_type='podcast', option_sort='smart'):
    return types.SimpleNamespace(uid=uid, data=data, option_type=option_type, option_sort=option_sort)


class Tracklist:
    def __init__(self, uris):
        self.tl = [types.SimpleNamespace(tlid=i, track=types.SimpleNamespace(uri=u))
                   for i, u in enumerate(uris)]

    def index(self):
        return 0                                   # the first entry is playing

    def get_tl_tracks(self):
        return list(self.tl)

    def move(self, start, end, to):
        self.tl.insert(to, self.tl.pop(start))

    def uris(self):
        return [t.track.uri for t in self.tl]


class TestLeadUnfinished(unittest.TestCase):
    def fixture(self, boxes, queue, unfinished, parents=None):
        """queue: (uri, owning box uid) pairs."""
        o = O2mToMopidy.__new__(O2mToMopidy)
        o.activeboxs = boxes
        o._box_parent = parents or {}
        o.discover_level = 5
        o._track_info = {i: {'box_id': uid} for i, (_, uid) in enumerate(queue)}
        o.mopidyHandler = types.SimpleNamespace(tracklist=Tracklist([u for u, _ in queue]))
        o.get_spotify_uri = lambda u: u
        o.dbHandler = types.SimpleNamespace(
            unfinished_among=lambda uris, dl: [u for u in unfinished if u in uris])
        return o

    def test_a_podcast_box_arriving_last_takes_the_head(self):
        pod, mus = box('p'), box('m', 'auto:library', 'library')
        o = self.fixture([mus, pod], [('now', 'm'), ('t1', 'm'), ('e1', 'p'), ('e2', 'p')], ['e2'])
        o.lead_unfinished([pod])
        self.assertEqual(o.mopidyHandler.tracklist.uris(), ['now', 'e2', 't1', 'e1'])

    def test_a_music_box_arriving_last_leads_nothing(self):
        pod, mus = box('p'), box('m', 'auto:library', 'library')
        o = self.fixture([pod, mus], [('now', 'm'), ('t1', 'm'), ('e1', 'p')], ['e1'])
        o.lead_unfinished([mus])
        self.assertEqual(o.mopidyHandler.tracklist.uris(), ['now', 't1', 'e1'])

    def test_another_active_box_does_not_arrive_with_the_last(self):
        a, b = box('a'), box('b')
        o = self.fixture([a, b], [('now', 'a'), ('e1', 'b'), ('e2', 'a')], ['e2'])
        o.lead_unfinished([b])
        self.assertEqual(o.mopidyHandler.tracklist.uris(), ['now', 'e1', 'e2'])

    def test_an_explicit_order_is_left_alone(self):
        pod = box('p', option_sort='asc')
        o = self.fixture([pod], [('now', 'p'), ('e1', 'p'), ('e2', 'p')], ['e2'])
        o.lead_unfinished([pod])
        self.assertEqual(o.mopidyHandler.tracklist.uris(), ['now', 'e1', 'e2'])

    def test_a_cascade_arrives_whole_even_in_a_cycle(self):
        parent, child = box('c', 'box:p', 'library'), box('p')
        o = self.fixture([parent, child], [('now', 'c'), ('e1', 'p'), ('e2', 'p')], ['e2'],
                         parents={'p': 'c', 'c': 'p'})
        o.lead_unfinished([parent])
        self.assertEqual(o.mopidyHandler.tracklist.uris(), ['now', 'e2', 'e1'])


if __name__ == '__main__':
    unittest.main()
