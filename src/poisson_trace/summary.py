"""The plain parts at the head of a report: the sentence of its first line, the four labelled
lines of ``## Summary`` and the bullets of ``## Before you act on this``.

Each is composed from the report's own data, its private keys included, so every number is one
the report prints, or a sum or difference of its counts, rounded as the rules below say. The
words say no more than the statistics under them: *too small to tell* is "Can't tell yet", *no
significant difference* is "No clear change", and a range rules a size in or out only where it
is reliable, and then always "if tries of an input are independent".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from poisson_trace.look import count
from poisson_trace.report import _gap, _p, file_timed, input_words, value_words

# How a Next that ends on a placeholder ceiling says to choose it.
CHOOSE_X = "choosing X before you look"

SIDE = (
    "Trace can't tell whether they were run side by side, so anything else that changed between "
    "them (the provider, the model behind the API, the day) may be part of the difference, in "
    "either direction."
)
SIDE_BY_SIDE = "Before putting the difference down to the version, run both side by side."
FRESH = (
    "Even with good estimates, about half of runs built to it end up a little too small. Make it "
    "a fresh run, judged on its own"
)
LABEL_ONLY = "That changes the label only, not the evidence."
# the top line where no run failed in either version on the inputs compared
NEITHER_FAILED = "neither version failed"

# the kinds of step Prove records, as a sentence names the place a try stopped
KIND_WORDS = {
    "llm": "a model call",
    "tool": "a tool call",
    "retrieval": "a retrieval",
    "db": "a database call",
    "http": "an HTTP call",
    "agent": "an agent step",
    "other": "another kind of step",
}

# the inputs a sentence names before it says how many more there are
NAMED = 3


@dataclass(frozen=True)
class Plain:
    """A report's plain parts. ``follows`` is the command the last ``next:`` line runs where
    the Next calls for another than the verb's own; None keeps the verb's."""

    sentence: str
    lines: tuple[tuple[str, str], ...]
    caveats: tuple[str, ...] = ()
    follows: str | None = None


# ---------- numbers and words ----------


def num(value: float) -> str:
    """Points, or failures per 100 tries: whole from 10 up, one decimal below, two below 1."""
    v = abs(value)
    if round(v) >= 10:
        return f"{v:.0f}"
    return f"{v:.1f}" if round(v, 2) >= 1 else f"{v:.2f}"


def points(share: float, asked: float | None = None) -> str:
    """A share as points, with one more decimal where rounding would make it the size asked."""
    said = num(100.0 * share)
    if asked is not None and round(float(said), 6) == round(100.0 * asked, 6):
        v = abs(100.0 * share)
        said = f"{v:.1f}" if v >= 10 else (f"{v:.2f}" if v >= 1 else f"{v:.3f}")
    return said


def a_or_an(number: str) -> str:
    """The article before a number word as it is spoken: an 8-, an 11-, an 18-, an 80-point."""
    whole = number.split(".")[0]
    return "an" if whole.startswith("8") or whole in ("11", "18") else "a"


def percent(share: float) -> str:
    return f"{100.0 * share:.1f}%"


def two_figures(p: float) -> str:
    return f"{p:.2f}" if p >= 0.01 else f"{p:.2g}"


def and_list(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def or_list(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def tries(n: int) -> str:
    return f"{count(n)} {'try' if n == 1 else 'tries'}"


def inputs(n: int) -> str:
    return f"{count(n)} {'input' if n == 1 else 'inputs'}"


def range_words(lo: float, hi: float) -> str:
    """A range of differences as failures per 100 tries."""
    low, high = 100.0 * lo, 100.0 * hi
    if low < 0.0 < high:
        return f"anything from {num(low)} fewer failures per 100 tries to {num(high)} more"
    if high <= 0.0:
        return f"anything from {num(high)} to {num(low)} fewer failures per 100 tries"
    return f"anything from {num(low)} to {num(high)} more failures per 100 tries"


def chance(p: float) -> str:
    """How often chance alone gives a gap at least this big."""
    if p < 0.001:
        return "less than once in 1,000"
    if p < 0.01:
        return f"about {round(1000 * p)} times in 1,000"
    n = round(100 * p)
    return "about once in 100" if n == 1 else f"about {n} times in 100"


def chance_sentence(p: float) -> str:
    return (
        "If each input failed equally often under both versions, a gap at least this big, either "
        f"way, would turn up {chance(p)} (counting tries as independent)."
    )


def alike(kappa: float | None) -> str | None:
    """How alike the tries of one input are, from the agreement: shown from 0.3, much from 0.7."""
    if kappa is None or kappa < 0.3:
        return None
    return "much" if kappa >= 0.7 else "fairly"


def _first_pair(config: Any) -> tuple[str, str] | None:
    if not isinstance(config, Mapping) or len(config) < 2:
        return None
    key, value = next(iter(config.items()))
    return str(key), value_words(value)


def shared_key(configs: Sequence[Any]) -> tuple[str, str] | None:
    """The first key and value several inputs share, where they differ only in their settings."""
    firsts = {_first_pair(c) for c in configs}
    if len(configs) < 2 or len(firsts) != 1 or None in firsts:
        return None
    return firsts.pop()


def inputs_named(configs: Sequence[Any]) -> str:
    """Inputs as a sentence names them: one key's value at several settings, or each in turn."""
    shared = shared_key(configs)
    if shared is not None:
        settings = "both settings" if len(configs) == 2 else f"{count(len(configs))} settings"
        return f"{shared[0]} {shared[1]} at {settings}"
    named = [input_words(c) for c in configs[:NAMED]]
    more = len(configs) - NAMED
    if more > 0:
        named.append(f"{count(more)} more")
    return named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]


def unit_of(run: Mapping[str, Any]) -> str:
    """The word for a run's clock: turn for a run counted in turns, step otherwise."""
    return "turn" if run.get("t_unit") == "turns" else "step"


def _name(run: Mapping[str, Any]) -> str:
    return str(run.get("run_name", run["run_id"]))


# ---------- the caveats every comparison shares ----------


def when_they_ran(runs: Sequence[Mapping[str, Any]], gap: float | None) -> str:
    """When the two ran, and that Trace can't tell whether it was side by side: not known where
    a start is a file's modification time, and within a minute for two JUnit suites' times."""
    filed = [_name(run) for run in runs if file_timed(run)]
    if len(filed) == 1:
        why = f"the start of {filed[0]} is when its file was written or copied"
    elif filed:
        why = f"the starts of {filed[0]} and {filed[1]} are when their files were written or copied"
    elif gap is None:
        why = "a start time is not recorded"
    else:
        why = ""
    if why:
        return (
            f"Trace can't tell when they ran ({why}), so it can't tell whether they were run side "
            "by side either: anything else that changed between them (the provider, the model "
            "behind the API, the day) may be part of the difference, in either direction."
        )
    assert gap is not None
    starts = [run.get("_start") for run in runs]
    froms = {s.get("from") if isinstance(s, Mapping) else None for s in starts}
    tools = {s.get("tool") if isinstance(s, Mapping) else None for s in starts}
    if froms == {"file"} and tools == {"junit"} and gap < 60.0:
        return (
            f"Their reports' earliest suite timestamps are {_gap(gap)} apart, so they started "
            "within a minute of each other; Trace still can't confirm they were run side by side, "
            "so anything else that changed between them (the provider, the model behind the API, "
            "the day) may be part of the difference, in either direction."
        )
    if froms == {"file name"}:
        return f"The times in their files' names are {_gap(gap)} apart. {SIDE}"
    return f"They started {_gap(gap)} apart. {SIDE}"


def same_target(target: str) -> str:
    return (
        f"Both runs name the same target ({target}); Trace can't tell what differs between them, "
        "only what you tell it."
    )


def targets_differ(a: str, b: str, *, matching: bool) -> str:
    every = ", and every input failed the same number of times in both" if matching else ""
    return (
        f"Their targets differ ({a}, {b}){every}: if one replays the other, this is not a "
        "comparison of two versions."
    )


def replay_check(a: str, b: str, then: str) -> str:
    return f"First check whether {b} replays {a}; if it does, {then}"


# ---------- fix-check ----------


def failed_when(manifest: Any, events: Sequence[str]) -> str:
    """When a try counts as failed: the import's own rule for an imported run read by its
    failures, else the outcomes given as events."""
    from poisson_trace.ingest.cut import MISSED

    environment = getattr(manifest, "environment", None)
    recorded = environment.get("import") if isinstance(environment, Mapping) else None
    if isinstance(recorded, Mapping) and isinstance(recorded.get("declared"), Mapping):
        if list(events) == [MISSED]:
            from poisson_trace.ingest.importing import _failed_when

            return _failed_when({"declared": recorded["declared"], "tool": recorded.get("tool")})
    return "it ended " + or_list(sorted(events))


def _extra(row: Mapping[str, Any]) -> float:
    """An input's extra failures in the new version: its new failures less the old version's
    rate at the new version's tries."""
    return float(row["failed_b"] - row["failed_a"] * row["runs_b"] / row["runs_a"])


@dataclass(frozen=True)
class _Pair:
    """What the fix check's plain parts read from its data, under one roof."""

    d: Mapping[str, Any]

    @property
    def asked(self) -> str:
        return f"{100.0 * self.ceiling:g}"

    @property
    def ceiling(self) -> float:
        return float(self.d["limits"]["max_mde"])

    @property
    def old_share(self) -> float:
        old = self.d["rows"]["old"]
        return float(old["failed"] / old["runs"])

    @property
    def counts(self) -> str:
        old, new = self.d["rows"]["old"], self.d["rows"]["new"]
        return (
            f"The new version failed {count(new['failed'])} of {count(new['runs'])} tries and "
            f"the old {count(old['failed'])} of {count(old['runs'])}"
        )

    @property
    def flagged(self) -> list[Mapping[str, Any]]:
        return [r for r in self.d["changes"]["rows"] if r["flag"] is not None]

    @property
    def targets(self) -> tuple[str, str]:
        runs = self.d["runs"]
        return str(runs["old"]["target_id"]), str(runs["new"]["target_id"])

    @property
    def matching(self) -> bool:
        """Every input failed as often, of as many tries, in both runs."""
        return all(
            r["failed_a"] == r["failed_b"] and r["runs_a"] == r["runs_b"]
            for r in self.d["changes"]["rows"]
        )

    @property
    def replay(self) -> bool:
        return self.targets[0] != self.targets[1] and self.matching

    @property
    def no_outcome(self) -> tuple[int, int]:
        held = self.d.get("_no_outcome") or {}
        return int(held.get("old", 0)), int(held.get("new", 0))

    @property
    def no_outcome_gap(self) -> bool:
        """The gap in tries with no outcome is as large as the whole gap in failures."""
        a, b = self.no_outcome
        rows = self.d["rows"]
        return a != b and abs(b - a) >= abs(rows["new"]["failed"] - rows["old"]["failed"])

    @property
    def more_no_outcome(self) -> str:
        a, b = self.no_outcome
        return "the new version" if b > a else "the old version"

    @property
    def weak(self) -> bool:
        """The design cannot see the size asked: no rise limit, or the size asked at 80% or
        more of the old version's failure share."""
        return self.d["limits"]["rise"] is None or self.ceiling >= 0.8 * self.old_share


def _compared(p: _Pair) -> str:
    d = p.d
    old, new = d["runs"]["old"], d["runs"]["new"]
    rows, held = d["rows"], d["inputs"]
    each = (
        f"{tries(rows['old']['runs'])} of each"
        if rows["old"]["runs"] == rows["new"]["runs"]
        else f"{tries(rows['old']['runs'])} of the old, {count(rows['new']['runs'])} of the new"
    )
    n = held["compared"]
    if held["rule"] == "failing-from":
        times = held["min_failures"]
        failed = "failed" if times in (None, 1) else f"failed at least {count(times)} times"
        where = f"on the {inputs(n)} that {failed} in {d['_failing_from']} and were run again"
    else:
        where = f"on the same {inputs(n)}"
    rules = d.get("_rules") or {}
    rule_old, rule_new = rules.get("old", ""), rules.get("new", "")
    if rule_old == rule_new:
        rule = f"A try counts as failed when {rule_old}."
    else:
        rule = (
            f"A try counts as failed when {rule_old} in the old run, and when {rule_new} in the "
            "new."
        )
    said = f"old {_name(old)} against new {_name(new)}, {where}: {each}. {rule}"
    if d.get("_new_first"):
        said += (
            f" Check the order: the one you gave as new started {_gap(d['gap_seconds'])} before "
            "the old one."
        )
    if p.targets[0] != p.targets[1]:
        said += " " + targets_differ(*p.targets, matching=p.matching)
    return said


def _shared_caveats(p: _Pair) -> list[str]:
    """The caveats of every verdict, in their order: when they ran, the target, the inputs
    compared, the tries with no outcome, the range, a rise the design can hardly see, how alike
    an input's tries are, and a size asked near the most there is to see."""
    d = p.d
    old, new = d["runs"]["old"], d["runs"]["new"]
    held = d["inputs"]
    said = [when_they_ran([old, new], d["gap_seconds"])]
    if p.targets[0] == p.targets[1]:
        said.append(same_target(p.targets[0]))
    if held["rule"] == "failing-from":
        which = d["_failing_from"]
        n, selected = held["compared"], held["selected"]
        times = held["min_failures"]
        failed = "failed" if times in (None, 1) else f"failed at least {count(times)} times"
        if n < selected:
            said.append(
                f"{inputs(selected)} {failed} in {which}; only the {count(n)} run again on both "
                "versions are compared, so this speaks for those alone. If those were picked for "
                "re-running because they looked repaired, the result leans the new version's way."
            )
        old_rows = d["rows"]["old"]
        said.append(
            f"On these inputs, picked because they {failed} in {which}, the old version's run "
            f"passed {count(old_rows['runs'] - old_rows['failed'])} of "
            f"{count(old_rows['runs'])} tries. "
            "Inputs picked for failing once often do not fail when run again, so not failing on a "
            "re-run is not a repair by itself; Trace compares the new version's passes with the "
            "old version's, allowing for chance."
        )
    else:
        # inputs left out for want of an outcome are said with the tries that had none, below
        left = {
            reason: k
            for reason, k in held["left_out"].items()
            if k and not reason.startswith("no outcome")
        }
        if left:
            total = sum(left.values())
            reasons = "; ".join(f"{count(k)} {reason}" for reason, k in left.items())
            said.append(f"{inputs(total)} {'was' if total == 1 else 'were'} left out ({reasons}).")
    a, b = p.no_outcome
    if a or b:
        line = f"{count(a)} tries of the old and {count(b)} of the new had no outcome"
        left_out = held["left_out"]
        k = sum(n for reason, n in left_out.items() if reason.startswith("no outcome"))
        if k:
            line += (
                f"; the {inputs(k)} that leaves without a result on one side "
                f"{'is' if k == 1 else 'are'} left out on both versions."
            )
        else:
            line += ", and they are left out."
        if a != b:
            line += (
                f" If no outcome means a bad answer, {p.more_no_outcome}, which has more of them, "
                "fails more often than it looks."
            )
        gap_failed = abs(d["rows"]["new"]["failed"] - d["rows"]["old"]["failed"])
        if p.no_outcome_gap:
            size = "as large as" if abs(b - a) == gap_failed else "larger than"
            line += (
                f" The difference in them ({count(abs(b - a))}) is {size} the whole gap in "
                f"failures ({count(gap_failed)})."
            )
        said.append(line)
    diff = d["difference"]
    lo, hi = diff["lo"], diff["hi"]
    if lo is None or hi is None:
        said.append("Trace can't put a range around the difference on these counts.")
    elif d["_reliable"]:
        kept = "does not include" if lo > -p.ceiling else "includes"
        said.append(
            f"These results fit {range_words(lo, hi)} (ranges built this way hold the true "
            f"difference about {d['_level']:g} times in 100, if tries are independent), which "
            f"{kept} {a_or_an(p.asked)} {p.asked}-point drop."
        )
    elif d.get("_none_failed"):
        # nothing failed, so there is no drop in these results to fit: say what could still
        # differ, and that even that figure is rough here
        said.append(
            "Neither version failed here. Their true failure rates could still differ by about "
            f"{num(100.0 * max(-lo, hi))} points either way, and with {d['_rough'][0]} even that "
            "figure is rough: don't use it to rule any size in or out."
        )
    else:
        why = [
            "the range and the test disagree" if w.endswith("disagree") else w for w in d["_rough"]
        ]
        said.append(
            f"These results fit {range_words(lo, hi)}, but that range is only a rough guide here "
            f"and may be off either way ({and_list(why)}): don't use it to rule sizes in or out."
        )
    if d["limits"]["rise"] is None:
        said.append(
            "This design is weak at spotting the new version failing more: even if it failed every "
            "try, Trace would catch that less than 4 times in 5. So this is no evidence that the "
            "new version does not fail more often."
        )
    kappa = d["consistency"]["kappa"]
    how = alike(kappa)
    here = (
        f"; here they are {how} alike (agreement {kappa:.2f}, where 0 is no more alike than chance "
        "and 1 is identical)"
        if how is not None
        else ""
    )
    said.append(
        f"Tries of the same input are counted as separate chances{here}, and if they are near "
        "copies the answer is more confident than it should be."
    )
    if not d.get("_none_failed"):
        if d["rows"]["old"]["failed"] == 0:
            said.append(
                "The old version did not fail on these inputs, so there is no drop to look for: "
                "this check can only show whether the new version fails more."
            )
        elif p.ceiling >= 0.8 * p.old_share:
            said.append(
                f"The {p.asked} points you asked about is close to the most these inputs could "
                f"drop (the old version failed {percent(p.old_share)} of tries)."
            )
    return said


def _different(p: _Pair, changes: str) -> tuple[str, str, str, str | None, list[str]]:
    d = p.d
    diff = d["difference"]
    lo, hi = diff["lo"], diff["hi"]
    more = diff["points"] > 0
    word = "more" if more else "fewer"
    small = bool(d["_reliable"] and lo is not None and hi is not None and max(-lo, hi) < p.ceiling)
    unconfirmed = d.get("_unconfirmed")
    reversed_ = bool(d.get("_new_first"))
    head = f"Slightly {word} failures" if small else f"{word.capitalize()} failures"
    conditions = []
    if reversed_:
        conditions.append("if the order is right")
    if unconfirmed is not None:
        how = alike(d["consistency"]["kappa"])
        conditions.append(
            "if tries of an input count as independent"
            + (f" (here they are {how} alike)" if how is not None else "")
        )
    head += (", " + " and ".join(conditions) + ".") if conditions else "."
    per_100 = f"{num(100.0 * diff['points'])} {word} per 100 tries"
    if small:
        per_100 += (
            f"; the {p.asked} points you set was for a drop, not a rise"
            if more
            else f", smaller than the {p.asked}-point drop you set"
        )
    carried = ""
    flagged = p.flagged
    net = sum(_extra(r) for r in d["changes"]["rows"])
    share = sum(_extra(r) for r in flagged)
    if flagged and net != 0.0 and share * net > 0.0:
        who = (
            inputs_named([r["config"] for r in flagged])
            if unconfirmed is not None
            else inputs(len(flagged))
        )
        carried = (
            f"; {count(round(abs(share)))} of the net {count(round(abs(net)))} "
            f"{'extra' if more else 'fewer'} failures come from {who}"
        )
    if reversed_:
        carried += (
            "; the one you gave as new started first, so if you swapped them, the newer run failed "
            + ("less" if more else "more")
        )
    answer = f"{head} {p.counts} ({per_100}){carried}."
    sentence = (
        f"the new version failed {'slightly ' if small else ''}{'more' if more else 'less'} often"
    )
    if reversed_:
        sentence += " (the one you gave as new started first: check the order)"
    caveats = [chance_sentence(d["test"]["p"])]
    if unconfirmed is not None:
        line = (
            "A check of which inputs went up and which went down can't rule out chance on its own "
            f"(p = {_p(d['by_input']['p'])} in the report), so the gap rests on "
        )
        named = [i["config"] for i in unconfirmed["inputs"]]
        without = unconfirmed["points_without"]
        if named and without is not None and unconfirmed["p_without"] is not None:
            who = inputs_named(named)
            other = " the other way" if without * diff["points"] < 0 else ""
            line += (
                f"{who}. Without {who}, the gap is {num(100.0 * without)} points{other} "
                f"(p = {two_figures(unconfirmed['p_without'])})."
            )
        else:
            line += "the few inputs that moved most."
        caveats.append(line)
    if small and lo is not None and hi is not None:
        caveats.append(
            f"The whole range is at most {num(100.0 * max(-lo, hi))} points, under the {p.asked} "
            "points you set"
            + (" (you set it for a drop; this is a rise)" if more else "")
            + ", if tries of an input are independent."
        )
    caveats.append(SIDE_BY_SIDE)
    follows: str | None
    if reversed_:
        nxt = (
            "Check which run is newer, then run `poisson-trace fix-check` with the older one first."
        )
        follows = "poisson-trace fix-check --help"
    elif unconfirmed is not None:
        nxt = (
            "Run both versions side by side on these inputs with your own harness, then run "
            "`poisson-trace fix-check` on the two new runs."
        )
        follows = "poisson-trace fix-check --help"
    else:
        nxt = f"See which inputs moved: `{changes}`."
        follows = changes
    return sentence, answer, nxt, follows, caveats


def _no_difference(p: _Pair, changes: str) -> tuple[str, str, str, str | None, list[str]]:
    d = p.d
    diff, limits = d["difference"], d["limits"]
    block = d["changes"]
    caveats = []
    if limits["rise"] is not None:
        rise = points(limits["rise"])
        caveats.append(
            f"Trace would catch {a_or_an(rise)} {rise}-point rise 4 times in 5, a smaller rise "
            "less often."
        )
    if block["together"] != 1:
        caveats.append(
            "No single input can stand out on its own here: even one going from never failing to "
            f"always failing would need {tries(block['lone_flip_repeats'])} per input on each side."
        )
    bigger = "plan a bigger run with your own harness"
    if d.get("_none_failed") and d["_decided_by"] == "range":
        # no run failed in either version: there is no gap, and no input that moved to list
        answer = (
            f"Neither version failed. {p.counts}; the results fit "
            f"{range_words(diff['lo'], diff['hi'])}, so a change of {p.asked} points or more "
            "either way does not fit them (if tries of an input are independent)."
        )
        nxt = (
            f"If a change inside that range matters to you, {bigger}, then run "
            "`poisson-trace fix-check` on it."
        )
        return NEITHER_FAILED, answer, nxt, "poisson-trace fix-check --help", caveats
    if d["_decided_by"] == "range":
        sentence = "the gap could be chance"
        answer = (
            f"No clear change. {p.counts}; the results fit {range_words(diff['lo'], diff['hi'])}, "
            f"so a change of {p.asked} points or more either way does not fit them (if tries of an "
            "input are independent)."
        )
        if block["together"] == 1:
            return sentence, answer, f"See which inputs moved: `{changes}`.", changes, caveats
        nxt = (
            f"If a change inside that range matters to you, {bigger}, then run "
            "`poisson-trace fix-check` on it."
        )
        return sentence, answer, nxt, "poisson-trace fix-check --help", caveats
    drop = points(limits["drop"], p.ceiling)
    seen = 100.0 * diff["points"]
    gap = ""
    if num(seen) not in ("0.00", "0.0"):
        size = num(seen)
        gap = (
            f", {a_or_an(size)} {size}-point {'drop' if seen < 0 else 'rise'} that could be chance"
        )
    if p.weak:
        sentence = "the gap could be chance, and this run sees only very large changes"
        most = (
            f" (the most possible was {num(100.0 * p.old_share)})"
            if p.ceiling >= 0.8 * p.old_share
            else ""
        )
        hardly = (
            ", and it can hardly catch the new version failing more"
            if limits["rise"] is None
            else ""
        )
        estimate = (
            f"by Trace's rough estimate it would catch only a drop of {drop} points or more 4 "
            f"times in 5{most}{hardly}"
        )
    else:
        sentence = "the gap could be chance, and this run says little"
        estimate = (
            "its range is too rough here to say which sizes fit, though by Trace's rough estimate "
            f"it would catch a drop of {drop} points or more 4 times in 5"
        )
    answer = f"No clear change, but this run says little. {p.counts}{gap}; {estimate}."
    nxt = (
        "Plan a bigger run with your own harness (more tries per input on both versions), then run "
        "`poisson-trace fix-check` on it."
    )
    return sentence, answer, nxt, "poisson-trace fix-check --help", caveats


def _too_small(p: _Pair) -> tuple[str, str, str, str | None, list[str]]:
    d = p.d
    diff, limits, g = d["difference"], d["limits"], d["guidance"]
    held = d["inputs"]
    asked, article = p.asked, a_or_an(p.asked)
    lo, hi = diff["lo"], diff["hi"]
    ruled_out = d.get("_drop_ruled_out") is not None and lo is not None and hi is not None
    clean = bool(d.get("_none_failed") and d["_reliable"]) and lo is not None and hi is not None
    if clean:
        # no run failed in either version: the range is what is too wide, not a drop too small
        sentence = f"{NEITHER_FAILED}, on too few tries to rule out {article} {asked}-point change"
        fit = f"they fit {range_words(lo, hi)} (if tries of an input are independent)"
        if ruled_out:
            answer = (
                f"Can't tell yet. {p.counts}; {fit}: a drop of {asked} points or more does not "
                f"fit them, but a rise of {asked} or more still does"
            )
        else:
            answer = (
                f"Can't tell yet. {p.counts}; {fit}, so a change of {asked} points or more still "
                "fits them"
            )
    elif d.get("_none_failed") and d["_rough"]:
        # neither version failed, on a range too rough to read: no drop was there to see
        sentence = (
            f"neither version failed, and with {d['_rough'][0]} Trace can't say what size of "
            "change that rules out"
        )
        answer = (
            f"Can't tell. {p.counts}, but with {d['_rough'][0]} Trace can't say what size of "
            "change these tries rule out"
        )
    elif limits["drop"] is None:
        sentence = "too few tries to see a drop of any size"
        answer = (
            f"Can't tell. {p.counts}, and with these tries Trace can't reliably catch a drop of "
            "any size"
        )
    elif ruled_out:
        sentence = (
            f"too few tries to see {article} {asked}-point drop by Trace's rule; a drop that size "
            "does not fit the results"
        )
        answer = (
            f"Can't tell yet. {p.counts}; they fit {range_words(lo, hi)} (if tries of an input are "
            f"independent): a drop of {asked} points or more does not fit them, but a rise of "
            f"{asked} or more still does"
        )
    elif d["_decided_by"] == "range" and d["_tries_enough"]:
        sentence = f"the results still fit {article} {asked}-point drop"
        answer = (
            f"Can't tell yet. {p.counts}; they fit {range_words(lo, hi)} (if tries of an input are "
            f"independent), so a drop of {asked} points or more still fits them"
        )
    else:
        sentence = f"too few tries to see {article} {asked}-point drop"
        drop = points(limits["drop"], p.ceiling)
        rough = "" if d["_reliable"] else "rough "
        answer = (
            f"Can't tell yet. {p.counts}; by Trace's {rough}estimate, these tries would catch "
            f"{a_or_an(drop)} {drop}-point drop 4 times in 5 and smaller ones less often, and you "
            f"asked for {asked}"
            + (" (the range below says which sizes fit)" if d["_reliable"] else "")
        )
    if p.no_outcome_gap:
        answer += "; the gap is no bigger than the gap in tries with no outcome"
    answer += "."
    follows: str | None = None
    selecting = d["_failing_from"]
    n = held["compared"]
    if p.replay:
        sentence = "one run may replay the other: check that before adding tries"
        nxt = replay_check(
            *p.targets,
            "compare a real second version with `poisson-trace fix-check` instead of adding tries.",
        )
        follows = "poisson-trace fix-check --help"
    else:
        then = "with your own harness, then run `poisson-trace fix-check` on the two new runs."
        if g is not None and g["repeats"] is not None:
            also = ""
            if selecting is not None and held["selected"] > n:
                also = (
                    f" (or, to avoid picking which to re-run, on all {count(held['selected'])} "
                    f"that failed in {selecting}; Trace has not sized that)"
                )
            on = "this input" if n == 1 else f"each of these {inputs(n)}"
            plan = f"run each version {count(g['repeats'])} times on {on}{also} {then}"
        elif g is not None and g["inputs"] is not None:
            plan = f"run each version on {inputs(g['inputs'])} like these {then}"
        elif d.get("_none_failed") and d["_rough"]:
            # what is short is inputs, or tries that match, and not tries as such
            plan = (
                "run both versions with the same number of tries on every input, then run "
                "`poisson-trace fix-check` on it."
                if d["_rough"][0] == "unequal tries"
                else "run both versions on at least 3 inputs, with the same number of tries on "
                "each, then run `poisson-trace fix-check` on it."
            )
        else:
            plan = (
                "plan a bigger run with your own harness (more tries per input on both "
                "versions), then run `poisson-trace fix-check` on it."
            )
        if p.no_outcome_gap:
            nxt = (
                f"First find out why {p.more_no_outcome} has more tries with no outcome; then "
                f"{plan}"
            )
        elif ruled_out:
            nxt = (
                f"If only {article} {asked}-point drop mattered, you can stop here; otherwise "
                f"{plan}"
            )
        else:
            nxt = plan[:1].upper() + plan[1:]
    caveats = []
    if clean and g is not None and g["repeats"] is not None:
        others = ""
        if g["inputs"] is not None:
            others = f" {inputs(g['inputs'])} like these at the present tries would do the same"
            if selecting is not None and g["inputs"] > held["selected"]:
                others += f", but only {count(held['selected'])} such inputs exist"
            elif selecting is None and g["inputs"] > n:
                others += f", more than the {count(n)} here"
            others += "."
        caveats.append(
            f"The {count(g['repeats'])} times per input is what brings the range inside "
            f"±{asked} points if neither version fails then either.{others} Make it a fresh run, "
            "judged on its own: don't add tries to these and test again."
        )
    elif g is not None and (g["repeats"] is not None or g["inputs"] is not None):
        rough = (
            " (one try per input on one version, so rough)"
            if any(w.startswith("one try per input") for w in d["_rough"])
            else ""
        )
        if g["repeats"] is not None:
            what = f"The {count(g['repeats'])} times per input is"
            others = ""
            if g["inputs"] is not None:
                others = f" {inputs(g['inputs'])} like these at the present tries would do the same"
                if selecting is not None and g["inputs"] > held["selected"]:
                    others += f", but only {count(held['selected'])} such inputs exist"
                elif selecting is None and g["inputs"] > n:
                    others += f", more than the {count(n)} here"
                others += "."
        else:
            what = f"The {inputs(g['inputs'])} like these is"
            others = ""
        caveats.append(
            f"{what} an estimate from these runs' failure rates{rough}.{others} {FRESH}: don't add "
            "tries to these and test again."
        )
    if clean and g is not None and g["accepts_at"] is not None:
        limit = points(g["accepts_at"], p.ceiling)
        caveats.append(
            f"If {a_or_an(limit)} {limit}-point change is the smallest that matters to you, and "
            f"you would have said so before seeing this, `--max-mde {g['accepts_at']:.4f}` "
            "accepts this design as it stands. " + LABEL_ONLY
        )
    elif g is not None and g["accepts_at"] is not None:
        limit = points(g["accepts_at"], p.ceiling)
        caveats.append(
            f"If {a_or_an(limit)} {limit}-point drop is the smallest that matters to you (the old "
            f"version failed {percent(p.old_share)} of tries), and you would have said so before "
            f"seeing this, `--max-mde {g['accepts_at']:.4f}` accepts this design as it stands. "
            + LABEL_ONLY
        )
    return sentence, answer, nxt, follows, caveats


def fix_check(d: Mapping[str, Any], verdict: str, changes: str) -> Plain:
    """The fix check's plain parts. ``changes`` is the command that lists the inputs that moved
    on the same two runs."""
    p = _Pair(d)
    if verdict == "different":
        sentence, answer, nxt, follows, last = _different(p, changes)
    elif verdict == "no significant difference":
        sentence, answer, nxt, follows, last = _no_difference(p, changes)
    else:
        sentence, answer, nxt, follows, last = _too_small(p)
    question = (
        "Did the new version fail more or less often than the old? You asked that the run be able "
        f"to catch {a_or_an(p.asked)} {p.asked}-point drop in how often it fails."
    )
    return Plain(
        sentence=sentence,
        lines=(
            ("Compared", _compared(p)),
            ("Question", question),
            ("Answer", answer),
            ("Next", nxt),
        ),
        caveats=(*_shared_caveats(p), *last),
        follows=follows,
    )


# ---------- compare ----------


def compare(d: Mapping[str, Any], verdict: str, fix_check: str) -> Plain:
    """compare's plain parts. ``fix_check`` is the command that compares the two runs' failure
    shares, without its ceiling."""
    a, b = d["runs"]["a"], d["runs"]["b"]
    c = d["comparison"]
    unit = unit_of(a)
    asked = f"{c['max_mde_hr']:g}"
    common = d["_common"]
    (na, da), (nb, db) = (
        (common["a"]["tries"], common["a"]["failed"]),
        (
            common["b"]["tries"],
            common["b"]["failed"],
        ),
    )
    cells = c["cells"]
    excluded = c["excluded_cells"]
    each = f"{count(na)} tries each" if na == nb else f"{count(na)} tries before, {count(nb)} after"
    where = (
        f"on the same {inputs(cells)}"
        if not excluded["a_only"] and not excluded["b_only"]
        else f"on the {inputs(cells)} both ran"
    )
    rules = d.get("_rules") or {}
    rule_a, rule_b = rules.get("a", ""), rules.get("b", "")
    rule = (
        f"A try counts as failed when {rule_a}."
        if rule_a == rule_b
        else f"A try counts as failed when {rule_a} before, and when {rule_b} after."
    )
    compared = f"before {_name(a)} against after {_name(b)}, {where}: {each}. {rule}"
    targets = str(a["target_id"]), str(b["target_id"])
    matching = bool(d.get("_matching"))
    if targets[0] != targets[1]:
        compared += " " + targets_differ(*targets, matching=matching)
    question = (
        f"{unit.capitalize()} by {unit}, among tries still going, did the after version fail more "
        f"or less often? You asked to see that rate change {asked}-fold, either way."
    )
    counts = (
        f"Each version failed {count(da)} of {count(na)} tries"
        if (da, na) == (db, nb)
        else f"{count(db)} of {count(nb)} tries failed after and {count(da)} of {count(na)} before"
    )
    estimate = ""
    if c["hazard_ratio"] is not None:
        estimate = (
            f"; after against before, the per-{unit} failure rate is {c['hazard_ratio']:.2f} times "
            f"as high ({c['hazard_ratio_lo']:.2f} to {c['hazard_ratio_hi']:.2f})"
        )
    mde = c["mde_hazard_ratio"]
    fold = None if mde is None else f"{mde:.2f}"
    catch = (
        f"by Trace's estimate these tries would catch a {fold}-fold change in that rate 4 times "
        "in 5"
        if fold is not None
        else "these tries carry no information on that rate, so Trace can't say what change they "
        "would catch"
    )
    later = c["observed_a"] > c["expected_a"]
    if verdict == "different":
        sentence = f"failures come {'later' if later else 'sooner'} after the change"
        answer = (
            f"Failures come {'later' if later else 'sooner'}. {counts}; if each input failed "
            "equally often under both versions, a gap at least this big, either way, would turn up "
            f"{chance(c['p'])} (counting tries as independent){estimate}."
        )
    elif verdict == "no significant difference":
        sentence = "the gap could be chance"
        answer = (
            f"No clear change. {counts}; {catch}, so a smaller change could be hiding{estimate}."
        )
    else:
        sentence = f"too few failures to see a {asked}-fold change"
        answer = f"Can't tell yet. {counts}; {catch}, and you asked about {asked}-fold{estimate}."
    g = c.get("guidance")
    if verdict == "too small to tell" and g is not None and g["repeats"] is not None:
        nxt = (
            f"Run each version {count(g['repeats'])} times on each of these {inputs(cells)} with "
            "your own harness, then run `poisson-trace compare` on the two new runs."
        )
    elif verdict == "too small to tell":
        nxt = (
            f"No number of tries per input on these {inputs(cells)} reaches a {asked}-fold change; "
            "plan a run on more inputs with your own harness, then run `poisson-trace compare` "
            "on it."
        )
    else:
        nxt = (
            f"Compare how often each version fails overall: `{fix_check} --max-mde X`, {CHOOSE_X}."
        )
    if targets[0] != targets[1] and matching:
        nxt = replay_check(*targets, "compare a real second version instead. ") + nxt
    caveats = [when_they_ran([a, b], d.get("_gap_seconds"))]
    if targets[0] == targets[1]:
        caveats.append(same_target(targets[0]))
    caveats.append(
        f"A try that finished without failing counts as still going up to its last {unit}, so this "
        "mixes how often and how early tries fail. Tries of the same input are counted as separate "
        "chances; if they are near copies, this is more confident than it should be."
    )
    if mde is not None and fold is not None:
        caveats.append(
            f"A {fold}-fold change means the per-{unit} failure rate among tries still going rises "
            f"{fold} times, or falls to {1.0 / mde:.2f} of what it was; it is not the ratio of the "
            "failure counts."
        )
    caveats.append(
        "This asks whether failures come sooner or later among tries still going. Whether a "
        "version fails more often overall is fix-check's question, and on the same two runs the "
        "two can read differently."
    )
    only = [
        (n, side)
        for n, side in ((excluded["a_only"], "before"), (excluded["b_only"], "after"))
        if n
    ]
    if len(only) == 1:
        n, side = only[0]
        caveats.append(
            f"{inputs(n)} {'is' if n == 1 else 'are'} left out of the test because only the {side} "
            "run placed tries there."
        )
    elif only:
        caveats.append(
            f"{inputs(only[0][0] + only[1][0])} are left out of the test because only one run "
            f"placed tries there ({count(only[0][0])} only before, {count(only[1][0])} only after)."
        )
    if verdict == "different":
        caveats.append(
            "Before putting the difference down to the version, run both versions side by side."
        )
    if verdict == "too small to tell" and g is not None:
        if g["repeats"] is not None:
            caveats.append(
                f"The {count(g['repeats'])} times per input is an estimate from these runs' "
                f"failure rates. {FRESH}."
            )
        if g["accepts_at"] is not None and fold is not None:
            caveats.append(
                f"If a {fold}-fold change is the smallest that matters to you, and you would have "
                f"said so before seeing this, `--max-mde-hr {g['accepts_at']:.3f}` accepts this "
                f"design as it stands. {LABEL_ONLY}"
            )
    return Plain(
        sentence=sentence,
        lines=(("Compared", compared), ("Question", question), ("Answer", answer), ("Next", nxt)),
        caveats=tuple(caveats),
    )


# ---------- where ----------


def where(
    d: Mapping[str, Any],
    *,
    compare: str | None,
    passing: str,
    fix_check: str,
) -> Plain:
    """where's plain parts. ``compare`` compares the run before this one on its target with this
    one, None where there is none; ``passing`` is this verb again on an outcome to choose;
    ``fix_check`` compares the two runs' failure shares (a placeholder names the other run where
    there is no run before)."""
    run = d["run"]
    unit = unit_of(run)
    placement = run["placement"]
    events = list(d["events"])
    question = f"At which {unit} do failing tries stop?"
    if d.get("note") is not None:
        read = f"{_name(run)} ({run['target_id']}): {tries(run['tally']['rows'])}."
        answer = (
            f"Nothing to place. This run has no traces ({d['_how']}), so its tries carry no "
            f"{unit}s."
        )
        other = "" if compare is not None else ", OLD being the other version's run"
        nxt = (
            f"Compare its failures with another version's: `{fix_check} --max-mde X`{other}, "
            f"{CHOOSE_X}."
        )
        return Plain(
            sentence="this run has no traces, so there is no step to place its failures on",
            lines=(("Read", read), ("Question", question), ("Answer", answer), ("Next", nxt)),
        )
    placed, died = placement["placed"], placement["died"]
    causes = d["causes"]
    read = (
        f"{_name(run)} ({run['target_id']}): {tries(placed)}, each placed at the {unit} where it "
        "stopped."
    )
    failed_at = [row["step"] for row in d["curve"] if row["died"]]
    kinds = [
        f"{count(row['deaths'])} at {KIND_WORDS.get(row['cause'], row['cause'])}" for row in causes
    ]
    if died == 0:
        sentence = f"none of {count(placed)} tries failed ({' or '.join(events)})"
        answer = f"None failed. All {count(placed)} tries finished without {or_list(events)}."
    else:
        span = (
            f"at {unit} {count(failed_at[0])}"
            if failed_at[0] == failed_at[-1]
            else f"between {unit} {count(failed_at[0])} and {unit} {count(failed_at[-1])}"
        )
        if len(causes) == 1:
            kind = KIND_WORDS.get(causes[0]["cause"], causes[0]["cause"])
            whose, one = ("Its", "its") if died == 1 else ("Each failure's", "each one's")
            sentence = (
                f"{count(died)} of {count(placed)} tries failed; {one} last step was {kind} (not "
                "necessarily the cause)"
            )
            answer = (
                f"{count(died)} of {count(placed)} failed. {whose} last step was {kind} (not "
                f"necessarily the cause), {span}."
            )
        else:
            sentence = (
                f"{count(died)} of {count(placed)} tries failed; their last steps: "
                f"{and_list(kinds)} (not necessarily the cause)"
            )
            answer = (
                f"{count(died)} of {count(placed)} failed. Their last steps: {and_list(kinds)} "
                f"(not necessarily the cause), {span}."
            )
    if compare is not None:
        nxt = f"See whether a change moved this: `{compare} --max-mde-hr X`, {CHOOSE_X}."
    elif died:
        nxt = (
            f"Before blaming that step, see where passing tries stop too: `{passing}`, naming an "
            f"outcome other than {or_list(events)} (init lists a store's outcomes)."
        )
    else:
        nxt = (
            f"If {or_list(events)} {'is' if len(events) == 1 else 'are'} the failure you meant, "
            "compare this run with another version's: `poisson-trace fix-check --help` says how."
        )
    caveats = [
        f"The {unit} is where a try stopped, not where it went wrong; the kind of step is that of "
        f"its last {unit}, not the cause. Check what passing tries end on before reading it as one "
        "part's fault."
    ]
    timed = placement["timed out"]
    if timed:
        caveats.append(
            f"{tries(timed)} timed out; {'it ends' if timed == 1 else 'each ends'} where it "
            "stopped, counted beside the kinds and not as a failure."
        )
    capped = placement["capped"]
    if capped:
        caveats.append(
            f"{tries(capped)} reached the cap of {count(run['cap'])} spans and "
            f"{'counts' if capped == 1 else 'count'} as still going at the last {unit} recorded; "
            "if they would have failed soon after, the share failed here is low by that much."
        )
    excluded = {reason: n for reason, n in placement["excluded"].items() if n}
    if excluded:
        total = sum(excluded.values())
        reasons = "; ".join(f"{reason} {count(n)}" for reason, n in excluded.items())
        caveats.append(
            f"{count(total)} {'row is' if total == 1 else 'rows are'} not placed ({reasons}), so "
            f"{'it is' if total == 1 else 'they are'} in none of these counts."
        )
    caveats.append("One run shows where tries stop, not whether a change moved anything.")
    return Plain(
        sentence=sentence,
        lines=(("Read", read), ("Question", question), ("Answer", answer), ("Next", nxt)),
        caveats=tuple(caveats),
    )


# ---------- changes ----------


def per_input(runs: Sequence[int]) -> tuple[str, str]:
    """The tries per input, as the Compared line and the Answer say them: ``4`` and ``4``, or
    ``1 to 3`` and ``mostly 1``."""
    low, high = min(runs), max(runs)
    if low == high:
        return count(low), count(low)
    common = max(sorted(set(runs)), key=runs.count)
    if 2 * runs.count(common) > len(runs):
        return f"{count(low)} to {count(high)}, mostly {count(common)}", f"mostly {count(common)}"
    return f"{count(low)} to {count(high)}", f"{count(low)} to {count(high)}"


FALSE_ALARMS = (
    "Trace's rule keeps false alarms to at most about 1 in 20 of flagged inputs on average, if "
    "tries of an input are independent; a flag says the runs differ on that input, not why. An "
    "input with no flag may still have changed."
)


def changes(d: Mapping[str, Any], fix_check: str) -> Plain:
    """changes' plain parts. ``fix_check`` is the command that compares the two runs' failure
    shares, without its ceiling."""
    a, b = d["runs"]["a"], d["runs"]["b"]
    rows = d["rows"]
    tested = d["tested"]
    flagged = [r for r in rows if r["flag"] is not None]
    every, typical = per_input([r["runs_a"] for r in rows] + [r["runs_b"] for r in rows])
    compared = (
        f"A {_name(a)} against B {_name(b)}, input by input, on {inputs(tested)}: {every} per "
        "input."
    )
    if a["target_id"] != b["target_id"]:
        compared += f" Their targets differ ({a['target_id']}, {b['target_id']})."
    question = "Which single inputs failed more or less often in B than in A?"
    if flagged:
        named = [
            f"{input_words(r['config'])} failed {count(r['failed_b'])} of {count(r['runs_b'])} "
            f"tries against {count(r['failed_a'])} of {count(r['runs_a'])} in A"
            for r in flagged[:NAMED]
        ]
        more = len(flagged) - NAMED
        tail = f"; and {count(more)} more" if more > 0 else ""
        stand = "input stands" if len(flagged) == 1 else "inputs stand"
        answer = f"{count(len(flagged))} {stand} out. In B, {'; '.join(named)}{tail}."
        shown = "; ".join(f"{input_words(r['config'])} {r['flag']}" for r in flagged[:NAMED])
        sentence = f"{count(len(flagged))} of {inputs(tested)} stand out: {shown}{tail}"
    elif d["together"] is None:
        answer = (
            f"None stood out, and none can on this design. With {typical} tries per input, not "
            f"even all {count(tested)} going from never failing to always failing together could "
            "stand out."
        )
        sentence = (
            f"0 of {inputs(tested)} stand out; on this design, no single input could on its own"
        )
    elif d["together"] != 1:
        answer = (
            f"None stood out, and none could on its own on this design. With {typical} tries per "
            "input, even one input going from never failing to always failing couldn't stand out "
            f"among {count(tested)}."
        )
        sentence = (
            f"0 of {inputs(tested)} stand out; on this design, no single input could on its own"
        )
    else:
        answer = (
            "None stand out. One input going from never failing to always failing would have; a "
            "smaller change on one input might not."
        )
        sentence = f"0 of {inputs(tested)} stand out"
    nxt = f"See whether the versions differ overall: `{fix_check} --max-mde X`, {CHOOSE_X}."
    caveats = [when_they_ran([a, b], d.get("_gap_seconds"))]
    held = d.get("_no_outcome") or {}
    none_a, none_b, out = int(held.get("a", 0)), int(held.get("b", 0)), int(held.get("left_out", 0))
    if none_a or none_b:
        line = f"{count(none_a)} tries of A and {count(none_b)} of B had no outcome"
        if out:
            line += (
                f"; the {inputs(out)} where either run has no result {'is' if out == 1 else 'are'} "
                "left out of both."
            )
        else:
            line += ", and they are left out."
        if none_a != none_b:
            line += (
                f" If no outcome means a bad answer, {'B' if none_b > none_a else 'A'}, which has "
                "more of them, fails more often than it looks."
            )
        caveats.append(line)
    shared = shared_key([r["config"] for r in flagged])
    if shared is not None:
        both = "Both are" if len(flagged) == 2 else "They are all"
        caveats.append(
            f"{both} {shared[0]} {shared[1]} at different settings, which may be one fault rather "
            f"than {count(len(flagged))}."
        )
    if flagged or d["together"] == 1:
        caveats.append(FALSE_ALARMS)
    else:
        caveats.append(
            f"With {tries(d['lone_flip_repeats'])} per input on each side, an input that flipped "
            "completely could stand out; smaller changes need more. An input with no flag may "
            "still have changed."
        )
    return Plain(
        sentence=sentence,
        lines=(("Compared", compared), ("Question", question), ("Answer", answer), ("Next", nxt)),
        caveats=tuple(caveats),
    )
