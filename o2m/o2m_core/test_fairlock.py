"""The box lock serves waiters in arrival order, re-enters, and survives a waiter
that gives up."""
import threading
import time
import unittest

from o2m_core.fairlock import FairRLock


def _wait_queued(lock, n, limit=2.0):
    end = time.monotonic() + limit
    while lock.waiting() < n and time.monotonic() < end:
        time.sleep(0.005)


class FairRLockTest(unittest.TestCase):

    def test_waiters_are_served_in_arrival_order(self):
        lock, order = FairRLock(), []
        lock.acquire()
        threads = []
        for i in range(6):
            t = threading.Thread(target=lambda i=i: (lock.acquire(), order.append(i), lock.release()))
            t.start()
            threads.append(t)
            _wait_queued(lock, i + 1)        # each one queued before the next arrives
        lock.release()
        for t in threads:
            t.join(2)
        self.assertEqual(order, list(range(6)))

    def test_reentrant_on_the_same_thread(self):
        lock = FairRLock()
        with lock:
            with lock:                       # a cascade fills its child on the same thread
                pass
            self.assertFalse(self._try_from_other_thread(lock))
        self.assertTrue(self._try_from_other_thread(lock))

    def test_a_waiter_that_times_out_does_not_stall_the_line(self):
        lock, got = FairRLock(), []
        lock.acquire()
        quitter = threading.Thread(target=lambda: got.append(('quitter', lock.acquire(timeout=0.05))))
        quitter.start()
        _wait_queued(lock, 1)
        patient = threading.Thread(target=lambda: (got.append(('patient', lock.acquire(timeout=2))), lock.release()))
        patient.start()
        quitter.join(2)
        lock.release()
        patient.join(2)
        self.assertEqual(got, [('quitter', False), ('patient', True)])

    def test_release_by_a_non_owner_raises(self):
        lock = FairRLock()
        self.assertRaises(RuntimeError, lock.release)

    @staticmethod
    def _try_from_other_thread(lock):
        res = []
        t = threading.Thread(target=lambda: res.append(lock.acquire(timeout=0.05)) or (res[0] and lock.release()))
        t.start()
        t.join(2)
        return res[0]


if __name__ == '__main__':
    unittest.main()
