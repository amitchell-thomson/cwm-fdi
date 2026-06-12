"""Textual dashboard: live package power, thermals, utilisation, frequency
and C-state residency, sampled once per interval from a SensorSource."""

from __future__ import annotations

from collections import deque

from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Footer, Header, Sparkline, Static

from wattcher.carbon import CarbonIntensity, fetch_carbon
from wattcher.curve import load_curve
from wattcher.plot import line_chart
from wattcher.sample import Sample
from wattcher.sensors import SensorSource

HISTORY = 300  # samples kept for sparklines

# ansi_default leaves cells unpainted so the terminal's own (transparent)
# background shows through; ansi=True resolves every theme slot through the
# terminal palette instead of fixed RGB.
_THEME = Theme(
    name="wattcher",
    ansi=True,
    primary="ansi_blue",
    secondary="ansi_cyan",
    accent="ansi_bright_cyan",
    warning="ansi_yellow",
    error="ansi_red",
    success="ansi_green",
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    variables={
        "block-cursor-blurred-background": "ansi_default",
        "block-hover-background": "ansi_default",
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
    },
)


def bar(pct: float, width: int = 14) -> str:
    filled = round(max(0.0, min(100.0, pct)) / 100 * width)
    return "█" * filled + "·" * (width - filled)


class TrendPanel(Vertical):
    """A headline number with a sparkline and min/avg/max of recent history."""

    def __init__(self, title: str, unit: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = title
        self._unit = unit
        self._history: deque[float] = deque(maxlen=HISTORY)

    def compose(self) -> ComposeResult:
        yield Static("—", classes="headline")
        yield Sparkline([], summary_function=max)
        yield Static("", classes="stats")

    def update_value(self, value: float | None, extra: str = "") -> None:
        if value is None:
            self.query_one(".headline", Static).update("n/a")
            return
        self._history.append(value)
        hist = self._history
        self.query_one(".headline", Static).update(
            f"[b]{value:6.1f}[/b] {self._unit}{'   ' + extra if extra else ''}"
        )
        self.query_one(Sparkline).data = list(hist)
        self.query_one(".stats", Static).update(
            f"min {min(hist):5.1f}   avg {sum(hist) / len(hist):5.1f}   max {max(hist):5.1f}"
        )


class BarsPanel(Vertical):
    """A titled list of `label  ▕███▏ pct` rows."""

    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = title

    def compose(self) -> ComposeResult:
        yield Static("", classes="bars")

    def update_rows(self, rows: list[tuple[str, float]], header: str = "") -> None:
        lines = [header] if header else []
        lines += [f"{label:<6} {bar(pct)} {pct:5.1f}%" for label, pct in rows]
        self.query_one(".bars", Static).update("\n".join(lines))


class CarbonPanel(Vertical):
    """Live grid carbon intensity, turning watts into grams of CO2."""

    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = title

    def compose(self) -> ComposeResult:
        yield Static("locating grid…", classes="carbon")

    def update_carbon(
        self, carbon: CarbonIntensity | None, watts: float, joules: float
    ) -> None:
        if carbon is None:
            self.query_one(".carbon", Static).update("locating grid…")
            return
        tag = "" if carbon.live else "  [dim](static)[/dim]"
        self.query_one(".carbon", Static).update(
            f"[b]{carbon.grams_per_kwh:5.0f}[/b] gCO₂/kWh{tag}\n"
            f"[b]{carbon.grams_per_hour(watts):5.1f}[/b] gCO₂/h   "
            f"now at {watts:.1f} W\n"
            f"Σ [b]{carbon.grams_for_joules(joules):,.1f}[/b] gCO₂ this session\n"
            f"[dim]{carbon.zone} · {carbon.source}[/dim]"
        )


class CurvePlot(Static):
    """Renders a saved power curve as a braille chart; toggles util/freq view."""

    def __init__(self, data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._data = data
        self._view = "util"  # or "freq"

    def on_resize(self) -> None:
        self.refresh()  # re-fit the chart to the new size

    def toggle(self) -> None:
        self._view = "freq" if self._view == "util" else "util"
        self.refresh()

    def render(self) -> Text:
        if not self.size.width or not self.size.height:
            return Text("")  # not laid out yet; on_resize re-renders once sized
        width = max(20, self.size.width - 12)
        height = max(6, self.size.height - 7)
        util = self._data.get("util", [])

        if self._view == "util":
            points = [(p["target"], p["watts"]) for p in util]
            chart = line_chart(points, width, height, "utilisation %", "W", "Power vs utilisation")
            fit = self._data.get("fit") or {}
            sub = (
                f"fit: P ≈ {fit.get('intercept', 0):.1f}W + "
                f"{fit.get('slope', 0):.3f}·U%   (R²={fit.get('r2', 0):.3f})"
            )
        else:
            points = sorted((p["freq"], p["watts"]) for p in util if p.get("freq"))
            chart = line_chart(points, width, height, "avg frequency (MHz)", "W", "Power vs frequency")
            ff = self._data.get("freq_fit") or {}
            sub = (
                f"fit: P ≈ {ff.get('intercept', 0):.1f}W + "
                f"{ff.get('slope_per_ghz', 0):.2f}·GHz   (R²={ff.get('r2', 0):.3f})"
                if ff else "frequency data unavailable"
            )

        conc = self._data.get("concentration") or []
        conc_line = "    ".join(f"{c['label']}: [b]{c['watts']:.1f}W[/b]" for c in conc)
        return Text.from_markup(
            "\n".join(chart)
            + f"\n\n{sub}\n[dim]same total work →[/dim]  {conc_line}\n"
            + "[dim]f = toggle util/freq · esc = back[/dim]"
        )


class CurveScreen(Screen):
    """Full-screen curve viewer pushed over the dashboard."""

    BINDINGS = [
        ("escape", "back", "back"),
        ("q", "back", "back"),
        ("f", "toggle", "util/freq"),
    ]

    def __init__(self, data: dict) -> None:
        super().__init__()
        self._data = data

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield CurvePlot(self._data, id="plot")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_toggle(self) -> None:
        self.query_one(CurvePlot).toggle()


_PLOT_CSS = "CurvePlot { padding: 1 2; height: 1fr; }"


class WattcherApp(App):
    TITLE = "wattcher"
    BINDINGS = [("q", "quit", "quit"), ("c", "show_curve", "curve")]
    CSS = """
    Screen { background: ansi_default; }
    Horizontal { height: 1fr; }
    TrendPanel, BarsPanel, CarbonPanel {
        border: round $primary;
        border-title-color: $accent;
        padding: 0 1;
    }
    TrendPanel { height: 1fr; }
    BarsPanel { height: 1fr; }
    CarbonPanel { height: 6; }
    .headline { height: 1; }
    Sparkline { height: 1fr; min-height: 3; margin: 1 0; }
    Sparkline > .sparkline--max-color { color: $accent; }
    .stats { height: 1; color: $text-muted; }
    .bars, .carbon { height: auto; }
    #left { width: 3fr; }
    #right { width: 2fr; }
    CurvePlot { padding: 1 2; height: 1fr; }
    """

    def __init__(self, source: SensorSource, interval: float = 1.0) -> None:
        super().__init__()
        self._source = source
        self._interval = interval
        self._carbon: CarbonIntensity | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield TrendPanel("Package Power", "W", id="power")
                yield TrendPanel("Package Temperature", "°C", id="temp")
                yield CarbonPanel("Carbon", id="carbon")
            with Vertical(id="right"):
                yield BarsPanel("CPU", id="cpu")
                yield BarsPanel("CPU Sleep States", id="cstates")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(_THEME)
        self.theme = "wattcher"
        self.sub_title = self._source.description
        self.set_interval(self._interval, self._tick)
        self._refresh_carbon()
        self.set_interval(900, self._refresh_carbon)  # grid intensity drifts slowly

    @work(thread=True, exclusive=True)
    def _refresh_carbon(self) -> None:
        # blocking network calls — runs off the UI thread
        self._carbon = fetch_carbon()

    def action_show_curve(self) -> None:
        data = load_curve()
        if data:
            self.push_screen(CurveScreen(data))
        else:
            self.notify("No curve data yet — run `wattcher curve` first.", severity="warning")

    def _tick(self) -> None:
        self._render_sample(self._source.sample())

    def _render_sample(self, s: Sample) -> None:
        breakdown = "  ".join(
            f"{name.split('/')[-1]} {w:.1f}W" for name, w in sorted(s.watts.items())
        )
        self.query_one("#power", TrendPanel).update_value(
            s.package_watts, extra=f"Σ {s.package_joules:,.0f} J   [{breakdown}]"
        )
        self.query_one("#temp", TrendPanel).update_value(s.package_temp_c)
        self.query_one("#carbon", CarbonPanel).update_carbon(
            self._carbon, s.package_watts, s.package_joules
        )

        freq = f"avg freq {s.avg_freq_mhz:,.0f} MHz" if s.avg_freq_mhz else ""
        cpu_rows = [("all", s.busy_pct)] + [
            (f"cpu{i}", pct) for i, pct in enumerate(s.per_core_busy_pct)
        ]
        self.query_one("#cpu", BarsPanel).update_rows(cpu_rows, header=freq)

        cstates = dict(s.cstate_pct)
        active = max(0.0, 100 - sum(cstates.values()))
        rows = [("C0", active)] + sorted(cstates.items())
        self.query_one("#cstates", BarsPanel).update_rows(
            rows, header="% of time per state — C0 = awake, deeper = more power saved"
        )


class CurveViewerApp(App):
    """Standalone viewer for a saved curve — needs no RAPL, runs anywhere."""

    TITLE = "wattcher curve"
    BINDINGS = [("q", "quit", "quit"), ("f", "toggle", "util/freq")]
    CSS = "Screen { background: ansi_default; }\n" + _PLOT_CSS

    def __init__(self, data: dict) -> None:
        super().__init__()
        self._data = data

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield CurvePlot(self._data, id="plot")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(_THEME)
        self.theme = "wattcher"

    def action_toggle(self) -> None:
        self.query_one(CurvePlot).toggle()


def run_curve_viewer(path: str | None = None) -> None:
    data = load_curve(Path(path) if path else None)
    if not data:
        raise SystemExit("wattcher: no curve data — run `wattcher curve` first")
    CurveViewerApp(data).run()
