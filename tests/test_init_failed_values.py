"""init refuses a failure value no file carries, and a setup with no failure to set does not send
doctor and init to each other (Taylor's ruling on the partner wheel's yes/no 7, 2026-10-19).

- A ``--failed`` value that matches no cell of the outcome column in any table init imports is
  refused, naming the value and the column, with the column's values listed; nothing is written.
  A value one file carries and the other does not is a version that fixed it, and is taken.
- A store whose runs carry only words for success has no failure to set: init says so, and
  doctor's next step is not init. For imported runs it points to importing them again into a
  new store and setting up with it, which makes the setup ready; for Prove's runs it names none.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tf2_support import (  # noqa: F401
    CONFIG, check, doctor_doc, here, import_here, init_yes, outcome_runs, refused, scratch_home, work, write_config,
)
from tf3_support import TABLE_A, TABLE_B, outcome_rows, write_table

COLUMNS = ["--case-column", "case", "--outcome-column", "outcome"]


def _tables(folder: Path) -> None:
    (folder / "results").mkdir(parents=True, exist_ok=True)
    shutil.copy(TABLE_A, folder / "results" / "old.csv")
    shutil.copy(TABLE_B, folder / "results" / "new.csv")


def test_a_value_no_file_carries_is_refused_naming_it_and_the_column(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _tables(folder)
    line = refused(init_yes(folder, *COLUMNS, "--failed", "failed"))
    assert '"failed"' in line and "outcome" in line, line
    # the column's values, so the refusal says what to give instead
    assert all(f'"{v}"' in line for v in ("passed", "failed_assertion", "crashed")), line
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()


def test_one_value_no_file_carries_is_refused_beside_one_that_matches(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _tables(folder)
    line = refused(init_yes(folder, *COLUMNS, "--failed", "failed_assertion", "--failed", "timeout"))
    assert '"timeout"' in line and '"failed_assertion" matches' not in line, line
    assert not (folder / CONFIG).exists() and not (folder / "trace-store").exists()


def test_a_value_only_the_old_version_carries_is_taken(tmp_path: Path) -> None:
    """A new version that no longer crashes carries no crashed cell; the value is not a typo."""
    folder = work(tmp_path)
    write_table(folder / "old.csv", outcome_rows([("a", "passed"), ("b", "crashed"), ("c", "failed")]))
    write_table(folder / "new.csv", outcome_rows([("a", "passed"), ("b", "passed"), ("c", "failed")]))
    result = init_yes(folder, *COLUMNS, "--failed", "failed", "--failed", "crashed")
    assert result.code == 0 and result.out.startswith("ok  wrote trace.toml and imported 2 runs"), result.text
    assert "failures missed" in result.out.splitlines()[0], result.out


def _imported_with_no_failure(folder: Path) -> None:
    """Two runs imported with a failure value that matches nothing, so every row is met."""
    for name, table in (("old", TABLE_A), ("new", TABLE_B)):
        argv = ["table", str(table), "--store", "trace-store", "--run", name, *COLUMNS, "--failed", "failed"]
        assert import_here(folder, argv).code == 0


def test_runs_that_carry_only_met_are_said_so_by_init(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _imported_with_no_failure(folder)
    result = init_yes(folder)
    assert result.code == 0, result.text
    first = result.out.splitlines()[0]
    assert "met" in first and "success" in first and "no outcome" not in first, first


def test_doctor_does_not_send_runs_that_carry_only_met_back_to_init(tmp_path: Path) -> None:
    folder = work(tmp_path)
    _imported_with_no_failure(folder)
    assert init_yes(folder).code == 0
    code, data = doctor_doc(folder)
    item = check(data, "config")
    assert code == 4 and item["ok"] is False, item
    assert item["next"] is not None and "init" not in item["next"].split()[:2], item
    assert "met" in item["line"] and "success" in item["line"], item
    # the advice, followed: the results imported again into a new store, then set up with it
    for name, table in (("old", TABLE_A), ("new", TABLE_B)):
        argv = ["table", str(table), "--store", "fixed", "--run", name, *COLUMNS,
                "--failed", "failed_assertion", "--failed", "crashed"]
        assert import_here(folder, argv).code == 0
    assert init_yes(folder, "--force", "--store", "fixed").code == 0
    code, data = doctor_doc(folder)
    assert code == 0 and check(data, "config")["ok"] is True, data


def test_prove_runs_that_carry_only_words_for_success_name_no_command(tmp_path: Path) -> None:
    folder = work(tmp_path)
    outcome_runs(folder / "runs", [["solved", "solved"], ["solved", "resolved"]])
    write_config(folder, 'version = 1\n\n[store]\npath = "runs"\n')
    item = check(doctor_doc(folder)[1], "config")
    assert item["ok"] is False and item["next"] is None, item
    assert "success" in item["line"], item
    first = here(folder, ["init", "--yes"]).out.splitlines()[0]
    assert "resolved, solved" in first and "no outcome" not in first, first
