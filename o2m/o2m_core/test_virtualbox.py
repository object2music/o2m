"""The object-activation policy and its truth table.

DB-free on purpose: `virtualbox` imports the Box model only inside `build`, so
everything below runs on a host with no peewee — which is where these tests run.
`build` itself is stubbed out; what is under test is the decision, not peewee.
"""
import unittest

from o2m_core import virtualbox as vb


class _FakeBox:
    """Stands in for an unsaved peewee Box: the two attributes the module reads,
    and equality by uid, which is what peewee's Model gives for a set primary key."""

    def __init__(self, uid='', description='', **kw):
        self.uid = uid
        self.description = description
        for k, v in kw.items():
            setattr(self, k, v)

    def __eq__(self, other):
        return getattr(other, 'uid', None) == self.uid

    __hash__ = None


class _FakeHandler:
    def __init__(self):
        self.activeboxs = []
        self.filled = []
        self.removed = []
        self.activations = 0

    def box_action(self, box):
        self.filled.append(box.uid)

    def box_action_remove(self, box, removed):
        self.removed.append(removed.uid)

    def deactivate_box(self, box):
        # Stands in for O2mToMopidy.deactivate_box, which toggle now calls.
        self.activeboxs.remove(box)
        self.box_action_remove(box, box)

    def note_box_activation(self):
        self.activations += 1


class KindAndUid(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(vb.kind_of('spotify:album:7vEJAtP3KgKSpOHVgwm3Eh'), 'album')
        self.assertEqual(vb.kind_of('spotify:artist:5TkylUv5ysSbNoawmn3PBj'), 'artist')
        self.assertEqual(vb.kind_of('spotify:playlist:abc'), 'playlist')

    def test_not_activable(self):
        # A track is not an object to activate (it is one thing to play), and
        # neither is anything that would resolve to nothing.
        for uri in ('spotify:track:abc', 'spotify:album:', 'podcast+http://x/f',
                    'web:https://example.org', 'http://stream', '', None):
            self.assertIsNone(vb.kind_of(uri), uri)
            self.assertFalse(vb.is_activable(uri), uri)

    def test_uid_round_trip(self):
        uri = 'spotify:album:7vEJAtP3KgKSpOHVgwm3Eh'
        uid = vb.uid_for(uri)
        self.assertTrue(uid.startswith('obj:'))
        self.assertTrue(vb.is_virtual(uid))
        self.assertEqual(vb.uri_of(uid), uri)

    def test_a_real_box_uid_is_not_virtual(self):
        # The namespace is what keeps get_box_by_uid from opening a junk row, so
        # an NFC uid must never be mistaken for one.
        self.assertFalse(vb.is_virtual('04A2B3C4D5'))
        self.assertIsNone(vb.uri_of('04A2B3C4D5'))


class Spec(unittest.TestCase):
    def test_album_plays_in_order(self):
        # Basic path (non-smart) → Mopidy resolves the album whole; 'asc' rather
        # than 'shuffle' because one_box_changed re-shuffles everything else.
        s = vb.spec('spotify:album:X', 'Kind of Blue')
        self.assertEqual(s['option_sort'], 'asc')
        self.assertEqual(s['data'], 'spotify:album:X')
        self.assertEqual(s['description'], 'Kind of Blue')
        self.assertEqual(s['option_type'], 'library')

    def test_artist_goes_through_the_sampler(self):
        self.assertEqual(vb.spec('spotify:artist:X', 'Bashung')['option_sort'], 'smart')

    def test_nameless_falls_back_to_the_uri(self):
        # Never blank: the name is what the tracklist's Source line shows.
        self.assertEqual(vb.spec('spotify:album:X')['description'], 'spotify:album:X')
        self.assertEqual(vb.spec('spotify:album:X', '   ')['description'], 'spotify:album:X')

    def test_unsupported_has_no_spec(self):
        self.assertIsNone(vb.spec('spotify:track:X', 'a song'))


class Toggle(unittest.TestCase):
    def setUp(self):
        self._build = vb.build
        vb.build = lambda uri, name='': _FakeBox(**vb.spec(uri, name))
        self.h = _FakeHandler()

    def tearDown(self):
        vb.build = self._build

    def test_toggle_on_then_off(self):
        uri = 'spotify:album:X'
        r = vb.toggle(self.h, uri, name='Kind of Blue')
        self.assertTrue(r['ok'] and r['active'])
        self.assertEqual(r['action'], 'added')
        self.assertEqual([b.uid for b in self.h.activeboxs], ['obj:' + uri])
        self.assertEqual(self.h.filled, ['obj:' + uri])
        self.assertEqual(self.h.activations, 1)

        r = vb.toggle(self.h, uri)
        self.assertFalse(r['active'])
        self.assertEqual(r['action'], 'removed')
        self.assertEqual(self.h.activeboxs, [])
        self.assertEqual(self.h.removed, ['obj:' + uri])

    def test_add_twice_is_not_a_second_fill(self):
        # Two taps on the same tile, or a stale client: the box path would double
        # the tracks it added.
        uri = 'spotify:artist:X'
        vb.toggle(self.h, uri, mode='add')
        vb.toggle(self.h, uri, mode='add')
        self.assertEqual(len(self.h.activeboxs), 1)
        self.assertEqual(self.h.filled, ['obj:' + uri])

    def test_remove_when_absent_does_nothing(self):
        r = vb.toggle(self.h, 'spotify:album:X', mode='remove')
        self.assertTrue(r['ok'])
        self.assertEqual(r['action'], 'none')
        self.assertEqual(self.h.removed, [])

    def test_unsupported_uri_is_refused_not_activated(self):
        r = vb.toggle(self.h, 'spotify:track:X')
        self.assertFalse(r['ok'])
        self.assertEqual(self.h.activeboxs, [])

    def test_active_objects_ignores_real_boxes(self):
        self.h.activeboxs.append(_FakeBox(uid='04A2B3', description='Morning'))
        vb.toggle(self.h, 'spotify:album:X', name='Kind of Blue')
        rows = vb.active_objects(self.h)
        self.assertEqual(rows, [{'uri': 'spotify:album:X', 'kind': 'album',
                                 'name': 'Kind of Blue'}])

    def test_the_two_halves_partition_activeboxs(self):
        # One call answers for the whole column, so nothing a person put down may
        # fall between the halves, and nothing may be counted twice.
        self.h.activeboxs.append(_FakeBox(uid='04A2B3', description='Morning'))
        vb.toggle(self.h, 'spotify:album:X', name='Kind of Blue')
        objs = {o['uri'] for o in vb.active_objects(self.h)}
        uids = set(vb.active_box_uids(self.h))
        self.assertEqual(uids, {'04A2B3'})
        self.assertEqual(len(objs) + len(uids), len(self.h.activeboxs))

    def test_internal_boxes_are_not_reported_as_lit(self):
        # mopidy_box joins activeboxs by itself as soon as a track plays. It is
        # not pinned and has no tile, so calling it active would be a state the
        # interface cannot show and the user never chose.
        self.h.activeboxs.append(_FakeBox(uid='mopidy_box', description='mopidy_box'))
        self.h.activeboxs.append(_FakeBox(uid='04A2B3', description='Morning'))
        self.assertEqual(vb.active_box_uids(self.h), ['04A2B3'])


if __name__ == '__main__':
    unittest.main()
