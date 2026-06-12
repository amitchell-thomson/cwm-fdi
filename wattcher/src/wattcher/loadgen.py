"""Controllable CPU load for the power experiments.

To draw a utilisation->power curve, or to compare "4 cores at 25%" against
"1 core at 100%", we need to put a *known* amount of work on *chosen* cores.
Python's GIL means one thread can't load several cores, so each worker is a
separate process. Within a worker we hit a target utilisation by duty-cycling:
spin for `duty` of every time slice, sleep the rest. os.sched_setaffinity pins
each worker to one core so the distribution is exactly what we asked for.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import time
from contextlib import contextmanager

SLICE = 0.02  # duty-cycle period in seconds; small enough to look like steady load


def _worker(core: int, duty: float) -> None:
    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, {core})
        except OSError:
            pass  # affinity is best-effort; still generates load without it
    duty = max(0.0, min(1.0, duty))
    while True:
        start = time.monotonic()
        busy_until = start + SLICE * duty
        while time.monotonic() < busy_until:
            pass  # spin = the actual work
        idle = SLICE - (time.monotonic() - start)
        if idle > 0:
            time.sleep(idle)


@contextmanager
def load(cores: list[int], duty: float):
    """Run, for the duration of the `with` block, one busy worker on each core in
    `cores`, each targeting `duty` (0..1) utilisation. duty=0 yields no workers."""
    procs: list[mp.Process] = []
    if duty > 0:
        ctx = mp.get_context("fork") if hasattr(os, "fork") else mp.get_context()
        for core in cores:
            p = ctx.Process(target=_worker, args=(core, duty), daemon=True)
            p.start()
            procs.append(p)
    try:
        yield
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.join(timeout=1.0)
