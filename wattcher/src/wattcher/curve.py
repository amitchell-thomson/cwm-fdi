"""`wattcher curve` — measure how CPU power responds to load.

Drives the machine to known utilisation levels with the load generator and
records steady-state package power at each, then:

- fits a utilisation->power line  (P ≈ P_idle + slope·U%), the classic
  "static power + dynamic power proportional to activity" model;
- shows the power vs average-frequency relationship observed during the sweep
  (frequency rises with load, and dynamic power grows ~V²·f, so this climbs
  faster than the utilisation line);
- runs the "same total work, spread differently" experiment — e.g. 4 cores at
  100% vs 8 cores at 50% — to show whether concentrating or spreading load is
  cheaper on this chip.

Needs Linux with readable RAPL counters (run with sudo). Core pinning needs
sched_setaffinity (Linux); without it the totals are still right, just not
pinned to specific cores.
"""

from __future__ import annotations

import os
import time
from contextlib import nullcontext

from wattcher.loadgen import load
from wattcher.sample import SensorError
from wattcher.sensors.linux import LinuxSource

DEFAULT_LEVELS = [0, 20, 40, 60, 80, 100]


def _measure(source: LinuxSource, seconds: float, interval: float = 0.25):
    """Average (busy%, watts, freq_mhz) over `seconds` of steady state."""
    n = max(1, round(seconds / interval))
    busy = watts = freq = 0.0
    fcount = 0
    for _ in range(n):
        time.sleep(interval)
        s = source.sample()
        busy += s.busy_pct
        watts += s.package_watts
        if s.avg_freq_mhz:
            freq += s.avg_freq_mhz
            fcount += 1
    return busy / n, watts / n, (freq / fcount if fcount else None)


def _linfit(xs, ys):
    """Least-squares y = a + b·x, returning (a, b, r2)."""
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return sy / n, 0.0, 0.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    mean = sy / n
    ss_tot = sum((y - mean) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


def _bar(value: float, vmax: float, width: int = 32) -> str:
    filled = round(value / vmax * width) if vmax > 0 else 0
    return "█" * filled + "·" * (width - filled)


def _prime() -> LinuxSource:
    source = LinuxSource()
    source.sample()  # establish the first counter baseline
    return source


def run_curve(
    levels: list[int] | None = None,
    settle: float = 1.5,
    window: float = 2.0,
) -> None:
    levels = levels or DEFAULT_LEVELS
    ncpu = os.cpu_count() or 1
    cores = list(range(ncpu))
    pinned = hasattr(os, "sched_setaffinity")

    try:
        source = _prime()
    except SensorError as exc:
        raise SystemExit(f"wattcher: {exc}")

    print(f"wattcher curve — {ncpu} logical CPUs"
          f"{'' if pinned else '  (no core pinning on this OS)'}\n")

    # -- utilisation -> power sweep ---------------------------------------
    print("Sweeping utilisation (all cores) …")
    rows = []  # (target%, measured busy%, watts, freq)
    for lvl in levels:
        duty = lvl / 100
        ctx = load(cores, duty) if duty > 0 else nullcontext()
        with ctx:
            time.sleep(settle)
            source.sample()  # reset baseline after the load settles
            busy, watts, freq = _measure(source, window)
        rows.append((lvl, busy, watts, freq))

    wmax = max(w for _, _, w, _ in rows)
    print("\nUtilisation → power")
    print(f"  {'target':>6}  {'busy':>5}  {'power':>32}  {'watts':>6}  {'freq':>7}")
    for lvl, busy, watts, freq in rows:
        fr = f"{freq:,.0f}MHz" if freq else "   —"
        print(f"  {lvl:>5}%  {busy:>4.0f}%  {_bar(watts, wmax)}  {watts:>5.1f}W  {fr:>7}")

    a, b, r2 = _linfit([busy for _, busy, _, _ in rows], [w for _, _, w, _ in rows])
    print(f"\n  fit: power ≈ {a:.1f} W + {b:.3f} W/%busy   (R²={r2:.3f})")
    print(f"       idle ≈ {a:.1f} W, full-load ≈ {a + 100 * b:.1f} W,"
          f" dynamic range ≈ {100 * b:.1f} W")

    # -- frequency -> power (same samples, reordered) ---------------------
    freq_rows = sorted((f, w) for _, _, w, f in rows if f)
    if len(freq_rows) >= 2:
        fmax = max(w for _, w in freq_rows)
        print("\nFrequency → power")
        for freq, watts in freq_rows:
            print(f"  {freq:>6,.0f} MHz  {_bar(watts, fmax)}  {watts:>5.1f}W")
        fa, fb, fr2 = _linfit([f for f, _ in freq_rows], [w for _, w in freq_rows])
        print(f"\n  fit: power ≈ {fa:.1f} W + {fb * 1000:.2f} W/GHz   (R²={fr2:.3f})")

    # -- concentrated vs spread (same total work) ------------------------
    half = max(1, ncpu // 2)
    total_pct = half * 100
    configs = [
        (cores[:half], 1.0, f"{half} cores @ 100%"),
        (cores, half / ncpu, f"{ncpu} cores @ {100 * half / ncpu:.0f}%"),
    ]
    print(f"\nSame total work (~{total_pct}% CPU), distributed differently")
    results = []
    for sel, duty, label in configs:
        with load(sel, duty):
            time.sleep(settle)
            source.sample()
            _, watts, freq = _measure(source, window)
        fr = f"{freq:,.0f}MHz" if freq else "—"
        results.append((label, watts, freq))
        print(f"  {label:<18} → {watts:>5.1f} W   (avg freq {fr})")

    if len(results) == 2:
        (la, wa, _), (lb, wb, _) = results
        cheaper, dearer = (results[0], results[1]) if wa < wb else (results[1], results[0])
        delta = dearer[1] - cheaper[1]
        pct = 100 * delta / dearer[1] if dearer[1] else 0
        print(f"\n  → '{cheaper[0]}' is cheaper by {delta:.1f} W ({pct:.0f}%).")
        print("    Spreading lets each core clock lower (dynamic power ~V²·f);"
              " concentrating lets idle cores reach deeper C-states. The winner"
              " depends on which effect dominates on this chip.")
