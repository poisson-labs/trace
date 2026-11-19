"""Shared helpers for the tests of the import under the main command and the table and JUnit
readers (TF3-1 to TF3-30): the two spellings of the import, run side by side; tables in every
format the table reader takes; JUnit reports built element by element; the stored rows read
back through Prove; and the integration pages' marked blocks, run as a reader runs them.

Not a test module and not collected.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import stat
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from conftest import FIXTURES
from tf0_support import Ran, trace, trace_import

REPO = Path(__file__).resolve().parent.parent
TABLE = FIXTURES / "ingest" / "table"
JUNIT = FIXTURES / "ingest" / "junit"
TABLE_A, TABLE_B = TABLE / "humaneval-a.csv", TABLE / "humaneval-b.csv"
# pytest's reports on two small suites of Trace's own, each run twice: a slice of Trace's own tests,
# and a suite that replays the stored HumanEval outcomes, run against each stored run
OWN_1, OWN_2 = JUNIT / "trace-suite-1.xml", JUNIT / "trace-suite-2.xml"
SUITE_1, SUITE_2 = JUNIT / "humaneval-a.xml", JUNIT / "humaneval-b.xml"
# the readers TF3 adds, and every reader a module of the install carries once it lands
PRESENT = ("deepeval", "ragas", "table", "junit")
OLD = "poisson-trace-import"
VERB = "poisson-trace import"
HE_FAILED = ("failed_assertion", "crashed")
PAGES = REPO / "docs" / "integrations"


def src_files() -> list[Path]:
    """Every module of the package under test, the readers' included."""
    import poisson_trace

    return sorted(Path(poisson_trace.__file__).resolve().parent.rglob("*.py"))


# ---------- the two spellings ----------


def verb(argv: Sequence[Any]) -> Ran:
    """``poisson-trace import`` in-process."""
    return trace(["import", *[str(a) for a in argv]])


def alias(argv: Sequence[Any]) -> Ran:
    """``poisson-trace-import`` in-process."""
    return trace_import([str(a) for a in argv])


def both(argv: Sequence[Any]) -> tuple[Ran, Ran]:
    return verb(argv), alias(argv)


# ---------- argv builders ----------


def table_argv(
    files: Sequence[Path | str] | Path | str,
    store: Path | str,
    run: str,
    *extra: str,
    case: str = "case",
    outcome: str | None = "outcome",
    failed: Sequence[str] = ("fail",),
    score: str | None = None,
    cut: str | None = None,
    side: str | None = None,
) -> list[str]:
    """``table FILE … --store S --run R --case-column C`` and either the outcome form
    (``--outcome-column O --failed V …``) or, when ``score`` is given, the score form
    (``--score-column S --cut X --below|--above``)."""
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    argv = ["table", *[str(p) for p in paths], "--store", str(store), "--run", run, "--case-column", case]
    if score is None:
        assert outcome is not None
        argv += ["--outcome-column", outcome]
        for value in failed:
            argv += ["--failed", value]
    else:
        argv += ["--score-column", score]
        if cut is not None:
            argv += ["--cut", cut]
        if side is not None:
            argv.append(f"--{side}")
    return [*argv, *extra]


def he_table_argv(store: Path | str, run: str, which: str = "a", *extra: str) -> list[str]:
    """The committed HumanEval table of one run, read as the fixture means it."""
    started = "2026-09-05T18:54:07Z" if which == "a" else "2026-09-05T19:50:09Z"
    return table_argv(TABLE / f"humaneval-{which}.csv", store, run, "--started", started, *extra, failed=HE_FAILED)


def junit_argv(files: Sequence[Path | str] | Path | str, store: Path | str, run: str, *extra: str) -> list[str]:
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    return ["junit", *[str(p) for p in paths], "--store", str(store), "--run", run, *extra]


# ---------- tables ----------


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_table(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None) -> Path:
    """The rows in the format the name's extension says (``.csv``, ``.jsonl``, ``.json``, each
    also ``.gz``, or ``.parquet``). In a CSV every cell is text and None is an empty cell; in
    JSON a None is a null; a key a row lacks is left out of that row's object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = path.name
    gz = name.endswith(".gz")
    plain = name[: -len(".gz")] if gz else name
    cols = list(columns) if columns is not None else list(dict.fromkeys(k for row in rows for k in row))
    if plain.endswith(".parquet"):
        import pandas as pd

        pd.DataFrame([{c: row.get(c) for c in cols} for row in rows], columns=cols).to_parquet(path, index=False)
        return path
    if plain.endswith(".csv"):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(cols)
        for row in rows:
            writer.writerow([_cell(row.get(c)) for c in cols])
        data = buf.getvalue().encode("utf-8")
    elif plain.endswith(".jsonl"):
        data = "".join(json.dumps(dict(row)) + "\n" for row in rows).encode("utf-8")
    else:
        data = json.dumps([dict(row) for row in rows]).encode("utf-8")
    path.write_bytes(gzip.compress(data, mtime=0) if gz else data)
    return path


def outcome_rows(spec: Sequence[tuple[str, str | None]], **other: Any) -> list[dict[str, Any]]:
    """``[(case, outcome cell), …]`` as rows with the columns ``case`` and ``outcome``, and the
    other columns given, the same value on every row."""
    return [{"case": case, "outcome": outcome, **other} for case, outcome in spec]


# ---------- JUnit reports ----------


@dataclass(frozen=True)
class Case:
    """One ``<testcase>``: ``result`` is ``pass``, ``failure``, ``error`` or ``skipped``."""

    name: str | None
    classname: str | None = "tests.test_agent"
    result: str = "pass"
    message: str = ""
    text: str = ""


def _testcase(case: Case) -> str:
    attrs = ""
    if case.classname is not None:
        attrs += f" classname={quoteattr(case.classname)}"
    if case.name is not None:
        attrs += f" name={quoteattr(case.name)}"
    attrs += ' time="0.010"'
    if case.result == "pass":
        return f"<testcase{attrs} />"
    body = case.text.replace("&", "&amp;").replace("<", "&lt;")
    return f"<testcase{attrs}><{case.result} message={quoteattr(case.message)}>{body}</{case.result}></testcase>"


def suite(cases: Sequence[Case], *, timestamp: str | None = "2026-10-12T09:30:00.000000+00:00",
          name: str = "pytest", extra: str = "") -> str:
    """One ``<testsuite>`` element holding the cases."""
    counts = {r: sum(1 for c in cases if c.result == r) for r in ("failure", "error", "skipped")}
    stamp = "" if timestamp is None else f" timestamp={quoteattr(timestamp)}"
    return (
        f'<testsuite name={quoteattr(name)} errors="{counts["error"]}" failures="{counts["failure"]}" '
        f'skipped="{counts["skipped"]}" tests="{len(cases)}" time="1.000"{stamp} hostname="localhost">'
        f"{extra}{''.join(_testcase(c) for c in cases)}</testsuite>"
    )


def report(*suites: str, root: str = "testsuites", head: str = '<?xml version="1.0" encoding="utf-8"?>') -> str:
    """A JUnit report: the suites inside ``<testsuites>``, or a lone ``<testsuite>`` as the root
    when ``root`` is ``testsuite`` (one suite)."""
    if root == "testsuite":
        assert len(suites) == 1
        return head + suites[0]
    return head + f'<testsuites name="pytest tests">{"".join(suites)}</testsuites>'


def write_report(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------- what was stored ----------


def read_rows(root: Path, run: str) -> list[dict[str, Any]]:
    """The run's rows through Prove: case, repeat, outcome, error, seed, and ``meta``, sorted by
    case then repeat."""
    from poisson_prove.store import Store

    frame = Store(root).read(run, meta=True, trace="none")
    out = []
    for row in frame.to_dict("records"):
        out.append({
            "case": row["config"]["case"], "config": row["config"], "repeat": int(row["replicate_index"]),
            "outcome": row["outcome"], "error": row["error"], "seed": int(row["seed"]), "meta": row["meta"],
        })
    return sorted(out, key=lambda r: (r["case"], r["repeat"]))


def by_case(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[str | None]]:
    """Case -> the rows' outcomes in repeat order."""
    out: dict[str, list[str | None]] = {}
    for row in sorted(rows, key=lambda r: (r["case"], r["repeat"])):
        out.setdefault(row["case"], []).append(row["outcome"])
    return out


def all_bytes(root: Path) -> list[tuple[str, bytes]]:
    """Every file under ``root`` as raw bytes, and every Parquet part decoded cell by cell."""
    import pyarrow.parquet as pq

    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out.append((str(path), path.read_bytes()))
        if path.suffix == ".parquet":
            cells = json.dumps(pq.read_table(path).to_pylist(), default=str).encode("utf-8")
            out.append((f"{path} (decoded)", cells))
    return out


def holds(root: Path, needle: str) -> list[str]:
    raw = needle.encode("utf-8")
    return [name for name, data in all_bytes(root) if raw in data]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalars(value: Any) -> list[Any]:
    """Every scalar inside a JSON value."""
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in scalars(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in scalars(v)]
    return [value]


def no_outcome_total(doc: Mapping[str, Any]) -> int:
    return int(sum(doc["no_outcome"].values()))


def imported(result: Ran) -> dict[str, Any]:
    """The import's JSON summary of a run that was written."""
    assert result.code == 0, result.text
    data: dict[str, Any] = result.json()
    assert data["schema"] == "poisson-trace.import/1" and data["verdict"] == "ok", data
    return data


def usage_error(result: Ran) -> list[str]:
    """Exit 2, nothing on stdout, one ``error:`` line and ``  next:`` lines under it; the words
    of the first next line's command."""
    from tf1_support import shell_words

    assert result.code == 2 and result.out == "", result.text
    lines = result.lines()
    assert lines[0].startswith("error: ") and len(lines) >= 2, result.err
    assert all(line.startswith("  next: ") for line in lines[1:]), result.err
    return shell_words(lines[1][len("  next: "):])


def refusal(result: Ran) -> str:
    """Exit 1, nothing on stdout, one ``error:`` line with only ``  next:`` lines under it; the
    error line."""
    assert result.code == 1 and result.out == "", result.text
    lines = result.lines()
    assert lines and lines[0].startswith("error: "), result.err
    assert all(line.startswith("  next: ") for line in lines[1:]), result.err
    return lines[0]


# ---------- the pages ----------

FENCE = re.compile(r"^```")


@dataclass(frozen=True)
class Block:
    kind: str  # command, output or excerpt
    code: int | None
    line: int  # the first line of the body, counting from 1
    body: str
    varies: bool = False


def blocks(text: str) -> list[Block]:
    """Every block of a page that is run or held against what was printed, in order. The marks
    are read by the one reader every page is held to (``tf5_support.parse``): ``command`` in
    each of its forms, ``output`` and ``excerpt``."""
    from tf5_support import parse

    return [Block(b.kind, b.code, b.line, b.body, b.varies) for b in parse(text)[0] if b.kind in ("command", "output", "excerpt")]


def fenced(text: str) -> list[str]:
    """The bodies of every fenced block of a markdown text, marked or not."""
    out, body, inside = [], [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            if inside:
                out.append("\n".join(body))
                body = []
            inside = not inside
        elif inside:
            body.append(line)
    return out


def shims(folder: Path) -> Path:
    """A folder holding ``poisson-trace`` and ``poisson-trace-import`` as small scripts that run
    this interpreter on the package under test, whatever console scripts are installed."""
    folder.mkdir(parents=True, exist_ok=True)
    bodies = {
        "poisson-trace": "from poisson_trace.cli import main",
        "poisson-trace-import": "from poisson_trace.ingest.cli import main",
    }
    for name, line in bodies.items():
        path = folder / name
        path.write_text(f"#!{sys.executable}\nimport sys\n{line}\nsys.exit(main(sys.argv[1:]))\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return folder


def page_root(tmp_path: Path) -> Path:
    """A folder laid out as a clone's root for the pages' commands: the fixtures they read,
    copied, so nothing a page runs can touch the repository."""
    root = tmp_path / "clone"
    shutil.copytree(FIXTURES / "ingest", root / "tests" / "fixtures" / "ingest")
    return root


@dataclass(frozen=True)
class Checked:
    block: Block
    command: str
    code: int
    printed: str


def run_page(page: Path, root: Path, home: Path, bin_dir: Path) -> list[Checked]:
    """Every command block of the page run in ``root``, in page order, by the one runner every
    page is held to (``tf5_support.run_block``: bash, the shims first on PATH, HOME a folder of
    its own, a pull answered from the committed captures); each output and excerpt block
    paired with the command above it, its exit code and what it printed (stdout, then
    stderr)."""
    import tf5_support as tf5

    tf5.shims(bin_dir)
    out: list[Checked] = []
    last: tuple[str, int, str] | None = None
    for block in tf5.parse(page.read_text(encoding="utf-8"))[0]:
        if block.kind == "command":
            code, printed = tf5.run_block(block, root, tf5.page_env(home, bin_dir, pull=block.pull))
            last = (block.body.replace("\\\n", " "), code, printed.replace("\r\n", "\n"))
        elif block.kind in ("output", "excerpt"):
            assert last is not None, (page.name, block.line)
            out.append(Checked(Block(block.kind, block.code, block.line, block.body, block.varies), *last))
    return out


def holds_block(checked: Checked) -> bool:
    """An output block is the whole of what the command printed; an excerpt a run of whole lines
    of it; both with the exit code the mark names, and under ``varies`` by that rule."""
    import tf5_support as tf5

    block = checked.block
    return tf5.holds(tf5.Checked(tf5.Block(block.kind, block.line, block.body, code=block.code, varies=block.varies),
                                 checked.command, checked.code, checked.printed))
