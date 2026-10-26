"""Tests for o2m_core.dbstate — is the database answering, and how often we ask.

Run from o2m/:  python3 -m unittest o2m_core.test_dbstate
"""

import unittest

from o2m_core.dbstate import DbState


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, s):
        self.t += s


class Probe:
    """A database that can be unplugged, and that counts how often it is asked."""

    def __init__(self, up=True):
        self.up = up
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if not self.up:
            raise RuntimeError("Can't connect to MySQL server (timed out)")


class TestTheVerdictIsCached(unittest.TestCase):

    def setUp(self):
        self.clock = Clock()
        self.probe = Probe()
        self.s = DbState(self.probe, clock=self.clock, retry_s=30)

    def test_a_working_database_is_probed_once_and_then_trusted(self):
        """The whole point: no instance that HAS its database pays for this."""
        for _ in range(50):
            self.assertTrue(self.s.available())
        self.assertEqual(self.probe.calls, 1)

    def test_unknown_is_probed_at_once(self):
        """A process must not report a degraded mode it never verified."""
        self.assertFalse(self.s.degraded, 'unknown is not degraded')
        self.probe.up = False
        self.assertFalse(self.s.available())
        self.assertEqual(self.probe.calls, 1)
        self.assertTrue(self.s.degraded)

    def test_a_dead_database_is_tried_once_a_cadence_not_once_a_call(self):
        """A page polling every second must not pay a connect timeout a second.
        Measured on pi1: a blackholed address costs the whole timeout."""
        self.probe.up = False
        self.assertFalse(self.s.available())
        for _ in range(100):
            self.clock.tick(0.2)
            self.assertFalse(self.s.available())
        self.assertEqual(self.probe.calls, 1, 'one probe for 20s of asking')
        self.clock.tick(30)
        self.assertFalse(self.s.available())
        self.assertEqual(self.probe.calls, 2)

    def test_the_link_coming_back_is_noticed(self):
        self.probe.up = False
        self.assertFalse(self.s.available())
        self.probe.up = True
        self.assertFalse(self.s.available(), 'still inside the cadence')
        self.clock.tick(31)
        self.assertTrue(self.s.available())
        self.assertFalse(self.s.degraded)


class TestWhatCallersReport(unittest.TestCase):

    def setUp(self):
        self.clock = Clock()
        self.probe = Probe()
        self.s = DbState(self.probe, clock=self.clock, retry_s=30)

    def test_a_caught_failure_is_not_re_probed_to_be_confirmed(self):
        """The caller's own query WAS the probe, and a better one than any this
        class could make — it is the query that actually matters."""
        self.assertTrue(self.s.available())
        self.s.note_failure(RuntimeError('timed out'))
        self.assertTrue(self.s.degraded)
        self.assertFalse(self.s.available())
        self.assertEqual(self.probe.calls, 1, 'no probe beyond the first')

    def test_a_caught_failure_restarts_the_cadence(self):
        self.s.note_failure()
        self.clock.tick(29)
        self.assertFalse(self.s.available())
        self.assertEqual(self.probe.calls, 0)
        self.clock.tick(2)
        self.assertTrue(self.s.available())

    def test_a_success_is_enough_to_come_back(self):
        self.s.note_failure()
        self.assertTrue(self.s.degraded)
        self.s.note_success()
        self.assertFalse(self.s.degraded)
        self.assertTrue(self.s.available())
        self.assertEqual(self.probe.calls, 0, 'a real query beats a probe')

    def test_degraded_never_probes(self):
        """A status line may read it on every render."""
        self.probe.up = False
        for _ in range(100):
            self.clock.tick(60)
            self.assertFalse(self.s.degraded)
        self.assertEqual(self.probe.calls, 0)

    def test_any_failure_counts_as_unreachable(self):
        """Measured on pi1, every shape of absence — no route, refused port,
        unresolvable name — arrives as one peewee.OperationalError. The probe
        still catches anything: a driver is free to raise its own, and a
        degraded mode is a better answer than a traceback out of a status call.
        """
        class OddFailure(Exception):
            pass

        def boom():
            raise OddFailure('something else entirely')
        s = DbState(boom, clock=self.clock)
        self.assertFalse(s.available())
        self.assertTrue(s.degraded)

    def test_an_interrupt_is_not_a_database_problem(self):
        """`except Exception`, never BaseException: a Ctrl-C or a SystemExit
        during a probe must leave, not be reported as an unreachable base."""
        def interrupted():
            raise KeyboardInterrupt
        s = DbState(interrupted, clock=self.clock)
        with self.assertRaises(KeyboardInterrupt):
            s.available()

    def test_the_state_is_reportable(self):
        self.assertTrue(self.s.available())
        self.clock.tick(5)
        st = self.s.state()
        self.assertEqual(st['up'], True)
        self.assertEqual(st['degraded'], False)
        self.assertEqual(st['failures'], 0)
        self.assertEqual(st['probed_s_ago'], 5.0)


if __name__ == '__main__':
    unittest.main()
