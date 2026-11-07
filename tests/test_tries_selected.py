"""TRIES-1 on ``fix-check --failing-from``: the verdict counts only the inputs the control run's
failures picked, so its count is smaller than the whole run's by those as well; the sentence says
so (the same sentence, with ``and --failing-from picked`` after ``with an outcome``). The counts
are read independently, as ``test_tries_section.py`` reads them."""

from __future__ import annotations

from pathlib import Path

from breakdown_support import of_line, ok, section, table_store
from test_tries_section import of_index, thousands


def _store(tmp: Path) -> Path:
    sel = {f"c{i}": ("failed" if i < 6 else "passed") for i in range(10)}
    old = {f"c{i}": ("failed" if i < 5 else "passed") for i in range(10)}
    new = {f"c{i}": ("failed" if i < 2 else "passed") for i in range(10)}
    old["c5"] = old["c8"] = ""
    new["c1"] = new["c9"] = ""
    return table_store(tmp, {"sel": sel, "old": old, "new": new})


def _read(store: Path) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    from poisson_prove.store import Store

    sel, old, new = (Store(store).read(n) for n in ("sel", "old", "new"))
    picked = set(sel.loc[sel["outcome"] == "missed", "config_hash"])
    keep = [set(f.loc[f["outcome"].notna(), "config_hash"]) & picked for f in (old, new)]
    both = keep[0] & keep[1]
    used = tuple(int((f["outcome"].notna() & f["config_hash"].isin(both)).sum()) for f in (old, new))
    return (
        (len(old), len(new)),
        (int(old["outcome"].isna().sum()), int(new["outcome"].isna().sum())),
        used,  # type: ignore[return-value]
    )


def test_tries_1_failing_from_says_the_picked_inputs_too(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tries, none, used = _read(store)
    assert (tries, none, used) == ((10, 10), (2, 2), (4, 4))
    out = ok(["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--failing-from", "sel",
              "--max-mde", "0.5"]).out
    got = section(out)
    at = of_index(got)
    assert got[at] == of_line("fix-check", tries)
    assert got[at + 1] == ""
    assert got[at + 2] == (
        f"Tries with no outcome: {none[0]} of the old version's {thousands(tries[0])} and {none[1]} of the "
        f"new version's {thousands(tries[1])}; the counts above include them. The verdict counts only "
        f"inputs both runs carry with an outcome and --failing-from picked, so it counts {used[0]} tries "
        f"of each."
    )
    assert [line for line in got if "no outcome" in line] == [got[at + 2]]
