"""TR21, TR26 to TR30: the outputs, in markdown, JSON and SVG, and the
wording the source must and must not carry."""

from __future__ import annotations

import ast
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from poisson_prove.steps import declaration_check
from poisson_prove.store import Store

from pin_support import installed
from conftest import (
    CANNOT_SAY, COMPARE_KEYS, CS, CS_EVENTS, CS_RECORD, SYNTH_CAP,
    SYNTH_DECLARED, SYNTH_EVENTS, TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, WHERE_KEYS, Row, build_store,
    chdir, compare, deaths_rows, norm, synth_rows, where,
)


def package() -> Path:
    import poisson_trace

    return Path(poisson_trace.__file__).resolve().parent


def src_files() -> list[Path]:
    """Every module of the package, the readers' and the statistics' included."""
    return sorted(package().rglob("*.py"))


BANNED = ("better", "worse", "unchanged", "verified", "guaranteed", "pass", "sure")
# The one banned word the readers may carry: ``pass`` is the tools' own word for a met verdict
# (and Python's statement), in the modules under ``ingest/`` only.
READERS_WORD = re.compile(r"\bpass\b", re.IGNORECASE)
# A banned word allowed in one sentence of one module, by the words around it.
ALLOWED_PHRASES = (("stats/continuous.py", "looks better"),)


# ---------- TR21 ----------


def _pair_a_later(two_run_store):  # type: ignore[no-untyped-def]
    # A dies late, B dies early: O_A < E_A, so runs die later in A and earlier in B.
    return two_run_store(deaths_rows(list(range(21, 41))), deaths_rows(list(range(1, 21))))


def _pair_identical(two_run_store):  # type: ignore[no-untyped-def]
    return two_run_store(deaths_rows(list(range(1, 11))), deaths_rows(list(range(1, 11))))


def test_tr21_direction_names_the_arm_that_dies_earlier(two_run_store) -> None:  # type: ignore[no-untyped-def]
    later_in_a = compare(_pair_a_later(two_run_store), "a", "b", ["fail"], 100.0)
    earlier_in_a = compare(_pair_a_later(two_run_store), "b", "a", ["fail"], 100.0)
    assert later_in_a.code == 0 and earlier_in_a.code == 0, later_in_a.text + earlier_in_a.text
    a_text, b_text = norm(later_in_a.out), norm(earlier_in_a.out)
    assert "earlier in B" in a_text and "later in A" in a_text
    assert "later in B" in b_text and "earlier in A" in b_text
    a_json = compare(_pair_a_later(two_run_store), "a", "b", ["fail"], 100.0, "--json").json()["comparison"]
    assert a_json["observed_a"] < a_json["expected_a"]
    assert "earlier in B" in a_json["direction"]


def test_tr21_equality_prints_no_direction(two_run_store) -> None:  # type: ignore[no-untyped-def]
    result = compare(_pair_identical(two_run_store), "a", "b", ["fail"], 100.0, "--json")
    assert result.code == 0, result.text
    comparison = result.json()["comparison"]
    assert comparison["observed_a"] == comparison["expected_a"]
    assert comparison["direction"] == "no direction"
    assert "no direction" in norm(compare(_pair_identical(two_run_store), "a", "b", ["fail"], 100.0).out)


# ---------- TR26 ----------


def test_tr26_json_is_byte_identical_across_invocations() -> None:
    one = where(TAU2, TAU2_A, TAU2_EVENTS, "--at", "10", "--json")
    two = where(TAU2, TAU2_A, TAU2_EVENTS, "--at", "10", "--json")
    assert one.code == two.code == 0, one.text
    assert one.out == two.out
    c1 = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--json")
    c2 = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--json")
    assert c1.code == c2.code == 0, c1.text
    assert c1.out == c2.out


def test_tr26_json_is_byte_identical_across_span_order(tmp_path: Path) -> None:
    rows = synth_rows()
    reversed_rows = [Row(r.config, r.outcome, None if r.spans is None else list(r.spans)[::-1], r.error, r.replicate_index) for r in rows]
    for name, batch in (("one", rows), ("two", reversed_rows)):
        (tmp_path / name).mkdir()
        build_store(tmp_path / name / "store", "run", batch, cap=SYNTH_CAP, declared=SYNTH_DECLARED)
    outputs = []
    for name in ("one", "two"):
        with chdir(tmp_path / name):
            result = where("store", "run", SYNTH_EVENTS, "--at", "2", "--json")
            assert result.code == 0, result.text
            outputs.append(result.out)
    assert outputs[0] == outputs[1]


def test_tr26_keys_are_in_the_spec_order_and_nothing_is_nan(synth) -> None:  # type: ignore[no-untyped-def]
    declared = where(*synth, SYNTH_EVENTS, "--at", "2", "--json")
    plain = where(TAU2, TAU2_A, TAU2_EVENTS, "--at", "10", "--json")
    cmp = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--at", "10", "--json")
    for r in (declared, plain, cmp):
        assert r.code == 0, r.text
        assert r.out.rstrip("\n").endswith("}")
        json.loads(r.out, parse_constant=_reject)
    assert list(declared.json()) == list(WHERE_KEYS)
    assert list(plain.json()) == [k for k in WHERE_KEYS if k != "declared"]
    assert list(cmp.json()) == list(COMPARE_KEYS)
    assert declared.json()["schema"] == "poisson-trace.where/1"
    assert cmp.json()["schema"] == "poisson-trace.compare/1"
    assert plain.json()["prove"] == {"version": installed(), "store": str(TAU2)}  # the Prove installed, at or above the floor
    assert plain.json()["clock"] == {"unit": "leaf span index", "by": "kind"}
    for row in plain.json()["curve"]:
        assert list(row) == ["step", "at_risk", "died", "survival", "var", "lo", "hi"]
    for row in plain.json()["causes"]:
        assert list(row) == ["cause", "deaths", "f", "lo", "hi"]
    assert set(cmp.json()["comparison"]) >= {
        "cells", "excluded_cells", "observed_a", "expected_a", "variance", "statistic", "p", "alpha",
        "direction", "paired", "mde_hazard_ratio", "max_mde_hr", "verdict",
    }
    assert cmp.json()["comparison"]["paired"] is False
    for row in cmp.json()["per_cause"]:
        assert set(row) >= {"cause", "deaths_a", "deaths_b", "statistic", "p", "q", "mde_hazard_ratio"}


def _reject(name: str) -> None:
    raise ValueError(name)


# ---------- TR27 ----------


def _svg_tags(path: Path) -> list[str]:
    tree = ET.parse(path)
    return [el.tag.split("}")[-1] for el in tree.iter()]


def _svg_text(path: Path) -> str:
    return norm(" ".join(el.text or "" for el in ET.parse(path).iter()))


@pytest.mark.parametrize("root,run,events,n_causes", [(TAU2, TAU2_A, TAU2_EVENTS, 1), (CS, CS_RECORD, CS_EVENTS, 2)])
def test_tr27_svg_parses_with_one_polyline_per_curve_and_the_labels(tmp_path: Path, root, run, events, n_causes) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "curve.svg"
    result = where(root, run, events, "--svg", str(out))
    assert result.code == 0, result.text
    tags = _svg_tags(out)
    assert tags.count("polyline") == 1 + n_causes
    assert tags.count("polygon") == 1
    text = _svg_text(out)
    assert "step" in text.split()
    # the curve is the share not yet failed, Aalen-Johansen's, banded by resampling inputs;
    # Kaplan-Meier and Greenwood are named nowhere
    assert "share of runs not yet failed" in text and "share of runs still going" not in text
    assert "Kaplan-Meier" not in text and "Greenwood" not in text
    assert "Aalen-Johansen" in text and "bootstrap" in text


def test_tr27_svg_is_the_only_file_written(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "out.svg"
    with chdir(work):
        result = where(TAU2, TAU2_A, TAU2_EVENTS, "--svg", str(out))
        assert result.code == 0, result.text
        plain = where(TAU2, TAU2_A, TAU2_EVENTS)
        assert plain.code == 0
        cmp = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5)
        assert cmp.code == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.svg", "work"]
    assert list(work.iterdir()) == []


# ---------- TR28 ----------


def test_tr28_every_caption_names_its_test_and_band() -> None:
    w = where(CS, CS_RECORD, CS_EVENTS)
    c = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5)
    assert w.code == 0 and c.code == 0, w.text + c.text
    wt, ct = norm(w.out), norm(c.out)
    # Aalen-Johansen with competing ends, a band resampling inputs;
    # compare's limit from the log-rank's own information, not Schoenfeld's
    for word in ("Aalen-Johansen", "bootstrap", "resampling inputs"):
        assert word in wt, word
    for word in ("log-rank", "stratified", "Benjamini-Hochberg", "information"):
        assert word in ct, word
    assert "Schoenfeld" not in ct and "Kaplan-Meier" not in wt and "Greenwood" not in wt
    assert re.search(r"B = \d+", wt) and re.search(r"seed = \d+", wt)


def test_tr21_tr28_the_banned_words_appear_nowhere_in_src_but_the_readers_pass() -> None:
    """No module holds a verdict word Trace never says (TR21's better, worse and unchanged; TR28's
    verified, guaranteed, pass and sure), but for ``pass`` under ``ingest/`` and the phrases
    ``ALLOWED_PHRASES`` names."""
    pattern = re.compile(r"\b(" + "|".join(BANNED) + r")\b", re.IGNORECASE)
    for path in src_files():
        name = path.relative_to(package()).as_posix()
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            read = READERS_WORD.sub("", line) if name.startswith("ingest/") else line
            for module, phrase in ALLOWED_PHRASES:
                if module == name:
                    read = read.replace(phrase, "")
            assert not pattern.search(read), f"{name}:{lineno}: {line.strip()}"


def test_tr28_no_verdict_word_leaks_into_the_reports(two_run_store) -> None:  # type: ignore[no-untyped-def]
    root = _pair_identical(two_run_store)
    outputs = [
        compare(root, "a", "b", ["fail"], 100.0).out,
        compare(root, "a", "b", ["fail"], 1.01).out,
        where(TAU2, TAU2_A, TAU2_EVENTS).out,
    ]
    pattern = re.compile(r"\b(unchanged|verified|guaranteed|pass|sure|better|worse)\b", re.IGNORECASE)
    for text in outputs:
        assert not pattern.search(text)


# ---------- TR29 ----------


def test_tr29_the_cannot_say_block_prints_under_both_verbs_and_is_in_the_json(synth) -> None:  # type: ignore[no-untyped-def]
    w = where(*synth, SYNTH_EVENTS)
    c = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5)
    assert w.code == 0 and c.code == 0, w.text + c.text
    for out in (w.out, c.out):
        text = norm(out)
        for sentence in CANNOT_SAY:
            assert sentence in text, sentence
    wj = where(*synth, SYNTH_EVENTS, "--json").json()
    cj = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.5, "--json").json()
    assert wj["cannot_say"] == list(CANNOT_SAY)
    assert cj["cannot_say"] == list(CANNOT_SAY)


# ---------- TR30 ----------


def _declared_lines(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if "Declared steps" in line)
    out: dict[str, str] = {}
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        for name in ("plan", "act", "check", "extra"):
            if re.search(rf"\b{name}\b", line):
                out.setdefault(name, norm(line))
    return out


def test_tr30_declared_table_lists_names_reached_by_counts_and_never_reached(synth) -> None:  # type: ignore[no-untyped-def]
    root, run = synth
    result = where(root, run, SYNTH_EVENTS)
    assert result.code == 0, result.text
    lines = _declared_lines(result.out)
    assert set(lines) == {"plan", "act", "check", "extra"}
    assert "1 of 4" in lines["plan"] and "never reached" not in lines["plan"]
    assert "2 of 4" in lines["act"] and "never reached" not in lines["act"]
    assert "0 of 4" in lines["check"] and "never reached" in lines["check"]
    assert "never reached" not in lines["extra"]
    store = Store(root)
    check = declaration_check(store.manifest(run), store.read(run, meta=False, trace="envelope"))
    assert check is not None and check.never_reached == frozenset({"check"})
    assert check.undeclared_steps == frozenset({"extra"})
    data = where(root, run, SYNTH_EVENTS, "--json").json()
    assert data["declared"] == check.provenance()


def test_tr30_a_run_with_no_declaration_prints_no_such_word_and_has_no_key() -> None:
    md = where(TAU2, TAU2_A, TAU2_EVENTS)
    js = where(TAU2, TAU2_A, TAU2_EVENTS, "--json")
    assert md.code == 0 and js.code == 0, md.text + js.text
    text = norm(md.out).lower()
    assert "declared" not in text
    assert "never reached" not in text
    assert "declared" not in js.json()
    assert "declared" not in js.out


def test_tr30_never_reached_is_read_from_prove_and_computed_nowhere_in_src() -> None:
    for path in src_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            for t in targets:
                for name in ast.walk(t):
                    assert not (isinstance(name, ast.Name) and name.id == "never_reached"), path.name
                    assert not (isinstance(name, ast.Attribute) and name.attr == "never_reached"), path.name
        assert "never_reached =" not in path.read_text()
        assert "never_reached=" not in path.read_text()
