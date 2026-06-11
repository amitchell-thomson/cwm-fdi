"""Real sensor source: reads the same kernel interfaces turbostat does.

- Energy/power: /sys/class/powercap/intel-rapl*/energy_uj (RAPL MSRs exposed
  by the powercap driver). The counter is cumulative microjoules and wraps at
  max_energy_range_uj, so each sample diffs against the previous reading.
- Temperature: /sys/class/thermal/thermal_zone*/temp (millidegrees C).
- Utilisation: /proc/stat jiffy counters, overall and per core.
- Frequency: /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq (kHz).
- C-states: /sys/devices/system/cpu/cpu*/cpuidle/state*/time (cumulative usec
  per state per cpu).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from wattcher.sample import Sample, SensorError
from wattcher.sensors import SensorSource

POWERCAP = Path("/sys/class/powercap")
THERMAL = Path("/sys/class/thermal")
CPU = Path("/sys/devices/system/cpu")
PREFERRED_THERMAL_TYPES = ("x86_pkg_temp", "k10temp", "acpitz")


@dataclass
class _RaplDomain:
    name: str
    energy_path: Path
    max_range_uj: int
    last_uj: int
    total_uj: int = 0

    def read(self) -> int:
        """Return microjoules consumed since the previous read, wrap-corrected."""
        now = int(self.energy_path.read_text())
        delta = now - self.last_uj
        if delta < 0:  # counter wrapped past max_energy_range_uj
            delta += self.max_range_uj
        self.last_uj = now
        self.total_uj += delta
        return delta


class LinuxSource(SensorSource):
    def __init__(self) -> None:
        self._domains = self._discover_rapl()
        self.description = f"RAPL via {POWERCAP} ({len(self._domains)} domains)"
        self._thermal_path = self._discover_thermal()
        self._prev_stat = self._read_proc_stat()
        self._cstate_names, self._prev_cstates = self._read_cstates()
        self._n_cpus = len(self._prev_stat) - 1
        self._t0 = time.monotonic()
        self._last_t = self._t0

    # -- discovery ---------------------------------------------------------

    def _discover_rapl(self) -> list[_RaplDomain]:
        if not POWERCAP.exists():
            raise SensorError("no /sys/class/powercap: RAPL needs Linux on Intel/AMD")
        domains: list[_RaplDomain] = []
        denied = 0
        # intel-rapl:0 is a package; intel-rapl:0:1 is a subdomain (core/uncore/dram)
        for path in sorted(POWERCAP.glob("intel-rapl:*")):
            try:
                name = (path / "name").read_text().strip()
                if path.name.count(":") == 2:
                    parent = (path.parent / path.name.rsplit(":", 1)[0] / "name").read_text().strip()
                    name = f"{parent}/{name}"
                domain = _RaplDomain(
                    name=name,
                    energy_path=path / "energy_uj",
                    max_range_uj=int((path / "max_energy_range_uj").read_text()),
                    last_uj=int((path / "energy_uj").read_text()),
                )
            except PermissionError:
                denied += 1
                continue
            except (OSError, ValueError):
                continue
            domains.append(domain)
        if not domains:
            if denied:
                raise SensorError(
                    "energy_uj not readable: run with sudo, or "
                    "`sudo chmod a+r /sys/class/powercap/intel-rapl*/energy_uj`"
                )
            raise SensorError("no intel-rapl domains found")
        return domains

    def _discover_thermal(self) -> Path | None:
        zones: dict[str, Path] = {}
        for zone in sorted(THERMAL.glob("thermal_zone*")):
            try:
                zones[(zone / "type").read_text().strip()] = zone / "temp"
            except OSError:
                continue
        for preferred in PREFERRED_THERMAL_TYPES:
            if preferred in zones:
                return zones[preferred]
        return next(iter(zones.values()), None)

    # -- raw counter reads --------------------------------------------------

    @staticmethod
    def _read_proc_stat() -> list[tuple[int, int]]:
        """[(busy_jiffies, total_jiffies)] — index 0 is the 'cpu' aggregate line."""
        rows = []
        for line in Path("/proc/stat").read_text().splitlines():
            if not line.startswith("cpu"):
                break
            fields = [int(x) for x in line.split()[1:]]
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0)  # idle + iowait
            rows.append((sum(fields) - idle, sum(fields)))
        return rows

    def _read_cstates(self) -> tuple[list[str], dict[str, int]]:
        """Cumulative usec per C-state name, summed across all cpus."""
        names: list[str] = []
        totals: dict[str, int] = {}
        for state in sorted(CPU.glob("cpu[0-9]*/cpuidle/state*")):
            try:
                name = (state / "name").read_text().strip()
                usec = int((state / "time").read_text())
            except OSError:
                continue
            if name not in totals:
                names.append(name)
                totals[name] = 0
            totals[name] += usec
        return names, totals

    @staticmethod
    def _read_avg_freq_mhz() -> float | None:
        freqs = []
        for path in CPU.glob("cpu[0-9]*/cpufreq/scaling_cur_freq"):
            try:
                freqs.append(int(path.read_text()))
            except OSError:
                continue
        return (sum(freqs) / len(freqs)) / 1000 if freqs else None

    # -- public API ----------------------------------------------------------

    def sample(self) -> Sample:
        now = time.monotonic()
        interval = max(now - self._last_t, 1e-6)
        self._last_t = now

        watts: dict[str, float] = {}
        joules: dict[str, float] = {}
        for domain in self._domains:
            delta_uj = domain.read()
            watts[domain.name] = delta_uj / 1e6 / interval
            joules[domain.name] = domain.total_uj / 1e6

        temp = None
        if self._thermal_path is not None:
            try:
                temp = int(self._thermal_path.read_text()) / 1000
            except OSError:
                pass

        stat = self._read_proc_stat()
        busy_rows = []
        for (busy0, total0), (busy1, total1) in zip(self._prev_stat, stat):
            dtotal = total1 - total0
            busy_rows.append(100 * (busy1 - busy0) / dtotal if dtotal else 0.0)
        self._prev_stat = stat

        _, cstates = self._read_cstates()
        cpu_usec = self._n_cpus * interval * 1e6
        cstate_pct = {
            name: 100 * (cstates.get(name, 0) - self._prev_cstates.get(name, 0)) / cpu_usec
            for name in self._cstate_names
        }
        self._prev_cstates = cstates

        return Sample(
            elapsed_s=now - self._t0,
            watts=watts,
            joules=joules,
            package_temp_c=temp,
            busy_pct=busy_rows[0] if busy_rows else 0.0,
            per_core_busy_pct=busy_rows[1:],
            avg_freq_mhz=self._read_avg_freq_mhz(),
            cstate_pct=cstate_pct,
        )
