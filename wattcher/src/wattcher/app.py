"""Textual dashboard: live package power, thermals, utilisation, frequency
and C-state residency, sampled once per interval from a SensorSource."""

from __future__ import annotations

from collections import deque

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Footer, Header, Sparkline, Static

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


class WattcherApp(App):
    TITLE = "wattcher"
    BINDINGS = [("q", "quit", "quit")]
    CSS = """
    Screen { background: ansi_default; }
    Horizontal { height: 1fr; }
    TrendPanel, BarsPanel {
        border: round $primary;
        border-title-color: $accent;
        padding: 0 1;
    }
    TrendPanel { height: 1fr; }
    BarsPanel { height: 1fr; }
    .headline { height: 1; }
    Sparkline { height: 1fr; min-height: 3; margin: 1 0; }
    Sparkline > .sparkline--max-color { color: $accent; }
    .stats { height: 1; color: $text-muted; }
    .bars { height: auto; }
    #left { width: 3fr; }
    #right { width: 2fr; }
    """

    def __init__(self, source: SensorSource, interval: float = 1.0) -> None:
        super().__init__()
        self._source = source
        self._interval = interval

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield TrendPanel("Package Power", "W", id="power")
                yield TrendPanel("Package Temperature", "°C", id="temp")
            with Vertical(id="right"):
                yield BarsPanel("CPU", id="cpu")
                yield BarsPanel("CPU Sleep States", id="cstates")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(_THEME)
        self.theme = "wattcher"
        self.sub_title = self._source.description
        self.set_interval(self._interval, self._tick)

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
