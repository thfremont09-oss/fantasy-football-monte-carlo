"""Keep the app inside the server's memory (Render Starter: 512 MB for everything).

Two glibc settings help a lot for a threaded Python server:
* fewer malloc "arenas": by default each thread can get its own pool of memory that's never shared, which
  multiplies the footprint of every request that runs in a thread;
* ``trim()`` after a big job hands freed memory back to the system instead of keeping it reserved.
"""

from __future__ import annotations

import ctypes
import gc

_M_ARENA_MAX = -8

try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:                       # not Linux/glibc (e.g. a Mac running it locally): nothing to tune
    _libc = None


def limit_arenas(n: int = 2) -> None:
    if _libc is not None:
        try:
            _libc.mallopt(_M_ARENA_MAX, n)
        except AttributeError:
            pass


def trim() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except AttributeError:
            pass


def rss_mb() -> float:
    """This process's current memory use, in MB (Linux)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * 4096 / 1024 / 1024
    except OSError:
        return 0.0


# One big job at a time. The server is shared by everyone on the site; two visitors starting a parlay search
# (or a season download) at the same moment would add their memory together and blow through the limit.
# A second job simply waits its turn; memory is handed back to the system after each one.
import contextlib
import threading

_HEAVY = threading.RLock()


@contextlib.contextmanager
def heavy():
    with _HEAVY:
        try:
            yield
        finally:
            trim()


# Background housekeeping: every few seconds hand freed memory back to the system, and run any registered
# clean-ups (e.g. dropping a cached market scan nobody has asked for in a while).
_CLEANUPS: list = []
_STARTED = False


def on_cleanup(fn) -> None:
    if fn not in _CLEANUPS:
        _CLEANUPS.append(fn)


def start_housekeeping(every: float = 15.0) -> None:
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    import time

    def loop():
        while True:
            time.sleep(every)
            for fn in list(_CLEANUPS):
                try:
                    fn()
                except Exception:
                    pass
            if _libc is not None and _HEAVY.acquire(blocking=False):   # never in the middle of a big job
                try:
                    _libc.malloc_trim(0)
                finally:
                    _HEAVY.release()
    threading.Thread(target=loop, daemon=True, name="memory-housekeeping").start()
