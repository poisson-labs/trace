"""TF1-14: the import's name holes, and the names a run can be
imported under.

``--run`` is a folder's name: an empty name, ``.``, ``..``, a name holding a slash, a backslash
or a NUL, and one over 80 characters are refused in Trace's own sentence, one line, exit 1,
before Prove is asked anything and with nothing written, not even the store's folder. A name of
80 characters is taken. Since an imported run is named by its import name, the import refuses
too what ``name`` refuses: a reserved form, a name another run of the store already answers
to, and a name a command could not give back (a space at either end, a newline, a dash first). A name the store holds as a run keeps its own refusal."""

from __future__ import annotations

from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import deepeval_import, trace_import
from tf1_support import T_A, T_NAMES, refused, snapshot, tau2_copy, write_names

HOLES = {
    "empty": "",
    "a dot": ".",
    "two dots": "..",
    "a slash": "a/b",
    "a leading slash": "/abs",
    "up a folder": "../up",
    "a backslash": "a\\b",
    "a NUL": "a\0b",
    "81 characters": "r" * 81,
}


@pytest.fixture
def prove_untouched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every call the import makes to Prove's store, recorded and refused."""
    calls: list[str] = []
    for method in ("__init__", "runs", "manifest", "create_run", "append", "mark_complete", "read", "tally"):
        real = getattr(Store, method)

        def spy(self: Store, *args: object, _name=method, _real=real, **kwargs: object) -> object:  # type: ignore[no-untyped-def]
            calls.append(_name)
            return _real(self, *args, **kwargs)

        monkeypatch.setattr(Store, method, spy)
    return calls


@pytest.mark.parametrize("label", HOLES)
def test_tf1_14_a_run_name_that_is_not_a_folder_name_is_refused_before_prove(tmp_path: Path, label: str, prove_untouched: list[str]) -> None:
    store = tmp_path / "new-store"
    line = refused(trace_import(deepeval_import(store, HOLES[label])))
    assert prove_untouched == [], prove_untouched
    assert not store.exists()
    assert list(tmp_path.iterdir()) == []
    if label not in ("a NUL", "81 characters"):
        assert f'"{HOLES[label]}"' in line, line


def test_tf1_14_a_hole_in_a_store_that_exists_writes_nothing(tmp_path: Path, prove_untouched: list[str]) -> None:
    store = tau2_copy(tmp_path)
    before = snapshot(store)
    refused(trace_import(deepeval_import(store, "..")))
    assert snapshot(store) == before and prove_untouched == []


@pytest.mark.parametrize("text", ["r" * 80, "é" * 80, "spaces and: colons"], ids=["80 characters", "80 letters outside ASCII", "spaces and a colon"])
def test_tf1_14_a_name_at_the_limit_is_taken(tmp_path: Path, text: str) -> None:
    store = tmp_path / "store"
    result = trace_import(deepeval_import(store, text))
    assert result.code == 0, result.text
    assert Store(store).runs() == [text]


@pytest.mark.parametrize("text", ["latest", "previous", "latest:import", "previous:x", "#1", "#two", " padded ", "two\nlines", "-x"])
def test_tf1_14_a_reserved_form_is_refused_as_an_import_name(tmp_path: Path, text: str) -> None:
    store = tmp_path / "store"
    assert trace_import(deepeval_import(store, "kept")).code == 0
    before = snapshot(store)
    argv = deepeval_import(store, text, "b")
    if text.startswith("-"):
        # a value that begins with a dash is given joined to its option
        at = argv.index("--run")
        argv[at:at + 2] = [f"--run={text}"]
    refused(trace_import(argv))
    assert snapshot(store) == before


@pytest.mark.parametrize("taken", ["a name you gave", "a name from a manifest"])
def test_tf1_14_a_name_another_run_answers_to_is_refused(tmp_path: Path, taken: str) -> None:
    store = tau2_copy(tmp_path)
    write_names(store, {"selecting": T_A})
    before = snapshot(store)
    text = "selecting" if taken == "a name you gave" else T_NAMES[T_A]
    refused(trace_import(deepeval_import(store, text)))
    assert snapshot(store) == before
