"""The reports: markdown to stdout, the JSON structure, and the one SVG. Stdlib only."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

from poisson_trace.look import count

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


def _expected(x: float) -> str:
    """An expected count: three decimals, with thousands separators as counts have."""
    return f"{x:,.3f}"


def _p(p: float) -> str:
    return f"{p:.3f}" if p >= 0.001 else f"{p:.2e}"


# The exact test's p can be smaller than a double can hold, where it reads 0. Below this
# floor the fix check prints the floor as a bound and no figure.
P_FLOOR = 1e-300


def _p_is(p: float) -> str:
    """``p = 0.036``, or ``p < 1e-300`` for a p below the floor."""
    return f"p < {P_FLOOR:g}" if p < P_FLOOR else f"p = {_p(p)}"


def _g(x: float) -> str:
    return f"{x:g}"


def _band(lo: float | None, hi: float | None) -> str:
    return "–" if lo is None or hi is None else f"{_f(lo)} – {_f(hi)}"


def _dumps(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, allow_nan=False) + "\n"


def _named(run: Mapping[str, Any]) -> str:
    """A run as a report's header names it: its name, and its id once for the record."""
    name, run_id = run.get("run_name", run["run_id"]), run["run_id"]
    return run_id if name == run_id else f"{name} ({run_id})"


def _name(run: Mapping[str, Any]) -> str:
    """A run as every other line names it."""
    return str(run.get("run_name", run["run_id"]))


def _header_lines(run: Mapping[str, Any], events: Sequence[str]) -> list[str]:
    tally = run["tally"]
    placement = run["placement"]
    excluded = placement["excluded"]
    cap = "no cap" if run["cap"] is None else f"cap: {count(run['cap'])} spans"
    lines = [
        f"- run: {_named(run)} · target: {run['target_id']} · t_unit: {run['t_unit']} · "
        f"status: {run['status']} · {cap}",
        "- Prove's tally: "
        + " · ".join(
            f"{label} {count(tally[key])}"
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
            f"{label} {count(placement[label])}"
            for label in ("placed", "died", "ended", "timed out", "capped")
        )
        + f" · excluded {count(sum(excluded.values()))}"
        + (
            " (" + "; ".join(f"{reason} {count(n)}" for reason, n in excluded.items() if n) + ")"
            if any(excluded.values())
            else ""
        ),
        f"- events: {', '.join(events)}",
    ]
    return lines


def _cannot_say_lines(sentences: Sequence[str] = CANNOT_SAY) -> list[str]:
    return ["## What this cannot say", ""] + [f"- {sentence}" for sentence in sentences]


COMPARE_POINTER = (
    "For the share of runs that fail, input by input, and the inputs that changed: "
    "poisson-trace fix-check A B --inputs all"
)
GUIDE_NOT_PROMISE = (
    "It is a guide to the next design and not a promise about it: a design built to the "
    "number has an expected limit at the ceiling asked for, so about half the time its own "
    "limit will land a little above."
)
CMH_CAPTION = (
    "exact conditional Cochran-Mantel-Haenszel test, stratified by input over {inputs} "
    "{input_word} ({informative} informative), two-sided; α = {alpha}"
)
DIFFERENCE_CAPTION = "Mantel-Haenszel weights; interval: Sato variance, large-sample, {level}%"
LIMIT_CAPTION = (
    "proportional change on every input, 80% power, α = {alpha}, continuity-corrected normal "
    "approximation to the stratified statistic"
)
FLAGS_CAPTION = (
    "Fisher's exact test per input, Benjamini-Hochberg at q = {alpha} over {tested} "
    "{input_word}; {flagged} flagged"
)
NO_INTERVAL = "no interval: Sato's variance is not positive on these counts"
DISAGREE = "the interval and the test disagree; the line above follows the test"
ONE_RUN = (
    "consistency cannot be measured with one run per input per version: it takes two or more "
    "runs of an input on one version to see whether a failure repeats"
)
FEW_REPEAT = (
    "consistency cannot be measured with {repeating} of {compared} inputs run more than once on "
    "a version: it takes at least half the inputs run two or more times on a version to see "
    "whether a failure repeats"
)
COPIES = (
    "no input gave mixed outcomes across its repeats in the {arm} arm: the repeats may be "
    "copies of one another, and the by-input reading is the safer one"
)


def _points(x: float, *, signed: bool = False, places: int | None = None) -> str:
    """A share as points: one decimal, two below one point."""
    value = 100.0 * x
    if places is None:
        places = 1 if abs(value) >= 1.0 else 2
    return f"{value:+.{places}f}" if signed and value != 0.0 else f"{value:.{places}f}"


def _percent(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _sig(x: float) -> str:
    return f"{x:.3g}"


def _count(n: int, word: str) -> str:
    return f"{count(n)} {word}" if n == 1 else f"{count(n)} {word}s"


def _gap(seconds: float) -> str:
    """Hours and minutes, whole minutes rounded down: ``40 h 50 min``, ``56 min``."""
    if seconds < 60.0:
        return f"{int(seconds)} s"
    hours, minutes = divmod(int(seconds // 60), 60)
    return f"{count(hours)} h {minutes} min" if hours else f"{minutes} min"


def _tally_line(label: str, tally: Mapping[str, Any]) -> str:
    return f"- Prove's tally ({label}): " + " · ".join(
        f"{name} {count(tally[key])}"
        for name, key in (
            ("rows", "rows"),
            ("with outcome", "with_outcome"),
            ("no outcome", "no_outcome"),
            ("timed out", "timed_out"),
            ("infra", "infra"),
            ("other", "other"),
        )
    )


def _run_lines(label: str, run: Mapping[str, Any]) -> list[str]:
    declared = run["declared_repeats"]
    return [
        f"- {label}: {_named(run)} · target: {run['target_id']} · status: {run['status']} · "
        f"started: {run['created_at']} · declared repeats: "
        f"{'not recorded' if declared is None else count(declared)}",
        _tally_line(label, run["tally"]),
    ]


def _config_cell(config: Any) -> str:
    text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.replace("|", "\\|")


def _flag_lines(block: Mapping[str, Any], top: int, first: str, second: str) -> list[str]:
    """The flags table and the attainability sentences. ``first`` and ``second`` name the two
    arms in the column heads and in the flag."""
    tested = block["tested"]
    lines = [
        FLAGS_CAPTION.format(
            alpha=_g(block["alpha"]),
            tested=count(tested),
            input_word="input" if tested == 1 else "inputs",
            flagged=count(block["flagged"]),
        )
        + ".",
        "",
        f"| input | {first} failed/runs | {second} failed/runs | change | p | q | flag | "
        "could not have detected a rise below |",
        "|---|---|---|---|---|---|---|---|",
    ]
    flagged = [r for r in block["rows"] if r["flag"] is not None]
    rest = [r for r in block["rows"] if r["flag"] is None]
    shown = flagged + rest[: max(0, top - len(flagged))]
    for r in shown:
        flag = "–" if r["flag"] is None else r["flag"][: -len("B")] + second
        lines.append(
            f"| {_config_cell(r['config'])} | {count(r['failed_a'])}/{count(r['runs_a'])} | "
            f"{count(r['failed_b'])}/{count(r['runs_b'])} | "
            f"{_points(r['change'], signed=True, places=1)} points | "
            f"{_p(r['p'])} | {_p(r['q'])} | {flag} | "
            f"{_points(r['limit_rise'], places=1)} points |"
        )
    if len(shown) < tested:
        lines += [
            "",
            f"{count(len(shown))} of {count(tested)} inputs shown, by ascending p; "
            "--json lists all.",
        ]
    lone = (
        f"A lone changed input is flagged only if its p is below α / M = "
        f"{_sig(block['lone_threshold'])}, and the smallest p an input of this design can give "
        f"is {_sig(block['smallest_attainable_p'])}: "
    )
    if block["together"] is None:
        lone += "no input can be flagged whatever happens"
    elif block["together"] == 1:
        lone += "a lone change can be flagged"
    else:
        lone += (
            "a lone changed input cannot be flagged; at least "
            f"{count(block['together'])} inputs would have to flip completely together"
        )
    lone += (
        f"; a lone complete flip needs {count(block['lone_flip_repeats'])} repeats per arm. "
        "An input with no flag is not an input that did not change."
    )
    return lines + ["", lone]


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
        lines = [f"# Poisson Trace · where runs die · {_name(run)}", "", "## Run", ""]
        lines += _header_lines(run, d["events"])
        if d.get("note") is not None:
            # a run with no traces: its one line, in place of an empty curve and causes table
            lines += ["", d["note"], "", *_cannot_say_lines(), ""]
            return "\n".join(lines)
        lines += ["", "## Survival over step index", "", f"{KM_CAPTION}.", ""]
        lines += ["| step | at risk | died | S | 95% band |", "|---|---|---|---|---|"]
        for row in d["curve"]:
            lines.append(
                f"| {count(row['step'])} | {count(row['at_risk'])} | {count(row['died'])} | "
                f"{_f(row['survival'])} | "
                f"{_band(row['lo'], row['hi'])} |"
            )
        if not d["curve"]:
            lines.append("| – | – | 0 | 1.000 | 1.000 – 1.000 |")
        lines.append("")
        median = d["median_step"]
        lines.append(f"median step: {'not reached' if median is None else count(median)}")
        for row in d["at"]:
            lines.append(
                f"S({count(row['step'])}) = {_f(row['survival'])} ({_band(row['lo'], row['hi'])})"
            )
        boot = d["bootstrap"]
        lines += ["", f"## Where they die, by {by_label}", ""]
        lines += [AJ_CAPTION.format(b=count(boot["b"]), seed=boot["seed"]) + ".", ""]
        last = d["curve"][-1]["step"] if d["curve"] else None
        at_label = f"F at step {count(last)}" if last is not None else "F"
        lines += [f"| {cause_word} | deaths | {at_label} | 95% band |", "|---|---|---|---|"]
        for row in d["causes"]:
            lines.append(
                f"| {row['cause']} | {count(row['deaths'])} | {_f(row['f'])} | "
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
            lines.append(f"| {name} | {count(reached.get(name, 0))} of {count(placed)} | {flag} |")
        for name in declared["undeclared_steps"]:
            lines.append(
                f"| {name} | {count(reached.get(name, 0))} of {count(placed)} | undeclared |"
            )
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
            f"# Poisson Trace · compare · {_name(a)} (before) and {_name(b)} (after)",
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
                cells=count(c["cells"]),
                cell_word="cell" if c["cells"] == 1 else "cells",
                a_only=count(c["excluded_cells"]["a_only"]),
                b_only=count(c["excluded_cells"]["b_only"]),
                salt=salt,
                alpha=_g(c["alpha"]),
            )
            + "."
        )
        lines += ["", "| arm | placed | died | observed | expected |", "|---|---|---|---|---|"]
        deaths = c["observed_a"] + d["_observed_b"]
        lines.append(
            f"| A (before) | {count(a['placement']['placed'])} | {count(a['placement']['died'])} | "
            f"{count(c['observed_a'])} | {_expected(c['expected_a'])} |"
        )
        lines.append(
            f"| B (after) | {count(b['placement']['placed'])} | {count(b['placement']['died'])} | "
            f"{count(d['_observed_b'])} | {_expected(deaths - c['expected_a'])} |"
        )
        lines += [
            "",
            f"statistic: χ² = {_f(c['statistic'])} on 1 d.f., variance {_f(c['variance'])}, "
            f"p = {_p(c['p'])}",
            f"direction: {c['direction']}",
        ]
        for row in d["at"]:
            lines.append(
                f"S_B({count(row['step'])}) − S_A({count(row['step'])}) = {_f(row['diff'])} "
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
                f"| {row['cause']} | {count(row['deaths_a'])} | {count(row['deaths_b'])} | "
                f"{_f(row['statistic'])} | {_p(row['p'])} | {_p(row['q'])} | "
                f"{_f(row['mde_hazard_ratio'])} |"
            )
        lines += [
            "",
            MDE_LINE.format(
                mde=_f(c["mde_hazard_ratio"]),
                alpha=_g(c["alpha"]),
                deaths=count(d["_deaths_common"]),
                share=_f(d["_share_a"]),
            ),
            "",
            f"**{d['_verdict_line']}**",
            "",
        ]
        guidance = c.get("guidance")
        if guidance is not None:
            lines += self._guidance_lines(guidance) + [""]
        lines += [COMPARE_POINTER, ""]
        lines += _cannot_say_lines() + [""]
        return "\n".join(lines)

    def _guidance_lines(self, g: Mapping[str, Any]) -> list[str]:
        d = self.data
        c = d["comparison"]
        asked = _g(c["max_mde_hr"])
        lines = ["## Guidance", ""]
        if g["deaths"] is None:
            lines.append(f"- no number of deaths reaches a hazard ratio of {asked}")
        else:
            lines += [
                f"- deaths: {count(g['deaths'])} would bring the detectable hazard ratio to "
                f"{asked}; this design has {count(d['_deaths_common'])}",
                f"- runs: {count(g['runs'])} placed runs at the present share of deaths, which is "
                f"{count(g['inputs'])} inputs at the present repeats, or {count(g['repeats'])} "
                f"repeats per arm on these {count(c['cells'])}; this design has "
                f"{count(d['_placed_common'])} placed runs",
            ]
        if g["accepts_at"] is not None:
            lines.append(
                f"- ceiling: --max-mde-hr {g['accepts_at']:.3f} accepts this design as it stands"
            )
        lines += [
            "",
            "These numbers assume the share of runs that die holds in the next runs, and that "
            "new inputs resemble the present ones. " + GUIDE_NOT_PROMISE,
        ]
        return lines

    def to_json(self) -> str:
        return _dumps({k: v for k, v in self.data.items() if not k.startswith("_")})


@dataclass(frozen=True)
class FixCheckReport:
    """``data`` is the ``poisson-trace.fix-check/1`` structure, keys in order; keys that start
    with an underscore serve the markdown only."""

    data: Mapping[str, Any]

    def to_markdown(self) -> str:
        d = self.data
        old, new = d["runs"]["old"], d["runs"]["new"]
        lines = [
            f"# Poisson Trace · fix check · {_name(old)} (old) and {_name(new)} (new)",
            "",
            "## Runs",
            "",
        ]
        lines += self._header_lines()
        lines += ["", "## The control", ""]
        lines += self._control_lines()
        lines += ["", "## The comparison", ""]
        lines += self._comparison_lines()
        lines += ["", "## Consistency", ""]
        lines += self._consistency_lines()
        lines += ["", "## What it could not have detected", ""]
        lines += self._limit_lines()
        lines += ["", f"**{d['_verdict_line']}**", ""]
        if d.get("_disagree"):
            lines += [DISAGREE, ""]
        if d["guidance"] is not None:
            lines += self._guidance_lines() + [""]
        lines += ["## Inputs that changed", ""]
        lines += _flag_lines(d["changes"], d["_top"], "old", "new")
        lines += [""] + _cannot_say_lines(d["cannot_say"]) + [""]
        return "\n".join(lines)

    def _header_lines(self) -> list[str]:
        d = self.data
        inputs, rows = d["inputs"], d["rows"]
        lines = _run_lines("old", d["runs"]["old"]) + _run_lines("new", d["runs"]["new"])
        lines.append(f"- the two runs started {_gap(d['gap_seconds'])} apart")
        lines.append(f"- events: {', '.join(d['events'])}")
        lines += [f"- {note}" for note in d.get("_event_notes", [])]
        if inputs["rule"] == "all":
            rule = "every input either run carries"
        else:
            rule = (
                f"inputs that failed at least {_count(inputs['min_failures'], 'time')} in "
                f"{d.get('_failing_from') or inputs['failing_from']}"
            )
        left = inputs["left_out"]
        reasons = "; ".join(f"{reason} {count(n)}" for reason, n in left.items() if n)
        lines.append(
            f"- inputs: {rule} · selected {count(inputs['selected'])} · compared "
            f"{count(inputs['compared'])} · left out {count(sum(left.values()))}"
            + (f" ({reasons})" if reasons else "")
        )
        lines.append(
            "- rows used: "
            + " · ".join(
                f"{arm} {count(rows[arm]['runs'])} (timed out {count(rows[arm]['timed_out'])}, "
                f"no outcome {count(rows[arm]['no_outcome'])})"
                for arm in ("old", "new")
            )
        )
        lines.append(
            "- inputs short of the declared repeats: "
            f"old {count(rows['old']['short'])} · new {count(rows['new']['short'])}"
        )
        lines.append(
            "- inputs with mixed outcomes across their repeats: "
            f"old {count(rows['old']['mixed'])} · new {count(rows['new']['mixed'])}"
        )
        lines += [f"- {COPIES.format(arm=arm)}" for arm in d.get("_copies", [])]
        return lines

    def _control_lines(self) -> list[str]:
        d = self.data
        lines = [
            "The old version, re-run on the same inputs with nothing changed.",
            "",
            "| version | runs | failed | failure share | did not fail on re-run |",
            "|---|---|---|---|---|",
        ]
        for arm in ("old", "new"):
            r = d["rows"][arm]
            stayed = d["control"][f"{arm}_did_not_fail_share"]
            lines.append(
                f"| {arm} | {count(r['runs'])} | {count(r['failed'])} | {_percent(1.0 - stayed)} | "
                f"{_percent(stayed)} |"
            )
        lines += [
            "",
            "Re-running these inputs and counting the runs that did not fail would have read "
            f"{_percent(d['control']['old_did_not_fail_share'])} on the old version, where "
            "nothing changed.",
        ]
        return lines

    def _comparison_lines(self) -> list[str]:
        d = self.data
        t, diff, by = d["test"], d["difference"], d["by_input"]
        inputs = d["inputs"]
        lines = [
            CMH_CAPTION.format(
                inputs=count(inputs["compared"]),
                input_word="input" if inputs["compared"] == 1 else "inputs",
                informative=count(inputs["informative"]),
                alpha=_g(t["alpha"]),
            )
            + ".",
            "",
            f"new failures: observed {count(t['observed_new'])}, expected "
            f"{_expected(t['expected_new'])}, variance {_f(t['variance'])}; {_p_is(t['p'])}",
        ]
        caption = DIFFERENCE_CAPTION.format(level=_g(100.0 * (1.0 - t["alpha"])))
        if diff["variance"] is None:
            lines.append(
                f"difference: {_points(diff['points'], signed=True)} points, new minus old "
                f"(Mantel-Haenszel weights); {NO_INTERVAL}"
            )
        else:
            figures = (diff["points"], diff["lo"], diff["hi"])
            places = 2 if all(abs(100.0 * x) < 1.0 for x in figures) else 1
            point, lo, hi = (_points(x, signed=True, places=places) for x in figures)
            lines.append(f"difference: {point} points, new minus old ({lo} to {hi}; {caption})")
        if by["method"] == "exact":
            how = "exact"
        else:
            how = f"{count(by['draws'])} draws, seed = {by['seed']}"
        lines.append(
            f"by input: p = {_p(by['p'])} (sign-flip over the {_count(by['moved'], 'input')} "
            f"that moved, {how}); not part of the line below"
        )
        return lines

    def _consistency_lines(self) -> list[str]:
        c = self.data["consistency"]
        if self.data.get("_one_run"):
            return [f"failure share {_f(c['failure_share'])}", ONE_RUN]
        few = self.data.get("_few_repeat")
        if few is not None:
            repeating, compared = few
            sentence = FEW_REPEAT.format(repeating=count(repeating), compared=count(compared))
            return [f"failure share {_f(c['failure_share'])}", sentence]
        kappa = c["kappa"]
        lines = [
            f"failure share {_f(c['failure_share'])} · fails again {_f(c['fails_again'])} · "
            f"κ {_f(kappa)} · within-input variance {_f(c['within'])} against pooled "
            f"{_f(c['pooled'])}"
        ]
        if kappa is not None and kappa < 1.0:
            lines.append(
                "a comparison that ignored the inputs would need 1/(1 − κ) = "
                f"{1.0 / (1.0 - kappa):.2f} times the runs"
            )
        return lines

    def _limit_lines(self) -> list[str]:
        limits = self.data["limits"]
        alpha = _g(self.data["test"]["alpha"])
        lines = [LIMIT_CAPTION.format(alpha=alpha) + ".", ""]
        largest = self.data["_largest"]
        for name, extreme in (("drop", "every failure gone"), ("rise", "every run failing")):
            limit = limits[name]
            if limit is None:
                lines.append(
                    f"- a {name} in failure share: no limit; even {extreme}, a {name} of "
                    f"{_points(largest[name])} points, would have been detected less than four "
                    "times in five"
                )
            else:
                lines.append(
                    f"- a {name} in failure share: could not have detected one below "
                    f"{_points(limit)} points"
                )
        return lines

    def _guidance_lines(self) -> list[str]:
        d = self.data
        g = d["guidance"]
        compared = d["inputs"]["compared"]
        asked = _g(100.0 * d["limits"]["max_mde"])
        lines = ["## Guidance", ""]
        if g["repeats"] is None:
            lines.append(f"- no number of repeats on these inputs reaches {asked} points")
        else:
            lines.append(
                f"- repeats: {count(g['repeats'])} per arm on these "
                f"{_count(compared, 'input')} would bring the limit to {asked} points"
            )
        if g["inputs"] is None:
            lines.append(f"- no number of inputs at the present repeats reaches {asked} points")
        else:
            lines.append(
                f"- inputs: {count(g['inputs'])} inputs like these, at the present repeats, would "
                "do the same"
            )
        if g["accepts_at"] is None:
            lines.append("- ceiling: no value of --max-mde accepts this design as it stands")
        else:
            lines.append(
                f"- ceiling: --max-mde {g['accepts_at']:.4f} accepts this design as it stands"
            )
        lines += [
            "",
            "These numbers assume the next runs fail at the rates these did, input by input, "
            "and that new inputs resemble the present ones: for failing inputs chosen by a "
            "rule, chosen by the same rule. " + GUIDE_NOT_PROMISE,
        ]
        return lines

    def to_json(self) -> str:
        return _dumps({k: v for k, v in self.data.items() if not k.startswith("_")})


@dataclass(frozen=True)
class ChangesReport:
    """``data`` is the ``poisson-trace.changes/1`` structure, keys in order; keys that start
    with an underscore serve the markdown only."""

    data: Mapping[str, Any]

    def to_markdown(self) -> str:
        d = self.data
        a, b = d["runs"]["a"], d["runs"]["b"]
        lines = [
            f"# Poisson Trace · changes · {_name(a)} (A) and {_name(b)} (B)",
            "",
            "## Runs",
            "",
        ]
        lines += _run_lines("A", a) + _run_lines("B", b)
        if "_gap_seconds" in d:
            lines.append(f"- the two runs started {_gap(d['_gap_seconds'])} apart")
        lines.append(f"- events: {', '.join(d['events'])}")
        lines += [f"- {note}" for note in d.get("_event_notes", [])]
        held = d.get("_inputs")
        if held is not None:
            lines.append(
                f"- inputs: A carries {count(held['a'])}, B carries {count(held['b'])} · compared "
                f"{count(d['tested'])}, each with an outcome in both runs · in A only "
                f"{count(held['a_only'])} · in B only {count(held['b_only'])}"
            )
        lines += ["", "## Inputs that changed", ""]
        lines += _flag_lines(d, d.get("_top", 10), "A", "B")
        lines += [""] + _cannot_say_lines(d["cannot_say"]) + [""]
        return "\n".join(lines)

    def to_json(self) -> str:
        return _dumps({k: v for k, v in self.data.items() if not k.startswith("_")})


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
        f"{escape(_name(run))} · {escape(run['target_id'])}</text>"
    )
    parts.append(
        f'<text x="{_PAD_L}" y="40" fill="{_INK2}">placed {count(placement["placed"])} · '
        f"died {count(placement['died'])} · ended {count(placement['ended'])} · "
        f"timed out {count(placement['timed out'])} · capped {count(placement['capped'])} · "
        f"excluded {count(sum(placement['excluded'].values()))} · "
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
                f'text-anchor="middle">{count(tick)}</text>'
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
            f"median step {count(median)}</text>"
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
        label = f"{row['cause']} · {count(row['deaths'])} deaths · F = {row['f']:.3f}"
        parts.append(
            f'<text x="{legend_x + 15}" y="{_LEGEND_Y}" fill="{_INK}">{escape(label)}</text>'
        )
        legend_x += 15 + 7 * len(label) + 20
    parts.append(
        f'<text x="{_PAD_L}" y="{_BOT_Y - 8}" fill="{_INK}">'
        f"{escape(AJ_CAPTION.format(b=count(boot['b']), seed=boot['seed']))}</text>"
    )
    parts.append(
        f'<text x="{_PAD_L}" y="{_H - 10}" fill="{_INK2}">Poisson Trace · Prove '
        f"{escape(d['prove']['version'])} · {escape(d['clock']['unit'])}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
