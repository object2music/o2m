import unittest

from o2m_core.snapwatch import ListenerWatch, connected_clients, snap_output_enabled


class SnapWatchTest(unittest.TestCase):

    def test_output_rule(self):
        self.assertTrue(snap_output_enabled('audioconvert ! filesink location=/tmp/snapfifo'))
        self.assertFalse(snap_output_enabled('alsasink'))
        self.assertFalse(snap_output_enabled(None))

    def test_connected_clients(self):
        status = {'server': {'groups': [
            {'clients': [{'id': 'a', 'connected': True}, {'id': 'b', 'connected': False}]},
            {'clients': [{'id': 'c', 'connected': True}]},
        ]}}
        self.assertEqual(connected_clients(status), {'a', 'c'})
        self.assertEqual(connected_clients(None), set())

    def test_never_a_listener_never_fires(self):
        w = ListenerWatch(grace_s=10)
        self.assertFalse(any(w.observe(0, t) for t in range(0, 100, 3)))

    def test_departure_fires_once_after_grace(self):
        w = ListenerWatch(grace_s=10)
        w.observe(1, 0)
        self.assertFalse(w.observe(0, 3))
        self.assertFalse(w.observe(0, 9))
        self.assertTrue(w.observe(0, 13))
        self.assertFalse(w.observe(0, 30))

    def test_reload_inside_grace_does_not_fire(self):
        w = ListenerWatch(grace_s=10)
        w.observe(1, 0)
        w.observe(0, 3)
        w.observe(1, 6)                  # the page came back
        self.assertFalse(w.observe(0, 9))
        self.assertFalse(w.observe(0, 15))
        self.assertTrue(w.observe(0, 19))

    def test_one_of_two_leaving_does_not_fire(self):
        w = ListenerWatch(grace_s=10)
        w.observe(2, 0)
        self.assertFalse(any(w.observe(1, t) for t in range(3, 60, 3)))

    def test_rearmed_by_next_listener(self):
        w = ListenerWatch(grace_s=10)
        w.observe(1, 0); w.observe(0, 1); self.assertTrue(w.observe(0, 11))
        w.observe(1, 20); w.observe(0, 21); self.assertTrue(w.observe(0, 31))


if __name__ == '__main__':
    unittest.main()
