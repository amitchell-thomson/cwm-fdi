"""Sensor sources: real Linux kernel counters (RAPL, thermal, /proc/stat,
cpufreq, cpuidle)."""

from __future__ import annotations

from wattcher.sample import Sample, SensorError


class SensorSource:
    """Interface: prime counters in __init__, then call sample() once per interval."""

    description = ""

    def sample(self) -> Sample:
        raise NotImplementedError


__all__ = ["Sample", "SensorError", "SensorSource"]
