"""TF2-5: ``[names] from`` names the runs Prove stored (spec sections 3.2 and 5.2; handed on by TF1
Session A's yes/no 9; yes/no 7).

``target`` (the default) gives ``tau2-airline 2026-09-15 a``; ``date`` gives ``2026-09-15 a``;
``target-date`` gives the target with the model after it, ``tau2-airline gpt-4.1-mini 2026-09-15
a``. The model is the target id after its first ``/``, up to an ``@``, without a date stamp
``-YYYY-MM-DD`` at its end; a target id with no model is named as ``target`` names it. The letter
runs in start order among the runs that share the rest of the name. A name of yours and an
import's name stay what they are, under every form; ``latest:TARGET`` still takes the target.
Names are computed each time: a form changes no file under the store, and every verb, the
listing and the words a verb takes all follow the form the config sets."""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import deepeval_import
from tf1_support import T_A, T_B, T_PILOT, tau2_copy, write_names
from tf2_support import R, doc, here, import_here, scratch_home, stamp, store_of, tree, work, write_config  # noqa: F401


def _config(form: str | None, event: str = "fail") -> str:
    names = "" if form is None else f'\n[names]\nfrom = "{form}"\n'
    return f'version = 1\n\n[store]\npath = "store"\n\n[events]\nfailed = ["{event}"]\n{names}'


def _names(folder: Path) -> dict[str, str]:
    result = here(folder, ["runs", "--all", "--json"])
    assert result.code == 0, result.text
    return {row["run_id"]: row["name"] for row in doc(result)["runs"]}


def _reaches(folder: Path, word: str) -> str | None:
    result = here(folder, ["where", word, "--json"])
    if result.code != 0:
        assert result.code == 1 and result.out == "", result.text
        return None
    return str(doc(result)["run"]["run_id"])


@pytest.fixture
def mixed(tmp_path: Path) -> Path:
    """Two targets on 3 October and one on the 4th, in start order x1, y1, x2, x3."""
    place = work(tmp_path)
    store_of(place / "store", [
        R("x1", stamp(3, 9), target_id="agent-x/model-1@v0"),
        R("y1", stamp(3, 10), target_id="agent-y/model-1@v0"),
        R("x2", stamp(3, 11), target_id="agent-x/model-1@v0"),
        R("x3", stamp(4, 9), target_id="agent-x/model-1@v0"),
    ])
    return place


def test_tf2_05_date_names_a_run_by_its_day_and_a_letter_across_targets(mixed: Path) -> None:
    write_config(mixed, _config("date"))
    assert _names(mixed) == {"x1": "2026-10-03 a", "y1": "2026-10-03 b", "x2": "2026-10-03 c", "x3": "2026-10-04 a"}
    assert _reaches(mixed, "2026-10-03 b") == "y1"
    assert _reaches(mixed, "agent-x 2026-10-03 a") is None
    assert _reaches(mixed, "latest:agent-y") == "y1"


@pytest.mark.parametrize("form", [None, "target"], ids=["no names table", "target"])
def test_tf2_05_target_is_the_default(mixed: Path, form: str | None) -> None:
    write_config(mixed, _config(form))
    assert _names(mixed) == {
        "x1": "agent-x 2026-10-03 a", "y1": "agent-y 2026-10-03 a", "x2": "agent-x 2026-10-03 b", "x3": "agent-x 2026-10-04 a",
    }


def test_tf2_05_target_date_puts_the_model_after_the_target(tmp_path: Path) -> None:
    place = work(tmp_path)
    store_of(place / "store", [
        R("m1", stamp(3, 9), target_id="tau2-airline/gpt-4.1-mini-2025-04-14@v0"),
        R("m2", stamp(3, 10), target_id="tau2-airline/gpt-4o-2024-08-06@v0"),
        R("m3", stamp(3, 11), target_id="tau2-airline/gpt-4.1-mini-2025-04-14@v1"),
        R("solo", stamp(3, 12), target_id="solo"),
        R("bare", stamp(3, 13), target_id="agent/model-2"),
        R("empty", stamp(3, 14), target_id="agent/@v0"),
    ])
    write_config(place, _config("target-date"))
    assert _names(place) == {
        "m1": "tau2-airline gpt-4.1-mini 2026-10-03 a",
        "m2": "tau2-airline gpt-4o 2026-10-03 a",
        "m3": "tau2-airline gpt-4.1-mini 2026-10-03 b",
        "solo": "solo 2026-10-03 a",
        "bare": "agent model-2 2026-10-03 a",
        "empty": "agent 2026-10-03 a",
    }
    assert _reaches(place, "tau2-airline gpt-4o 2026-10-03 a") == "m2"
    assert _reaches(place, "latest:tau2-airline") == "m3"


def test_tf2_05_the_fixtures_runs_under_each_form(tmp_path: Path) -> None:
    place = work(tmp_path)
    tau2_copy(place, "store")
    expected = {
        "date": {T_A: "2026-09-15 a", T_B: "2026-09-15 b", T_PILOT: "2026-09-17 a"},
        "target-date": {
            T_A: "tau2-airline gpt-4.1-mini 2026-09-15 a", T_B: "tau2-airline gpt-4.1-mini 2026-09-15 b",
            T_PILOT: "tau2-airline gpt-4.1-mini 2026-09-17 a",
        },
    }
    for form, names in expected.items():
        write_config(place, _config(form, "unsolved"))
        assert _names(place) == names, form


def test_tf2_05_yours_and_imported_names_stay_under_every_form(tmp_path: Path) -> None:
    place = work(tmp_path)
    store = tau2_copy(place, "store")
    write_names(store, {"old re-run": T_B})
    assert import_here(place, deepeval_import("store", "he-a")).code == 0
    for form in ("target", "date", "target-date"):
        write_config(place, _config(form, "unsolved"))
        names = _names(place)
        assert names[T_B] == "old re-run" and names["he-a"] == "he-a", (form, names)
        assert _reaches(place, "old re-run") == T_B


@pytest.mark.parametrize("form", ["date", "target-date"])
def test_tf2_05_an_import_takes_no_letter_of_its_day(tmp_path: Path, form: str) -> None:
    """An import that started on the day of two Prove runs, before them: they keep the letters a
    and b, and the import answers to its own name alone."""
    place = work(tmp_path)
    tau2_copy(place, "store")
    assert import_here(place, deepeval_import("store", "he-a", "a", "--started", "2026-09-15T20:00:00Z")).code == 0
    write_config(place, _config(form, "unsolved"))
    names = _names(place)
    first = "2026-09-15 a" if form == "date" else "tau2-airline gpt-4.1-mini 2026-09-15 a"
    assert names[T_A] == first and names["he-a"] == "he-a", names
    assert _reaches(place, first) == T_A
    # nor does the import answer to a name of the form, as its target would make it
    assert _reaches(place, "import deepeval 2026-09-15 a") is None and _reaches(place, "import 2026-09-15 a") is None


def test_tf2_05_an_import_named_as_a_run_of_the_form_is_named_is_refused(mixed: Path) -> None:
    """An import's name is the word for its run: under the date form, "2026-10-03 b" is y1's."""
    write_config(mixed, _config("date"))
    result = import_here(mixed, deepeval_import("store", "2026-10-03 b"))
    assert result.code == 1 and result.out == "", result.text
    assert "2026-10-03 b" not in [p.name for p in (mixed / "store").iterdir()]
    assert _reaches(mixed, "2026-10-03 b") == "y1"


def test_tf2_05_a_target_no_name_could_show_is_still_named_by_its_day(tmp_path: Path) -> None:
    """A target with a space at its end gives no name of the target form (a name no verb could
    take back); the date form does not show the target, so it names that run."""
    place = work(tmp_path)
    store_of(place / "store", [R("odd", stamp(3, 9), target_id="agent ")])
    write_config(place, _config("date"))
    assert _names(place) == {"odd": "2026-10-03 a"}
    write_config(place, _config("target-date"))
    assert _names(place) == {"odd": "odd"}


def test_tf2_05_a_form_changes_no_file_under_the_store(mixed: Path) -> None:
    before = tree(mixed / "store")
    for form in ("date", "target-date", "target"):
        write_config(mixed, _config(form))
        assert here(mixed, ["runs", "--json"]).code == 0
        assert here(mixed, ["where", "latest", "--json"]).code == 0
    assert tree(mixed / "store") == before


def test_tf2_05_name_lists_the_name_from_the_manifest_in_the_form_set(mixed: Path) -> None:
    write_config(mixed, _config("date"))
    assert here(mixed, ["name", "x2", "second"]).code == 0
    listed = here(mixed, ["name", "--list"])
    assert listed.code == 0, listed.text
    row = [line for line in listed.out.splitlines() if "second" in line]
    assert len(row) == 1 and "2026-10-03 c" in row[0] and "agent-x" not in row[0], listed.out
