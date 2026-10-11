"""Offline regression tests for the backup/restore ETA estimator.

``src/devicemanagement/eta.py`` turns the device's 0..100 percentage stream
into a remaining-time estimate. The clock is faked so the tests are instant
and deterministic. No device or Qt is needed.

Run: python3 tools/test_eta.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.devicemanagement.eta as eta_mod
from src.devicemanagement.eta import ProgressEta, _format_duration

PASS = 0


def check(name, cond):
    global PASS
    assert cond, f"FAILED: {name}"
    PASS += 1
    print(f"  ok: {name}")


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


clock = Clock()
eta_mod.time = types.SimpleNamespace(monotonic=clock)


def new_estimator(**kw):
    clock.t = 1000.0
    defaults = {"window_seconds": 30.0, "min_elapsed": 5.0, "min_delta": 1.0}
    defaults.update(kw)
    return ProgressEta(**defaults)


# 1. Nothing to report until a stable rate exists.
e = new_estimator()
check("zero progress resets and reports nothing", e.update(0) == "")
check("no estimate before min_elapsed", e.update(10) == "")

# 2. Linear progress yields a proportional estimate (10% at t=0, 20% at t=5
#    -> 2%/s over the window -> 80% left -> 40s).
clock.advance(5)
check("linear estimate (20% -> 0:40)", e.update(20) == "0:40")
clock.advance(5)
check("progressed estimate (40% -> 0:20)", e.update(40) == "0:20")

# 3. Completion short-circuits to zero.
check("100% reports 0:00", new_estimator().update(100) == "0:00")

# 4. A dropped percentage means a restart -> reset, no stale estimate.
e = new_estimator()
e.update(50)
clock.advance(10)
check("drop resets the estimator", e.update(5) == "")
clock.advance(5)
check("new baseline produces a fresh estimate", e.update(10) == "1:30")

# 5. A stalled window (progress pauses but samples keep arriving) falls back
#    to the overall rate instead of dividing by zero.
e = new_estimator(window_seconds=4.0, min_elapsed=2.0)
e.update(10)
clock.advance(3)
check("mid-run estimate", e.update(50) == "0:04")
clock.advance(3)
check("stall falls back to overall rate", e.update(50) == "0:06")

# 6. A gap longer than the window (reboot wait) restarts measurement instead
#    of extrapolating across the dead time.
e = new_estimator(window_seconds=30.0)
e.update(90)
clock.advance(5)
check("estimate before the gap", e.update(92) != "")
clock.advance(600)
check("long gap reports nothing", e.update(95) == "")
clock.advance(5)
check("estimate resumes after the gap", e.update(96) != "")

# 7. Non-numeric input is ignored.
check("non-numeric ignored", new_estimator().update("busy") == "")
check("None ignored", new_estimator().update(None) == "")
check("bool ignored", new_estimator().update(True) == "")

# 8. Duration formatting.
check("seconds format", _format_duration(20) == "0:20")
check("minute format", _format_duration(125) == "2:05")
check("hour format", _format_duration(3725) == "1:02:05")
check("negative clamps", _format_duration(-3) == "0:00")
check("None -> empty", _format_duration(None) == "")

print(f"\nAll {PASS} ETA checks passed.")
