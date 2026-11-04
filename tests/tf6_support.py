"""Shared helpers for TF6's tests: verdicts saved in the suite format (spec sections 11.1 to 11.6,
17.3 items 1 to 5, 18.5, 18.6 and the step 16 rows of 18.7), with what earlier rulings sent to
TF6: the continuous-measures table wired into ``fix-check`` (CT2), the near-zero old mean (HY1),
the plain spelling of the plus-minus sign, and ``--verdicts`` on the comparison verbs (FI9).

Not a test module and not collected.

The rules as these tests read them (the readings the spec leaves open are put to Taylor in
``log/trace-tf6-a/rulings.md``, SV1 on; each test file's opening says which it holds):

- ``--save`` on ``where``, ``compare``, ``fix-check`` and ``changes`` saves the verdict as one
  artifact of the suite's format (``poisson.artifact/1``) into the store the runs were read from,
  at ``<store>/.poisson/artifacts/<kind>/<id>/``, the kind the verb's name. Without ``--save`` or
  ``--out`` nothing is written, as today.
- The artifact folder holds ``artifact.json`` (the descriptor), ``result.json`` (role
  ``result``), ``report.md`` (role ``report``), ``table.parquet`` (role ``table``,
  ``poisson.table/1``) and, for ``where``, ``charts/curve.svg`` with ``charts/curve.json``.
- ``result.json`` is the verb's ``--json`` document as printed with the same flags, with the
  keys section 11.3 adds and TF6's own: ``summary`` and ``before_you_act`` (S2), ``note`` as a
  list, ``versions``, and, on the three verbs of two runs, ``failure_taxonomy_diff`` and
  ``continuous_measures``; every store path written as section 11.2 rules for ``handover.json``.
- ``report.md`` is the report as the plain command prints it, without the detail lines
  ``--save`` and ``--out`` add, with the same store-path rule.
- ``--out DIR`` saves as ``--save`` does and writes a copy of the artifact's folder into DIR,
  with ``handover.json`` beside it. ``poisson-trace handover --check DIR`` checks a bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from conftest import FIXTURES
from tf0_support import Ran, trace, trace_import

PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
# the two runs of the committed Prove 0.1.3 store, by the names they were given at sweep time
# (the store moved from 0.1.2 to 0.1.3 with the Prove pin: SB7, ruled by Taylor 2026-11-04)
BEFORE, AFTER = "agent before", "agent after"
BEFORE_ID, AFTER_ID = "20261104T162926Z-b4d5", "20261104T162928Z-1596"
EVENTS_012 = ["--event", "violated", "--event", "timeout"]
INGEST = FIXTURES / "ingest"
JUNIT = INGEST / "junit"
TABLE = INGEST / "table"
VERBS = ("where", "compare", "fix-check", "changes")
TWO_RUNS = ("compare", "fix-check", "changes")
# each verb's arms, as its JSON names them under "runs"
ARMS = {"compare": ("a", "b"), "fix-check": ("old", "new"), "changes": ("a", "b")}
# the labels the continuous measures name each version by in their sentences
LABELS = {"compare": ("A", "B"), "fix-check": ("old", "new"), "changes": ("A", "B")}
# the schema each verb's JSON carries today (fix-check and changes are at their second number)
SCHEMAS = {
    "where": "poisson-trace.where/1",
    "compare": "poisson-trace.compare/1",
    "fix-check": "poisson-trace.fix-check/2",
    "changes": "poisson-trace.changes/2",
}
DESCRIPTOR_KEYS = ["format", "kind", "id", "tool", "tool_version", "created_at", "inputs",
                   "settings", "summary", "files"]
HANDOVER_KEYS = ["schema", "verb", "files", "versions", "written_at", "runs"]
TABLE_COLUMNS = ["artifact_id", "event", "condition", "condition_hash", "arm", "metric", "value",
                 "note", "level", "step", "cause"]
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---------- stores ----------


def store012(tmp: Path, name: str = "store") -> Path:
    """A copy of the committed Prove 0.1.3 store, with its sweep-time names and its own saved
    comparison: two runs of four inputs, 160 tries each, every one traced, failure kinds in
    both."""
    target = tmp / name
    shutil.copytree(PROVE_013, target)
    return target


def junit_store(tmp: Path, name: str = "jstore", files: Sequence[str] = ("humaneval-a.xml", "humaneval-b.xml"),
                runs: Sequence[str] = ("ja", "jb"), *extra: str) -> Path:
    """A store of JUnit imports of committed reports, one run each, a day apart."""
    store = tmp / name
    for i, (run, file) in enumerate(zip(runs, files, strict=True)):
        made = trace_import(["junit", str(JUNIT / file), "--store", str(store), "--run", run,
                             "--started", f"2026-11-0{i + 1}T10:00:00Z", *extra])
        assert made.code == 0, made.text
    return store


def table_store(tmp: Path, old: Mapping[str, Sequence[float]], new: Mapping[str, Sequence[float]],
                measure: str = "cost_usd", name: str = "tstore") -> Path:
    """A store of two table imports, ``old`` and ``new``: one row a try, the measure's column
    holding the values given per case; every fourth case's first try failed in the old run, and
    the one after it in the new."""
    store = tmp / name
    for i, (run, cases) in enumerate((("old", old), ("new", new))):
        csv = tmp / f"{name}-{run}.csv"
        lines = [f"case,outcome,{measure}"]
        for j, (case, values) in enumerate(cases.items()):
            lines += [f"{case},{'failed' if k == 0 and j % 4 == i else 'passed'},{v!r}" for k, v in enumerate(values)]
        csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
        made = trace_import(["table", str(csv), "--store", str(store), "--run", run,
                             "--case-column", "case", "--outcome-column", "outcome",
                             "--failed", "failed", "--started", f"2026-11-0{i + 1}T10:00:00Z"])
        assert made.code == 0, made.text
    return store


# ---------- the verbs on the Prove 0.1.3 store ----------


def argv012(verb: str, store: Path, *extra: str) -> list[str]:
    """Each verb on the two runs of a copy of the Prove 0.1.3 store."""
    s = str(store)
    return {
        "where": ["where", AFTER, "--store", s, *EVENTS_012, "--at", "3"],
        "compare": ["compare", BEFORE, AFTER, "--store", s, *EVENTS_012, "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", BEFORE, AFTER, "--store", s, *EVENTS_012, "--inputs", "all",
                      "--max-mde", "0.2"],
        "changes": ["changes", BEFORE, AFTER, "--store", s, *EVENTS_012],
    }[verb] + list(extra)


def run_ok(argv: Sequence[Any]) -> Ran:
    ran = trace([str(a) for a in argv])
    assert ran.code == 0, ran.text
    return ran


# ---------- what a save wrote ----------


def artifacts(store: Path, kind: str | None = None) -> list[Path]:
    """Every saved artifact folder of ``kind`` (any kind when None) Trace wrote: the folders
    under ``.poisson/artifacts/<kind>/`` named as a 16-hex id, Prove's own kind left out."""
    base = store / ".poisson" / "artifacts"
    if not base.is_dir():
        return []
    kinds = [kind] if kind is not None else [k for k in VERBS if (base / k).is_dir()]
    return sorted(p for k in kinds if (base / k).is_dir() for p in (base / k).iterdir()
                  if HEX16.match(p.name))


def the_artifact(store: Path, kind: str) -> Path:
    found = artifacts(store, kind)
    assert len(found) == 1, found
    return found[0]


def descriptor(folder: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
    return doc


def result_of(folder: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    return doc


def files_in(folder: Path) -> list[str]:
    """Every file under the folder, as a path relative to it with forward slashes, sorted."""
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path) -> dict[str, tuple[int, int, str]]:
    """Every file under ``root``: its size, modification time and digest."""
    out = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        st = path.stat()
        out[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns, sha256_file(path))
    return out


def outside_dot_poisson(snap: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in snap.items() if not k.startswith(".poisson/")}


def canonical(value: Any) -> str:
    """The format's canonical JSON: sorted keys, no spaces, UTF-8 as it is (the Artifact
    Format, section 5.1)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


# the settings kept in artifact.json that record how a result was asked for, and are not in
# its id: where each setting came from, and the trace.toml names of the stores read
HOW_ASKED = ("from", "stores")


def expected_id(desc: Mapping[str, Any]) -> str:
    """The id the format defines, recomputed from the descriptor: the first 16 hex of the
    sha256 of the canonical JSON of the kind, the tool, its major.minor version, the inputs and
    the result-changing settings."""
    payload = {
        "kind": desc["kind"],
        "tool": desc["tool"],
        "tool_version": ".".join(str(desc["tool_version"]).split(".")[:2]),
        "inputs": desc["inputs"],
        "settings": {k: v for k, v in desc["settings"].items() if k not in HOW_ASKED},
    }
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:16]


def saved_line(kind: str, identity: str) -> str:
    return f"  saved  {kind} {identity[:12]}"


def without_detail(out: str, *labels: str) -> str:
    """The output with its detail lines of these labels (``  saved  ``, ``  wrote  ``,
    ``  verdicts  ``) taken out."""
    keep = [line for line in out.splitlines(keepends=True)
            if not any(line.startswith(f"  {label}  ") for label in labels)]
    return "".join(keep)


def trace_version() -> str:
    from importlib.metadata import version

    return version("poisson-trace")


def prove_version() -> str:
    import poisson_prove

    return str(poisson_prove.__version__)


def strings_in(value: Any) -> Iterable[str]:
    """Every string in a JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for k, v in value.items():
            yield str(k)
            yield from strings_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v)


def keys_in(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield str(k)
            yield from keys_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from keys_in(v)


def read_table(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    return list(pq.read_table(path).to_pylist())


def table_schema(path: Path) -> list[tuple[str, str]]:
    import pyarrow.parquet as pq

    return [(f.name, str(f.type)) for f in pq.read_schema(path)]


def reseal(bundle: Path) -> None:
    """Rewrite ``handover.json``'s digests and sizes to the files as they now are, so that a
    test that changes one file in a bundle fails only on the rule it means to break."""
    doc = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    for entry in doc["files"]:
        path = bundle / entry["name"]
        if path.is_file():
            entry["sha256"] = sha256_file(path)
            entry["bytes"] = path.stat().st_size
    (bundle / "handover.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def reseal_descriptor(bundle: Path) -> None:
    """Rewrite ``artifact.json``'s file digests to the files as they now are, then reseal."""
    desc = json.loads((bundle / "artifact.json").read_text(encoding="utf-8"))
    for entry in desc["files"]:
        entry["sha256"] = sha256_file(bundle / entry["path"])
    (bundle / "artifact.json").write_text(json.dumps(desc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reseal(bundle)


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def env_ascii() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "ascii"
    return env


def measures_store(tmp: Path, name: str = "mstore", cases: int = 16) -> Path:
    """A small store of two table imports, ``old`` and ``new``, every try recording its time,
    its tokens and its output length, worked out from the case's number (no draw): the time a
    little longer in the new run on most cases, the tokens alike but for a few, so the table holds
    a tested call, a quiet one and one under the floor. Every fifth case failed in the old run and
    every seventh in the new."""
    store = tmp / name
    for i, run in enumerate(("old", "new")):
        lines = ["case,outcome,wall_time_s,input_tokens,output_tokens,output_chars"]
        for j in range(cases):
            wall = 1.0 + 0.1 * (j % 5) + (0.05 + 0.01 * (j % 3) if run == "new" else 0.0)
            tin = 100 + 7 * j + ((-1) ** j * (j % 4) if run == "new" else 0)
            tout = 40 + 3 * (j % 6) + (1 if run == "new" and j < 3 else 0)
            failed = j % (5 if run == "old" else 7) == 0
            lines.append(f"c{j},{'failed' if failed else 'passed'},{wall!r},{tin},{tout},{200 + j}")
        csv = tmp / f"{name}-{run}.csv"
        csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
        made = trace_import(["table", str(csv), "--store", str(store), "--run", run,
                             "--case-column", "case", "--outcome-column", "outcome",
                             "--failed", "failed", "--started", f"2026-11-0{i + 1}T10:00:00Z"])
        assert made.code == 0, made.text
    return store
