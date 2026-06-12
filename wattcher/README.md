# wattcher

Live CPU power / energy / thermal dashboard in the terminal — a Python
reimplementation of the assignment 3 `turbostat` + `ttyplot` workflow, reading
the same kernel counters directly (no subprocesses).

## What it shows

- **Package power (W)** with a sparkline history, cumulative joules, and a
  per-domain breakdown (package / core / dram) — from the RAPL counters in
  `/sys/class/powercap/intel-rapl*/energy_uj`, wraparound-corrected via
  `max_energy_range_uj`.
- **Package temperature (°C)** from `/sys/class/thermal`.
- **CPU utilisation** overall + per core from `/proc/stat`, and average
  frequency from cpufreq.
- **CPU sleep states** — % of time spent in each idle C-state (where the CPU
  sleeps, and how deeply) from `/sys/devices/system/cpu/cpu*/cpuidle`.
- **Carbon** — live grid carbon intensity for your location turned into
  gCO₂/h and a running session total, so wattage reads out as emissions.

## Running

```sh
uv run wattcher              # real counters (Linux + Intel/AMD)
uv run wattcher -i 0.5       # 0.5 s sampling interval
```

Press `q` to quit.

Requires Linux with RAPL (`/sys/class/powercap`); on other machines it exits
with an error explaining what's missing.

### Carbon intensity

The Carbon panel geolocates the machine from its public IP (ip-api.com) and
looks up the grid's carbon intensity (gCO₂eq/kWh), then multiplies it by the
live package power. Sources, best first:

- **Electricity Maps** — live and global, if you set a token:
  `export WATTCHER_EMAPS_TOKEN=...`
- **UK National Grid** (carbonintensity.org.uk) — live, keyless, used in GB.
- a built-in table of recent **annual averages** otherwise — labelled
  `(static)`, so it works anywhere with no key and no network.

## Power experiments

```sh
sudo uv run wattcher curve                      # default 0,20,…,100% sweep
sudo uv run wattcher curve --step 5             # finer: 0,5,10,…,100%
sudo uv run wattcher curve --levels 0,25,50,75,100
```

`wattcher curve` drives the CPU to known utilisation levels (a load generator
duty-cycles busy processes pinned to individual cores) and measures
steady-state package power at each, then reports:

- **Utilisation → power** — a fitted `P ≈ P_idle + slope·U%` line (static power
  plus dynamic power proportional to activity), with idle/full-load endpoints.
- **Frequency → power** — power against the average frequency observed during
  the sweep; because dynamic power scales ~V²·f, this climbs faster than the
  utilisation line.
- **Same total work, spread differently** — e.g. *N/2 cores at 100%* vs *N
  cores at 50%*: identical total load, but is it cheaper to concentrate it
  (letting idle cores sleep deep) or spread it (letting every core clock
  lower)? The answer is empirical and printed for your chip.

The sweep is saved to `$XDG_DATA_HOME/wattcher/curve.json` (override with
`--out`). View it as a braille chart, with a `f` key to toggle the
utilisation and frequency curves:

```sh
uv run wattcher plot          # standalone viewer — no RAPL needed, runs anywhere
```

or press **`c`** inside the live dashboard to open the same page. A finer
`--step` gives a smoother curve to plot.

### Permissions on Linux

Recent kernels restrict `energy_uj` to root (mitigation for the PLATYPUS
power side-channel — see assignment 4). Either:

```sh
sudo uv run wattcher
# or, for the session:
sudo chmod a+r /sys/class/powercap/intel-rapl*/energy_uj
```

## Layout

- `src/wattcher/sensors/linux.py` — real counter reads (RAPL, thermal,
  /proc/stat, cpufreq, cpuidle)
- `src/wattcher/app.py` — Textual TUI
- `src/wattcher/carbon.py` — IP geolocation + grid carbon intensity
- `src/wattcher/loadgen.py` — controllable per-core load for experiments
- `src/wattcher/curve.py` — `wattcher curve` measurement + saved-data I/O
- `src/wattcher/plot.py` — dependency-free braille line chart for the viewer

## Roadmap

- Per-process energy attribution ("top, but for joules")
- `wattcher run <cmd>` / `wattcher race <a> <b>` energy measurement modes

## PROMPTS USED

A reconstruction of the project as a series of learning/research prompts —
roughly the questions you would ask to build this from the ground up.

1. **Understand what turbostat actually reads.**
   "In assignment 3 we watched CPU package power by piping `turbostat` into
   `ttyplot`. I want to understand what turbostat is actually measuring rather
   than treating it as a black box. Walk me through the kernel interfaces
   behind it: the RAPL energy counters under `/sys/class/powercap`, CPU
   utilisation from `/proc/stat`, frequency from cpufreq, and C-state
   residency from cpuidle. For each one, what are the units, is the counter
   cumulative or instantaneous, and could I read them directly from Python
   without spawning subprocesses?"

2. **Design the project before writing sensor code.**
   "Let's build `wattcher`, a live terminal dashboard that reimplements that
   workflow in pure Python. Scaffold a uv-managed package with a `wattcher`
   entry point and an architecture where the UI never touches sysfs directly:
   a `Sample` dataclass holding one snapshot (watts and joules per RAPL
   domain, package temperature, overall and per-core busy %, average
   frequency, C-state residency %), and a `SensorSource` interface that
   produces one `Sample` per interval. Explain why deriving everything from
   counter deltas over an interval is the right model."

3. **Implement the real Linux source, carefully.**
   "Now implement `LinuxSource` against the real counters. Discover the
   intel-rapl domains (including core/uncore/dram subdomains and their parent
   package names), and handle the fact that `energy_uj` is a cumulative
   microjoule counter that wraps at `max_energy_range_uj` — show me how the
   wraparound correction works. Pick a sensible thermal zone (prefer
   `x86_pkg_temp`/`k10temp`), compute busy % from `/proc/stat` jiffy deltas
   including iowait as idle, and turn cumulative cpuidle residency into a
   per-interval percentage. Fail with a clear error when RAPL is missing or
   unreadable rather than crashing."

4. **Make it developable on a machine without RAPL.**
   "I'm developing on macOS where none of these interfaces exist. Write a
   `MockSource` that simulates an idle desktop with occasional bursts of
   load, where power, temperature, frequency and C-state residency are all
   derived from one underlying load signal so the panels move together
   plausibly — calibrated to the i7-7700 numbers from assignment 3 (~3 W
   idle, ~31 W loaded). Then make `pick_source()` try the real source first
   and fall back to the mock with a visible warning banner, plus a `--mock`
   flag to force it."

5. **Build the TUI.**
   "Build the dashboard with Textual: a power panel and a temperature panel
   each showing a headline value, a sparkline of recent history, and
   min/avg/max; a CPU panel with per-core utilisation bars and average
   frequency; and a C-state residency panel (explain what C0 vs the deeper
   states mean in the header). Sample once per configurable interval
   (`-i`), bind `q` to quit, and use an ANSI-palette theme so the dashboard
   respects the terminal's own colours and transparent background."

6. **Understand the permissions issue, then document everything.**
   "On the Linux box `energy_uj` is only readable as root — why? Explain the
   PLATYPUS power side-channel attack from assignment 4 and why kernels now
   restrict RAPL readings, then document the sudo/chmod workarounds. Finish
   the README: what each panel shows and which kernel file it comes from,
   how to run it, the layout of the code, and a roadmap (per-process energy
   attribution, and `wattcher run <cmd>` / `wattcher race <a> <b>`
   measurement modes)."

7. **Tie wattage to real-world carbon, and map the power curves.**
   "Add a live carbon panel: geolocate the machine from its public IP, look up
   the grid's carbon intensity, and turn package watts into gCO₂/h and a
   running session total — degrading gracefully from a live API to a static
   annual-average table so it works with no key. Then add a `wattcher curve`
   command that drives the CPU to known utilisation levels with a duty-cycled,
   core-pinned load generator and measures steady-state power, reporting the
   utilisation→power fit, the frequency→power relationship, and a
   concentrated-vs-spread experiment (the same total load on few cores at high
   duty versus many cores at low duty)."
