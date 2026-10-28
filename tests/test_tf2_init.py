"""TF2-10 to TF2-16: what ``init`` asks, what it writes and what it prints, without a terminal
(spec sections 4.2 and 4.4 to 4.7, rulings R2 and R4; yes/nos 16 to 24).

``--yes`` asks nothing and takes every answer from a flag or its default: the first store listed,
every outcome of the newest 20 runs that is not a word for success, and with no store, the
import of the result files found when the reader's answers are given as the import's own flags.
``trace.toml`` is written once, at the end, as a version 1 config that the verbs read, holding no
run id; one that is there already is refused without ``--force`` and left as it was, but for a
config with a store and no failures, which ``init`` completes; ``--add-store`` adds one named
store to a config and changes nothing else in it. Stdin not a terminal and no ``--yes`` is
refused before the search. ``--json`` is one document, its keys in the spec's order. The
summary ends with ``next: poisson-trace runs``, which runs as written, and shows the same setup
as one command, which, run in a copy of the folder as it was, writes the same file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import INSTALL_PROVE, RUN_ID, VERDICT_LINE
from tf1_support import shell_words, tau2_copy, write_names
from tf2_support import (  # noqa: F401
    CONFIG, SUCCESS_WORDS, R, config, refused, config_of, copy_tree, deepeval_file, doc, here, init_yes, numbered,
    outcome_runs, ragas_file, run, scratch_home, stamp, store_of, summary_command, tree, two_stores, work,
    write_config,
)

INIT_KEYS = ["schema", "verdict", "sentence", "config_path", "stores", "events", "named", "prove", "equivalent_command", "next"]


def _yes(folder: Path, *argv: str):  # type: ignore[no-untyped-def]
    result = init_yes(folder, *argv)
    assert result.code == 0, result.text
    return result


def _next(result) -> str:  # type: ignore[no-untyped-def]
    lines = result.lines("out")
    assert lines and lines[-1].startswith("next: "), result.out
    return lines[-1][len("next: "):]


# ---------- TF2-10 and TF2-11: the answers --yes takes ----------


def test_tf2_10_one_store_is_taken_with_its_failures(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    result = _yes(folder)
    written = config(folder)
    assert written["version"] == 1
    assert written["store"]["path"] == "proofload-runs"
    assert written["events"]["failed"] == ["unsolved"]
    assert VERDICT_LINE.match(result.lines("out")[0]) and result.lines("out")[0].startswith("ok  "), result.out


def test_tf2_11_the_default_failures_are_every_outcome_but_the_words_for_success(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [(*SUCCESS_WORDS, "boom", "unsolved")])
    _yes(folder)
    assert sorted(config(folder)["events"]["failed"]) == ["boom", "unsolved"]


def test_tf2_11_events_given_answer_the_question(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("boom", "unsolved", "ok")])
    _yes(folder, "--event", "ok", "--event", "boom")
    assert sorted(config(folder)["events"]["failed"]) == ["boom", "ok"]


def test_tf2_11_an_event_no_run_carries_is_refused(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [("boom", "ok")])
    result = init_yes(folder, "--event", "bust")
    assert "bust" in refused(result)
    assert not (folder / CONFIG).exists()


def test_tf2_11_runs_with_no_outcome_give_no_failures(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "store", [(None, None), (None,)])
    result = _yes(folder, "--json")
    assert "events" not in config(folder) and config(folder)["store"]["path"] == "store"
    assert doc(result)["events"] == []


# ---------- TF2-12: names ----------


@pytest.mark.parametrize("form,shown,not_shown", [
    ("target", "tau2-airline 2026-09-17 a", None),
    ("date", "2026-09-17 a", "tau2-airline 2026-09-17 a"),
    ("target-date", "tau2-airline gpt-4.1-mini 2026-09-17 a", None),
])
def test_tf2_12_the_summary_shows_the_names_and_writes_the_form(tmp_path: Path, form: str, shown: str, not_shown: str | None) -> None:
    folder = work(tmp_path)
    store = tau2_copy(folder, "proofload-runs")
    result = _yes(folder, "--names", f"from={form}")
    assert shown in result.out, result.out
    if not_shown is not None:
        assert not_shown not in result.out, result.out
    assert config(folder)["names"]["from"] == form
    assert not (store / "trace-names.toml").exists()


def test_tf2_12_named_counts_the_names_of_yours(tmp_path: Path) -> None:
    folder = work(tmp_path)
    store = tau2_copy(folder, "proofload-runs")
    data = doc(_yes(folder, "--json"))
    assert data["named"] == 0
    (folder / CONFIG).unlink()
    write_names(store, {"old": "20260915T211148Z-965d", "new": "20260917T140219Z-2b2d"})
    assert doc(_yes(folder, "--json"))["named"] == 2


@pytest.mark.parametrize("argv,right", [
    (["--names", "from=model"], ["--names", "from=date"]),
    (["--names", "target"], ["--names", "from=target"]),
    (["--fail-on", "regressed"], ["--fail-on", "failed-more"]),
])
def test_tf2_12_a_value_outside_its_choices_is_a_wrong_command_line(tmp_path: Path, argv: list[str], right: list[str]) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    result = init_yes(folder, *argv)
    assert result.code == 2 and result.out == "", result.text
    assert not (folder / CONFIG).exists()
    _yes(folder, *right)


def test_tf2_12_the_ceilings_and_the_gate_are_written_only_when_given(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    _yes(folder)
    assert "check" not in config(folder)
    _yes(folder, "--force", "--max-mde", "0.2", "--max-mde-hr", "1.5", "--fail-on", "failed-more,too-small")
    assert config(folder)["check"] == {"max_mde": 0.2, "max_mde_hr": 1.5, "fail_on": ["failed-more", "too-small"]}
    for flag, value in (("--max-mde", "1.5"), ("--max-mde", "nan"), ("--max-mde-hr", "0.5"), ("--max-mde-hr", "inf")):
        out_of_range = init_yes(folder, "--force", flag, value)
        assert out_of_range.code == 1 and config(folder)["check"]["max_mde"] == 0.2, (flag, value, out_of_range.text)


def test_tf2_13_a_failure_given_twice_is_written_once(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    _yes(folder, "--event", "unsolved", "--event", "unsolved")
    assert config(folder)["events"]["failed"] == ["unsolved"]
    assert here(folder, ["runs"]).code == 0


# ---------- TF2-10: no store ----------


def test_tf2_10_nothing_found_writes_a_config_with_no_store(tmp_path: Path) -> None:
    folder = work(tmp_path)
    result = _yes(folder)
    written = config(folder)
    assert written["version"] == 1 and "store" not in written and "events" not in written
    pointers = _next(result)
    assert "poisson-trace import --help" in pointers or "poisson-trace-import --help" in pointers, pointers
    assert "https://github.com/poisson-labs/prove" in pointers, pointers


def _two_results(folder: Path) -> list[Path]:
    return [
        deepeval_file(folder / "results" / "test_run_20261002_101500.json"),
        deepeval_file(folder / "results" / "test_run_20261002_111500.json", cases=20),
    ]


DEEPEVAL_ANSWERS = ["--metric", "Tests Passed", "--cut", "recorded", "--case", "name"]


def test_tf2_10_result_files_with_the_readers_answers_are_imported(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _two_results(folder)
    result = _yes(folder, *DEEPEVAL_ANSWERS)
    store = Store(folder / "trace-store")
    assert sorted(store.runs()) == ["test_run_20261002_101500", "test_run_20261002_111500"]
    assert store.tally("test_run_20261002_111500").rows == 20
    written = config(folder)
    assert written["store"]["path"] == "trace-store" and written["events"]["failed"] == ["missed"]
    named: set[str] = set()
    for line in result.out.splitlines():
        at = max(line.find("poisson-trace-import deepeval"), line.find("poisson-trace import deepeval"))
        if at >= 0:
            named.update(shell_words(line[at:]))
    assert {f"results/test_run_20261002_{t}.json" for t in ("101500", "111500")} <= named, result.out


def test_tf2_10_the_ragas_reader_is_asked_its_own_questions(tmp_path: Path) -> None:
    folder = work(tmp_path)
    ragas_file(folder / "scores" / "base.jsonl")
    _yes(folder, "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case")
    assert Store(folder / "trace-store").runs() == ["base"]


def test_tf2_10_result_files_without_the_readers_answers_are_refused(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _two_results(folder)
    result = init_yes(folder)
    refused(result)
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()
    declined = _yes(folder, "--no-import")
    assert "store" not in config(folder) and not (folder / "trace-store").exists(), declined.text


def test_tf2_10_a_refusal_on_any_file_writes_no_run_of_the_others(tmp_path: Path) -> None:
    folder = work(tmp_path)
    good, bad = _two_results(folder)
    held = json.loads(bad.read_text(encoding="utf-8"))
    for case in held["testCases"]:
        for metric in case["metricsData"]:
            metric["name"] = "Another Metric"
    bad.write_text(json.dumps(held), encoding="utf-8")
    refused(init_yes(folder, *DEEPEVAL_ANSWERS))
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()


def test_tf2_10_a_readers_refusal_writes_nothing(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _two_results(folder)
    result = init_yes(folder, "--metric", "Tests Pased", "--cut", "recorded", "--case", "name")
    refused(result)
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()


# ---------- TF2-13: writing ----------


def test_tf2_13_a_config_there_already_is_refused_and_left_as_it_was(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    mine = write_config(folder, config_of("proofload-runs", ("solved",), "\n# mine\n"))
    before = mine.read_bytes()
    result = init_yes(folder)
    refused(result)
    assert mine.read_bytes() == before
    _yes(folder, "--force")
    assert config(folder)["events"]["failed"] == ["unsolved"]


def test_tf2_13_a_config_with_a_store_and_no_failures_is_completed(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    mine = write_config(folder, '# my notes\nversion = 1\n\n[store]\npath = "proofload-runs"\n\n[check]\nmax_mde = 0.25\n')
    _yes(folder)
    written = config(folder)
    assert written["store"]["path"] == "proofload-runs" and written["check"]["max_mde"] == 0.25
    assert written["events"]["failed"] == ["unsolved"]
    assert "# my notes" in mine.read_text(encoding="utf-8")


def test_tf2_13_add_store_adds_one_named_store_and_keeps_the_rest(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _, second = two_stores(folder)
    mine = write_config(folder, config_of("proofload-runs", extra="\n# kept as written\n[check]\nmax_mde = 0.2\n"))
    before = mine.read_text(encoding="utf-8")
    result = run(["init", "--add-store", "demo/store"], cwd=folder)
    assert result.code == 0, result.text
    after = mine.read_text(encoding="utf-8").splitlines()
    kept = iter(after)
    assert all(line in kept for line in before.splitlines()), after
    written = config(folder)
    assert written["store"]["store"]["path"] == "demo/store" and written["store"]["path"] == "proofload-runs"
    assert here(folder, ["where", "latest", "--store", "store", "--event", "fail", "--json"]).code == 0


def test_tf2_13_add_store_writes_the_path_from_the_configs_folder(tmp_path: Path) -> None:
    """With the config in another folder, the store added is written as that folder reads it, so
    every verb reaches it through the config."""
    folder = work(tmp_path)
    two_stores(folder)
    (folder / "conf").mkdir()
    write_config(folder / "conf", config_of("../proofload-runs"), "team.toml")
    added = run(["init", "--add-store", "demo/store", "--config", "conf/team.toml"], cwd=folder)
    assert added.code == 0, added.text
    found = here(folder, ["where", "latest", "--store", "store", "--config", "conf/team.toml", "--event", "fail", "--json"])
    assert found.code == 0 and doc(found)["run"]["run_id"] == "x-two", found.text


ADD_REFUSED = {
    # (the config there, or None; the path given)
    "no config": (None, "demo/store"),
    "no store there": (config_of("proofload-runs"), "nowhere"),
    "a name in use": (config_of("proofload-runs", extra='\n[store.proofload-runs]\npath = "proofload-runs"\n'), "x/proofload-runs"),
    "not a store name": (config_of("proofload-runs"), "odd name"),
}


@pytest.mark.parametrize("case", ADD_REFUSED)
def test_tf2_13_add_store_refusals_change_nothing(tmp_path: Path, case: str) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    store_of(folder / "x" / "proofload-runs", [R("dup", stamp(6, 9))])
    store_of(folder / "odd name", [R("odd", stamp(6, 9))])
    text, path = ADD_REFUSED[case]
    before = None if text is None else write_config(folder, text).read_bytes()
    result = run(["init", "--add-store", path], cwd=folder)
    refused(result)
    after = (folder / CONFIG).read_bytes() if (folder / CONFIG).exists() else None
    assert after == before


def test_tf2_13_the_stores_not_chosen_are_offered_as_commands_that_run(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = _yes(folder)
    offered = []
    for line in result.out.splitlines():
        at = line.find("poisson-trace init --add-store")
        if at >= 0:
            offered.append(shell_words(line[at:]))
    assert offered == [["poisson-trace", "init", "--add-store", "demo/store"]], result.out
    assert here(folder, offered[0][1:]).code == 0
    assert config(folder)["store"]["store"]["path"] == "demo/store"
    single = work(tmp_path, "single")
    tau2_copy(single, "proofload-runs")
    assert "--add-store" not in _yes(single).out


def test_tf2_13_a_second_store_given_is_named_by_its_folder(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    data = doc(_yes(folder, "--store", "proofload-runs", "--store", "demo/store", "--json"))
    written = config(folder)
    assert written["store"]["path"] == "proofload-runs" and written["store"]["store"]["path"] == "demo/store"
    assert [(s["name"], s["path"], s["runs"]) for s in data["stores"]] == [(None, "proofload-runs", 3), ("store", "demo/store", 2)]


def test_tf2_13_config_names_the_file_init_writes_and_the_verbs_read_it(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    (folder / "conf").mkdir()
    _yes(folder, "--config", "conf/team.toml")
    assert (folder / "conf" / "team.toml").exists() and not (folder / CONFIG).exists()
    result = here(folder, ["where", "previous", "--config", "conf/team.toml", "--json"])
    assert result.code == 0, result.text
    assert doc(result)["run"]["run_id"] == "20260915T211148Z-965d" and doc(result)["events"] == ["unsolved"]


def test_tf2_13_with_config_the_next_and_the_command_shown_name_that_file(tmp_path: Path) -> None:
    source = work(tmp_path, "source")
    tau2_copy(source, "proofload-runs")
    (source / "conf").mkdir()
    pristine = copy_tree(source, tmp_path / "pristine")
    result = _yes(source, "--config", "conf/team.toml")
    following = shell_words(_next(result))
    assert following[:2] == ["poisson-trace", "runs"], following
    assert here(source, following[1:]).code == 0
    command = summary_command(result.out)
    assert here(pristine, command[1:]).code == 0
    assert (pristine / "conf" / "team.toml").read_bytes() == (source / "conf" / "team.toml").read_bytes()
    assert not (pristine / CONFIG).exists()


def test_tf2_10_the_imports_store_is_beside_the_config(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _two_results(folder)
    (folder / "conf").mkdir()
    _yes(folder, "--config", "conf/team.toml", *DEEPEVAL_ANSWERS)
    assert sorted(Store(folder / "conf" / "trace-store").runs()) == ["test_run_20261002_101500", "test_run_20261002_111500"]
    assert not (folder / "trace-store").exists()
    result = here(folder, ["runs", "--config", "conf/team.toml", "--json"])
    assert result.code == 0 and len(doc(result)["runs"]) == 2, result.text


# ---------- TF2-14: without questions ----------


def test_tf2_14_stdin_not_a_terminal_is_refused_before_the_search(tmp_path: Path) -> None:
    folder = work(tmp_path)
    two_stores(folder)
    result = run(["init"], cwd=folder)
    refused(result)
    lines = result.lines()
    assert lines[0].startswith("error: ") and all(line.startswith("  next: ") for line in lines[1:]), result.err
    assert "proofload-runs" not in result.err and numbered(result.err) == {}
    assert not (folder / CONFIG).exists()


def test_tf2_14_json_is_one_document_with_the_keys_in_order(tmp_path: Path) -> None:
    import poisson_prove

    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    result = _yes(folder, "--json")
    data = doc(result)
    assert list(data) == INIT_KEYS
    assert data["schema"] == "poisson-trace.init/1" and data["verdict"] == "ok"
    assert (folder / data["config_path"]).resolve() == (folder / CONFIG).resolve()
    assert data["stores"] == [{"name": None, "path": "proofload-runs", "runs": 3}]
    assert data["events"] == ["unsolved"] and data["named"] == 0
    assert data["prove"] == {"installed": True, "version": poisson_prove.__version__}
    assert data["equivalent_command"][:2] == ["poisson-trace", "init"] and "--yes" in data["equivalent_command"]
    assert data["next"] == "poisson-trace runs"


# ---------- TF2-15 and TF2-16: the same setup as one command, and next ----------


def test_tf2_15_the_command_shown_writes_the_same_file(tmp_path: Path) -> None:
    source = work(tmp_path, "source")
    two_stores(source)
    pristine = copy_tree(source, tmp_path / "pristine")
    flags = ["--store", "demo/store", "--names", "from=date", "--max-mde", "0.2", "--max-mde-hr", "1.5", "--fail-on", "too-small"]
    text = _yes(source, *flags)
    command = summary_command(text.out)
    data = doc(_yes(copy_tree(pristine, tmp_path / "again-json"), *flags, "--json"))
    assert command == data["equivalent_command"], (command, data["equivalent_command"])
    # it names the store and each failure it wrote, so it gives the same setup when the store has
    # gained runs since
    pairs = [(command[i], command[i + 1]) for i in range(len(command) - 1)]
    assert ("--store", "demo/store") in pairs, command
    assert [v for k, v in pairs if k == "--event"] == config(source)["events"]["failed"], command
    replay = copy_tree(pristine, tmp_path / "replay")
    assert command[:2] == ["poisson-trace", "init"] and RUN_ID.search(" ".join(command)) is None
    assert here(replay, command[1:]).code == 0
    assert (replay / CONFIG).read_bytes() == (source / CONFIG).read_bytes()
    assert config(replay)["check"] == {"max_mde": 0.2, "max_mde_hr": 1.5, "fail_on": ["too-small"]}


def test_tf2_15_the_command_shown_after_an_import_writes_the_same_store(tmp_path: Path) -> None:
    source = work(tmp_path, "source")
    _two_results(source)
    pristine = copy_tree(source, tmp_path / "pristine")
    command = doc(_yes(source, *DEEPEVAL_ANSWERS, "--json"))["equivalent_command"]
    replay = copy_tree(pristine, tmp_path / "replay")
    assert here(replay, command[1:]).code == 0
    assert (replay / CONFIG).read_bytes() == (source / CONFIG).read_bytes()
    for run_id in Store(source / "trace-store").runs():
        assert Store(replay / "trace-store").tally(run_id) == Store(source / "trace-store").tally(run_id)


def test_tf2_16_next_runs_as_written(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    command = _next(_yes(folder))
    assert shell_words(command) == ["poisson-trace", "runs"], command
    followed = here(folder, shell_words(command)[1:])
    assert followed.code == 0 and followed.err == "", followed.text


def test_tf2_16_the_install_line_is_never_the_next_with_prove_present(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    assert INSTALL_PROVE not in _yes(folder).text
