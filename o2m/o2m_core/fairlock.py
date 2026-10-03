"""A reentrant lock that serves its waiters in arrival order.

`threading.RLock` makes no promise about order: with three boxes waiting behind a
fill, the last one put down can go before the second. For a queue of things a
person did — tags put down, tiles tapped — arrival order IS the expected order.

Same interface as RLock where o2m uses it (`acquire(timeout=)`, `release()`,
context manager), so it drops in. A waiter that gives up on a timeout leaves
the queue and wakes the others, so an abandoned ticket never stalls the line.
"""
import collections
import threading


class FairRLock:
    def __init__(self):
        self._cond = threading.Condition(threading.Lock())
        self._owner = None
        self._count = 0
        self._queue = collections.deque()

    def acquire(self, blocking=True, timeout=None):
        me = threading.get_ident()
        with self._cond:
            if self._owner == me:            # reentrant: a cascade re-enters on its thread
                self._count += 1
                return True
            if self._owner is None and not self._queue:
                self._owner, self._count = me, 1
                return True
            if not blocking:
                return False
            ticket = object()
            self._queue.append(ticket)
            ok = self._cond.wait_for(
                lambda: self._owner is None and self._queue[0] is ticket,
                None if timeout is None or timeout < 0 else timeout)
            if not ok:
                self._queue.remove(ticket)
                self._cond.notify_all()      # the next in line may be free to go now
                return False
            self._queue.popleft()
            self._owner, self._count = me, 1
            return True

    def release(self):
        with self._cond:
            if self._owner != threading.get_ident():
                raise RuntimeError("cannot release un-acquired lock")
            self._count -= 1
            if self._count == 0:
                self._owner = None
                self._cond.notify_all()

    def waiting(self):
        """How many callers are queued behind the holder."""
        with self._cond:
            return len(self._queue)

    __enter__ = acquire

    def __exit__(self, *exc):
        self.release()
