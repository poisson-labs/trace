"""``steps`` and ``timings`` in ``poisson-trace.where/1`` and ``poisson-trace.compare/1``
(``docs/handover.md``, "Steps and timings").

``steps``, always written: each step on Trace's clock from 1 to the run's last, with how many
placed conversations reached it, how many ended there and how, the deaths by label and the
labels of those that reached it. ``timings``, with ``--timings`` (or ``timings=True``): each placed
conversation's steps with their start offsets and durations from the spans, and the parent spans
above them, each once, joined by ``parent_id``; or, with ``--timings-of HASH:REPLICATE`` (or
``timings_of``), the named conversations only. The runs read are the suite's workspace, the ``cs``
and ``tau2`` stores, a LangSmith import, and the steps and timings fixture
(``tests/fixtures/steps-timings``, see its ``make.py``), whose run D holds three traces Prove
would refuse. Each is held to its stored rows, read from the episodes files apart from Trace
(``steps_timings_support.stored``).

steps
- TS-1: ``where`` and ``compare`` carry ``steps`` in ``--json`` and ``result.json``, the key
  immediately before ``cannot_say``.
- TS-2: the steps run 1 to the run's largest placed step, with no gap.
- TS-3: ``reached[k] - reached[k+1] == ended_here[k]``, and ``ended_here`` is the sum of ``ends``.
- TS-4: ``ends`` has the four end words in their order at every step, zeros kept.
- TS-5: ``steps[0].reached`` is the placed count, and each end summed over the steps is the
  header's count of it.
- TS-6: the curve is ``steps`` where something died: the same steps, ``at_risk == reached`` and
  ``died == ends.died``.
- TS-7: each cause's deaths are its ``died_by`` counts summed; ``per_cause`` likewise per side.
- TS-8: ``median_step`` is the step where the running deaths reach ``(D - 1) // 2 + 1``.
- TS-9: ``died_by`` never passes ``labels`` for a label, and the labels sum to ``reached``.
- TS-10: ``--by`` moves only ``died_by`` and ``labels``; the labels are kinds, or step names and
  ``unnamed``, as the spans give them.
- TS-11: rows off the clock are in no step.
- TS-12: a run with no traces has ``steps == []``.
- TS-13: an imported run with spans: nothing capped, and TS-3 to TS-6 hold.
- TS-14: ``compare``'s two lists share one axis, padded with zero counts, and side A's equals
  ``where``'s on run A.

timings
- TS-15: without ``--timings`` there is no ``timings`` key, and the settings and artifact ids are
  main's.
- TS-16: the header counts, the items' order and identity, the end words.
- TS-17: offsets whole, not below 0, not going down; durations whole and not below 0, or null.
- TS-18: a leaf with no end, a child before its parent, parallel leaves and leaves that start
  together, on the fixture.
- TS-19: ``kind``, ``label`` and ``cause``.
- TS-20: ``span_id`` as stored up to 80 printable characters, else a digest.
- TS-21: the same command twice gives the same bytes.
- TS-22: the ceiling cuts the whole-run form to a prefix of whole conversations, with one
  sentence; as shipped nothing is cut.
- TS-23: seeds equal across runs that share a salt, different across salts, 0 on an import.
- TS-24: ``--timings`` adds ``timings: true`` (from ``flag``) to the settings and moves the id.
- TS-25: a run with no traces lists nothing.
- TS-26: no content: no planted marker in any string, short strings, a fixed set of keys.
- TS-27: ``handover --check`` holds the two keys to their shape when there.
- TS-29: the API's ``steps`` and ``timings`` are ``--json``'s.
- TS-30: the ``--timings`` help, and the verbs that refuse it.

parent spans
- TS-31: the shape of ``parents`` and ``parent_id``; flat traces have no parents.
- TS-32: every span of a stored trace is listed once, as a step or a parent.
- TS-33: the links close: every ``parent_id`` names one listed parent, with no cycle.
- TS-34: an orphan and its child, two roots, a flat conversation.
- TS-35: parents with no end, counted in ``parents_no_end``.
- TS-36: one start for steps and parents.
- TS-37: a long parent id is written as a digest on both ends of the link.
- TS-38: parents in start order, and the same bytes twice.
- TS-39: parents count toward the ceiling; a conversation with no tree counts its steps.
- TS-40: a trace whose links cannot be followed has ``parents`` null and is still listed.
- TS-41: no content in parents, and nothing outside ``timings`` moves.

named conversations
- TS-42: ``--timings-of``'s word.
- TS-43: the named form selects, and lists each named item as the whole-run form does.
- TS-44: ``--timings-of`` implies ``--timings``; the settings and the artifact id.
- TS-45: a named conversation the run did not place is in ``not_listed``.
- TS-46: a name that is in no run is refused; one side's name is listed on the other side's
  ``not_listed``.
- TS-47: on ``compare`` one list names both sides.
- TS-48: the named form has no ceiling.
- TS-49: the API's ``timings_of``.
- TS-50: the ``--timings-of`` help.
- TS-51: ``handover --check`` on nested and named bundles, and their breaks.
- TS-53: ``where --by step`` returns on a trace with a parent cycle.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from api_support import VERBS_ARGV, api, cli, workspace
from conftest import FIXTURES
from look_support import run_sub
from saved_support import reseal_descriptor
from steps_timings_support import (
    COMPARE_RUNS, EVENT, HEADER_KEYS, ITEM_KEYS, KINDS, MARKERS, MOST_STEPS, PARENT_KEYS,
    PROVE_WRITTEN, REASONS, STEP_KEYS, TAU2_EV, TAU2_PILOT, TIMED_KEYS, WHERE_RUNS, WHY,
    bundled, compare_argv, details, doc, expected_item, fresh, label, leaves, numbers, pair, placed,
    placed_rows, ran, read_only, stored, strings, the_row, where_argv, written,
)

TIMINGS_HELP = ("also put each conversation's step times in the JSON: when each step started and how "
                "long it took (no default: left out)")
TIMINGS_OF_HELP = ("also put in the JSON the step times of only the conversation with this config hash "
                   "and replicate index; repeatable, and implies --timings (no default: with --timings, "
                   "every conversation)")
#: The artifact ids main gives the workspace's ``where`` and ``compare`` bundles.
MAIN_IDS = {"where": "b35053b6123c9201", "compare": "004ef6df2b56cae9"}
MAIN_SETTINGS = {"where": ["events", "by", "at", "boot", "seed", "from", "stores"],
                 "compare": ["events", "by", "at", "max_mde_hr", "alpha", "verdicts", "from", "stores"]}

#: The fixture's span ids (``make.py``): conversation ``k``'s ``n``-th span.
LONG_ID = "handoff-" + "x" * 73
EIGHTY = "leaf-" + "y" * 75
LONG_LEAF = "leaf-" + "z" * 85
TAB_LEAF = "leaf\twith a tab"


def sid(k: int, n: int) -> str:
    return f"{k:08x}{n:08x}"


ALL = list(WHERE_RUNS)
#: Every run but D, which ``--by step`` is held on alone (TS-53).
STEPPED = [r for r in ALL if r != "fixture D"]


def _where(run: str, *extra: str) -> Any:
    return doc(where_argv(run, *extra))


def _item(document: Any, row: Any) -> Any:
    found = [i for i in document["items"] if (i["config_hash"], i["replicate_index"]) == (row.config_hash, row.replicate_index)]
    assert len(found) == 1, (row.config_hash, row.replicate_index, len(found))
    return found[0]


def _by_side(document: Any) -> list[tuple[str, Any]]:
    """The ``timings`` objects of a document: one for ``where``, ``a`` and ``b`` for ``compare``."""
    t = document["timings"]
    return [("a", t["a"]), ("b", t["b"])] if document["schema"] == "poisson-trace.compare/1" else [("", t)]


def _ceiling(monkeypatch: pytest.MonkeyPatch, most: int) -> None:
    import poisson_trace.core as core

    monkeypatch.setattr(core, "MOST_STEPS", most)


def _cut_line(listed: int, conversations: int, most: int, side: str = "") -> str:
    return (f"timings lists {listed:,} of {conversations:,} conversations{side}: listing more would pass "
            f"{most:,} steps and parent spans")


def _help_entry(text: str, flag: str) -> str:
    """An option's entry in a help page, its lines joined with single spaces."""
    lines = text.splitlines()
    found = [i for i, line in enumerate(lines) if line.strip() == flag or line.strip().startswith(f"{flag} ")]
    assert found, f"the help lists no {flag}"
    at = found[0]
    entry = [lines[at].strip()]
    for line in lines[at + 1:]:
        if not line.strip() or line.strip().startswith("-") or not line.startswith(" " * 8):
            break
        entry.append(line.strip())
    return " ".join(" ".join(entry).split())


# ---------- TS-1 ----------


ONE_CASES = {
    "where": VERBS_ARGV["where"], "where by step": VERBS_ARGV["where by step"],
    "where untraced": VERBS_ARGV["where untraced"], "where by number": VERBS_ARGV["where by number"],
    "where latest": VERBS_ARGV["where latest"], "where config": VERBS_ARGV["where config"],
    "compare": VERBS_ARGV["compare"], "compare at": VERBS_ARGV["compare at"],
    "compare previous latest": VERBS_ARGV["compare previous latest"], "compare config": VERBS_ARGV["compare config"],
    "where with a run Prove cannot read": VERBS_ARGV["where with a run Prove cannot read"],
    "fixture where B": where_argv("fixture B"), "fixture compare A B": compare_argv("fixture A B"),
}


def _just_before_cannot_say(document: Any, key: str) -> None:
    keys = list(document)
    assert key in keys, f"no {key} key: {keys}"
    assert keys[keys.index("cannot_say") - 1] == key, keys


@pytest.mark.parametrize("case", list(ONE_CASES))
def test_ts_1_steps_is_written_just_before_cannot_say(case: str) -> None:
    document = doc(ONE_CASES[case])
    _just_before_cannot_say(document, "steps")
    if document["schema"] == "poisson-trace.compare/1":
        assert list(document["steps"]) == ["a", "b"] and list(document)[list(document).index("steps") - 1] == "per_cause"
    else:
        assert isinstance(document["steps"], list)


@pytest.mark.parametrize("case", list(ONE_CASES))
def test_ts_1_result_json_carries_steps_just_before_cannot_say(tmp_path: Path, case: str) -> None:
    _just_before_cannot_say(bundled(fresh(tmp_path), ONE_CASES[case]), "steps")


# ---------- TS-2 to TS-9 ----------


@pytest.mark.parametrize("run", ["agent after", "cs record", "cs replay", "fixture B"])
def test_ts_2_the_steps_run_from_1_to_the_last_placed_step(run: str) -> None:
    steps = _where(run)["steps"]
    assert [s["step"] for s in steps] == list(range(1, len(steps) + 1))
    assert len(steps) == max(len(leaves(r.spans)) for r in placed_rows(run))


@pytest.mark.parametrize("run", ALL)
def test_ts_3_what_ends_at_a_step_is_what_reached_it_less_what_reached_the_next(run: str) -> None:
    steps = _where(run)["steps"]
    assert steps
    for k, s in enumerate(steps):
        after = steps[k + 1]["reached"] if k + 1 < len(steps) else 0
        assert s["reached"] - after == s["ended_here"], (run, s)
        assert s["ended_here"] == sum(s["ends"].values()), (run, s)
    assert steps[-1]["reached"] == steps[-1]["ended_here"] > 0


@pytest.mark.parametrize("run", ALL)
def test_ts_4_ends_holds_the_four_words_in_order_at_every_step(run: str) -> None:
    for s in _where(run)["steps"]:
        assert list(s) == list(STEP_KEYS)
        assert list(s["ends"]) == list(REASONS) and all(isinstance(n, int) and n >= 0 for n in s["ends"].values())


@pytest.mark.parametrize("run", ALL)
def test_ts_5_the_first_step_holds_every_placed_conversation_and_the_ends_sum_to_the_header(run: str) -> None:
    document = _where(run)
    placement = document["run"]["placement"]
    assert document["steps"][0]["reached"] == placement["placed"] == len(placed_rows(run))
    for reason in REASONS:
        assert sum(s["ends"][reason] for s in document["steps"]) == placement[reason], reason
    found = Counter(placed(run, row)[0] for row in placed_rows(run))
    assert {r: placement[r] for r in REASONS} == {r: found[r] for r in REASONS}


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("run", ["agent before", "agent after", "tau2 a", "tau2 b", "cs record", "cs replay",
                                 "fixture A", "fixture B", "fixture C"])
def test_ts_6_the_curve_is_steps_where_something_died(run: str, by: str) -> None:
    document = _where(run, "--by", by)
    steps = {s["step"]: s for s in document["steps"]}
    assert {c["step"] for c in document["curve"]} == {k for k, s in steps.items() if s["ends"]["died"] > 0}
    for c in document["curve"]:
        assert c["at_risk"] == steps[c["step"]]["reached"] and c["died"] == steps[c["step"]]["ends"]["died"], c


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("run", STEPPED)
def test_ts_7_each_cause_has_the_deaths_its_label_has_over_the_steps(run: str, by: str) -> None:
    document = _where(run, "--by", by)
    sums: Counter[str] = Counter()
    for s in document["steps"]:
        for d in s["died_by"]:
            sums[d["label"]] += d["count"]
    assert {c["cause"]: c["deaths"] for c in document["causes"]} == dict(sums)
    order = [c["cause"] for c in document["causes"]]
    for s in document["steps"]:
        labels = [d["label"] for d in s["died_by"]]
        assert labels == [c for c in order if c in labels] and all(d["count"] > 0 for d in s["died_by"])


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("pair_", list(COMPARE_RUNS))
def test_ts_7_compare_per_cause_has_each_side_s_deaths_over_its_steps(pair_: str, by: str) -> None:
    document = doc(compare_argv(pair_, "--by", by))
    for side in ("a", "b"):
        sums: Counter[str] = Counter()
        for s in document["steps"][side]:
            for d in s["died_by"]:
                sums[d["label"]] += d["count"]
        assert {c["cause"]: c[f"deaths_{side}"] for c in document["per_cause"] if c[f"deaths_{side}"]} == dict(sums), side


@pytest.mark.parametrize("run", ALL)
def test_ts_8_the_median_step_is_where_the_running_deaths_reach_the_middle(run: str) -> None:
    document = _where(run)
    deaths = sum(s["ends"]["died"] for s in document["steps"])
    if deaths == 0:
        assert document["median_step"] is None
        return
    running, want = 0, (deaths - 1) // 2 + 1
    for s in document["steps"]:
        running += s["ends"]["died"]
        if running >= want:
            assert document["median_step"] == s["step"]
            return
    raise AssertionError("the deaths never reach the middle")


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("run", STEPPED)
def test_ts_9_deaths_by_label_never_pass_the_label_s_count_and_the_labels_sum_to_reached(run: str, by: str) -> None:
    for s in _where(run, "--by", by)["steps"]:
        counts = {x["label"]: x["count"] for x in s["labels"]}
        assert sum(counts.values()) == s["reached"] and all(n > 0 for n in counts.values())
        for d in s["died_by"]:
            assert d["count"] <= counts.get(d["label"], 0), (s["step"], d)


# ---------- TS-10 to TS-14 ----------


def _expected_labels(run: str, by: str) -> list[Counter[str]]:
    rows = placed_rows(run)
    last = max(len(leaves(r.spans)) for r in rows)
    out: list[Counter[str]] = [Counter() for _ in range(last)]
    for row in rows:
        for k, leaf in enumerate(leaves(row.spans)):
            out[k][label(leaf, row.spans, by)] += 1
    return out


@pytest.mark.parametrize("run", STEPPED)
def test_ts_10_by_moves_only_the_labels_and_the_deaths_by_label(run: str) -> None:
    kind, step = _where(run, "--by", "kind")["steps"], _where(run, "--by", "step")["steps"]
    assert len(kind) == len(step)
    for a, b in zip(kind, step, strict=True):
        assert {k: a[k] for k in ("step", "reached", "ended_here", "ends")} == {k: b[k] for k in ("step", "reached", "ended_here", "ends")}
    assert {x["label"] for s in kind for x in s["labels"]} <= {*KINDS, "unknown"}


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("run", ["fixture A", "fixture B", "fixture C", "agent after", "cs record"])
def test_ts_10_the_labels_at_each_step_are_those_the_spans_give(run: str, by: str) -> None:
    steps = _where(run, "--by", by)["steps"]
    want = _expected_labels(run, by)
    assert [Counter({x["label"]: x["count"] for x in s["labels"]}) for s in steps] == want
    if by == "step" and run.startswith("fixture"):
        names = {x["label"] for s in steps for x in s["labels"]}
        assert "unnamed" in names and names - {"unnamed"} and not names & set(KINDS), names


def test_ts_11_rows_off_the_clock_are_in_no_step() -> None:
    document = _where("cs replay")
    assert document["steps"][0]["reached"] == 21
    assert document["run"]["placement"]["excluded"]["no outcome, not a timeout"] == 3
    b = _where("fixture B")
    assert b["steps"][0]["reached"] == 4 and b["run"]["placement"]["excluded"]["no leaf span"] == 1


@pytest.mark.parametrize("argv", [VERBS_ARGV["where untraced"], ["where", TAU2_PILOT, "--store", "tau2", *TAU2_EV]],
                         ids=["junit import", "tau2 pilot"])
def test_ts_12_a_run_with_no_traces_has_no_step(argv: list[str]) -> None:
    document = doc(argv)
    assert "steps" in document and document["steps"] == []


_LS = ["--case-from", "example", "--outcome-from", "feedback:exact", "--cut", "0.5", "--below"]
_LANGSMITH: list[Path] = []


def _langsmith() -> Path:
    """The two LangSmith captures imported into a store of their own, once in each process."""
    if not _LANGSMITH:
        import atexit
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="steps-timings-ls-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        work = root / "work"
        work.mkdir()
        shutil.copytree(FIXTURES / "ingest" / "langsmith", work / "ls")
        for run, version in (("old", "baseline"), ("new", "candidate")):
            made = cli(work, ["import", "langsmith", f"ls/api/{version}.runs-v2.json", f"ls/api/{version}.feedback.json",
                              "--store", "lst", "--run", run, *_LS])
            assert made.code == 0, made.text
        _LANGSMITH.append(work)
    return _LANGSMITH[0]


@cache
def _ls_doc(*argv: str) -> Any:
    out = cli(_langsmith(), [*argv, "--json"])
    assert out.code == 0, out.text
    return json.loads(out.out)


@pytest.mark.parametrize("by", ["kind", "step"])
def test_ts_13_an_imported_run_with_spans_has_steps_and_none_capped(by: str) -> None:
    for run in ("old", "new"):
        document = _ls_doc("where", run, "--store", "lst", "--event", "missed", "--by", by)
        steps = document["steps"]
        assert steps and all(s["ends"]["capped"] == 0 for s in steps)
        for k, s in enumerate(steps):
            after = steps[k + 1]["reached"] if k + 1 < len(steps) else 0
            assert s["reached"] - after == s["ended_here"] == sum(s["ends"].values())
            assert list(s["ends"]) == list(REASONS)
        assert steps[0]["reached"] == document["run"]["placement"]["placed"]
        for reason in REASONS:
            assert sum(s["ends"][reason] for s in steps) == document["run"]["placement"][reason]
        by_step = {s["step"]: s for s in steps}
        assert {c["step"] for c in document["curve"]} == {k for k, s in by_step.items() if s["ends"]["died"]}
        assert all(c["at_risk"] == by_step[c["step"]]["reached"] for c in document["curve"])
        assert all(c["died"] == by_step[c["step"]]["ends"]["died"] for c in document["curve"])


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("pair_", ["workspace", "fixture A B"])
def test_ts_14_compare_s_two_sides_share_one_axis_and_side_a_is_where_s(pair_: str, by: str) -> None:
    argv, run_a, run_b = COMPARE_RUNS[pair_]
    document = doc([*argv, "--by", by])
    a, b = document["steps"]["a"], document["steps"]["b"]
    alone_a, alone_b = _where(run_a, "--by", by)["steps"], _where(run_b, "--by", by)["steps"]
    assert len(a) == len(b) == max(len(alone_a), len(alone_b))
    assert [s["step"] for s in a] == [s["step"] for s in b] == list(range(1, len(a) + 1))
    assert a[: len(alone_a)] == alone_a and b[: len(alone_b)] == alone_b
    for s in [*a[len(alone_a):], *b[len(alone_b):]]:
        assert s == {"step": s["step"], "reached": 0, "ended_here": 0, "ends": dict.fromkeys(REASONS, 0),
                     "died_by": [], "labels": []}
    if pair_ == "fixture A B":
        assert len(alone_b) > len(alone_a), "the fixture's B reaches further than A"


# ---------- TS-15 to TS-25 ----------


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_15_without_timings_there_is_no_timings_key_and_the_ids_are_main_s(tmp_path: Path, verb: str) -> None:
    printed = doc(VERBS_ARGV[verb])
    work = workspace(tmp_path)
    result = bundled(work, VERBS_ARGV[verb])
    for document in (printed, result):
        assert "steps" in document and "timings" not in document
    artifact = json.loads((work / "bundle" / "artifact.json").read_text(encoding="utf-8"))
    assert list(artifact["settings"]) == MAIN_SETTINGS[verb] and "timings" not in artifact["settings"]["from"]
    assert artifact["id"] == MAIN_IDS[verb]


@pytest.mark.parametrize("run", ALL)
def test_ts_16_the_header_counts_and_the_items_in_store_order(run: str) -> None:
    document = _where(run, "--timings")
    keys = list(document)
    assert keys[keys.index("cannot_say") - 2: keys.index("cannot_say")] == ["steps", "timings"]
    t = document["timings"]
    placement = document["run"]["placement"]
    assert t["most_steps"] == MOST_STEPS and t["asked"] is None and t["not_listed"] == []
    assert t["conversations"] == placement["placed"] and t["listed"] == len(t["items"]) == t["conversations"]
    got = [(i["config_hash"], i["replicate_index"]) for i in t["items"]]
    assert got == sorted(set(got)) == [(r.config_hash, r.replicate_index) for r in placed_rows(run)]
    for item in t["items"]:
        assert [s["step"] for s in item["steps"]] == list(range(1, len(item["steps"]) + 1))
    ends = Counter(i["end"] for i in t["items"])
    assert {r: ends[r] for r in REASONS} == {r: placement[r] for r in REASONS}


@pytest.mark.parametrize("pair_", list(COMPARE_RUNS))
def test_ts_16_compare_lists_each_side_as_where_does(pair_: str) -> None:
    argv, run_a, run_b = COMPARE_RUNS[pair_]
    document = doc([*argv, "--timings"])
    keys = list(document)
    assert keys[keys.index("cannot_say") - 2: keys.index("cannot_say")] == ["steps", "timings"]
    assert list(document["timings"]) == ["a", "b"]
    for side, run in (("a", run_a), ("b", run_b)):
        assert document["timings"][side] == _where(run, "--timings")["timings"], side


@pytest.mark.parametrize("run", ALL)
def test_ts_17_offsets_and_durations_are_whole_nanoseconds(run: str) -> None:
    t = _where(run, "--timings")["timings"]
    assert all(isinstance(n, int) for n in numbers(t)), [n for n in numbers(t) if not isinstance(n, int)][:3]
    for item in t["items"]:
        offsets = [s["offset_ns"] for s in item["steps"]]
        assert offsets == sorted(offsets) and offsets[0] >= 0
        for span in [*item["steps"], *(item["parents"] or ())]:
            assert span["offset_ns"] >= 0
            assert span["duration_ns"] is None or span["duration_ns"] >= 0
        assert item["steps"] == expected_item(run, _row_of(run, item), "kind")["steps"]


def _row_of(run: str, item: Any) -> Any:
    return next(r for r in stored(run) if (r.config_hash, r.replicate_index) == (item["config_hash"], item["replicate_index"]))


def test_ts_18_open_leaves_skew_parallel_leaves_and_leaves_that_start_together() -> None:
    t = _where("fixture B", "--timings")["timings"]
    timed_out = _item(t, the_row("fixture B", "beta", 0))
    assert timed_out["end"] == "timed out" and timed_out["steps"][-1]["duration_ns"] is None
    assert t["no_end"] == sum(1 for i in t["items"] for s in i["steps"] if s["duration_ns"] is None) >= 1
    deep = _item(t, the_row("fixture B", "alpha", 0))
    ids = [s["span_id"] for s in deep["steps"]]
    # the leaf that starts before its parent is the first step, at an offset of 15 ms
    assert ids[0] == sid(201, 5) and deep["steps"][0]["offset_ns"] == 15_000_000
    # two leaves that start in the same nanosecond, in span id order
    assert ids[1:3] == [sid(201, 6), sid(201, 7)] and deep["steps"][1]["offset_ns"] == deep["steps"][2]["offset_ns"]
    # two leaves that run at once: the earlier is still running when the later starts
    first, later = deep["steps"][1], deep["steps"][3]
    assert later["span_id"] == EIGHTY and first["offset_ns"] < later["offset_ns"] < first["offset_ns"] + first["duration_ns"]


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("run", STEPPED)
def test_ts_19_kind_label_and_cause(run: str, by: str) -> None:
    t = _where(run, "--by", by, "--timings")["timings"]
    for item in t["items"]:
        want = expected_item(run, _row_of(run, item), by)
        assert all(s["kind"] in (*KINDS, "unknown") for s in item["steps"])
        assert [s["label"] for s in item["steps"]] == [s["label"] for s in want["steps"]]
        assert [s["kind"] for s in item["steps"]] == [s["kind"] for s in want["steps"]]
        assert item["cause"] == (item["steps"][-1]["label"] if item["end"] == "died" else None)


@pytest.mark.parametrize("run", ALL)
def test_ts_20_span_ids_as_stored_up_to_80_printable_characters_else_a_digest(run: str) -> None:
    for item in _where(run, "--timings")["timings"]["items"]:
        row = _row_of(run, item)
        assert [s["span_id"] for s in item["steps"]] == [written(leaf["span_id"]) for leaf in leaves(row.spans)]
        assert all(len(s["span_id"]) <= 80 for s in item["steps"])
    deep = _item(_where("fixture B", "--timings")["timings"], the_row("fixture B", "alpha", 0))
    assert EIGHTY in [s["span_id"] for s in deep["steps"]]
    digest = written(LONG_ID)
    assert digest.startswith("sha256:") and len(digest) == 23 and digest in [p["span_id"] for p in deep["parents"]]
    # a leaf id of 90 characters, and one holding a tab, are written as digests
    orphan = _item(_where("fixture B", "--timings")["timings"], the_row("fixture B", "alpha", 2))
    ids = [s["span_id"] for s in orphan["steps"]]
    for stored_id in (LONG_LEAF, TAB_LEAF):
        assert written(stored_id).startswith("sha256:") and written(stored_id) in ids and stored_id not in ids


TWICE = {
    "where": where_argv("fixture B"),
    "where timings": where_argv("fixture B", "--timings"),
    "where timings by step": where_argv("fixture B", "--timings", "--by", "step"),
    "compare timings": compare_argv("fixture A B", "--timings"),
    "workspace where timings": [*VERBS_ARGV["where"], "--timings"],
}


@pytest.mark.parametrize("case", list(TWICE))
def test_ts_21_the_same_command_twice_gives_the_same_bytes(tmp_path: Path, case: str) -> None:
    argv = TWICE[case]
    work = read_only()
    one, two = cli(work, [*argv, "--json"]), cli(work, [*argv, "--json"])
    assert one.code == two.code == 0 and one.out == two.out
    assert "steps" in json.loads(one.out)
    files = []
    for name in ("one", "two"):
        w = fresh(tmp_path / name)
        assert cli(w, [*argv, "--out", "bundle"]).code == 0
        files.append((w / "bundle" / "result.json").read_bytes())
    assert files[0] == files[1]


def test_ts_22_the_ceiling_cuts_the_whole_run_to_whole_conversations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = "agent after"
    full = _where(run, "--timings")["timings"]
    sizes = [len(i["steps"]) + len(i["parents"] or ()) for i in full["items"]]
    most = sizes[0] + sizes[1] + sizes[2] - 1
    _ceiling(monkeypatch, most)
    work = fresh(tmp_path)
    printed = cli(work, [*where_argv(run), "--timings", "--json"])
    assert printed.code == 0, printed.text
    t = json.loads(printed.out)["timings"]
    assert t["most_steps"] == most and t["listed"] == 2 < t["conversations"] == full["conversations"]
    assert t["items"] == full["items"][:2]
    line = _cut_line(2, full["conversations"], most)
    assert line in details(cli(work, [*where_argv(run), "--timings"]).out)
    assert line in bundled(work, [*where_argv(run), "--timings"])["note"]
    _ceiling(monkeypatch, sizes[0] - 1)
    alone = json.loads(cli(work, [*where_argv(run), "--timings", "--json"]).out)["timings"]
    assert alone["listed"] == 0 and alone["items"] == []


def test_ts_22_compare_says_which_side_was_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    full = doc(compare_argv("workspace", "--timings"))["timings"]
    _ceiling(monkeypatch, 30)
    work = fresh(tmp_path)
    t = json.loads(cli(work, compare_argv("workspace", "--timings", "--json")).out)["timings"]
    lines = details(cli(work, compare_argv("workspace", "--timings")).out)
    note = bundled(work, compare_argv("workspace", "--timings"))["note"]
    for side, word in (("a", " of A (before)"), ("b", " of B (after)")):
        sizes = [len(i["steps"]) + len(i["parents"] or ()) for i in full[side]["items"]]
        listed = max(m for m in range(len(sizes) + 1) if sum(sizes[:m]) <= 30)
        assert t[side]["listed"] == listed < t[side]["conversations"] and t[side]["items"] == full[side]["items"][:listed]
        line = _cut_line(listed, full[side]["conversations"], 30, word)
        assert line in lines and line in note


@pytest.mark.parametrize("argv", [where_argv(r, "--timings") for r in ALL] + [compare_argv(p, "--timings") for p in COMPARE_RUNS],
                         ids=[*ALL, *COMPARE_RUNS])
def test_ts_22_as_shipped_nothing_is_cut(argv: list[str]) -> None:
    document = doc(argv)
    for _side, t in _by_side(document):
        assert t["most_steps"] == MOST_STEPS and t["listed"] == t["conversations"]
    assert not [line for line in details(ran(argv).out) if line.startswith("timings lists")]


def test_ts_23_seeds_pair_across_one_salt_differ_across_two_and_are_0_on_an_import() -> None:
    def pairs(document: Any) -> list[tuple[int, int]]:
        a = {(i["config_hash"], i["replicate_index"]): i["seed"] for i in document["timings"]["a"]["items"]}
        b = {(i["config_hash"], i["replicate_index"]): i["seed"] for i in document["timings"]["b"]["items"]}
        return [(a[k], b[k]) for k in a.keys() & b.keys()]

    same = pairs(doc(compare_argv("workspace", "--timings")))
    assert same and all(x == y for x, y in same)
    other = pairs(doc(compare_argv("fixture A C", "--timings")))
    assert other and all(x != y for x, y in other)
    imported = _ls_doc("compare", "old", "new", "--store", "lst", "--event", "missed", "--max-mde-hr", "1.5", "--timings")
    seeds = [i["seed"] for side in ("a", "b") for i in imported["timings"][side]["items"]]
    assert seeds and set(seeds) == {0}


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_24_timings_joins_the_settings_from_the_flag_and_moves_the_id(tmp_path: Path, verb: str) -> None:
    ids = {}
    for name, extra in (("without", []), ("with", ["--timings"])):
        work = workspace(tmp_path / name)
        bundled(work, [*VERBS_ARGV[verb], *extra])
        artifact = json.loads((work / "bundle" / "artifact.json").read_text(encoding="utf-8"))
        ids[name] = artifact["id"]
        settings = artifact["settings"]
        if extra:
            assert settings["timings"] is True and settings["from"]["timings"] == "flag"
            assert list(settings) == [*MAIN_SETTINGS[verb][:-2], "timings", "from", "stores"]
            assert "timings_of" not in settings and "timings_of" not in settings["from"]
    assert ids["with"] != ids["without"] == MAIN_IDS[verb]


def test_ts_25_a_run_with_no_traces_lists_no_conversation() -> None:
    t = doc([*VERBS_ARGV["where untraced"], "--timings"])["timings"]
    assert t["conversations"] == 0 and t["listed"] == 0 and t["items"] == []


# ---------- TS-26, TS-27, TS-29, TS-30 ----------


def _keys_are_the_layout(document: Any) -> None:
    steps = document["steps"]
    for listed in (steps["a"], steps["b"]) if isinstance(steps, dict) else (steps,):
        for s in listed:
            assert list(s) == list(STEP_KEYS) and list(s["ends"]) == list(REASONS)
            assert all(set(x) == {"label", "count"} for x in [*s["died_by"], *s["labels"]])
    for _side, t in _by_side(document) if "timings" in document else ():
        assert set(t) == set(HEADER_KEYS)
        assert all(set(a) == {"config_hash", "replicate_index"} for a in t["asked"] or ())
        assert all(set(n) == {"config_hash", "replicate_index", "why"} and n["why"] in WHY for n in t["not_listed"])
        for item in t["items"]:
            assert set(item) == set(ITEM_KEYS)
            assert all(list(s) == list(TIMED_KEYS) for s in item["steps"])
            assert all(list(p) == list(PARENT_KEYS) for p in item["parents"] or ())


def _no_content(document: Any) -> None:
    for text in strings(document):
        assert not [m for m in MARKERS if m in text], text
    for _side, t in _by_side(document) if "timings" in document else ():
        for item in t["items"]:
            texts = [item["config_hash"], item["end"]]
            texts += [x for s in item["steps"] for x in (s["kind"], s["span_id"], s["parent_id"]) if x is not None]
            texts += [x for p in item["parents"] or () for x in (p["span_id"], p["parent_id"], p["kind"]) if x is not None]
            assert all(len(x) <= 80 for x in texts)


CONTENT_CASES = {
    **{f"where {r} by {by}": where_argv(f"fixture {r}", "--timings", "--by", by) for r in "ABC" for by in ("kind", "step")},
    "where D by kind": where_argv("fixture D", "--timings"),
    "compare A B by step": compare_argv("fixture A B", "--timings", "--by", "step"),
    "compare A B by kind": compare_argv("fixture A B", "--timings"),
}


@pytest.mark.parametrize("case", list(CONTENT_CASES))
def test_ts_26_no_marker_reaches_the_json_and_the_keys_are_the_layout(tmp_path: Path, case: str) -> None:
    argv = CONTENT_CASES[case]
    printed = doc(argv)
    result = bundled(fresh(tmp_path), argv)
    for document in (printed, result):
        assert "timings" in document
        _no_content(document)
        _keys_are_the_layout(document)


def _check(bundle: Path) -> Any:
    return cli(bundle.parent, ["handover", "--check", bundle.name])


def _edit(bundle: Path, change: Any) -> None:
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    change(result)
    (bundle / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reseal_descriptor(bundle)


def _fails(bundle: Path, line: str | None, *named: str) -> None:
    ran_ = _check(bundle)
    assert ran_.code == 4, ran_.text
    first = ran_.out.splitlines()[0]
    if line is not None:
        assert first == f"not valid  {line}", first
    assert all(n in first for n in named), (first, named)


def _a_bundle(tmp_path: Path, argv: list[str], name: str) -> Path:
    work = fresh(tmp_path / name)
    out = cli(work, [*argv, "--out", "bundle"])
    assert out.code == 0, out.text
    return work / "bundle"


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_27_the_check_passes_the_bundles_with_and_without_steps(tmp_path: Path, verb: str) -> None:
    bundle = _a_bundle(tmp_path, [*VERBS_ARGV[verb], "--timings"], "a")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    assert "steps" in result and "timings" in result
    assert _check(bundle).code == 0, _check(bundle).text
    _edit(bundle, lambda r: r.pop("steps"))
    assert _check(bundle).code == 0, _check(bundle).text


def test_ts_27_the_check_fails_steps_or_timings_not_of_their_shape(tmp_path: Path) -> None:
    breaks = [
        ("steps", lambda r: r.__setitem__("steps", "every step"), "result.json's steps is not a list of steps"),
        ("step without ends", lambda r: r["steps"][0].pop("ends"), "result.json's steps is not a list of steps"),
        ("timings a list", lambda r: r.__setitem__("timings", []), "result.json's timings is not a timings object"),
        ("timings without items", lambda r: r["timings"].pop("items"), "result.json's timings is not a timings object"),
    ]
    for name, change, line in breaks:
        bundle = _a_bundle(tmp_path, [*VERBS_ARGV["where"], "--timings"], name.replace(" ", "-"))
        _edit(bundle, change)
        _fails(bundle, line)
    bundle = _a_bundle(tmp_path, [*VERBS_ARGV["compare"], "--timings"], "compare-steps")
    _edit(bundle, lambda r: r["steps"]["b"][0].pop("labels"))
    _fails(bundle, None, "result.json", "steps")


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_29_the_api_s_steps_and_timings_are_the_json_s(verb: str) -> None:
    a = api()
    store = str(read_only() / "store")
    if verb == "where":
        call = lambda **kw: a.where(store, "agent after", event=["violated", "timeout"], at=[3], **kw)  # noqa: E731
    else:
        call = lambda **kw: a.compare(store, "agent before", "agent after", event=["violated", "timeout"], max_mde_hr=1.5, **kw)  # noqa: E731
    with_ = call(timings=True)
    printed = doc([*VERBS_ARGV[verb], "--timings"])
    assert with_.timings == printed["timings"] and with_.steps == printed["steps"]
    without = call()
    assert without.timings is None and without.steps == doc(VERBS_ARGV[verb])["steps"]


def _refused_as_unknown(flag: list[str]) -> None:
    for verb in ("fix-check", "changes", "runs"):
        out = ran([*VERBS_ARGV[verb], *flag])
        assert out.code == 2 and out.out == "", (verb, out.text)
        assert out.err.splitlines()[0] == f"error: unrecognized arguments: {' '.join(flag)}", (verb, out.err)


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_30_where_and_compare_list_timings_and_the_other_verbs_refuse_it(verb: str) -> None:
    out = ran([verb, "--help"])
    assert out.code == 0
    assert _help_entry(out.out, "--timings") == f"--timings {TIMINGS_HELP}"
    _refused_as_unknown(["--timings"])


# ---------- TS-31 to TS-41: parent spans ----------


@pytest.mark.parametrize("run", ALL)
def test_ts_31_parents_and_parent_id_are_the_last_keys(run: str) -> None:
    t = _where(run, "--timings")["timings"]
    assert {"parents_no_end", "no_tree"} <= set(t)
    for item in t["items"]:
        assert list(item)[-1] == "parents" and (item["parents"] is None or isinstance(item["parents"], list))
        assert all(list(s)[-1] == "parent_id" for s in item["steps"])
        assert all(list(p) == list(PARENT_KEYS) for p in item["parents"] or ())


@pytest.mark.parametrize("run", ["agent before", "agent after", "tau2 a"])
def test_ts_31_a_flat_trace_has_no_parents(run: str) -> None:
    t = _where(run, "--timings")["timings"]
    assert t["items"] and t["no_tree"] == 0 and t["parents_no_end"] == 0
    for item in t["items"]:
        assert item["parents"] == [] and all(s["parent_id"] is None for s in item["steps"])


@pytest.mark.parametrize("run", ["fixture A", "fixture B", "fixture C", "cs record", "cs replay"])
def test_ts_32_every_span_is_listed_once_as_a_step_or_a_parent(run: str) -> None:
    for item in _where(run, "--timings")["timings"]["items"]:
        row = _row_of(run, item)
        listed = [s["span_id"] for s in item["steps"]] + [p["span_id"] for p in item["parents"]]
        assert len(listed) == len(set(listed)) == len(row.spans)
        parenting = {s.get("parent_id") for s in row.spans}
        assert {p["span_id"] for p in item["parents"]} == {written(s["span_id"]) for s in row.spans if s["span_id"] in parenting}
    if run == "cs record":
        assert sum(len(i["parents"]) for i in _where(run, "--timings")["timings"]["items"]) == 1894


@pytest.mark.parametrize("run", ALL)
def test_ts_33_every_link_names_one_listed_parent_and_none_goes_round(run: str) -> None:
    for item in _where(run, "--timings")["timings"]["items"]:
        if item["parents"] is None:
            continue
        parents = {}
        for p in item["parents"]:
            parents.setdefault(p["span_id"], []).append(p)
        steps = {s["span_id"] for s in item["steps"]}
        spans = [*item["steps"], *item["parents"]]
        for span in spans:
            if span["parent_id"] is not None:
                assert len(parents.get(span["parent_id"], [])) == 1, span
                assert span["parent_id"] not in steps
            at, moves = span, 0
            while at["parent_id"] is not None:
                at, moves = parents[at["parent_id"]][0], moves + 1
                assert moves < len(spans), "a cycle"
        row = _row_of(run, item)
        ids = {s["span_id"] for s in row.spans}
        for leaf, s in zip(leaves(row.spans), item["steps"], strict=True):
            if leaf.get("parent_id") in ids:
                assert s["parent_id"] == written(leaf["parent_id"])


def test_ts_34_an_orphan_two_roots_and_a_flat_conversation() -> None:
    t = _where("fixture B", "--timings")["timings"]
    orphan = _item(t, the_row("fixture B", "alpha", 2))
    by_id = {s["span_id"]: s for s in [*orphan["steps"], *orphan["parents"]]}
    assert by_id[sid(203, 3)]["parent_id"] is None and by_id[sid(203, 4)]["parent_id"] == sid(203, 3)
    two = _item(t, the_row("fixture B", "alpha", 1))
    assert sum(1 for s in [*two["steps"], *two["parents"]] if s["parent_id"] is None) == 2
    flat = _item(_where("fixture A", "--timings")["timings"], the_row("fixture A", "beta", 1))
    assert flat["parents"] == [] and len(flat["steps"]) == 3


def test_ts_35_parents_with_no_end() -> None:
    t = _where("fixture B", "--timings")["timings"]
    timed_out = _item(t, the_row("fixture B", "beta", 0))
    by_id = {p["span_id"]: p for p in timed_out["parents"]}
    for span_id in (sid(204, 1), sid(204, 2)):
        assert by_id[span_id]["duration_ns"] is None and isinstance(by_id[span_id]["offset_ns"], int) and by_id[span_id]["offset_ns"] >= 0
    assert timed_out["steps"][-1]["parent_id"] == sid(204, 2)
    for document in (t, _where("fixture D", "--timings")["timings"]):
        assert document["parents_no_end"] == sum(1 for i in document["items"] for p in i["parents"] or () if p["duration_ns"] is None)
        assert document["no_end"] == sum(1 for i in document["items"] for s in i["steps"] if s["duration_ns"] is None)
    d = _item(_where("fixture D", "--timings")["timings"], the_row("fixture D", "beta", 1))
    by_id = {p["span_id"]: p for p in d["parents"]}
    # the parent that ends before it starts, and the one whose end is not a whole number
    assert by_id[sid(404, 2)]["duration_ns"] is None and by_id[sid(404, 4)]["duration_ns"] is None
    assert by_id[sid(404, 1)]["duration_ns"] == 500_000_000
    # the leaf that ends before it starts
    assert d["steps"][-1]["span_id"] == sid(404, 6) and d["steps"][-1]["duration_ns"] is None


@pytest.mark.parametrize("run", PROVE_WRITTEN)
def test_ts_36_steps_and_parents_share_one_start(run: str) -> None:
    for item in _where(run, "--timings")["timings"]["items"]:
        assert min(s["offset_ns"] for s in [*item["steps"], *item["parents"]]) == 0
        assert item["parents"] == expected_item(run, _row_of(run, item), "kind")["parents"]


def test_ts_36_the_root_starts_at_0_and_a_child_before_its_parent_is_below_it() -> None:
    row = the_row("fixture B", "alpha", 0)
    deep = _item(_where("fixture B", "--timings")["timings"], row)
    root = next(p for p in deep["parents"] if p["span_id"] == sid(201, 1))
    stored_ = {s["span_id"]: s for s in row.spans}
    assert root["offset_ns"] == 0 and root["parent_id"] is None
    assert deep["steps"][0]["offset_ns"] == stored_[sid(201, 5)]["start_ns"] - stored_[sid(201, 1)]["start_ns"]
    answer = next(p for p in deep["parents"] if p["span_id"] == sid(201, 4))
    assert deep["steps"][0]["parent_id"] == sid(201, 4) and 0 <= deep["steps"][0]["offset_ns"] < answer["offset_ns"]
    # a leaf that starts before every parent is the conversation's start; the parents are after it
    early = _item(_where("fixture A", "--timings")["timings"], the_row("fixture A", "alpha", 1))
    assert early["steps"][0]["span_id"] == sid(2, 5) and early["steps"][0]["offset_ns"] == 0
    assert [p["offset_ns"] for p in early["parents"]] == [10_000_000]


def test_ts_37_a_long_parent_id_is_one_digest_on_both_ends_of_the_link() -> None:
    deep = _item(_where("fixture B", "--timings")["timings"], the_row("fixture B", "alpha", 0))
    digest = written(LONG_ID)
    assert [p["span_id"] for p in deep["parents"]].count(digest) == 1
    children = [s for s in deep["steps"] if s["parent_id"] == digest]
    assert [s["span_id"] for s in children] == [sid(201, 9), sid(201, 10)]
    assert all(LONG_ID not in text for text in strings(deep))


def test_ts_38_parents_in_start_order_and_the_same_bytes_twice() -> None:
    deep = _item(_where("fixture B", "--timings")["timings"], the_row("fixture B", "alpha", 0))
    ids = [p["span_id"] for p in deep["parents"]]
    # two parents that start in the same nanosecond, in span id order
    assert ids == [sid(201, 1), sid(201, 2), sid(201, 3), sid(201, 4), written(LONG_ID)]
    assert deep["parents"][2]["offset_ns"] == deep["parents"][3]["offset_ns"]
    named = where_argv("fixture B", "--timings-of", pair(the_row("fixture B", "alpha", 0)), "--json")
    one, two = cli(read_only(), named), cli(read_only(), named)
    assert one.code == 0 and one.out == two.out


def test_ts_39_parents_count_toward_the_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = "cs record"
    full = _where(run, "--timings")["timings"]
    steps = [len(i["steps"]) for i in full["items"]]
    sizes = [len(i["steps"]) + len(i["parents"]) for i in full["items"]]
    most = sum(steps[:3])
    assert most < sum(sizes[:3])
    listed = max(m for m in range(len(sizes) + 1) if sum(sizes[:m]) <= most)
    assert listed < 3
    _ceiling(monkeypatch, most)
    work = fresh(tmp_path, "cs")
    t = json.loads(cli(work, [*where_argv(run), "--timings", "--json"]).out)["timings"]
    assert t["listed"] == listed and t["items"] == full["items"][:listed]
    line = _cut_line(listed, full["conversations"], most)
    assert line in details(cli(work, [*where_argv(run), "--timings"]).out)
    assert line in bundled(work, [*where_argv(run), "--timings"])["note"]


def test_ts_39_a_conversation_whose_links_cannot_be_followed_counts_its_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    full = _where("fixture D", "--timings")["timings"]
    sizes = [len(i["steps"]) + len(i["parents"] or ()) for i in full["items"]]
    assert [i["parents"] is None for i in full["items"]] == [False, True, True, False] and sizes[:3] == [3, 2, 2]
    _ceiling(monkeypatch, 7)
    t = json.loads(cli(read_only(), [*where_argv("fixture D"), "--timings", "--json"]).out)["timings"]
    assert t["listed"] == 3 and t["items"] == full["items"][:3]


def test_ts_40_a_trace_whose_links_cannot_be_followed_is_listed_with_no_parents() -> None:
    with_ = _where("fixture D", "--timings")
    t = with_["timings"]
    assert t["no_tree"] == 2 and t["listed"] == t["conversations"] == 4
    for task, replicate in (("alpha", 1), ("beta", 0)):
        row = the_row("fixture D", task, replicate)
        item = _item(t, row)
        assert item["parents"] is None and all(s["parent_id"] is None for s in item["steps"])
        assert item["steps"] == expected_item("fixture D", row, "kind")["steps"]
    without = _where("fixture D")
    assert {k: with_[k] for k in ("steps", "curve", "run")} == {k: without[k] for k in ("steps", "curve", "run")}


NAMED_ROW = ("fixture B", "alpha", 0)


@pytest.mark.parametrize("by", ["kind", "step"])
@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_41_nothing_outside_timings_moves_and_no_parent_carries_content(tmp_path: Path, verb: str, by: str) -> None:
    named = pair(the_row(*NAMED_ROW))
    base = where_argv("fixture B", "--by", by) if verb == "where" else compare_argv("fixture A B", "--by", by)
    forms = {"none": [], "whole": ["--timings"], "named": ["--timings-of", named]}
    printed = {name: doc([*base, *extra]) for name, extra in forms.items()}
    assert "timings" in printed["whole"] and "timings" in printed["named"]
    for name in ("whole", "named"):
        assert {k: v for k, v in printed[name].items() if k != "timings"} == printed["none"]
        _no_content(printed[name])
        for _side, t in _by_side(printed[name]):
            assert all(p["kind"] in (*KINDS, "unknown") for i in t["items"] for p in i["parents"] or ())
    results = {name: bundled(fresh(tmp_path / name), [*base, *extra]) for name, extra in forms.items()}
    for name in ("whole", "named"):
        _no_content(results[name])
        assert {k: v for k, v in results[name].items() if k not in ("timings", "saved")} == {
            k: v for k, v in results["none"].items() if k != "saved"}


# ---------- TS-42 to TS-51, TS-53: named conversations ----------


@pytest.mark.parametrize("value", ["3f9c", "3f9c:", ":0", "3f9c:x", "3f9c:-1", "3f9c:1.5"])
@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_42_a_word_that_is_not_hash_replicate_is_a_wrong_command_line(verb: str, value: str) -> None:
    argv = where_argv("fixture B") if verb == "where" else compare_argv("fixture A B")
    out = ran([*argv, "--timings-of", value])
    assert out.code == 2 and out.out == ""
    assert out.err == (f'error: argument --timings-of: "{value}" is not HASH:REPLICATE, such as 3f9c0a1b2d4e5f60:0\n'
                       f"  next: poisson-trace {verb} --help\n"), out.err
    _refused_as_unknown(["--timings-of", "3f9c:0"])


def test_ts_43_the_named_form_selects_and_each_item_is_the_whole_run_s() -> None:
    row = the_row(*NAMED_ROW)
    whole = _where("fixture B", "--timings")
    t = _where("fixture B", "--timings-of", pair(row))["timings"]
    assert t["asked"] == [{"config_hash": row.config_hash, "replicate_index": row.replicate_index}]
    assert t["most_steps"] is None and t["not_listed"] == [] and t["listed"] == 1
    assert t["conversations"] == whole["run"]["placement"]["placed"]
    assert json.dumps(t["items"][0], indent=2) == json.dumps(_item(whole["timings"], row), indent=2)
    one, zero = the_row("fixture B", "alpha", 1), row
    again = _where("fixture B", "--timings-of", pair(one), "--timings-of", pair(zero), "--timings-of", pair(one))["timings"]
    keys = [(zero.config_hash, 0), (one.config_hash, 1)]
    assert [(a["config_hash"], a["replicate_index"]) for a in again["asked"]] == keys
    assert [(i["config_hash"], i["replicate_index"]) for i in again["items"]] == keys
    assert again["items"] == [_item(whole["timings"], zero), _item(whole["timings"], one)]


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_44_timings_of_implies_timings_and_names_its_own_artifact(tmp_path: Path, verb: str) -> None:
    row = the_row(*NAMED_ROW)
    base = where_argv("fixture B") if verb == "where" else compare_argv("fixture A B")
    forms = {"named": ["--timings-of", pair(row)], "both": ["--timings", "--timings-of", pair(row)],
             "whole": ["--timings"], "none": []}
    printed = {name: ran([*base, *extra, "--json"]) for name, extra in forms.items()}
    assert printed["named"].code == 0 and printed["named"].out == printed["both"].out
    artifacts = {}
    for name, extra in forms.items():
        work = fresh(tmp_path / name)
        bundled(work, [*base, *extra])
        artifacts[name] = json.loads((work / "bundle" / "artifact.json").read_text(encoding="utf-8"))
    named = artifacts["named"]["settings"]
    assert named["timings"] is True and named["timings_of"] == [[row.config_hash, row.replicate_index]]
    assert named["from"]["timings"] == named["from"]["timings_of"] == "flag"
    assert list(named)[-4:] == ["timings", "timings_of", "from", "stores"]
    assert artifacts["named"]["id"] == artifacts["both"]["id"]
    assert len({artifacts[n]["id"] for n in ("named", "whole", "none")}) == 3
    whole = artifacts["whole"]["settings"]
    assert whole["timings"] is True and "timings_of" not in whole and "timings_of" not in whole["from"]
    assert whole["from"]["timings"] == "flag" and "timings" not in artifacts["none"]["settings"]


def test_ts_45_a_named_conversation_the_run_did_not_place_is_not_listed_with_why(tmp_path: Path) -> None:
    kept, no_leaf, no_outcome = the_row(*NAMED_ROW), the_row("fixture B", "beta", 1), the_row("fixture B", "gamma", 0)
    argv = where_argv("fixture B", "--timings-of", pair(kept), "--timings-of", pair(no_leaf), "--timings-of", pair(no_outcome))
    t = doc(argv)["timings"]
    assert t["listed"] == 1 and [(i["config_hash"], i["replicate_index"]) for i in t["items"]] == [(kept.config_hash, 0)]
    missed = sorted([(no_leaf, "no leaf span"), (no_outcome, "no outcome, not a timeout")], key=lambda x: (x[0].config_hash, x[0].replicate_index))
    assert t["not_listed"] == [{"config_hash": r.config_hash, "replicate_index": r.replicate_index, "why": why} for r, why in missed]
    line = ("timings lists 1 of the 3 conversations asked; not listed: "
            + ", ".join(f"{r.config_hash[:12]}:{r.replicate_index} ({why})" for r, why in missed))
    text = ran(argv)
    assert text.code == 0 and line in details(text.out)
    assert line in bundled(fresh(tmp_path), argv)["note"]


def test_ts_46_a_name_no_run_holds_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    h = the_row(*NAMED_ROW).config_hash
    one = ran(where_argv("fixture B", "--timings-of", f"{h}:7"))
    assert one.code == 1 and one.out == ""
    assert one.err == (f"error: --timings-of names {h}:7, which is not a conversation of the run B\n"
                       "  next: poisson-trace where B --store st --event failed --timings --json\n"), one.err
    two = ran(where_argv("fixture B", "--timings-of", f"{h}:9", "--timings-of", f"{h}:7", "--json"))
    assert two.code == 1 and two.out == ""
    assert two.err.splitlines()[0] == f"error: --timings-of names {h}:7 and {h}:9, which are not conversations of the run B"
    work = fresh(tmp_path)
    out = cli(work, where_argv("fixture B", "--timings-of", f"{h}:7", "--out", "bundle"))
    assert out.code == 1 and not (work / "bundle").exists()
    both = ran(compare_argv("fixture A B", "--timings-of", f"{h}:7"))
    assert both.code == 1 and both.out == ""
    assert both.err == (f"error: --timings-of names {h}:7, which is not a conversation of A (before) or of B (after)\n"
                        "  next: poisson-trace compare A B --store st --event failed --max-mde-hr 2 --timings --json\n"), both.err


def test_ts_46_a_name_one_side_holds_is_not_listed_on_the_other() -> None:
    only_b = the_row("fixture B", "alpha", 2)
    assert not [r for r in stored("fixture A") if (r.config_hash, r.replicate_index) == (only_b.config_hash, 2)]
    argv = compare_argv("fixture A B", "--timings-of", pair(only_b))
    t = doc(argv)["timings"]
    assert [(i["config_hash"], i["replicate_index"]) for i in t["b"]["items"]] == [(only_b.config_hash, 2)]
    assert t["a"]["items"] == [] and t["b"]["not_listed"] == []
    assert t["a"]["not_listed"] == [{"config_hash": only_b.config_hash, "replicate_index": 2, "why": "not in the run"}]
    line = f"timings lists 0 of the 1 conversations asked of A (before); not listed: {only_b.config_hash[:12]}:2 (not in the run)"
    text = ran(argv)
    assert text.code == 0 and line in details(text.out)
    assert not [x for x in details(text.out) if "of B (after)" in x]


def test_ts_47_one_list_names_the_pair_on_both_sides() -> None:
    row = stored("agent before")[0]
    asked = [{"config_hash": row.config_hash, "replicate_index": i} for i in (0, 1)]
    t = doc(compare_argv("workspace", "--timings-of", f"{row.config_hash}:1", "--timings-of", f"{row.config_hash}:0"))["timings"]
    assert t["a"]["asked"] == t["b"]["asked"] == asked
    a = {(i["config_hash"], i["replicate_index"]): i for i in t["a"]["items"]}
    b = {(i["config_hash"], i["replicate_index"]): i for i in t["b"]["items"]}
    assert list(a) == list(b) == [(x["config_hash"], x["replicate_index"]) for x in asked]
    assert all(a[k]["seed"] == b[k]["seed"] for k in a)


def test_ts_48_the_named_form_has_no_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    row = the_row(*NAMED_ROW)
    whole = _item(_where("fixture B", "--timings")["timings"], row)
    _ceiling(monkeypatch, 2)
    work = fresh(tmp_path)
    argv = where_argv("fixture B", "--timings-of", pair(row))
    t = json.loads(cli(work, [*argv, "--json"]).out)["timings"]
    assert t["most_steps"] is None and t["listed"] == 1 and t["items"] == [whole]
    assert not [x for x in details(cli(work, argv).out) if x.startswith("timings lists")]
    assert not [x for x in bundled(work, argv)["note"] if x.startswith("timings lists")]


def test_ts_49_the_api_takes_timings_of() -> None:
    a = api()
    store = str(read_only() / "st")
    row = the_row(*NAMED_ROW)
    named = a.where(store, "B", event=["failed"], timings_of=[(row.config_hash, 0)])
    assert named.timings == doc(where_argv("fixture B", "--timings-of", pair(row)))["timings"]
    assert named.timings["asked"] is not None
    both = a.compare(store, "A", "B", event=["failed"], max_mde_hr=2, timings_of=[(row.config_hash, 0)])
    assert both.timings == doc(compare_argv("fixture A B", "--timings-of", pair(row)))["timings"]
    said = "timings_of takes (config_hash, replicate_index) pairs, as the flag's HASH:REPLICATE is read"
    for wrong in (f"{row.config_hash}:0", (row.config_hash, -1), (row.config_hash, True), (1, 0)):
        with pytest.raises(ValueError) as e:
            a.where(store, "B", event=["failed"], timings_of=[wrong])
        assert str(e.value).startswith(said), str(e.value)
    with pytest.raises(a.Refusal) as refused:
        a.where(store, "B", event=["failed"], timings_of=[(row.config_hash, 7)])
    assert str(refused.value) == f"--timings-of names {row.config_hash}:7, which is not a conversation of the run B"
    assert refused.value.exit_code == 1


@pytest.mark.parametrize("verb", ["where", "compare"])
def test_ts_50_the_help_lists_timings_of(verb: str) -> None:
    out = ran([verb, "--help"])
    assert out.code == 0
    assert _help_entry(out.out, "--timings-of") == f"--timings-of HASH:REPLICATE {TIMINGS_OF_HELP}"


def test_ts_51_the_check_passes_nested_and_named_bundles_and_fails_their_breaks(tmp_path: Path) -> None:
    kept, no_leaf = the_row(*NAMED_ROW), the_row("fixture B", "beta", 1)
    only_b = the_row("fixture B", "alpha", 2)
    cases = {
        "where": where_argv("fixture B", "--timings"),
        "compare": compare_argv("fixture A B", "--timings"),
        "where named": where_argv("fixture B", "--timings-of", pair(kept), "--timings-of", pair(no_leaf)),
        "compare named": compare_argv("fixture A B", "--timings-of", pair(kept), "--timings-of", pair(only_b)),
    }
    for name, argv in cases.items():
        bundle = _a_bundle(tmp_path, argv, name.replace(" ", "-"))
        assert _check(bundle).code == 0, (name, _check(bundle).text)
    line = "result.json's timings is not a timings object"
    breaks = [
        ("where", "a parent loses kind", lambda r: r["timings"]["items"][0]["parents"][0].pop("kind")),
        ("where", "a step's parent_id is a number", lambda r: r["timings"]["items"][0]["steps"][0].__setitem__("parent_id", 7)),
        ("where", "parents is a string", lambda r: r["timings"]["items"][0].__setitem__("parents", "none")),
        ("where named", "asked is a string", lambda r: r["timings"].__setitem__("asked", "all")),
        ("where named", "a why not one of the five", lambda r: r["timings"]["not_listed"][0].__setitem__("why", "skipped")),
    ]
    for case, name, change in breaks:
        bundle = _a_bundle(tmp_path, cases[case], f"{case}-{name}".replace(" ", "-").replace("'", ""))
        _edit(bundle, change)
        _fails(bundle, line)
    bundle = _a_bundle(tmp_path, cases["compare named"], "compare-b")
    _edit(bundle, lambda r: r["timings"]["b"].__setitem__("asked", "all"))
    _fails(bundle, "result.json's timings.b is not a timings object")


def test_ts_53_where_by_step_returns_on_a_parent_cycle() -> None:
    cycle = the_row("fixture D", "beta", 0)
    assert not [s for s in cycle.spans if s.get("step_name")]
    try:
        out = run_sub("trace", ["where", "D", "--store", "st", *EVENT, "--by", "step", "--json"], cwd=read_only(), timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail("where --by step did not return within 10 seconds on a trace with a parent cycle")
    assert out.code == 0, out.text
    document = json.loads(out.out)
    assert document["causes"] == [{**document["causes"][0], "cause": "unnamed", "deaths": 2}]
    assert {x["label"] for s in document["steps"] for x in s["labels"]} == {"unnamed"}
