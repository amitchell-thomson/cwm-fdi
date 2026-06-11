"""Shared data model produced by every sensor source once per interval."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sample:
    """One snapshot of the machine, derived from counter deltas over an interval."""

    elapsed_s: float
    # RAPL domain name -> average watts over the interval (e.g. "package-0", "core")
    watts: dict[str, float] = field(default_factory=dict)
    # RAPL domain name -> cumulative joules since the source was created
    joules: dict[str, float] = field(default_factory=dict)
    package_temp_c: float | None = None
    busy_pct: float = 0.0
    per_core_busy_pct: list[float] = field(default_factory=list)
    avg_freq_mhz: float | None = None
    # C-state name -> % of cpu-time spent in that state over the interval
    cstate_pct: dict[str, float] = field(default_factory=dict)

    @property
    def package_watts(self) -> float:
        """Headline number: sum of top-level package domains."""
        return sum(w for name, w in self.watts.items() if name.startswith("package")) or sum(
            self.watts.values()
        )

    @property
    def package_joules(self) -> float:
        return sum(j for name, j in self.joules.items() if name.startswith("package")) or sum(
            self.joules.values()
        )


class SensorError(RuntimeError):
    """Raised when a sensor source cannot be initialised."""
