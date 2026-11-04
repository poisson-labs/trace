"""Shared helpers for TF22's tests: folder ingest (``ingest/folder.py``) and the ``--verdicts``
sidecar join (``ingest/verdicts.py``), spec section 18.2 and 18.3.1, ruled by SG5, SG8 and SG17.

Not a test module and not collected.

Every folder here is built from committed fixtures, never from invented values: the JUnit
reports, the table and the Ragas tables are copied whole or split by case into shards; the
DeepEval test runs are the files DeepEval wrote, unzipped under the names DeepEval gave them
(``tests/fixtures/PROVENANCE.md``, their digests checked); the Prove folders are the committed
stores. A pull folder's ``pull.json`` is the spec's own shape (section 18.3.2) around committed
files. A verdicts file is built from the cases a committed fixture holds.

The rules as these tests read them:

- A folder is read in this order (section 18.3.1): a Prove run folder (``manifest.json`` and
  ``episodes/``); a folder Prove reads as a store; a folder holding ``pull.json``; otherwise
  the regular files directly in it, each claimed by the reader whose ``looks_like`` claims it
  (the readers' own detectors are the signature table), leaving out hidden files, names
  starting with ``_`` and names starting with ``README``. Files no reader claims are left out.
  Subfolders are not read. Files are taken in the order of their names.
- Several files of one tool are one run when no case is in two of them (shards); a case in two
  files means two runs, refused with each file named. DeepEval test runs are one run each.
- On a verb, a run word that reaches a stored run is that run, as before; a word that reaches
  none and names a folder is the folder. A Prove folder is read where it is. A tool folder is
  read through its reader, with the reader's own flags given on the verb's command line, into a
  store that does not outlive the command; nothing is written anywhere that stays.
- What a verb prints on folders is, outside its commands, byte for byte what it prints on the
  same folders imported one by one into an empty store, each under its folder's name. The
  commands name each folder by the path typed, carry no ``--store``, carry the reader's flags,
  and run as printed. ``--json``'s ``store`` is null.
- ``--verdicts FILE`` (import only in TF22): a ``.csv`` or ``.jsonl`` file of rows keyed by
  ``case``, or by ``input`` when no case matches (``input:`` and the first 12 hex characters of
  the SHA-256 of the canonical input). A verdict fills what the source did not record and must
  agree with what it did.
"""

from __future__ import annotations

import contextlib
import csv
import gzip
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conftest import FIXTURES

INGEST = FIXTURES / "ingest"
JUNIT = INGEST / "junit"
TABLE = INGEST / "table"
RAGAS = INGEST / "ragas"
DEEPEVAL = INGEST / "deepeval"
PROVE_012 = FIXTURES / "prove-stores" / "prove-0.1.2"
PROVE_012_RUNS = ("20261103T150857Z-24db", "20261103T150859Z-81ef")
CS_RUNS = ("20260925T234602Z-3ea0", "20260925T235434Z-af48")
TAU2_RUNS = ("20260915T210140Z-4847", "20260915T211148Z-965d", "20260917T140219Z-2b2d")

# the files DeepEval wrote, as PROVENANCE.md records them (name, sha256 before gzip)
DEEPEVAL_WROTE = {
    "a": ("test_run_20260929_143252.json",
          "8782a23fd56704d6f68cf0677e8ca5a2a7ece84e680ce900187f00fe2d1ce0e6"),
    "b": ("test_run_20260929_143257.json",
          "81a8d2f3fed0c09fa42b8c581284d739d74f9fa10caa1b5035ff09bc62139bb2"),
}

# Each tool's flags, as the committed fixtures are read everywhere else (tf21_support.IMPORTS).
FLAGS: dict[str, list[str]] = {
    "junit": [],
    "table": ["--case-column", "case", "--outcome-column", "outcome", "--failed",
              "failed_assertion", "--failed", "crashed"],
    "ragas": ["--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"],
    "deepeval": ["--metric", "Tests Passed", "--cut", "recorded", "--case", "name"],
}
# the failure words each tool's runs are counted by
EVENTS: dict[str, list[str]] = {
    "junit": ["--event", "missed"],
    "table": ["--event", "missed"],
    "ragas": ["--event", "missed"],
    "deepeval": ["--event", "missed"],
}
OLD, NEW = "tf22-old", "tf22-new"


# ---------- running the commands in-process ----------


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err

    def json(self) -> Any:
        return json.loads(self.out)


def _call(module: str, argv: Sequence[Any]) -> Ran:
    import importlib

    main = importlib.import_module(module).main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return Ran(int(code), out.getvalue(), err.getvalue())


def trace(*argv: Any) -> Ran:
    """``poisson-trace`` in-process, plain (no colour, as on a pipe)."""
    return _call("poisson_trace.cli", [*argv])


def trace_import(*argv: Any) -> Ran:
    """``poisson-trace import`` in-process, through the main command."""
    return _call("poisson_trace.cli", ["import", *argv])


@contextlib.contextmanager
def chdir(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


# ---------- folders built from the committed fixtures ----------


def copy_into(folder: Path, *files: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, folder / f.name)
    return folder


def deepeval_wrote(which: str) -> bytes:
    """The bytes DeepEval wrote for run ``which``, unzipped and checked against PROVENANCE.md."""
    data = gzip.decompress((DEEPEVAL / f"humaneval-{which}.json.gz").read_bytes())
    assert hashlib.sha256(data).hexdigest() == DEEPEVAL_WROTE[which][1]
    return data


def deepeval_folder(folder: Path, *which: str) -> Path:
    """A DeepEval results folder holding the test runs ``which``, each under DeepEval's name."""
    folder.mkdir(parents=True, exist_ok=True)
    for w in which:
        (folder / DEEPEVAL_WROTE[w][0]).write_bytes(deepeval_wrote(w))
    return folder


def deepeval_inputs(which: str = "a") -> dict[str, str]:
    """Each test case's name and its ``input``, as DeepEval wrote them (one input per name)."""
    doc = json.loads(deepeval_wrote(which))
    out: dict[str, str] = {}
    for case in doc["testCases"]:
        out.setdefault(case["name"], case["input"])
    return out


def junit_shards(folder: Path, source: Path = JUNIT / "humaneval-a.xml",
                 pattern: str = "junit-{i}.xml") -> Path:
    """``source`` split into one report per test class, as parallel workers write them: each
    shard a ``testsuites`` holding the suite with its counts for the cases it carries, and the
    suite's own timestamp. No case is in two shards."""
    folder.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(source)
    suites = tree.getroot()
    suite = suites.find("testsuite")
    assert suite is not None
    classes: dict[str, list[ET.Element]] = {}
    for case in suite.findall("testcase"):
        classes.setdefault(case.get("classname", ""), []).append(case)
    for i, (_, cases) in enumerate(sorted(classes.items())):
        new_suites = ET.Element("testsuites", dict(suites.attrib))
        attrs = dict(suite.attrib)
        attrs["tests"] = str(len(cases))
        attrs["failures"] = str(sum(1 for c in cases if c.find("failure") is not None))
        attrs["errors"] = str(sum(1 for c in cases if c.find("error") is not None))
        attrs["skipped"] = str(sum(1 for c in cases if c.find("skipped") is not None))
        new_suite = ET.SubElement(new_suites, "testsuite", attrs)
        for c in cases:
            new_suite.append(c)
        data = ET.tostring(new_suites, encoding="utf-8", xml_declaration=True)
        (folder / pattern.format(i=i)).write_bytes(data)
    return folder


def _split_rows(rows: list[Any], key: Any, parts: int) -> list[list[Any]]:
    """Rows split into ``parts`` shards by case (every repeat of a case in one shard), each shard
    keeping the rows' order."""
    cases = list(dict.fromkeys(key(r) for r in rows))
    shard_of = {c: i * parts // len(cases) for i, c in enumerate(cases)}
    out: list[list[Any]] = [[] for _ in range(parts)]
    for r in rows:
        out[shard_of[key(r)]].append(r)
    return out


def table_parts(folder: Path, source: Path = TABLE / "humaneval-a.csv", parts: int = 2) -> Path:
    """The table split by case into ``part-00000.csv`` and on, each with the header."""
    folder.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    header, *lines = text.splitlines(keepends=True)
    shards = _split_rows(lines, lambda line: line.split(",", 1)[0], parts)
    for i, shard in enumerate(shards):
        (folder / f"part-{i:05d}.csv").write_text(header + "".join(shard), encoding="utf-8")
    return folder


def ragas_parts(folder: Path, source: Path = RAGAS / "rag-base.jsonl", parts: int = 2) -> Path:
    """The Ragas table split by case into ``part-00000.jsonl`` and on."""
    folder.mkdir(parents=True, exist_ok=True)
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    shards = _split_rows(lines, lambda line: json.loads(line)["case"], parts)
    for i, shard in enumerate(shards):
        (folder / f"part-{i:05d}.jsonl").write_text("".join(shard), encoding="utf-8")
    return folder


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pull_folder(folder: Path, tool: str, listed: Sequence[Path], **override: Any) -> Path:
    """A saved pull folder (section 18.3.2): the files copied in and ``pull.json`` listing them
    with their digests, in the spec's shape; ``override`` replaces or adds keys."""
    files = list(listed)
    copy_into(folder, *files)
    doc: dict[str, Any] = {
        "schema": "poisson.raw-pull/1",
        "tool": tool,
        "pulled_at": "2026-10-28T18:30:00Z",
        "source_uri": f"{tool}:fixture",
        "endpoint": "file:committed-fixture",
        "raw_text_stripped": True,
        "files": [{"path": f.name, "sha256": sha256_of(f), "rows": None} for f in files],
    }
    doc.update(override)
    (folder / "pull.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return folder


def one_run_store(folder: Path, source: Path, run_id: str) -> Path:
    """A copy of the store ``source`` holding only ``run_id`` (and its ``.poisson`` folder and
    names file, if any)."""
    folder.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.is_dir() and not entry.name.startswith(".") and entry.name != run_id:
            continue
        if entry.is_dir():
            shutil.copytree(entry, folder / entry.name)
        else:
            shutil.copy2(entry, folder / entry.name)
    return folder


def store_copy(folder: Path, source: Path) -> Path:
    shutil.copytree(source, folder)
    return folder


# ---------- comparing what the two routes print ----------

COMMAND = "<COMMAND>"
_SPAN = re.compile(r"`poisson-trace[^`]*`")


def commands_of(text: str) -> list[str]:
    """Every command a plain output shows: each ``next:`` line's command (its ``  # ...``
    comment cut off) and each backtick span that opens with ``poisson-trace``."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("next:"):
            out.append(stripped.removeprefix("next:").strip().split("  # ", 1)[0])
        for span in _SPAN.findall(line):
            out.append(span.strip("`"))
    return out


def masked(text: str) -> str:
    """The plain output with every command replaced by ``<COMMAND>``."""
    lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("next:"):
            lead = line[: len(line) - len(line.lstrip())]
            line = f"{lead}next: {COMMAND}\n"
        lines.append(_SPAN.sub(COMMAND, line))
    return "".join(lines)


def masked_json(value: Any) -> Any:
    """A JSON document with every command string (one that
    opens with ``poisson-trace`` or holds a backtick span that does) replaced by ``<COMMAND>``."""
    if isinstance(value, dict):
        return {k: masked_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [masked_json(v) for v in value]
    if isinstance(value, str):
        if value.startswith("poisson-trace "):
            return COMMAND
        return _SPAN.sub(COMMAND, value)
    return value


def json_commands(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [c for v in value.values() for c in json_commands(v)]
    if isinstance(value, list):
        return [c for v in value for c in json_commands(v)]
    if isinstance(value, str):
        if value.startswith("poisson-trace "):
            return [value.split("  # ", 1)[0]]
        return [s.strip("`") for s in _SPAN.findall(value)]
    return []


def without_store(doc: Any) -> Any:
    """The document with every ``store`` key dropped, at any depth (``store`` at the top of
    some verbs' JSON, ``prove.store`` in others')."""
    if isinstance(doc, dict):
        return {k: without_store(v) for k, v in doc.items() if k != "store"}
    if isinstance(doc, list):
        return [without_store(v) for v in doc]
    return doc


def stores_of(doc: Any) -> list[Any]:
    """Every ``store`` value in the document, at any depth."""
    if isinstance(doc, dict):
        return [v for k, v in doc.items() if k == "store"] + [
            s for k, v in doc.items() if k != "store" for s in stores_of(v)]
    if isinstance(doc, list):
        return [s for v in doc for s in stores_of(v)]
    return []


PLACEHOLDERS = frozenset({"X", "OLD", "NEW", "OLDER", "NEWER", "OTHER", "RUN", "N", "K"})


def runnable(command: str) -> bool:
    """A command that names no placeholder and is a whole command (more than the verb)."""
    words = shlex.split(command)
    return len(words) > 2 and not any(w in PLACEHOLDERS for w in words)


def strip_flags(words: Sequence[str], flags: Sequence[str]) -> list[str]:
    """``words`` with each ``--flag value`` or ``--flag`` pair of ``flags`` taken out once, in
    the order given; asserts every one was there."""
    out = list(words)
    i = 0
    while i < len(flags):
        flag = flags[i]
        takes = i + 1 < len(flags) and not flags[i + 1].startswith("--")
        pair = [flag, flags[i + 1]] if takes else [flag]
        for at in range(len(out) - len(pair) + 1):
            if out[at : at + len(pair)] == pair:
                del out[at : at + len(pair)]
                break
        else:
            raise AssertionError(f"{pair} is not in {words}")
        i += len(pair)
    return out


def strip_store(words: Sequence[str]) -> list[str]:
    out = list(words)
    while "--store" in out:
        at = out.index("--store")
        del out[at : at + 2]
    return [w for w in out if not w.startswith("--store=")]


# ---------- what a refusal looks like ----------

EXIT_CODES = frozenset({0, 1, 2, 3, 4, 130})
_REPR = re.compile(
    r"Traceback \(most recent call last\)|\[Errno \d+\]|<[\w.]+ object at 0x[0-9a-fA-F]+>"
    r"|\b\w+(?:Error|Exception):"
)


def plain_refusal(ran: Ran, code: int = 1) -> str:
    """The refusal's one ``error:`` sentence, after checking it is plain: the exit code given,
    nothing on stdout, one ``error:`` line then only ``next:`` lines, no traceback or Python
    text. Returns the sentence for the caller to check what it names."""
    assert ran.code == code, ran.text
    assert code in EXIT_CODES
    assert ran.out == "", ran.out
    lines = [line for line in ran.err.splitlines() if line.strip()]
    assert lines and lines[0].startswith("error: "), ran.err
    assert all(line.startswith("  next: ") for line in lines[1:]), ran.err
    assert not _REPR.search(ran.err), ran.err
    return lines[0].removeprefix("error: ")


def names(sentence: str, *things: str, tmp: Path | None = None) -> bool:
    """Whether the sentence names each thing, read after the test's own temporary folder is cut
    out of it (pytest names that folder after the test)."""
    text = sentence.replace(str(tmp), "") if tmp is not None else sentence
    return all(t in text for t in things)


# ---------- the store, read back ----------


def tree(root: Path) -> dict[str, str]:
    """Every path under ``root``: a file by its sha256, a folder as ``dir``."""
    if not root.exists():
        return {}
    out = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        out[rel] = "dir" if path.is_dir() else sha256_of(path)
    return out


def records(root: Path, run: str) -> list[dict[str, Any]]:
    """Each stored row's case, repeat, outcome, error and ``meta["trace_signals"]``, in order."""
    from poisson_prove.store import Store

    frame = Store(root).read(run, meta=True, trace="full")
    out = []
    for row in frame.to_dict(orient="records"):
        meta = row.get("meta")
        meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
        out.append({
            "outcome": row.get("outcome"),
            "error": row.get("error") if isinstance(row.get("error"), str) else None,
            "signals": meta.get("trace_signals"),
        })
    return sorted(out, key=lambda r: (r["signals"]["case"], r["signals"]["repeat"]))


def manifest(root: Path, run: str) -> dict[str, Any]:
    return json.loads((root / run / "manifest.json").read_text(encoding="utf-8"))


def import_block(root: Path, run: str) -> dict[str, Any]:
    env = manifest(root, run).get("environment", {})
    return dict(env.get("import", {}))


def csv_text(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def junit_cases(path: Path) -> list[tuple[str, str]]:
    """Each test case of a report as ``(its case, what it ended as)``: the case as the JUnit
    reader names it (``classname::name``, or its digest past 80 characters, ``rows.case_id``),
    and passed, failure, error or skipped."""
    from poisson_trace.ingest.rows import case_id

    out = []
    for case in ET.parse(path).getroot().iter("testcase"):
        ended = "passed"
        for kind in ("failure", "error", "skipped"):
            if case.find(kind) is not None:
                ended = kind
                break
        out.append((case_id(f"{case.get('classname')}::{case.get('name')}"), ended))
    return out


def file_entries(root: Path, run: str) -> list[dict[str, Any]]:
    return list(import_block(root, run).get("files", []))
