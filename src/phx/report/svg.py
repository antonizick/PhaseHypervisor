"""Trend charts in the timeline's visual style (Phase 12f, ADR-0032).

Inline CSS with light and dark palettes, no external fonts, a ``<title>`` on every mark
and a plain-text line under each chart. The figures come only from the report and its
as-of time is the newest record, so the same logs give byte-identical files.
"""

from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape as _escape

from phx.report.model import Period, Report, Totals
from phx.report.rules import money

W = 830
H = 340
LEFT = 64
RIGHT = 24
TOP = 76
BOTTOM = 84
FONT = "system-ui, -apple-system, &quot;Segoe UI&quot;, Roboto, sans-serif"
LIGHT = {
    "card": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#6f6d68", "grid": "#e1e0d9",
    "axis": "#c3c2b7", "border": "#d9d8d2", "other": "#a3a19a",
}  # fmt: skip
DARK = {
    "card": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#a3a19a", "grid": "#2c2c2a",
    "axis": "#4a4a46", "border": "#3a3a37", "other": "#6f6d68",
}  # fmt: skip
# Fixed categorical order, the slots validated for adjacent stacks; more models fold into Other.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181")
OTHER = "Other"


def _x(text: str) -> str:
    return _escape(text, {'"': "&quot;"})


def _n(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _css(c: dict[str, str], series: tuple[str, ...]) -> str:
    slots = "".join(f".s{i}{{fill:{v}}}" for i, v in enumerate(series))
    return (
        f".card{{fill:{c['card']};stroke:{c['border']}}}"
        f".t1{{fill:{c['ink']}}}.t2{{fill:{c['ink2']}}}.t3{{fill:{c['muted']}}}"
        f".grid{{stroke:{c['grid']}}}.axis{{stroke:{c['axis']}}}"
        f".line{{stroke:{series[0]};fill:none}}.dot{{fill:{series[0]};stroke:{c['card']}}}"
        f".nd{{stroke:{c['axis']};fill:none}}.so{{fill:{c['other']}}}{slots}"
    )


def _nice_top(value: float) -> float:
    """A round axis maximum at or above ``value``."""
    step = 1.0
    while step * 10 < value:
        step *= 10
    while step > value > 0:
        step /= 10
    for factor in (1, 2, 2.5, 5, 10):
        if step * factor >= value:
            return step * factor
    return step * 10


class _Chart:
    def __init__(self, report: Report, slug: str, title: str, subtitle: str) -> None:
        self.report = report
        self.title = title
        self.subtitle = subtitle
        self.slug = slug
        self.marks: list[str] = []
        self.periods = report.periods
        self.plot_w = W - LEFT - RIGHT
        self.plot_h = H - TOP - BOTTOM
        self.band = self.plot_w / max(1, len(self.periods))

    def center(self, index: int) -> float:
        return LEFT + self.band * (index + 0.5)

    def y(self, value: float, top: float) -> float:
        return TOP + self.plot_h * (1 - (value / top if top else 0))

    def axes(self, top: float, fmt: Callable[[float], str]) -> None:
        for i in range(5):
            value = top * i / 4
            y = self.y(value, top)
            cls = "axis" if i == 0 else "grid"
            self.marks.append(
                f'<line class="{cls}" x1="{LEFT}" x2="{W - RIGHT}" y1="{_n(y)}" y2="{_n(y)}"/>'
                f'<text class="t3" x="{LEFT - 8}" y="{_n(y + 4)}" font-size="12" '
                f'text-anchor="end">{_x(fmt(value))}</text>'
            )
        skip = max(1, round(len(self.periods) / 12))
        for i, period in enumerate(self.periods):
            if i % skip == 0:
                self.marks.append(
                    f'<text class="t2" x="{_n(self.center(i))}" y="{H - BOTTOM + 20}" '
                    f'font-size="12" text-anchor="middle">{_x(period.label)}</text>'
                )

    def no_data(self, index: int) -> None:
        """A dashed outline: an empty period is shown as empty, never as zero."""
        width = min(24.0, self.band * 0.6)
        x = self.center(index) - width / 2
        self.marks.append(
            f'<rect class="nd" x="{_n(x)}" y="{TOP}" width="{_n(width)}" height="{self.plot_h}" '
            f'stroke-dasharray="4 4"><title>{_x(self.periods[index].label)}: no data</title></rect>'
        )

    def render(self, fallback: str) -> str:
        scope = (
            f"{self.subtitle} {len(self.report.projects)} project(s), "
            f"data through {self.report.as_of}."
        )
        body = "\n".join(self.marks)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="{_x(self.title)}" '
            f'font-family="{FONT}">\n'
            f"<title>{_x(self.title)}</title>\n<desc>{_x(fallback)}</desc>\n"
            f"<style>{_css(LIGHT, SERIES_LIGHT)}"
            f"@media (prefers-color-scheme: dark){{{_css(DARK, SERIES_DARK)}}}</style>\n"
            f'<rect class="card" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8"/>\n'
            f'<text class="t1" x="20" y="30" font-size="17" font-weight="600">'
            f"{_x(self.title)}</text>\n"
            f'<text class="t2" x="20" y="50" font-size="12.5">{_x(scope)}</text>\n'
            f"{body}\n"
            f'<text class="t2" x="20" y="{H - 12}" font-size="12">{_x(_clip(fallback))}</text>\n'
            "</svg>\n"
        )


def _clip(text: str, chars: int = 125) -> str:
    return text if len(text) <= chars else text[: chars - 1].rstrip() + "…"


def _bar(
    chart: _Chart,
    value: float | None,
    index: int,
    top: float,
    label: str,
    tip: str,
) -> None:
    period = chart.periods[index]
    if value is None:
        chart.no_data(index)
        return
    width = min(24.0, chart.band * 0.6)
    x = chart.center(index) - width / 2
    y = chart.y(value, top)
    base = TOP + chart.plot_h
    r = min(4.0, width / 2, base - y)
    path = (
        f"M{_n(x)} {_n(base)}V{_n(y + r)}Q{_n(x)} {_n(y)} {_n(x + r)} {_n(y)}"
        f"H{_n(x + width - r)}Q{_n(x + width)} {_n(y)} {_n(x + width)} {_n(y + r)}V{_n(base)}Z"
    )
    chart.marks.append(
        f'<path class="s0" d="{path}"><title>{_x(period.label)}: {_x(tip)}</title></path>'
        f'<text class="t1" x="{_n(chart.center(index))}" y="{_n(y - 6)}" font-size="12" '
        f'text-anchor="middle">{_x(label)}</text>'
    )


def _unpriced(report: Report) -> str:
    """The caveat a cost chart carries when part of its cost has no known price."""
    rest = report.totals.unverified_cost_usd
    return f". Includes {money(rest)} with no known price" if rest else ""


def _bars(
    report: Report,
    slug: str,
    title: str,
    subtitle: str,
    value: Callable[[Totals], float | None],
    fmt: Callable[[float], str],
    note: str = "",
) -> str:
    chart = _Chart(report, slug, title, subtitle)
    values = [value(p.totals) if p.totals.has_data else None for p in report.periods]
    top = _nice_top(max((v for v in values if v is not None), default=1.0) or 1.0)
    chart.axes(top, fmt)
    for index, v in enumerate(values):
        shown = fmt(v) if v is not None else "no data"
        _bar(chart, v, index, top, shown, shown)
    return chart.render(_summary(report.periods, values, fmt) + note)


def _summary(periods: list[Period], values: list[float | None], fmt: Callable[[float], str]) -> str:
    return "; ".join(
        f"{p.label} {fmt(v) if v is not None else 'no data'}"
        for p, v in zip(periods, values, strict=True)
    )


def cost_per_phase_chart(report: Report) -> str:
    chart = _Chart(
        report,
        "cost-per-phase",
        "Cost per completed phase",
        "List-price equivalent, not an invoice; phx-launched sessions only.",
    )
    values = [p.totals.cost_per_phase for p in report.periods]
    top = _nice_top(max((v for v in values if v is not None), default=1.0) or 1.0)
    chart.axes(top, lambda v: money(v).removesuffix(".00"))
    points = [
        (chart.center(i), chart.y(v, top), v, report.periods[i].label)
        for i, v in enumerate(values)
        if v is not None
    ]
    run: list[str] = []
    for i, v in enumerate(values):
        if v is None:
            if not report.periods[i].totals.has_data:
                chart.no_data(i)
            _flush(chart, run)
            run = []
        else:
            run.append(f"{_n(chart.center(i))},{_n(chart.y(v, top))}")
    _flush(chart, run)
    for x, y, v, label in points:
        chart.marks.append(
            f'<circle class="dot" cx="{_n(x)}" cy="{_n(y)}" r="5" stroke-width="2">'
            f"<title>{_x(label)}: {money(v)}</title></circle>"
            f'<text class="t1" x="{_n(x)}" y="{_n(y - 10)}" font-size="12" '
            f'text-anchor="middle">{money(v)}</text>'
        )
    return chart.render(_summary(report.periods, values, money) + _unpriced(report))


def _flush(chart: _Chart, run: list[str]) -> None:
    if len(run) > 1:
        chart.marks.append(f'<polyline class="line" stroke-width="2" points="{" ".join(run)}"/>')


def model_names(report: Report) -> list[str]:
    """Models by total cost; the fixed slots keep a model's color across periods."""
    costs: dict[str, float] = {}
    for period in report.periods:
        for name, cost in period.models.items():
            costs[name] = costs.get(name, 0.0) + cost
    return sorted(costs, key=lambda n: (-costs[n], n))


def model_mix_chart(report: Report) -> str:
    chart = _Chart(
        report,
        "model-mix",
        "Model mix per period, share of cost",
        "List-price equivalent, not an invoice; phx-launched sessions only.",
    )
    names = model_names(report)
    keep = names[: len(SERIES_LIGHT)]
    has_other = len(names) > len(keep)
    chart.axes(1.0, lambda v: f"{v * 100:.0f}%")
    summary = []
    for index, period in enumerate(report.periods):
        total = sum(period.models.values())
        if not total:
            chart.no_data(index)
            summary.append(f"{period.label} no data")
            continue
        shares = [(n, period.models.get(n, 0.0)) for n in keep]
        if has_other:
            rest = sum(c for n, c in period.models.items() if n not in keep)
            shares.append((OTHER, rest))
        width = min(24.0, chart.band * 0.6)
        x = chart.center(index) - width / 2
        y = float(TOP)
        for slot, (name, cost) in enumerate(shares):
            height = chart.plot_h * cost / total
            if height <= 0:
                continue
            cls = "so" if name == OTHER else f"s{slot}"
            drawn = max(0.5, height - 2)  # the 2px surface gap between segments
            chart.marks.append(
                f'<rect class="{cls}" x="{_n(x)}" y="{_n(y)}" width="{_n(width)}" '
                f'height="{_n(drawn)}"><title>{_x(period.label)}, {_x(name)}: {money(cost)} '
                f"({cost / total * 100:.0f}%)</title></rect>"
            )
            y += height
        lead = max(period.models, key=lambda n: (period.models[n], n))
        summary.append(f"{period.label} {lead} {period.models[lead] / total * 100:.0f}%")
    x = float(LEFT)
    row = H - 54
    legend = [*keep, *([OTHER] if has_other else [])]
    for slot, name in enumerate(legend):
        cls = "so" if name == OTHER else f"s{slot}"
        label = _clip(name, 30)
        wide = 14 + len(label) * 6.2 + 14
        if x + wide > W - RIGHT:  # the second of the two legend rows
            x, row = float(LEFT), H - 38
        chart.marks.append(
            f'<rect class="{cls}" x="{_n(x)}" y="{row}" width="10" height="10" rx="2"/>'
            f'<text class="t2" x="{_n(x + 14)}" y="{row + 9}" font-size="11.5">{_x(label)}</text>'
        )
        x += wide
    return chart.render("; ".join(summary) + _unpriced(report))


def charts(report: Report) -> dict[str, str]:
    """File name -> SVG for the four charts."""

    def dollars(value: float) -> str:
        return money(value).removesuffix(".00")

    return {
        "phx-report-cost.svg": _bars(
            report,
            "cost",
            f"Cost per {report.by}",
            "List-price equivalent, not an invoice; phx-launched sessions only.",
            lambda t: t.cost_usd,
            dollars,
            _unpriced(report),
        ),
        "phx-report-cost-per-phase.svg": cost_per_phase_chart(report),
        "phx-report-active-hours.svg": _bars(
            report,
            "active-hours",
            f"Active session hours per {report.by}",
            "phx-launched sessions only.",
            lambda t: t.active_s / 3600,
            lambda v: f"{v:.1f} h",
        ),
        "phx-report-model-mix.svg": model_mix_chart(report),
    }


def write_charts(report: Report, directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in charts(report).items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
