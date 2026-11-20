"""Choices setup and the config file make where the frozen tests leave room: the
same setup as one command replays whatever the values hold; Ctrl-C while the imported runs are
written, and stdin that ends before an answer, leave nothing behind; a store path is read
through a link to the config's folder as the system reads it; the Ragas check reads a row's
keys and not the text of its values, whatever byte the first 4 KB end on; and the refusals
these choices add write nothing."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from poisson_prove.store import Store

from look_support import VERDICT_LINE
from names_support import tau2_copy
from setup_support import (  # noqa: F401
    CONFIG, R, config_of, copy_tree, deepeval_file, doc, here, init_yes, outcome_runs, refused, scratch_home, stamp,
    store_of, tree, two_stores, work, write_config,
)
from poisson_trace.ingest import ragas

DEEPEVAL_ANSWERS = ["--metric", "Tests Passed", "--cut", "recorded", "--case", "name"]


def test_the_command_shown_replays_a_value_that_opens_with_a_dash(tmp_path: Path) -> None:
    """An outcome a command line would read as an option is given joined to its flag."""
    source = work(tmp_path, "source")
    outcome_runs(source / "store", [("-x", "ok")])
    pristine = copy_tree(source, tmp_path / "pristine")
    result = init_yes(source, "--json")
    assert result.code == 0, result.text
    command = doc(result)["equivalent_command"]
    replay = here(pristine, command[1:])
    assert replay.code == 0, (command, replay.text)
    assert (pristine / CONFIG).read_bytes() == (source / CONFIG).read_bytes()


def test_ctrl_c_while_the_imports_are_written_leaves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = work(tmp_path)
    deepeval_file(folder / "results" / "test_run_20261002_101500.json")
    deepeval_file(folder / "results" / "test_run_20261002_111500.json", cases=20)
    before = tree(folder)
    appended: list[str] = []
    original = Store.append

    def second_stops(self: Store, run_id: str, records: object) -> int:
        appended.append(run_id)
        if len(appended) == 2:
            raise KeyboardInterrupt
        return original(self, run_id, records)  # type: ignore[arg-type]

    monkeypatch.setattr(Store, "append", second_stops)
    result = init_yes(folder, *DEEPEVAL_ANSWERS)
    assert result.code == 130 and len(appended) == 2, result.text
    first = result.out.splitlines()[0]
    assert first.startswith("stopped  ") and VERDICT_LINE.match(first), result.out
    assert tree(folder) == before and not (folder / "trace-store").exists()


class _EndedStdin(io.StringIO):
    """A terminal whose input ends (Ctrl-D) before anything is typed."""

    def isatty(self) -> bool:
        return True


def test_stdin_that_ends_before_an_answer_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    before = tree(folder)
    monkeypatch.setattr("sys.stdin", _EndedStdin(""))
    refused(here(folder, ["init"]))
    assert tree(folder) == before and not (folder / CONFIG).exists()


def test_a_store_path_is_read_through_a_link_to_the_configs_folder(tmp_path: Path) -> None:
    """``conf`` is a link to ``real/conf``; the config's ``../runs`` is ``real/runs`` there, as
    the system reads it, and not the ``runs`` beside the link."""
    top = work(tmp_path)
    store_of(top / "real" / "runs", [R("far", stamp(7, 9))])
    store_of(top / "runs", [R("near", stamp(7, 10))])
    (top / "real" / "conf").mkdir()
    write_config(top / "real" / "conf", config_of("../runs", ("fail",)), "team.toml")
    os.symlink(top / "real" / "conf", top / "conf")
    result = here(top, ["where", "latest", "--config", "conf/team.toml", "--json"])
    assert result.code == 0 and doc(result)["run"]["run_id"] == "far", result.text


def test_the_ragas_check_reads_keys_not_the_text_of_values(tmp_path: Path) -> None:
    hidden = tmp_path / "hidden.jsonl"
    hidden.write_text(json.dumps({"case": "a", "notes": {"text": '}, "faithfulness": 1, {'}, "score": 0.5}) + "\n", encoding="utf-8")
    assert ragas.looks_like(hidden) is None
    after = tmp_path / "after.jsonl"
    after.write_text(json.dumps({"case": "a", "notes": {"text": "] } { [ \\\" ,"}, "faithfulness": 0.5}) + "\n", encoding="utf-8")
    said = ragas.looks_like(after)
    assert isinstance(said, str) and "faithfulness" in said, said


def test_the_ragas_check_reads_a_table_whose_4_kb_end_inside_a_character(tmp_path: Path) -> None:
    """A two-byte character falls across the 4,096th byte of a long header; the metric before
    it is still read."""
    path = tmp_path / "wide.csv"
    path.write_text("case,faithfulness,x" + "é" * 3000 + "\na,0.5,x\n", encoding="utf-8")
    assert path.read_bytes()[4095:4097] == "é".encode()
    said = ragas.looks_like(path)
    assert isinstance(said, str) and "faithfulness" in said, said


REFUSED = {
    "both sides of a cut": (["--store", "proofload-runs", "--below", "--above"], 2),
    "a failure and no store": (["--event", "unsolved"], 1),
    "a store the config names already": (["--add-store", "proofload-runs"], 1),
    "a setting beside a config to complete": (["--names", "from=date"], 1),
}


@pytest.mark.parametrize("case", REFUSED)
def test_these_refusals_write_nothing(tmp_path: Path, case: str) -> None:
    folder = work(tmp_path)
    if case != "a failure and no store":
        tau2_copy(folder, "proofload-runs")
    if case == "a store the config names already":
        write_config(folder, config_of("proofload-runs"))
    if case == "a setting beside a config to complete":
        write_config(folder, 'version = 1\n\n[store]\npath = "proofload-runs"\n')
    before = tree(folder)
    argv, code = REFUSED[case]
    words = argv if "--add-store" in argv else ["--yes", *argv]
    result = here(folder, ["init", *words])
    assert result.code == code and result.out == "", result.text
    assert tree(folder) == before


@pytest.mark.parametrize("label,text,line", [
    ("a store written as a value", 'version = 1\nstore = "proofload-runs"\n\n[events]\nfailed = ["unsolved"]\n', 2),
    ("an upload port that is not a number", config_of("proofload-runs", extra='\n[upload]\nurl = "http://localhost:port/up"\n'), 10),
], ids=lambda v: v if isinstance(v, str) and " " in v else "")
def test_two_more_faults_of_a_config_are_refused_naming_the_line(tmp_path: Path, label: str, text: str, line: int) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, text)
    error = refused(here(folder, ["runs"]))
    assert f"trace.toml line {line}:" in error, (label, error)


def test_doctor_is_not_ready_on_a_config_that_names_stores_by_name_alone(tmp_path: Path) -> None:
    """Every verb reads the unnamed store when no --store is given; a config with named stores
    and no [store] path leaves them none."""
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, 'version = 1\n\n[store.tau2]\npath = "proofload-runs"\n\n[events]\nfailed = ["unsolved"]\n')
    result = here(folder, ["doctor", "--json"])
    assert result.code == 4, result.text
    failing = [c["name"] for c in doc(result)["checks"] if not c["ok"]]
    assert failing == ["config"], doc(result)["checks"]
