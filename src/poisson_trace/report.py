"""The reports: markdown to stdout, the JSON structure, and the one SVG. Stdlib only."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

CANNOT_SAY: tuple[str, ...] = (
    "The step index is where the run stopped, not why. A run that died at a tool step may "
    "have gone wrong three steps earlier.",
    "Timed-out and capped runs are censored at their last recorded step. If they would have "
    "died soon after, the curve is optimistic by that much; the header counts them.",
    "Excluded rows are not on the curve; the header counts them by reason.",
    "On one run, this is a description. Only a comparison of two stored runs on the same "
    "cells says whether anything moved, and only within what it could not have detected.",
)

KM_CAPTION = "Kaplan–Meier over leaf-span index; band: Greenwood, plain, 95%"
AJ_CAPTION = "Aalen–Johansen cumulative incidence; band: bootstrap 95%, B = {b}, seed = {seed}"
LOGRANK_CAPTION = (
    "log-rank, stratified by config cell over {cells} common {cell_word} "
    "(excluded: {a_only} in A only, {b_only} in B only), unpaired{salt}; α = {alpha}"
)
PER_CAUSE_CAPTION = (
    "cause-specific log-rank, stratified by config cell, deaths of other {what} censored at "
    "their step; Benjamini–Hochberg at q = {alpha}"
)
MDE_LINE = (
    "could not have detected a hazard ratio below {mde} (Schoenfeld, 80% power, α = {alpha}, "
    "{deaths} deaths over the common cells, allocation {share})"
)


def _f(x: float | None, places: int = 3) -> str:
    return "–" if x is None else f"{x:.{places}f}"


def _p(p: float) -> str:
    return f"{p:.3f}" if p >= 0.001 else f"{p:.2e}"


def _g(x: float) -> str:
    return f"{x:g}"


def _band(lo: float | None, hi: float | None) -> str:
    return "–" if lo is None or hi is None else f"{_f(lo)} – {_f(hi)}"


def _dumps(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, allow_nan=False) + "\n"


def _header_lines(run: Mapping[str, Any], events: Sequence[str]) -> list[str]:
    tally = run["tally"]
    placement = run["placement"]
    excluded = placement["excluded"]
    cap = "no cap" if run["cap"] is None else f"cap: {run['cap']} spans"
    lines = [
        f"- run: {run['run_id']} · target: {run['target_id']} · t_unit: {run['t_unit']} · "
        f"status: {run['status']} · {cap}",
        "- Prove's tally: "
        + " · ".join(
            f"{label} {tally[key]}"
            for label, key in (
                ("rows", "rows"),
                ("with outcome", "with_outcome"),
                ("no outcome", "no_outcome"),
                ("timed out", "timed_out"),
                ("infra", "infra"),
                ("other", "other"),
            )
        ),
        "- placement: "
        + " · ".join(
            f"{label} {placement[label]}"
            for label in ("placed", "died", "ended", "timed out", "capped")
        )
        + f" · excluded {sum(excluded.values())}"
        + (
            " (" + "; ".join(f"{reason} {n}" for reason, n in excluded.items() if n) + ")"
            if any(excluded.values())
            else ""
        ),
        f"- events: {', '.join(events)}",
    ]
    return lines


def _cannot_say_lines() -> list[str]:
    return ["## What this cannot say", ""] + [f"- {sentence}" for sentence in CANNOT_SAY]


@dataclass(frozen=True)
class WhereReport:
    """``data`` is the JSON structure of the spec's section 5.3, keys in order. ``last_step``
    is the largest step index any placed row reached, and ``incidence`` each cause's
    cumulative incidence over the curve's death steps; both serve the SVG only."""

    data: Mapping[str, Any]
    last_step: int = 0
    incidence: Mapping[str, Sequence[float]] = field(default_factory=dict)

    def to_markdown(self) -> str:
        d = self.data
        run = d["run"]
        by = d["clock"]["by"]
        by_label = "kind of step" if by == "kind" else "step name"
        cause_word = "kind" if by == "kind" else "step"
        lines = [f"# Poisson Trace · where runs die · {run['run_id']}", "", "## Run", ""]
        lines += _header_lines(run, d["events"])
        lines += ["", "## Survival over step index", "", f"{KM_CAPTION}.", ""]
        lines += ["| step | at risk | died | S | 95% band |", "|---|---|---|---|---|"]
        for row in d["curve"]:
            lines.append(
                f"| {row['step']} | {row['at_risk']} | {row['died']} | {_f(row['survival'])} | "
                f"{_band(row['lo'], row['hi'])} |"
            )
        if not d["curve"]:
            lines.append("| – | – | 0 | 1.000 | 1.000 – 1.000 |")
        lines.append("")
        median = d["median_step"]
        lines.append(f"median step: {'not reached' if median is None else median}")
        for row in d["at"]:
            lines.append(
                f"S({row['step']}) = {_f(row['survival'])} ({_band(row['lo'], row['hi'])})"
            )
        boot = d["bootstrap"]
        lines += ["", f"## Where they die, by {by_label}", ""]
        lines += [AJ_CAPTION.format(b=boot["b"], seed=boot["seed"]) + ".", ""]
        last = d["curve"][-1]["step"] if d["curve"] else None
        at_label = f"F at step {last}" if last is not None else "F"
        lines += [f"| {cause_word} | deaths | {at_label} | 95% band |", "|---|---|---|---|"]
        for row in d["causes"]:
            lines.append(
                f"| {row['cause']} | {row['deaths']} | {_f(row['f'])} | "
                f"{_band(row['lo'], row['hi'])} |"
            )
        if not d["causes"]:
            lines.append("| – | 0 | 0.000 | – |")
        total = sum(row["f"] for row in d["causes"])
        s_last = d["curve"][-1]["survival"] if d["curve"] else 1.0
        lines += ["", f"sum of F = 1 − S = {_f(total)} (1 − {_f(s_last)})"]
        if "declared" in d:
            lines += ["", "## Declared steps", ""]
            lines += self._declared_lines()
        lines += [""] + _cannot_say_lines() + [""]
        return "\n".join(lines)

    def _declared_lines(self) -> list[str]:
        d = self.data
        declared = d["declared"]
        placed = d["run"]["placement"]["placed"]
        reached: Mapping[str, int] = d.get("_reached", {})
        never = set(declared["never_reached"])
        lines = [
            "Reached by k of N placed runs, from Prove's declaration; the set of steps never "
            "reached is Prove's own.",
            "",
            "| step | reached by | note |",
            "|---|---|---|",
        ]
        for name in declared["declared_steps"]:
            flag = "never reached" if name in never else ""
            lines.append(f"| {name} | {reached.get(name, 0)} of {placed} | {flag} |")
        for name in declared["undeclared_steps"]:
            lines.append(f"| {name} | {reached.get(name, 0)} of {placed} | undeclared |")
        return lines

    def to_json(self) -> str:
        return _dumps({k: v for k, v in self.data.items() if not k.startswith("_")})

    def to_svg(self) -> str:
        return _render_svg(self)


@dataclass(frozen=True)
class CompareReport:
    data: Mapping[str, Any]

    def to_markdown(self) -> str:
        d = self.data
        runs = d["runs"]
        c = d["comparison"]
        by = d["clock"]["by"]
        what = "kinds" if by == "kind" else "steps"
        cause_word = "kind" if by == "kind" else "step"
        a, b = runs["a"], runs["b"]
        lines = [
            f"# Poisson Trace · compare · {a['run_id']} (before) and {b['run_id']} (after)",
            "",
            "## Run A (before)",
            "",
        ]
        lines += _header_lines(a, d["events"])
        for line in d.get("_event_notes", []):
            lines.append(f"- {line}")
        lines += ["", "## Run B (after)", ""]
        lines += _header_lines(b, d["events"])
        lines += ["", "## Comparison", ""]
        salt = " (the runs share a run_salt)" if d.get("_same_salt") else ""
        lines.append(
            LOGRANK_CAPTION.format(
                cells=c["cells"],
                cell_word="cell" if c["cells"] == 1 else "cells",
                a_only=c["excluded_cells"]["a_only"],
                b_only=c["excluded_cells"]["b_only"],
                salt=salt,
                alpha=_g(c["alpha"]),
            )
            + "."
        )
        lines += ["", "| arm | placed | died | observed | expected |", "|---|---|---|---|---|"]
        deaths = c["observed_a"] + d["_observed_b"]
        lines.append(
            f"| A (before) | {a['placement']['placed']} | {a['placement']['died']} | "
            f"{_g(c['observed_a'])} | {_f(c['expected_a'])} |"
        )
        lines.append(
            f"| B (after) | {b['placement']['placed']} | {b['placement']['died']} | "
            f"{_g(d['_observed_b'])} | {_f(deaths - c['expected_a'])} |"
        )
        lines += [
            "",
            f"statistic: χ² = {_f(c['statistic'])} on 1 d.f., variance {_f(c['variance'])}, "
            f"p = {_p(c['p'])}",
            f"direction: {c['direction']}",
        ]
        for row in d["at"]:
            lines.append(
                f"S_B({row['step']}) − S_A({row['step']}) = {_f(row['diff'])} "
                f"({_f(row['lo'])} – {_f(row['hi'])}, Wald 95%)"
            )
        lines += ["", f"### Per {cause_word}", ""]
        lines.append(PER_CAUSE_CAPTION.format(what=what, alpha=_g(c["alpha"])) + ".")
        lines += [
            "",
            f"| {cause_word} | deaths A | deaths B | χ² | p | q | "
            "could not have detected a hazard ratio below |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in d["per_cause"]:
            lines.append(
                f"| {row['cause']} | {row['deaths_a']} | {row['deaths_b']} | "
                f"{_f(row['statistic'])} | {_p(row['p'])} | {_p(row['q'])} | "
                f"{_f(row['mde_hazard_ratio'])} |"
            )
        lines += [
            "",
            MDE_LINE.format(
                mde=_f(c["mde_hazard_ratio"]),
                alpha=_g(c["alpha"]),
                deaths=d["_deaths_common"],
                share=_f(d["_share_a"]),
            ),
            "",
            f"**{d['_verdict_line']}**",
            "",
        ]
        lines += _cannot_say_lines() + [""]
        return "\n".join(lines)

    def to_json(self) -> str:
        return _dumps({k: v for k, v in self.data.items() if not k.startswith("_")})


@dataclass(frozen=True)
class FixCheckReport:
    data: Mapping[str, Any]

    def to_markdown(self) -> str:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class ChangesReport:
    data: Mapping[str, Any]

    def to_markdown(self) -> str:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError


# ---------- SVG ----------

_W, _PAD_L, _PAD_R = 760, 64, 24
_TOP_Y, _TOP_H = 76, 250
_BOT_Y, _BOT_H = 394, 190
_LEGEND_Y = 632
_H = 672
_INK, _INK2, _GRID, _SURFACE = "#0b0b0b", "#52514e", "#e5e4e0", "#fcfcfb"
_CURVE, _BAND = "#2a78d6", "#cde2fb"
_SLOTS = ("#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
_OTHER = "#7a7975"
_FONT = "font-family=\"-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif\""


def _steps_of(
    values: Sequence[tuple[float, float]], last: float, start: float
) -> list[tuple[float, float]]:
    """The right-continuous step polyline through ``(x, y)`` values, from ``x = 0`` at ``start``
    to ``x = last``."""
    points = [(0.0, start)]
    level = start
    for x, y in values:
        points.append((x, level))
        points.append((x, y))
        level = y
    points.append((max(last, points[-1][0]), level))
    return points


def _ticks(last: int) -> list[int]:
    if last <= 0:
        return [0]
    raw = last / 6
    unit = 1
    for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        unit = candidate
        if candidate >= raw:
            break
    return list(range(0, last + 1, unit))


def _render_svg(report: WhereReport) -> str:
    d = report.data
    run = d["run"]
    last = max(report.last_step, 1)
    boot = d["bootstrap"]
    curve = d["curve"]
    inner_w = _W - _PAD_L - _PAD_R

    def sx(x: float) -> float:
        return _PAD_L + inner_w * x / last

    def sy_top(y: float) -> float:
        return _TOP_Y + _TOP_H * (1.0 - y)

    def sy_bot(y: float) -> float:
        return _BOT_Y + _BOT_H * (1.0 - y)

    def pts(points: Sequence[tuple[float, float]]) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" '
        f'viewBox="0 0 {_W} {_H}" {_FONT} font-size="12">',
        f'<rect x="0" y="0" width="{_W}" height="{_H}" fill="{_SURFACE}"/>',
    ]
    placement = run["placement"]
    parts.append(
        f'<text x="{_PAD_L}" y="22" fill="{_INK}" font-size="14" font-weight="600">'
        f"{escape(run['run_id'])} · {escape(run['target_id'])}</text>"
    )
    parts.append(
        f'<text x="{_PAD_L}" y="40" fill="{_INK2}">placed {placement["placed"]} · '
        f"died {placement['died']} · ended {placement['ended']} · "
        f"timed out {placement['timed out']} · capped {placement['capped']} · "
        f"excluded {sum(placement['excluded'].values())} · "
        f"events: {escape(', '.join(d['events']))}</text>"
    )
    for y0, h, sy, ylabel in (
        (_TOP_Y, _TOP_H, sy_top, "share of runs still going"),
        (_BOT_Y, _BOT_H, sy_bot, "share of runs died, cumulative"),
    ):
        for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
            yy = sy(tick)
            parts.append(
                f'<line x1="{_PAD_L}" y1="{yy:.1f}" x2="{_W - _PAD_R}" y2="{yy:.1f}" '
                f'stroke="{_GRID}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{_PAD_L - 8}" y="{yy + 4:.1f}" fill="{_INK2}" '
                f'text-anchor="end">{tick:g}</text>'
            )
        for tick in _ticks(last):
            xx = sx(tick)
            parts.append(
                f'<line x1="{xx:.1f}" y1="{y0 + h}" x2="{xx:.1f}" y2="{y0 + h + 4}" '
                f'stroke="{_INK2}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{xx:.1f}" y="{y0 + h + 17}" fill="{_INK2}" '
                f'text-anchor="middle">{tick}</text>'
            )
        parts.append(
            f'<line x1="{_PAD_L}" y1="{y0 + h}" x2="{_W - _PAD_R}" y2="{y0 + h}" '
            f'stroke="{_INK2}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{_W - _PAD_R}" y="{y0 + h + 32}" fill="{_INK2}" text-anchor="end">'
            "step</text>"
        )
        parts.append(
            f'<text transform="translate(16 {y0 + h / 2:.1f}) rotate(-90)" fill="{_INK2}" '
            f'text-anchor="middle">{ylabel}</text>'
        )
    # the all-cause curve and its band
    upper = _steps_of([(r["step"], r["hi"]) for r in curve], last, 1.0)
    lower = _steps_of([(r["step"], r["lo"]) for r in curve], last, 1.0)
    poly = [(sx(x), sy_top(y)) for x, y in upper] + [(sx(x), sy_top(y)) for x, y in lower[::-1]]
    parts.append(f'<polygon points="{pts(poly)}" fill="{_BAND}" opacity="0.7"/>')
    centre = _steps_of([(r["step"], r["survival"]) for r in curve], last, 1.0)
    line = [(sx(x), sy_top(y)) for x, y in centre]
    parts.append(
        f'<polyline points="{pts(line)}" fill="none" stroke="{_CURVE}" stroke-width="2" '
        'stroke-linejoin="round"/>'
    )
    parts.append(f'<text x="{_PAD_L}" y="{_TOP_Y - 8}" fill="{_INK}">{escape(KM_CAPTION)}</text>')
    median = d["median_step"]
    if median is not None:
        parts.append(
            f'<line x1="{sx(median):.1f}" y1="{sy_top(0.5):.1f}" x2="{sx(median):.1f}" '
            f'y2="{_TOP_Y + _TOP_H}" stroke="{_INK2}" stroke-width="1" stroke-dasharray="3 3"/>'
        )
        parts.append(
            f'<text x="{sx(median) + 6:.1f}" y="{sy_top(0.5) - 6:.1f}" fill="{_INK2}">'
            f"median step {median}</text>"
        )
    # one polyline per cause, and its bootstrap band at the last death step
    steps = [r["step"] for r in curve]
    legend_x = _PAD_L
    for i, row in enumerate(d["causes"]):
        colour = _SLOTS[i] if i < len(_SLOTS) else _OTHER
        values = report.incidence.get(row["cause"], [])
        points = _steps_of(list(zip(steps, values, strict=True)), last, 0.0)
        parts.append(
            f'<polyline points="{pts([(sx(x), sy_bot(y)) for x, y in points])}" fill="none" '
            f'stroke="{colour}" stroke-width="2" stroke-linejoin="round"/>'
        )
        if steps and row["lo"] is not None and row["hi"] is not None:
            xx = sx(steps[-1]) + 4 * i
            parts.append(
                f'<line x1="{xx:.1f}" y1="{sy_bot(row["lo"]):.1f}" x2="{xx:.1f}" '
                f'y2="{sy_bot(row["hi"]):.1f}" stroke="{colour}" stroke-width="2" '
                'stroke-linecap="round" opacity="0.6"/>'
            )
        parts.append(
            f'<rect x="{legend_x}" y="{_LEGEND_Y - 9}" width="10" height="10" rx="2" '
            f'fill="{colour}"/>'
        )
        label = f"{row['cause']} · {row['deaths']} deaths · F = {row['f']:.3f}"
        parts.append(
            f'<text x="{legend_x + 15}" y="{_LEGEND_Y}" fill="{_INK}">{escape(label)}</text>'
        )
        legend_x += 15 + 7 * len(label) + 20
    parts.append(
        f'<text x="{_PAD_L}" y="{_BOT_Y - 8}" fill="{_INK}">'
        f"{escape(AJ_CAPTION.format(b=boot['b'], seed=boot['seed']))}</text>"
    )
    parts.append(
        f'<text x="{_PAD_L}" y="{_H - 10}" fill="{_INK2}">Poisson Trace · Prove '
        f"{escape(d['prove']['version'])} · {escape(d['clock']['unit'])}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
