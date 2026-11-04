"""The recipe behind the seven stores in this directory: copy seven of Prove's stored runs
into a destination directory as the fixtures are committed, check each copy through Prove's
own reader, and compare every file written with ``SHA256SUMS``.

Three recipes (``PROVENANCE.md`` says which run got which, and why):

- bodies removed: ``manifest.json`` byte for byte; each part written back with its
  ``trace_obs`` column all-null. On the cs replay run, the home-directory prefix of the three
  recorded tracebacks in ``error`` is also replaced by ``~/``.
- whole: the manifest and every part byte for byte.
- outcome-only: ``manifest.json`` byte for byte; each part written back with its two JSON
  columns ``meta`` and ``backend_meta`` replaced by ``"{}"``.

This is the one place pyarrow is used; Trace itself reads a store only through Prove. The bytes
of a rewritten part depend on the pyarrow that writes it: the committed fixtures were written
by pyarrow 25.0.1, and another version may give other bytes for the same rows.

Usage, from the repository root, with Prove and pyarrow installed:

  python tests/fixtures/build_fixtures.py DEST --runs RUNS_ROOT --cs CS_ROOT

RUNS_ROOT is the Prove store that holds the tau2 and HumanEval runs, CS_ROOT the one that
holds the two cs_agents runs. DEST must not exist or be empty; nothing outside it is written.

``SHA256SUMS`` also lists the import fixtures under ``ingest/``; this script does not write
them (each has its own ``make.py``, and the tests check their digests), so it checks only the
lines under ``tau2/``, ``cs/`` and ``humaneval/``. Exit 0 when every file written has the digest
``SHA256SUMS`` lists for it and every file listed there under those three folders was written;
otherwise 1, naming each file that differs or is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from poisson_prove.store import Store

HERE = Path(__file__).resolve().parent
WRITTEN_BY = "25.0.1"

# group, run id, source store, recipe
RUNS = (
    ("tau2", "20260915T210140Z-4847", "runs", "bodies removed"),
    ("tau2", "20260915T211148Z-965d", "runs", "bodies removed"),
    ("cs", "20260925T234602Z-3ea0", "cs", "bodies removed"),
    ("cs", "20260925T235434Z-af48", "cs", "bodies removed"),
    ("tau2", "20260917T140219Z-2b2d", "runs", "whole"),
    ("humaneval", "20260905T185407Z-0313", "runs", "outcome-only"),
    ("humaneval", "20260905T195009Z-18ac", "runs", "outcome-only"),
)
GROUPS = frozenset(group for group, *_ in RUNS)  # the folders of SHA256SUMS this script writes
TRACEBACK_EDIT = {"20260925T235434Z-af48"}
HOME_PREFIX = re.compile(r"/(?:Users|home)/[^/\s\"']+/")
ELEVEN = ("run_id", "config_hash", "config", "seed", "replicate_index", "outcome", "t",
          "horizon", "confidence", "error", "wall_time")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_column(table: pa.Table, name: str, values: pa.Array) -> pa.Table:
    i = table.schema.get_field_index(name)
    return table.set_column(i, table.schema.field(i), values)


def rewrite(part: Path, out: Path, recipe: str, edit_tracebacks: bool) -> None:
    table = pq.read_table(part)
    if recipe == "bodies removed":
        table = replace_column(table, "trace_obs", pa.nulls(table.num_rows, pa.string()))
        if edit_tracebacks:
            errors = [None if e is None else HOME_PREFIX.sub("~/", e)
                      for e in table.column("error").to_pylist()]
            table = replace_column(table, "error", pa.array(errors, pa.string()))
    else:
        for name in ("meta", "backend_meta"):
            table = replace_column(table, name, pa.array(["{}"] * table.num_rows, pa.string()))
    pq.write_table(table, out)


def copy_run(src_root: Path, dest: Path, group: str, run_id: str, recipe: str) -> dict[str, object]:
    src, dst = src_root / run_id, dest / group / run_id
    (dst / "episodes").mkdir(parents=True)
    shutil.copyfile(src / "manifest.json", dst / "manifest.json")
    parts = sorted((src / "episodes").glob("part-*.parquet"))
    for part in parts:
        if recipe == "whole":
            shutil.copyfile(part, dst / "episodes" / part.name)
        else:
            rewrite(part, dst / "episodes" / part.name, recipe, run_id in TRACEBACK_EDIT)
    # the copy, through Prove's own reader, against the source
    a = Store(src_root).read(run_id, meta=False, trace="envelope")
    b = Store(dest / group).read(run_id, meta=False, trace="envelope")
    assert len(a) == len(b), run_id
    same = [c for c in ELEVEN if c != "error" or run_id not in TRACEBACK_EDIT]
    for column in same:
        assert a[column].tolist() == b[column].tolist() or a[column].equals(b[column]), column
    envelope = [None if e is None else json.dumps(e, sort_keys=True) for e in b["trace"]]
    if recipe == "bodies removed":
        assert envelope == [None if e is None else json.dumps(e, sort_keys=True) for e in a["trace"]]
    else:
        assert all(e is None for e in envelope), run_id
    assert Store(dest / group).tally(run_id) == Store(src_root).tally(run_id), run_id
    full = Store(dest / group).read(run_id, meta=True, trace="full")
    bodies = sum(
        1 for m in full["meta"]
        if isinstance(m, dict) and isinstance(m.get("trace"), dict)
        and any(s.get("input") is not None or s.get("output") is not None for s in m["trace"]["spans"])
    )
    assert bodies == 0, run_id
    return {"fixture": f"{group}/{run_id}", "recipe": recipe, "parts": len(parts), "rows": len(b),
            "envelopes": sum(e is not None for e in envelope),
            "manifest_equal": sha(src / "manifest.json") == sha(dst / "manifest.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the fixtures from Prove's stored runs.")
    parser.add_argument("dest", type=Path)
    parser.add_argument("--runs", type=Path, required=True, help="the store of the tau2 and HumanEval runs")
    parser.add_argument("--cs", type=Path, required=True, help="the store of the two cs_agents runs")
    ns = parser.parse_args()
    if ns.dest.exists() and any(ns.dest.iterdir()):
        print(f"{ns.dest} is not empty; nothing written", file=sys.stderr)
        return 1
    if pa.__version__ != WRITTEN_BY:
        print(f"pyarrow {pa.__version__} here; the committed fixtures were written by {WRITTEN_BY}, "
              "so the rewritten parts may differ in bytes", file=sys.stderr)
    roots = {"runs": ns.runs, "cs": ns.cs}
    for group, run_id, source, recipe in RUNS:
        print(copy_run(roots[source], ns.dest, group, run_id, recipe))
    listed = {}
    for line in (HERE / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix("./")
        if name.split("/", 1)[0] in GROUPS:
            listed[name] = digest
    written = {str(p.relative_to(ns.dest)): sha(p) for p in sorted(ns.dest.rglob("*")) if p.is_file()}
    differ = sorted(n for n in written if listed.get(n) != written[n])
    missing = sorted(set(listed) - set(written))
    print(f"{len(written)} files written, {len(listed)} listed in SHA256SUMS under "
          f"{', '.join(sorted(GROUPS))}: {len(written) - len(differ)} equal, "
          f"{len(differ)} differ, {len(missing)} missing")
    if not (differ or missing):
        print("OK: every file written has its SHA256SUMS digest, and every listed file was written")
        return 0
    for name in differ:
        why = "" if name in listed else " (SHA256SUMS lists no digest for it)"
        print(f"differs: {name}{why}", file=sys.stderr)
    for name in missing:
        print(f"missing: {name} (listed in SHA256SUMS, not written)", file=sys.stderr)
    print(f"FAIL: {len(differ)} file(s) differ, {len(missing)} missing", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
