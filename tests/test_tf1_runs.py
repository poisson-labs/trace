"""TF1-7: ``poisson-trace runs`` (``docs/commands.md``).

The runs of a store, newest first by start time: each complete run's number, its name, Prove's
row count, how many rows failed for the events given, whether any row carries a trace, when it
started (UTC, to the minute) and its status. Partial runs are hidden but counted unless
``--all``; past the newest 50 complete runs the listing says how many more there are and reads
no further. The verdict line counts every run and how each is named; ``next:`` points ``where``
at the newest run that carries traces, or at ``fix-check --help`` when none does. ``--json`` is
``poisson-trace.runs/1``, one row per run under ``runs``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from poisson_prove.store import Store

from conftest import FIXTURES
from tf0_support import HE_A, HE_B, chdir, run_sub, trace
from tf1_support import (
    T_A, T_B, T_NAMES, T_PILOT, R, counts_in, first_line, import_he, make_runs, name, next_line,
    positionals, resolved, runs_json, stamp, tau2_copy, verdict_parts,
)

ROW_KEYS = ("number", "name", "run_id", "named_by", "rows", "failed", "traced", "created_at", "status", "target_id", "backend")


def _line_of(text: str, shown: str) -> str:
    found = [line for line in text.splitlines() if shown in line and not line.startswith("next:")]
    assert len(found) == 1, (shown, text)
    return found[0]


def test_tf1_07_the_listing_newest_first_with_what_each_run_can_do(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["runs", "--store", str(store), "--event", "unsolved"])
    assert result.code == 0 and result.err == "", result.text
    text = result.out
    rows = [(T_PILOT, "1", "10", "3", "no", "2026-09-17 14:02"), (T_B, "2", "200", "112", "yes", "2026-09-15 21:11"),
            (T_A, "3", "200", "110", "yes", "2026-09-15 21:01")]
    at = [text.index(T_NAMES[run]) for run, *_ in rows]
    assert at == sorted(at), "newest first"
    for run, number, count, failed, traces, started in rows:
        line = _line_of(text, T_NAMES[run])
        words = line.replace(T_NAMES[run], " ").split()
        assert words[0] == number, line
        # the columns in their order: rows, failed, traces, started, status
        at = [words.index(w) for w in (count, failed, traces, started.split()[0], "complete")]
        assert at == sorted(at), line
        assert started in line, line
        # the listing names a run by its name and never asks for its id
        assert run not in line, line


def test_tf1_07_the_verdict_counts_every_run_and_how_it_is_named(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    assert name(store, T_B, "old re-run").code == 0
    with chdir(tmp_path):
        result = trace(["runs", "--store", "proofload-runs"])
    word, sentence = verdict_parts(first_line(result))
    assert word == "ok"
    assert "proofload-runs" in sentence, sentence
    assert counts_in(sentence) == ["3", "1", "2"], sentence


def test_tf1_07_the_json_row_by_row(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    doc = runs_json(store, "--event", "unsolved")
    assert list(doc)[:3] == ["schema", "verdict", "sentence"] and list(doc)[-1] == "next"
    assert doc["schema"] == "poisson-trace.runs/1" and doc["verdict"] == "ok"
    rows = doc["runs"]
    assert all(tuple(r) == ROW_KEYS for r in rows), [tuple(r) for r in rows]
    got = [(r["number"], r["name"], r["run_id"], r["named_by"], r["rows"], r["failed"], r["traced"], r["status"], r["backend"]) for r in rows]
    assert got == [
        (1, T_NAMES[T_PILOT], T_PILOT, "manifest", 10, 3, False, "complete", "modal"),
        (2, T_NAMES[T_B], T_B, "manifest", 200, 112, True, "complete", "modal"),
        (3, T_NAMES[T_A], T_A, "manifest", 200, 110, True, "complete", "modal"),
    ]
    manifest = Store(store).manifest(T_B)
    assert (rows[1]["created_at"], rows[1]["target_id"]) == (manifest.created_at, manifest.target_id)


def test_tf1_07_without_events_failed_is_not_counted_and_a_note_says_so(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["runs", "--store", str(store)])
    assert result.code == 0, result.text
    notes = [line for line in result.lines() if line.startswith("note: ")]
    assert len(notes) == 1 and len(result.lines()) == 1, result.err
    line = _line_of(result.out, T_NAMES[T_B])
    assert "–" in line.split() and "112" not in line.split(), line
    assert all(r["failed"] is None for r in runs_json(store)["runs"])


def test_tf1_07_counts_carry_separators_and_no_traces_says_no(tmp_path: Path) -> None:
    import shutil

    store = tmp_path / "he"
    shutil.copytree(FIXTURES / "humaneval", store)
    result = trace(["runs", "--store", str(store), "--event", "failed_assertion"])
    assert result.code == 0, result.text
    for run, failed in ((HE_A, "1,330"), (HE_B, "1,376")):
        words = _line_of(result.out, resolved_name(store, run)).split()
        assert "10,496" in words and failed in words and "no" in words, words
    # no run carries traces: where has nothing to read, so the next step is the fix check
    assert next_line(result).split()[:3] == ["poisson-trace", "fix-check", "--help"]


def resolved_name(store: Path, run: str) -> str:
    return next(r["name"] for r in runs_json(store, "--all")["runs"] if r["run_id"] == run)


def test_tf1_07_next_is_where_on_the_newest_run_with_traces(tmp_path: Path) -> None:
    store = tau2_copy(tmp_path)
    result = trace(["runs", "--store", str(store), "--event", "unsolved"])
    command = next_line(result)
    words = positionals(command, "where")
    assert len(words) == 1, command
    # the pilot is newest and carries no trace; the run before it does
    assert resolved(store, words[0], "unsolved") == T_B
    assert runs_json(store, "--event", "unsolved")["next"] == command


def test_tf1_07_imported_runs_say_where_cannot_read_them(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert import_he(store, "he-a").code == 0
    rows = runs_json(store)["runs"]
    assert [(r["name"], r["traced"], r["backend"]) for r in rows] == [("he-a", False, "import:deepeval")]
    words = _line_of(trace(["runs", "--store", str(store)]).out, "he-a").split()
    assert "no" in words and "10,496" in words, words


# ---------- partial runs and the newest 50 ----------


@pytest.fixture(scope="module")
def many(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """53 complete runs, one a minute, and a partial one between the newest two."""
    runs = [R(f"run-{i:02d}", stamp(7, 1, i), rows=("fail", "ok"), traced=i % 2 == 0) for i in range(53)]
    runs.append(R("half-done", stamp(7, 1, 51, 30), status="partial"))
    return make_runs(tmp_path_factory.mktemp("many") / "store", runs)


def test_tf1_07_partial_runs_are_hidden_but_counted(many: Path) -> None:
    result = trace(["runs", "--store", str(many)])
    assert result.code == 0, result.text
    assert "half-done" not in result.out and resolved_name(many, "half-done") not in result.out
    assert "54" in counts_in(verdict_parts(first_line(result))[1])
    footer = [line for line in result.out.splitlines() if "--all" in line and not line.startswith("next:")]
    assert footer and any("1" in counts_in(line) for line in footer), result.out


def test_tf1_07_all_lists_partial_and_older_runs(many: Path) -> None:
    result = trace(["runs", "--store", str(many), "--all"])
    assert result.code == 0, result.text
    line = _line_of(result.out, resolved_name(many, "half-done"))
    assert "partial" in line.split(), line
    doc = runs_json(many, "--all")
    assert len(doc["runs"]) == 54
    half = next(r for r in doc["runs"] if r["run_id"] == "half-done")
    assert (half["number"], half["status"]) == (None, "partial")
    assert [r["run_id"] for r in doc["runs"] if r["number"] is not None] == [f"run-{i:02d}" for i in range(52, -1, -1)]


def test_tf1_07_the_listing_shows_the_newest_50_and_says_how_many_more(many: Path) -> None:
    doc = runs_json(many)
    assert [r["run_id"] for r in doc["runs"]] == [f"run-{i:02d}" for i in range(52, 2, -1)]
    assert [r["number"] for r in doc["runs"]] == list(range(1, 51))
    result = trace(["runs", "--store", str(many)])
    more = [line for line in result.out.splitlines() if "3" in counts_in(line) and "--all" in line]
    assert more, result.out
    # a number past the listing still names its run
    assert resolved(many, "#51") == "run-02"
    assert resolved(many, "#53") == "run-00"


def test_tf1_07_the_listing_reads_the_rows_of_the_runs_it_lists_and_no_others(many: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    touched: set[str] = set()
    for method in ("read", "tally", "count"):
        if not hasattr(Store, method):
            continue
        real = getattr(Store, method)

        def spy(self: Store, run: str, *args: object, _real=real, **kwargs: object) -> object:  # type: ignore[no-untyped-def]
            touched.add(run)
            return _real(self, run, *args, **kwargs)

        monkeypatch.setattr(Store, method, spy)
    assert trace(["runs", "--store", str(many), "--event", "fail"]).code == 0
    assert touched == {f"run-{i:02d}" for i in range(3, 53)}


@pytest.mark.parametrize("zone", ["Asia/Tokyo", "America/Los_Angeles"])
def test_tf1_07_the_start_is_shown_in_utc(tmp_path: Path, zone: str) -> None:
    store = tau2_copy(tmp_path)
    env = dict(os.environ)
    env["TZ"] = zone
    result = run_sub("trace", ["runs", "--store", str(store)], env=env)
    assert result.code == 0, result.text
    assert "2026-09-15 21:11" in _line_of(result.out, T_NAMES[T_B])
    assert "2026-09-17 14:02" in _line_of(result.out, T_NAMES[T_PILOT])


def test_tf1_07_failed_counts_every_event_given(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(FIXTURES / "humaneval", tmp_path / "he")
    doc = runs_json(tmp_path / "he", "--event", "failed_assertion", "--event", "crashed")
    # failed_assertion and crashed: 1,330 + 8 on the first run, 1,376 + 11 on the second
    assert {r["run_id"]: r["failed"] for r in doc["runs"]} == {HE_A: 1338, HE_B: 1387}


def test_tf1_07_rows_are_every_row_prove_holds(tmp_path: Path) -> None:
    import shutil

    from conftest import CS

    shutil.copytree(CS, tmp_path / "cs")
    store = Store(tmp_path / "cs")
    doc = runs_json(tmp_path / "cs")
    # the replay holds rows with no outcome, which rows counts and failed does not
    assert {r["run_id"]: r["rows"] for r in doc["runs"]} == {run: store.tally(run).rows for run in store.runs()}
    assert any(store.tally(run).no_outcome for run in store.runs())


def test_tf1_07_a_run_with_traces_on_one_row_carries_traces(tmp_path: Path) -> None:
    from conftest import Row, build_store, roots

    from poisson_prove.store import config_hash

    # the trace on the input Prove reads last (rows come back sorted by config hash)
    cases = sorted((str(i) for i in range(9)), key=lambda c: config_hash({"case": c}))
    rows = [Row({"case": c}, "fail" if i % 2 else "ok", roots(["llm", "llm"]) if c == cases[-1] else None) for i, c in enumerate(cases)]
    build_store(tmp_path / "store", "mostly-bare", rows)
    assert Store(tmp_path / "store").read("mostly-bare", meta=False, trace="envelope")["trace"].notna().tolist() == [False] * 8 + [True]
    assert [r["traced"] for r in runs_json(tmp_path / "store")["runs"]] == [True]


def test_tf1_07_all_on_a_large_store_says_it_read_every_run(many: Path) -> None:
    listed = trace(["runs", "--store", str(many), "--event", "fail"])
    assert listed.code == 0 and listed.err == "", listed.text
    every = trace(["runs", "--store", str(many), "--event", "fail", "--all"])
    assert every.code == 0, every.text
    assert len(every.lines()) == 1 and every.lines()[0].startswith("note: "), every.err


def test_tf1_07_ctrl_c_stops_the_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tau2_copy(tmp_path)

    def interrupted(self: Store, *args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(Store, "read", interrupted)
    monkeypatch.setattr(Store, "tally", interrupted)
    text = trace(["runs", "--store", str(store), "--event", "unsolved"])
    assert text.code == 130 and verdict_parts(first_line(text))[0] == "stopped", text.text
    as_json = trace(["runs", "--store", str(store), "--event", "unsolved", "--json"])
    assert as_json.code == 130 and as_json.json()["verdict"] == "stopped", as_json.text


def test_tf1_07_the_verdict_counts_imported_runs_as_named_by_you(tmp_path: Path) -> None:
    with chdir(tmp_path):
        assert import_he("store", "he-a").code == 0
        assert import_he("store", "he-b", "b").code == 0
        result = trace(["runs", "--store", "store"])
    assert result.code == 0, result.text
    assert counts_in(verdict_parts(first_line(result))[1]) == ["2", "2", "0"]
