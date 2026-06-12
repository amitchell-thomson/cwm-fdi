"""A tiny dependency-free line chart for the terminal, using braille.

Each character cell of the Unicode braille block (U+2800–U+28FF) is a 2×4 dot
grid, so a W×H block of cells gives a 2W×4H drawing surface — enough to draw a
recognisable curve in a few rows. Keeping it in-house (rather than pulling in
plotext) matches the rest of wattcher: read/own the primitive instead of
shelling out to a library.

`line_chart` returns a list of strings (rows) ready to drop into a Static.
"""

from __future__ import annotations

# dot bit value for each (row 0..3, col 0..1) position within a braille cell
_DOTS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)


class Canvas:
    """A braille pixel grid `width`×`height` characters (2·w × 4·h pixels)."""

    def __init__(self, width: int, height: int) -> None:
        self.wc = max(1, width)
        self.hc = max(1, height)
        self.px_w = self.wc * 2
        self.px_h = self.hc * 4
        self._grid = [[0] * self.wc for _ in range(self.hc)]

    def set(self, x: int, y: int) -> None:
        if 0 <= x < self.px_w and 0 <= y < self.px_h:
            self._grid[y // 4][x // 2] |= _DOTS[y % 4][x % 2]

    def line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Bresenham line between two pixels."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rows(self) -> list[str]:
        return ["".join(chr(0x2800 + cell) for cell in row) for row in self._grid]


def _scale_x(x: float, lo: float, hi: float, w: int) -> int:
    return round((x - lo) / (hi - lo) * (w - 1))


def _scale_y(y: float, lo: float, hi: float, h: int) -> int:
    # invert: larger values nearer the top (smaller pixel row)
    return round((1 - (y - lo) / (hi - lo)) * (h - 1))


def line_chart(
    points: list[tuple[float, float]],
    width: int = 60,
    height: int = 14,
    x_label: str = "",
    y_unit: str = "",
    title: str = "",
) -> list[str]:
    """Render `points` (already sorted by x) as a connected braille line with a
    framed y-axis (3 ticks) and x-axis (min/max). Returns rows of text."""
    if not points:
        return [title, "(no data)"]

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1

    cv = Canvas(width, height)
    px = [(_scale_x(x, xmin, xmax, cv.px_w), _scale_y(y, ymin, ymax, cv.px_h)) for x, y in points]
    for (x0, y0), (x1, y1) in zip(px, px[1:]):
        cv.line(x0, y0, x1, y1)
    for x, y in px:  # make sure single points / endpoints show
        cv.set(x, y)

    body = cv.rows()
    ymid = (ymin + ymax) / 2
    labels = {
        0: f"{ymax:.0f}{y_unit}",
        height // 2: f"{ymid:.0f}{y_unit}",
        height - 1: f"{ymin:.0f}{y_unit}",
    }
    gutter = max(len(v) for v in labels.values())

    out: list[str] = []
    if title:
        out.append(" " * (gutter + 1) + title)
    for i, row in enumerate(body):
        out.append(f"{labels.get(i, ''):>{gutter}} │{row}")
    out.append(" " * gutter + " └" + "─" * width)

    left = f"{xmin:.0f}"
    right = f"{xmax:.0f}"
    span = max(width - len(left), len(right))
    out.append(" " * (gutter + 2) + left + right.rjust(span))
    if x_label:
        out.append(" " * (gutter + 2) + x_label.center(width))
    return out
