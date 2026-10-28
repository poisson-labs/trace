"""TF2-25: an interrupted import names the run and the folder to remove (spec section 9.1 rule L6;
handed on by TF0 Session A's yes/no 10; yes/no 5, pending: dropped on a no).

The ``stopped`` line of an import interrupted while it writes names the partial run and the
store whose folder holds it, so the one step it asks for needs nothing else run first; ``doctor``
is not in the way."""

from __future__ import annotations

from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import VERDICT_LINE, deepeval_import, trace_import
from tf2_support import scratch_home  # noqa: F401


def test_tf2_25_an_interrupted_import_names_the_run_and_its_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "trace-store"

    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    with monkeypatch.context() as patched:
        patched.setattr(Store, "append", stop)
        result = trace_import(deepeval_import(store, "he-a"))
    assert result.code == 130, result.text
    first = result.lines("out")[0]
    assert VERDICT_LINE.match(first) and first.startswith("stopped  "), result.out
    assert "he-a" in first and str(store) in first, first
    assert Store(store).manifest("he-a").status != "complete"
