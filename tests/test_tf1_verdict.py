"""TF1-9, TF1-10 and TF1-12: the result first (spec sections 9.4 and 9.1, rules L3 and L9; TF0's
handed-on ``wrote`` line).

Every verb's first stdout line is its verdict line, ``<word>  <sentence>``, then one blank line,
then the report as before. The word is from the verb's closed set; for ``compare`` and
``fix-check`` the sentence is the report's bold line after its verdict word, and the bold line
stays in the report; for the others the sentence states the facts the spec's line carries. With
``--json`` the document opens ``schema``, ``verdict``, ``sentence``, closes with ``next``, and
keeps every key it had; its verdict and sentence are the verdict line's, word for word. An SVG
written is said on the line right under the verdict line. Ctrl-C under ``--json`` leaves stdout
one JSON document."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from proofload.store import Store

from conftest import COMPARE_KEYS, WHERE_KEYS, deaths_rows
from fixcheck_support import CHANGES_KEYS, FIX_KEYS
from tf0_support import (
    VERDICT_LINE, changes_he, chdir, compare_tau2, deepeval_import, fix_check_he, fix_check_tau2, fix_check_tau2_all,
    trace, trace_import, where_cs,
)
from tf1_support import (
    T_B, counts_in, first_line, import_he, name, next_line, refused, runs_json, tau2_copy, verdict_parts,
)

THREE = ("different", "no significant difference", "too small to tell")


def _bold(out: str) -> str:
    lines = [line for line in out.splitlines() if line.startswith("**") and line.endswith("**")]
    assert len(lines) == 1, out
    return lines[0][2:-2]


def _plain(text: str) -> str:
    """Words and numbers, without the punctuation that joins a verdict word to its sentence."""
    return " ".join(re.sub(r"[():;,]", " ", text).split())


def _opens_with_the_verdict(result: Any) -> tuple[str, str]:
    assert result.code == 0, result.text
    lines = result.out.splitlines()
    assert VERDICT_LINE.match(lines[0]), lines[0]
    assert lines[1] == "", lines[:3]
    assert lines[2].startswith("# Poisson Trace · "), lines[:3]
    return verdict_parts(lines[0])


# ---------- TF1-9: compare and fix-check, the three lines ----------


@pytest.fixture
def compare_cases(two_run_store) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    different = two_run_store(deaths_rows(list(range(1, 21))), deaths_rows(list(range(21, 41))))
    return {
        "different": ["compare", "a", "b", "--store", str(different), "--event", "fail", "--max-mde-hr", "100"],
        "no significant difference": compare_tau2("1.5"),
        "too small to tell": compare_tau2("1.3"),
    }


FIX_CASES = {
    "different": fix_check_he(),
    "no significant difference": fix_check_tau2_all("0.2"),
    "too small to tell": fix_check_tau2(),
}


@pytest.mark.parametrize("want", THREE)
def test_tf1_09_compare_opens_with_its_verdict_and_keeps_the_bold_line(compare_cases: dict[str, list[str]], want: str) -> None:
    result = trace(compare_cases[want])
    word, sentence = _opens_with_the_verdict(result)
    assert word == want
    bold = _bold(result.out)
    assert bold.startswith(want), bold
    assert _plain(sentence) == _plain(bold[len(want):]), (sentence, bold)
    assert trace([*compare_cases[want], "--json"]).json()["comparison"]["verdict"] == want


@pytest.mark.parametrize("want", THREE)
def test_tf1_09_fix_check_opens_with_its_verdict_and_keeps_the_bold_line(want: str) -> None:
    result = trace(FIX_CASES[want])
    word, sentence = _opens_with_the_verdict(result)
    assert word == want
    bold = _bold(result.out)
    assert bold.startswith(want), bold
    assert _plain(sentence) == _plain(bold[len(want):]), (sentence, bold)


def test_tf1_09_where_states_the_deaths_the_kinds_and_the_median() -> None:
    word, sentence = _opens_with_the_verdict(trace(where_cs()))
    assert word == "ok"
    # cs record: 7 of 24 placed episodes died, 4 at a model call and 3 at an agent; median 50
    assert sorted(counts_in(sentence), key=int) == ["3", "4", "7", "24", "50"], sentence


def test_tf1_09_where_with_no_death_states_the_episodes_and_the_events(two_run_store) -> None:  # type: ignore[no-untyped-def]
    # the event is carried, but every row carrying it sits at the cap: four placed, none died
    rows = deaths_rows([2, 3], died=False) + deaths_rows([4, 4], died=True, start_rep=5)
    root = two_run_store(rows, rows, cap=4)
    word, sentence = _opens_with_the_verdict(trace(["where", "a", "--store", str(root), "--event", "fail"]))
    assert word == "ok" and counts_in(sentence) == ["4"] and "fail" in sentence, sentence


def test_tf1_09_where_on_a_run_with_no_traces_claims_no_count(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert import_he(store, "he-a").code == 0
    word, sentence = _opens_with_the_verdict(trace(["where", "he-a", "--store", str(store), "--event", "missed"]))
    assert word == "ok" and counts_in(sentence) == [], sentence


def test_tf1_09_changes_states_how_many_inputs_changed_of_how_many() -> None:
    result = trace(changes_he())
    word, sentence = _opens_with_the_verdict(result)
    doc = trace(changes_he("--json")).json()
    assert word == "ok"
    assert counts_in(sentence)[:2] == [str(doc["flagged"]), str(doc["tested"])], sentence
    assert (doc["flagged"], doc["tested"]) == (2, 328)


def test_tf1_09_import_states_the_run_the_store_and_what_it_wrote(tmp_path: Path) -> None:
    store = tmp_path / "store"
    result = import_he(store, "he-a")
    word, sentence = _opens_with_the_verdict(result)
    assert word == "ok"
    assert "he-a" in sentence and str(store) in sentence, sentence
    assert {"10,496", "328"} <= set(counts_in(sentence)), sentence


def test_tf1_09_runs_and_name_open_with_their_verdict(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    for result in (trace(["runs", "--store", str(store)]), name(store, T_B, "old"), name(store, "--list"), name(store, "old", "--forget")):
        assert result.code == 0, result.text
        assert verdict_parts(first_line(result))[0] == "ok"


# ---------- TF1-10: the JSON ----------


@pytest.mark.parametrize("verb", ["where", "compare", "fix-check", "changes", "runs", "import"])
def test_tf1_10_the_json_opens_with_the_verdict_line_and_closes_with_next(tmp_path: Path, verb: str) -> None:
    if verb == "import":
        # the same import into two folders, once as text and once as JSON
        (tmp_path / "text").mkdir()
        (tmp_path / "json").mkdir()
        with chdir(tmp_path / "text"):
            text = trace_import(deepeval_import("store", "he-a"))
        with chdir(tmp_path / "json"):
            as_json = trace_import([*deepeval_import("store", "he-a"), "--json"])
    else:
        argv = {
            "where": where_cs(), "compare": compare_tau2("1.3"), "fix-check": fix_check_tau2(), "changes": changes_he(),
            "runs": ["runs", "--store", str(tau2_copy(tmp_path)), "--event", "unsolved"],
        }[verb]
        text, as_json = trace(argv), trace([*argv, "--json"])
    assert text.code == 0 and as_json.code == 0, as_json.text
    doc = as_json.json()
    assert list(doc)[:3] == ["schema", "verdict", "sentence"], list(doc)
    assert list(doc)[-1] == "next", list(doc)
    assert (doc["verdict"], doc["sentence"]) == verdict_parts(first_line(text))
    assert doc["next"] == next_line(text)


@pytest.mark.parametrize("verb,keys", [("where", WHERE_KEYS), ("compare", COMPARE_KEYS), ("fix-check", FIX_KEYS), ("changes", CHANGES_KEYS)])
def test_tf1_10_every_key_the_json_had_is_kept_in_its_order(verb: str, keys: tuple[str, ...]) -> None:
    argv = {"where": [*where_cs(), "--json"], "compare": compare_tau2("1.3", "--json"), "fix-check": fix_check_tau2("--json"), "changes": changes_he("--json")}[verb]
    result = trace(argv)
    assert result.code == 0, result.text
    doc = result.json()
    added = ("verdict", "sentence", "next")
    # where's "declared" is there only when the run declares its steps
    want = [k for k in keys if k not in added and (k != "declared" or k in doc)]
    assert [k for k in doc if k not in added] == want, list(doc)


def test_tf1_10_fix_check_has_one_verdict_and_it_is_second() -> None:
    raw = trace(fix_check_tau2("--json")).out
    assert raw.count('"verdict"') == 1, raw[:400]
    doc = trace(fix_check_tau2("--json")).json()
    assert list(doc)[1] == "verdict" and doc["verdict"] == "too small to tell"


# ---------- TF1-12: the wrote line ----------


def test_tf1_12_the_svg_written_is_said_right_under_the_verdict_line(tmp_path: Path) -> None:
    svg = tmp_path / "curve.svg"
    with_svg = trace(where_cs("--svg", str(svg)))
    without = trace(where_cs())
    assert with_svg.code == 0 and svg.exists(), with_svg.text
    lines = with_svg.out.splitlines()
    assert lines[0] == without.out.splitlines()[0]
    assert lines[1].startswith("  wrote  ") and lines[1].endswith(str(svg)), lines[:3]
    assert lines[2] == "", lines[:3]
    assert with_svg.out.replace(lines[1] + "\n", "", 1) == without.out


# ---------- Ctrl-C under --json ----------


def test_tf1_10_ctrl_c_under_json_leaves_one_json_document(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(self: Store, *args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "read", interrupted)
    result = trace([*where_cs(), "--json"])
    assert result.code == 130, result.text
    doc = result.json()
    assert list(doc)[:3] == ["schema", "verdict", "sentence"] and doc["schema"] == "poisson-trace.where/1"
    assert doc["verdict"] == "stopped", doc
    plain = trace(where_cs())
    assert plain.code == 130 and verdict_parts(first_line(plain))[0] == "stopped"


def test_tf1_09_a_refusal_prints_no_verdict_line(tmp_path: Path) -> None:
    refused(trace(["runs", "--store", str(tmp_path / "nothing-here")]))
    assert runs_json(tau2_copy(tmp_path))["verdict"] == "ok"
