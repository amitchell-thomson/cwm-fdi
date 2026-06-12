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
with an error explaining what's missing. The saved-curve viewer
(`wattcher plot`) needs no RAPL and runs anywhere.

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
- **Same total work, spread differently** — a fixed ~200% load delivered as
  *2 cores @ 100%* vs *4 @ 50%* vs *8 @ 25%*: identical total work, but is it
  cheaper to concentrate it (letting idle cores sleep deep) or spread it
  (letting every core clock lower)? The answer is empirical and printed for
  your chip.

The sweep is saved to `$XDG_DATA_HOME/wattcher/curve.json` (override with
`--out`). View it as a braille chart, with `f` to cycle three views —
utilisation, frequency, and the concentrated-vs-spread bar chart:

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

- `src/wattcher/sample.py` — the `Sample` dataclass: one snapshot, all panels
  read from it; nothing else knows where the numbers come from
- `src/wattcher/sensors/__init__.py` — the `SensorSource` interface
- `src/wattcher/sensors/linux.py` — real counter reads (RAPL, thermal,
  /proc/stat, cpufreq, cpuidle)
- `src/wattcher/app.py` — Textual TUI (live dashboard + curve viewer screens)
- `src/wattcher/carbon.py` — IP geolocation + grid carbon intensity
- `src/wattcher/loadgen.py` — controllable per-core load for experiments
- `src/wattcher/curve.py` — `wattcher curve` measurement + saved-data I/O
- `src/wattcher/plot.py` — dependency-free braille line chart for the viewer

## Roadmap

- Per-process energy attribution ("top, but for joules")
- `wattcher run <cmd>` / `wattcher race <a> <b>` energy measurement modes
- A non-Linux mock source so the live dashboard is demoable off real hardware
  (today only the `plot` viewer runs everywhere)

## How this was built — a prompt history

I designed wattcher and then worked through the implementation with an AI
coding assistant under that design (declared in full below). The prompts below
trace that work — the sequence of design questions I worked through, roughly in
order, each mapping onto the module it produced — so you can read the code
alongside the question that motivated it.

1. **Understand what turbostat actually reads.**
   "In assignment 3 we watched CPU package power by piping `turbostat` into
   `ttyplot`. I want to understand what turbostat is actually measuring rather
   than treating it as a black box. Walk me through the kernel interfaces
   behind it: the RAPL energy counters under `/sys/class/powercap`, CPU
   utilisation from `/proc/stat`, frequency from cpufreq, and C-state
   residency from cpuidle. For each one, what are the units, is the counter
   cumulative or instantaneous, and could I read them directly from Python
   without spawning subprocesses?"

2. **Scaffold the package and CLI.**
   "Let's build `wattcher`, a live terminal dashboard that reimplements that
   workflow in pure Python. Scaffold a uv-managed package with a `wattcher`
   console-script entry point and a `python -m wattcher` form. Give it an
   `argparse` CLI: a default dashboard mode with `-i/--interval`, plus stubs
   for two subcommands (`curve` and `plot`) we'll fill in later. Import the
   heavy subcommand modules lazily inside each branch so launching the
   dashboard doesn't pull in the load-generator or plotting code."

3. **Pin down the data model.**
   "Before any sysfs code, define the snapshot every sensor will emit: a
   `Sample` dataclass holding watts and joules per RAPL domain, package
   temperature, overall and per-core busy %, average frequency, and C-state
   residency %. Add convenience properties for the headline package power and
   cumulative package joules that sum just the top-level `package*` domains.
   Explain why deriving everything from counter *deltas over an interval* is
   the right model rather than trying to read instantaneous power."

4. **Define the sensor seam.**
   "Add a `SensorSource` interface: prime counters in `__init__`, then return
   one `Sample` per call to `sample()`. The rule I want enforced by the
   architecture is that the UI only ever sees `Sample` objects and never
   touches sysfs — every reader is hidden behind this one interface. Also
   define a `SensorError` for sources that can't initialise."

5. **Implement RAPL, including the counter wraparound.**
   "Implement the RAPL half of `LinuxSource`. Discover the intel-rapl domains
   under `/sys/class/powercap`, distinguishing a package (`intel-rapl:0`) from
   a subdomain (`intel-rapl:0:1`, core/uncore/dram) and naming subdomains
   `parent/child`. `energy_uj` is a cumulative microjoule counter that wraps
   at `max_energy_range_uj`, so each read must diff against the previous value
   and add the range back when the delta goes negative. Track cumulative
   joules per domain too. Show me the wraparound correction explicitly."

6. **Implement the rest of the Linux source.**
   "Finish `LinuxSource`. Pick a sensible thermal zone (prefer
   `x86_pkg_temp`/`k10temp`/`acpitz`) from `/sys/class/thermal`; compute busy %
   from `/proc/stat` jiffy deltas counting iowait as idle, overall and per
   core; average cpufreq across cores; and turn cumulative cpuidle residency
   into a per-interval percentage. Assemble it all in `sample()` using a real
   `time.monotonic()` interval. When RAPL is missing or unreadable, raise a
   `SensorError` that says exactly what to do (sudo / chmod) rather than
   crashing."

7. **Build the reusable TUI panels.**
   "Start the Textual UI with the building blocks. A `TrendPanel` showing a
   headline value, a sparkline of recent history (cap it at 300 samples), and a
   min/avg/max line; a `BarsPanel` rendering `label [blocks] pct%` rows; and a
   `CarbonPanel` placeholder. Use an ANSI-palette theme (`ansi=True`,
   `ansi_default` backgrounds) so the dashboard respects the terminal's own
   colours and transparent background, and a small `bar()` helper for the
   block bars."

8. **Assemble the live dashboard.**
   "Wire the panels into `WattcherApp`: a left column with Package Power,
   Package Temperature and Carbon, a right column with CPU (per-core bars +
   average frequency header) and CPU Sleep States. Drive it with
   `set_interval(-i)` calling `source.sample()` each tick and fanning the
   `Sample` out to the panels. In the C-state panel synthesise C0 as
   `100 − sum(deeper states)` and explain in the header what C0 vs the deeper
   states mean. Bind `q` to quit and `c` to open the curve viewer."

9. **Understand the permissions wall, then document it.**
   "On the Linux box `energy_uj` is only readable as root — why? Explain the
   PLATYPUS power side-channel attack from assignment 4 and why kernels now
   restrict RAPL readings, then document the sudo/chmod workarounds and make
   the sensor's permission error point straight at the fix. Then write the
   README: what each panel shows and which kernel file it comes from, how to
   run it, the code layout, and a roadmap (per-process energy attribution, and
   `wattcher run <cmd>` / `wattcher race <a> <b>` measurement modes)."

10. **Tie wattage to real-world carbon.**
    "Add a live carbon panel. Geolocate the machine from its public IP, look up
    the grid's carbon intensity, and turn package watts into gCO₂/h plus a
    running session total from the cumulative joules. Degrade gracefully:
    Electricity Maps if a token is set, the UK National Grid API if we're in
    GB, otherwise a static annual-average table so it works with no key and no
    network. Every network call must be allowed to fail silently and fall back,
    and the lookup must run off the UI thread (a Textual worker) so a slow API
    never freezes the dashboard; refresh it only every 15 minutes."

11. **Build a controllable load generator.**
    "I want to drive the CPU to a *known* load on *chosen* cores for power
    experiments. Because the GIL stops one thread loading several cores, use one
    process per core; pin each with `os.sched_setaffinity`; and hit a target
    utilisation by duty-cycling — spin for `duty` of each ~20 ms slice, sleep
    the rest. Wrap it in a `load(cores, duty)` context manager that starts the
    workers on entry and terminates them on exit, with `duty=0` meaning no
    workers. Affinity should be best-effort so it still runs where pinning
    isn't available."

12. **Measure the power curves, then plot them.**
    "Add the `wattcher curve` command on top of that load generator. Sweep
    0→100% utilisation (default steps, or `--step`/`--levels`), letting each
    level settle before averaging steady-state package power, and report the
    utilisation→power least-squares fit (`P ≈ P_idle + slope·U%`), the
    frequency→power relationship from the same samples, and a
    concentrated-vs-spread experiment: the same total load on few cores at high
    duty versus many cores at low duty. Save the sweep to the XDG data dir as
    JSON. Then write a dependency-free braille line chart (each cell is a 2×4
    dot grid, so a block of cells is a pixel canvas with Bresenham lines) and a
    viewer over that JSON with three pages cycled by `f` — utilisation vs power
    with the fit line, frequency vs power, and the concentrated-vs-spread bar
    chart — exposed both as a standalone `wattcher plot` that needs no RAPL and
    as the `c` page over the live dashboard."

## On the use of AI

I used an AI coding assistant while building wattcher, and I want to declare
that use clearly and specifically.

**System used:** Anthropic Claude (Opus 4 family), via the Claude Code CLI.

**The structure and design are mine.** I laid out the architecture and the plan
before writing implementation code: the module breakdown; the `Sample` /
`SensorSource` separation that keeps the UI from ever touching sysfs; the
decision to derive everything from counter *deltas over an interval*; the choice
to own the primitives (the braille canvas, the least-squares fit, the
duty-cycled load generator) rather than pull in libraries, and the
function-level skeleton — what the modules, classes and functions are, what each
one takes and returns, and how they fit together. I also designed the
measurement methodology for the power experiments and ran them on real hardware
(the i7-7700 from assignment 3), read the kernel interfaces myself to confirm
the counters mean what I think and that the numbers are physically sensible,
interpreted the utilisation / frequency / concentration results, and debugged
the RAPL permission wall against an actual machine.

**Where AI assisted.** Working to that structure, I used the assistant mainly to
fill in the *bodies* of the functions I had laid out — translating my design and
the kernel-interface details into the working Python inside each function — and
to handle boilerplate and suggest Textual layout. I reviewed every function it
filled in, revised what didn't fit, and changed or removed suggestions that were
wrong (for example, an early non-Linux mock source was dropped — it's on the
roadmap, not in the tree). The prompt history above corresponds to that work. I
have read and understand every line in `src/wattcher/` and can explain it.

**Where AI was *not* used.** The data analysis, the graphs and their
interpretation, and the project report are my own work, not the assistant's.

A fuller prompt-and-response log of the AI interactions that materially shaped
the project accompanies this repository.
