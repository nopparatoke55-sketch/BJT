"""Dependency-free SVG chart helpers for the Lab 04 plots.

The web app passes only numbers parsed from the actual ngspice output.  This
module turns those numbers into a small inline SVG; it never generates sample
data, so a plot cannot exist without a successful solver run.
"""

from __future__ import annotations

import html
import math
from typing import Iterable, Sequence

PALETTE = ["#0d6efd", "#fd7e14", "#20c997", "#6f42c1", "#dc3545"]


def downsample(points: Sequence[tuple[float, float]], max_points: int = 420) -> list[tuple[float, float]]:
    """Keep an evenly spaced subset while preserving the last sample."""
    if not points:
        return []
    if len(points) <= max_points:
        return list(points)
    step = max(1, math.ceil(len(points) / max_points))
    sampled = list(points[::step])
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if not (_finite(low) and _finite(high)):
        return []
    if high <= low:
        high = low + 1.0
    span = high - low
    raw = span / max(count, 1)
    if raw <= 0:
        return [low]
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0):
        step = multiplier * magnitude
        if step >= raw:
            break
    start = math.floor(low / step) * step
    ticks: list[float] = []
    value = start
    while value <= high + step * 0.5 and len(ticks) < 100:
        if value >= low - step * 0.5:
            ticks.append(value)
        value += step
    return ticks


def _log_ticks(low: float, high: float) -> list[float]:
    if not (_finite(low) and _finite(high)) or low <= 0 or high <= 0:
        return []
    first = math.floor(math.log10(low))
    last = math.ceil(math.log10(high))
    ticks = []
    for exponent in range(first, last + 1):
        value = 10 ** exponent
        if low * 0.999 <= value <= high * 1.001:
            ticks.append(value)
    if len(ticks) < 2:
        ticks = [low, high]
    return ticks


def _fmt(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1e6 or magnitude < 1e-3:
        return f"{value:.2e}"
    if magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 1:
        return f"{value:g}"
    return f"{value:.3g}"


def _empty_svg(width: int, height: int, message: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(message)}" class="plot-svg">'
        f'<rect width="{width}" height="{height}" fill="#f8fbfd"/>'
        f'<text x="{width/2}" y="{height/2}" text-anchor="middle" '
        f'fill="#6c757d" font-size="14">{html.escape(message)}</text></svg>'
    )


def svg_line_chart(
    series: Iterable[dict],
    *,
    x_label: str = "",
    y_label: str = "",
    title: str = "",
    x_log: bool = False,
    width: int = 700,
    height: int = 300,
) -> str:
    """Return an inline SVG line chart.

    ``series`` is an iterable of ``{"name": str, "points": [(x, y), ...]}``.
    A colour is assigned automatically when the series has no ``color``.
    """
    clean: list[dict] = []
    for index, item in enumerate(series):
        points = [
            (float(x), float(y))
            for x, y in item.get("points", [])
            if _finite(x) and _finite(y) and (not x_log or x > 0)
        ]
        if points:
            clean.append(
                {
                    "name": item.get("name", f"Series {index + 1}"),
                    "color": item.get("color", PALETTE[index % len(PALETTE)]),
                    "points": points,
                }
            )

    if not clean:
        return _empty_svg(width, height, "No data returned by the solver.")

    xs = [x for item in clean for x, _ in item["points"]]
    ys = [y for item in clean for _, y in item["points"]]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    if x_log:
        x_min = max(x_min, 1e-12)
        if x_max <= x_min:
            x_max = x_min * 10
    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        pad = abs(y_min) * 0.1 or 1.0
        y_min -= pad
        y_max += pad

    x_pad = (x_max - x_min) * 0.02 if not x_log else 0.0
    y_pad = (y_max - y_min) * 0.08 or 1.0
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad

    margin_left, margin_right, margin_top, margin_bottom = 66, 18, 42, 48
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def sx(value: float) -> float:
        if x_log:
            span = math.log10(x_max) - math.log10(x_min)
            return margin_left + (math.log10(value) - math.log10(x_min)) / span * plot_width
        return margin_left + (value - x_min) / (x_max - x_min) * plot_width

    def sy(value: float) -> float:
        return margin_top + (y_max - value) / (y_max - y_min) * plot_height

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(title or y_label or "chart")}" class="plot-svg">',
        f'<rect width="{width}" height="{height}" fill="#f8fbfd"/>',
    ]

    if title:
        parts.append(
            f'<text x="{margin_left}" y="24" fill="#103658" font-size="14" '
            f'font-weight="700">{html.escape(title)}</text>'
        )

    y_ticks = _nice_ticks(y_min, y_max, 5)
    for tick in y_ticks:
        y = sy(tick)
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" '
            f'y2="{y:.1f}" stroke="#e3edf3" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="#6c757d" font-size="10">{_fmt(tick)}</text>'
        )

    x_ticks = _log_ticks(x_min, x_max) if x_log else _nice_ticks(x_min, x_max, 6)
    for tick in x_ticks:
        x = sx(tick)
        # Keep the first/last labels inside the SVG viewport instead of
        # letting them run past the plot edge and get clipped.
        if x < margin_left + 18:
            anchor = "start"
        elif x > width - margin_right - 18:
            anchor = "end"
        else:
            anchor = "middle"
        parts.append(
            f'<line x1="{x:.1f}" y1="{margin_top}" x2="{x:.1f}" '
            f'y2="{height - margin_bottom}" stroke="#e3edf3" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - margin_bottom + 16}" text-anchor="{anchor}" '
            f'fill="#6c757d" font-size="10">{_fmt(tick)}</text>'
        )

    parts.append(
        f'<line x1="{margin_left}" y1="{height - margin_bottom}" '
        f'x2="{width - margin_right}" y2="{height - margin_bottom}" '
        f'stroke="#9cb2c2" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" '
        f'y2="{height - margin_bottom}" stroke="#9cb2c2" stroke-width="1.2"/>'
    )

    for item in clean:
        points = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in item["points"])
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{item["color"]}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    legend_x = margin_left + 8
    legend_y = margin_top + 12
    for index, item in enumerate(clean):
        y = legend_y + index * 16
        parts.append(
            f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 18}" y2="{y}" '
            f'stroke="{item["color"]}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{legend_x + 24}" y="{y + 4}" fill="#495057" '
            f'font-size="11">{html.escape(item["name"])}</text>'
        )

    if x_label:
        parts.append(
            f'<text x="{margin_left + plot_width / 2:.1f}" y="{height - 8}" '
            f'text-anchor="middle" fill="#495057" font-size="11">'
            f'{html.escape(x_label)}</text>'
        )
    if y_label:
        parts.append(
            f'<text x="16" y="{margin_top + plot_height / 2:.1f}" '
            f'text-anchor="middle" fill="#495057" font-size="11" '
            f'transform="rotate(-90 16 {margin_top + plot_height / 2:.1f})">'
            f'{html.escape(y_label)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)
