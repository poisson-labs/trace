"""The saved verdict: one artifact of the suite's format (``poisson.artifact/1``, the Artifact
Format sections 2, 3 and 5; spec section 17.3 items 1 to 5), the handover bundle ``--out``
writes beside it (section 11.2), and the check ``poisson-trace handover --check DIR`` runs over
a bundle (sections 11.2 and 11.5).

An artifact is built whole in a staging folder: ``result.json`` (the verb's JSON with the keys
section 11.3 adds), ``report.md`` (the report as the plain command prints it), ``table.parquet``
(the long-form table, the format's columns then Trace's ``step`` and ``cause``), ``where``'s
curve as ``charts/curve.svg`` with its data beside it, and ``artifact.json`` listing them all.
Saving renames the folder into the store's ``.poisson/artifacts/<kind>/<id>/`` last, after the
store descriptor is written or gains Trace as a writer, so an interrupted save leaves nothing;
an id that is there already is that artifact, and nothing is written. The id is the format's:
the first 16 hex of the SHA-256 of the canonical JSON of the kind, the tool, its major.minor
version, the inputs (the runs by id) and the result-changing settings.

Nothing saved holds an absolute path, a platform string, a key or a row's content (section
17.3 item 9): the callers hand over documents already written short, and the check refuses
what carries Prove's content or observation keys or a string past 400 characters.

This is the one module that writes with pyarrow (``table.parquet``; writing an artifact is not
reading a run, which goes through Prove alone). Standard library, pyarrow and Prove's two
key lists otherwise.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

TOOL = "poisson-trace"
STORE_FORMAT = "poisson.store/1"
ARTIFACT_FORMAT = "poisson.artifact/1"
TABLE_FORMAT = "poisson.table/1"
CHART_FORMAT = f"{TOOL}.chart/1"
HANDOVER_SCHEMA = f"{TOOL}.handover/1"
#: The settings kept in a descriptor that say how a result was asked for, and are not in its
#: id: where each setting came from, and the config's names of the stores read (SV5).
HOW_ASKED: tuple[str, ...] = ("from", "stores")
#: The kinds Trace writes, each the verb's name, and the schema its ``result.json`` carries.
SCHEMAS: dict[str, str] = {
    "where": f"{TOOL}.where/1",
    "compare": f"{TOOL}.compare/1",
    "fix-check": f"{TOOL}.fix-check/2",
    "changes": f"{TOOL}.changes/2",
}
#: Each verb's closed set of verdict words (section 11.3).
VERDICTS: dict[str, tuple[str, ...]] = {
    "where": ("ok",),
    "compare": ("different", "no significant difference", "too small to tell"),
    "fix-check": ("different", "no significant difference", "too small to tell"),
    "changes": ("ok",),
}
#: The longest string a ``result.json`` may hold (section 11.2).
LONGEST = 400
#: The table's columns: the format's nine, then Trace's ``step`` (the curves) and ``cause``.
TABLE_COLUMNS: tuple[str, ...] = (
    "artifact_id",
    "event",
    "condition",
    "condition_hash",
    "arm",
    "metric",
    "value",
    "note",
    "level",
    "step",
    "cause",
)
_STAGING = "artifact.json"


REPORT_PAGE = "report.html"
#: The elements the HTML report never holds (section 11.7).
_FORBIDDEN = frozenset({"script", "link", "iframe", "object", "embed"})
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:")


class Invalid(Exception):
    """A bundle that does not hold what it promises: the first failing line, exit 4."""


class NotABundle(Exception):
    """DIR is missing, is not a folder, or holds no ``handover.json``: a refusal, exit 1."""


# ---------- the pieces ----------


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def major_minor(text: str) -> str:
    return ".".join(text.split(".")[:2])


def trace_version() -> str:
    return version(TOOL)


def prove_version() -> str:
    import poisson_prove

    return str(poisson_prove.__version__)


def canonical(value: Any) -> str:
    """The format's canonical JSON: sorted keys, no spaces, UTF-8 as it is."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def document(value: Any) -> str:
    """A JSON file as the format writes it: two-space indent, UTF-8 as it is, one newline."""
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def condition_hash(condition: Any) -> str:
    """The 16-hex digest of a condition's canonical JSON."""
    return hashlib.sha256(canonical(condition).encode("utf-8")).hexdigest()[:16]


def artifact_id(kind: str, inputs: Mapping[str, Any], settings: Mapping[str, Any]) -> str:
    """The first 16 hex of the SHA-256 of the canonical JSON of the kind, the tool, its
    major.minor version, the inputs and the result-changing settings."""
    payload = {
        "kind": kind,
        "tool": TOOL,
        "tool_version": major_minor(trace_version()),
        "inputs": dict(inputs),
        "settings": {k: v for k, v in settings.items() if k not in HOW_ASKED},
    }
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:16]


def saved_path(kind: str, identity: str) -> str:
    """The store-relative folder of a saved artifact, as ``--json``'s ``saved`` names it."""
    return f".poisson/artifacts/{kind}/{identity}"


def short(text: str, absolute: Mapping[str, str]) -> str:
    """``text`` with each absolute path the command carried written as its last folder's or
    file's name (section 11.2's rule, taken everywhere by SV7), the longest path first."""
    for path in sorted(absolute, key=len, reverse=True):
        text = text.replace(path, absolute[path])
    return text


def shortened(value: Any, absolute: Mapping[str, str]) -> Any:
    """``value`` with every string in it written short."""
    if isinstance(value, str):
        return short(value, absolute)
    if isinstance(value, Mapping):
        return {k: shortened(v, absolute) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [shortened(v, absolute) for v in value]
    return value


# ---------- the artifact ----------


@dataclass(frozen=True)
class Row:
    """One row of the long-form table."""

    metric: str
    value: float | None
    arm: str = "both"
    condition: Any = None  # None is the whole pair, written ``{}``
    condition_hash: str | None = None
    note: str | None = None
    level: float | None = None
    step: int | None = None
    cause: str | None = None


@dataclass(frozen=True)
class Artifact:
    """What one saved verdict holds, before it is written."""

    kind: str
    runs: Sequence[str]  # the run ids, in the verb's order
    settings: Mapping[str, Any]
    result: Mapping[str, Any]
    report: str
    events: Sequence[str]
    rows: Sequence[Row] = ()
    detail: Sequence[tuple[str, str]] = ()
    # (path under charts/, the SVG text, the chart's data)
    charts: Sequence[tuple[str, str, Mapping[str, Any]]] = ()

    @property
    def inputs(self) -> dict[str, Any]:
        return {"runs": list(self.runs)}

    @property
    def id(self) -> str:
        return artifact_id(self.kind, self.inputs, self.settings)


def _write_artifact_table(path: Path, artifact: Artifact) -> None:
    """The long-form table as Parquet: the format's nine columns, then ``step`` and ``cause``."""
    schema = pa.schema(
        [
            ("artifact_id", pa.string()),
            ("event", pa.string()),
            ("condition", pa.string()),
            ("condition_hash", pa.string()),
            ("arm", pa.string()),
            ("metric", pa.string()),
            ("value", pa.float64()),
            ("note", pa.string()),
            ("level", pa.float64()),
            ("step", pa.int64()),
            ("cause", pa.string()),
        ]
    )
    event = ",".join(sorted(artifact.events))
    identity = artifact.id
    columns: dict[str, list[Any]] = {name: [] for name in TABLE_COLUMNS}
    for row in artifact.rows:
        condition = {} if row.condition is None else row.condition
        columns["artifact_id"].append(identity)
        columns["event"].append(event)
        columns["condition"].append(canonical(condition))
        columns["condition_hash"].append(
            row.condition_hash if row.condition_hash is not None else condition_hash(condition)
        )
        columns["arm"].append(row.arm)
        columns["metric"].append(row.metric)
        columns["value"].append(None if row.value is None else float(row.value))
        columns["note"].append(row.note if row.value is None else None)
        columns["level"].append(None if row.level is None else float(row.level))
        columns["step"].append(row.step)
        columns["cause"].append(row.cause)
    table = pa.table(
        {name: pa.array(columns[name], type=schema.field(name).type) for name in TABLE_COLUMNS}
    )
    pq.write_table(table, path)


def build_artifact(staging: Path, artifact: Artifact) -> str:
    """Write the artifact's files and its descriptor into ``staging`` (an empty folder) and
    return its id. The result and the report are written as given."""
    identity = artifact.id
    files: list[dict[str, Any]] = []
    (staging / "result.json").write_text(document(artifact.result), encoding="utf-8")
    files.append(
        {
            "path": "result.json",
            "role": "result",
            "media_type": "application/json",
            "schema": SCHEMAS[artifact.kind],
        }
    )
    (staging / "report.md").write_text(artifact.report, encoding="utf-8")
    files.append({"path": "report.md", "role": "report", "media_type": "text/markdown"})
    _write_artifact_table(staging / "table.parquet", artifact)
    files.append(
        {
            "path": "table.parquet",
            "role": "table",
            "media_type": "application/vnd.apache.parquet",
            "schema": TABLE_FORMAT,
        }
    )
    for name, svg, data in artifact.charts:
        path = f"charts/{name}.svg"
        data_path = f"charts/{name}.json"
        (staging / "charts").mkdir(exist_ok=True)
        (staging / path).write_text(svg, encoding="utf-8")
        (staging / data_path).write_text(
            document({"schema": CHART_FORMAT, **data}), encoding="utf-8"
        )
        files.append(
            {"path": path, "role": "chart", "media_type": "image/svg+xml", "data": data_path}
        )
        files.append(
            {
                "path": data_path,
                "role": "table",
                "media_type": "application/json",
                "schema": CHART_FORMAT,
            }
        )
    for entry in files:
        entry["sha256"] = sha256_of(staging / entry["path"])
    descriptor = {
        "format": ARTIFACT_FORMAT,
        "kind": artifact.kind,
        "id": identity,
        "tool": TOOL,
        "tool_version": trace_version(),
        "created_at": utc_now(),
        "inputs": artifact.inputs,
        "settings": dict(artifact.settings),
        "summary": {
            "verdict": artifact.result["verdict"],
            "sentence": artifact.result["sentence"],
            "detail": [[str(label), str(text)] for label, text in artifact.detail],
        },
        "files": files,
    }
    (staging / _STAGING).write_text(document(descriptor), encoding="utf-8")
    return identity


# ---------- the store ----------


def descriptor_path(root: Path) -> Path:
    return root / ".poisson" / "store.json"


def _write_descriptor_file(path: Path, doc: Any) -> None:
    """A JSON file written whole through a temporary sibling renamed in."""
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(document(doc), encoding="utf-8")
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def write_store_descriptor(root: Path) -> None:
    """The store descriptor on Trace's first write into a store, or Trace and its major.minor
    version added once to ``writers``; a descriptor that lists this version already, and every
    other key, is left exactly as it is. Raises ``OSError`` where the store cannot be written."""
    path = descriptor_path(root)
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise OSError(f"{path} is not a store descriptor")
        writers = doc.get("writers")
        if not isinstance(writers, list):
            writers = []
            doc["writers"] = writers
        mine = major_minor(trace_version())
        for writer in writers:
            if (
                isinstance(writer, Mapping)
                and writer.get("tool") == TOOL
                and major_minor(str(writer.get("version", ""))) == mine
            ):
                return
        writers.append({"tool": TOOL, "version": trace_version(), "first_write": utc_now()})
        _write_descriptor_file(path, doc)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    at = utc_now()
    _write_descriptor_file(
        path,
        {
            "format": STORE_FORMAT,
            "created_by": {"tool": TOOL, "version": trace_version()},
            "created_at": at,
            "writers": [{"tool": TOOL, "version": trace_version(), "first_write": at}],
        },
    )


def _open_to_others(folder: Path) -> None:
    """A temporary folder as the user's umask would make it, not the private one ``mkdtemp``
    makes, so a saved verdict is readable to the others who read the store."""
    mask = os.umask(0)
    os.umask(mask)
    os.chmod(folder, 0o777 & ~mask)


def save_artifact(root: Path, staging: Path, kind: str, identity: str) -> bool:
    """Save the artifact built in ``staging`` into the store at ``root``: the descriptor first,
    then a copy of the folder renamed into its place. True when it was written, False when an
    artifact of that id was there already. Raises ``OSError`` where the store cannot be written,
    leaving nothing behind."""
    write_store_descriptor(root)
    parent = root / ".poisson" / "artifacts" / kind
    folder = parent / identity
    if (folder / _STAGING).is_file():
        return False
    parent.mkdir(parents=True, exist_ok=True)
    held = Path(tempfile.mkdtemp(prefix=f".{identity}.{os.getpid()}.", dir=parent))
    try:
        _open_to_others(held)
        shutil.rmtree(held)
        shutil.copytree(staging, held)
        try:
            os.replace(held, folder)
        except OSError:
            # another process saved the same result first: that is the artifact
            if not (folder / _STAGING).is_file():
                raise
    finally:
        if held.exists():
            shutil.rmtree(held, ignore_errors=True)
    return True


# ---------- the bundle ----------


@dataclass(frozen=True)
class RunRef:
    run_id: str
    run_name: str
    store: str | None


def _listed_files(folder: Path) -> list[dict[str, Any]]:
    """Every file under the folder but ``handover.json``, by name, with its digest and size."""
    out = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        name = path.relative_to(folder).as_posix()
        if name == "handover.json":
            continue
        out.append({"name": name, "sha256": sha256_of(path), "bytes": path.stat().st_size})
    return out


def write_bundle(
    staging: Path, target: Path, verb: str, runs: Sequence[RunRef], *, force: bool
) -> None:
    """A copy of the artifact's folder at ``target`` with ``handover.json`` beside it; a folder
    there already is replaced with ``force``. Raises ``OSError`` where it cannot be written."""
    if force and target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging, target)
    doc = {
        "schema": HANDOVER_SCHEMA,
        "verb": verb,
        "files": _listed_files(target),
        "versions": {"trace": trace_version(), "prove": prove_version()},
        "written_at": utc_now(),
        "runs": [{"run_id": r.run_id, "run_name": r.run_name, "store": r.store} for r in runs],
    }
    (target / "handover.json").write_text(document(doc), encoding="utf-8")


# ---------- the check ----------


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


def _is_text_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _is_run(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("run_id"), str)
        and isinstance(value.get("run_name"), str)
    )


@dataclass(frozen=True)
class Checked:
    """What a bundle that holds what it promises held."""

    verb: str
    files: int
    runs: int
    sentence: str = field(default="")


def _check_listed(folder: Path, doc: Any) -> int:
    """Each file ``handover.json`` lists: there, of the digest and the size it gives."""
    if not isinstance(doc, Mapping) or doc.get("schema") != HANDOVER_SCHEMA:
        raise Invalid(f"handover.json does not open with the schema {HANDOVER_SCHEMA}")
    if doc.get("verb") not in SCHEMAS:
        raise Invalid("handover.json names no verb of Trace's")
    listed = doc.get("files")
    if not isinstance(listed, list) or not listed:
        raise Invalid("handover.json lists no file")
    for entry in listed:
        name = entry.get("name") if isinstance(entry, Mapping) else None
        if not isinstance(name, str) or not name:
            raise Invalid("handover.json lists a file without a name")
        path = folder / name
        if not path.is_file():
            raise Invalid(f"{name} is listed in handover.json and is not in the bundle")
        if sha256_of(path) != entry.get("sha256"):
            raise Invalid(f"{name} does not have the digest handover.json lists for it")
        if path.stat().st_size != entry.get("bytes"):
            raise Invalid(f"{name} does not have the size handover.json lists for it")
    for name in ("artifact.json", "result.json", "report.md"):
        if name not in {e["name"] for e in listed}:
            raise Invalid(f"{name} is not listed in handover.json")
    return len(listed)


def _check_descriptor(folder: Path) -> None:
    """The digests ``artifact.json`` lists."""
    try:
        desc = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Invalid("artifact.json is not JSON") from None
    files = desc.get("files") if isinstance(desc, Mapping) else None
    if not isinstance(files, list):
        raise Invalid("artifact.json lists no file")
    for entry in files:
        name = entry.get("path") if isinstance(entry, Mapping) else None
        if not isinstance(name, str) or not name:
            raise Invalid("artifact.json lists a file without a path")
        path = folder / name
        if not path.is_file():
            raise Invalid(f"{name} is listed in artifact.json and is not in the bundle")
        if sha256_of(path) != entry.get("sha256"):
            raise Invalid(f"{name} does not have the digest artifact.json lists for it")


def _check_result(folder: Path, verb: str) -> dict[str, Any]:
    """``result.json``: JSON, the verb's schema, the promised keys of the promised types, the
    verdict in the verb's set."""
    try:
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Invalid("result.json is not JSON") from None
    if not isinstance(result, Mapping):
        raise Invalid("result.json is not a JSON object")
    if next(iter(result), None) != "schema":
        raise Invalid("result.json does not open with its schema")
    if result.get("schema") != SCHEMAS[verb]:
        raise Invalid(
            f"result.json carries the schema {json.dumps(result.get('schema'))}, not the "
            f"{verb} verdict's {SCHEMAS[verb]}"
        )
    promised: list[tuple[str, Any, str]] = [
        ("verdict", lambda v: isinstance(v, str), "a verdict word"),
        ("sentence", lambda v: isinstance(v, str), "one sentence"),
        ("next", lambda v: v is None or isinstance(v, str), "a command or null"),
        ("note", _is_text_list, "a list of sentences"),
        ("cannot_say", _is_text_list, "a list of sentences"),
        (
            "versions",
            lambda v: isinstance(v, Mapping)
            and isinstance(v.get("trace"), str)
            and isinstance(v.get("prove"), str),
            "the trace and prove versions",
        ),
    ]
    head = "run" if verb == "where" else "runs"
    if head == "run":
        promised.append(("run", _is_run, "the run with its run_id and run_name"))
    else:
        promised.append(
            (
                "runs",
                lambda v: isinstance(v, Mapping)
                and bool(v)
                and all(isinstance(x, Mapping) for x in v.values()),
                "the runs by arm",
            )
        )
    for key, holds, what in promised:
        if key not in result:
            raise Invalid(f"result.json lacks the promised key {key}")
        if not holds(result[key]):
            raise Invalid(f"result.json's {key} is not {what}")
    if head == "runs":
        for arm, run in result["runs"].items():
            for key in ("run_id", "run_name"):
                if not isinstance(run.get(key), str):
                    raise Invalid(f"result.json's runs.{arm} lacks its {key}")
    if result["verdict"] not in VERDICTS[verb]:
        raise Invalid(
            f"result.json's verdict {json.dumps(result['verdict'])} is not one {verb} gives "
            f"({', '.join(VERDICTS[verb])})"
        )
    return dict(result)


def _check_report(folder: Path, result: Mapping[str, Any]) -> None:
    try:
        first = (folder / "report.md").read_text(encoding="utf-8").split("\n", 1)[0]
    except (OSError, ValueError):
        raise Invalid("report.md is not UTF-8 text") from None
    if first != f"{result['verdict']}  {result['sentence']}":
        raise Invalid("report.md's first line is not the verdict line result.json promises")


def _check_content(result: Mapping[str, Any]) -> None:
    from poisson_prove.trace import CONTENT_KEYS, OBSERVATION_KEYS

    banned = set(CONTENT_KEYS) | set(OBSERVATION_KEYS)
    for key in _keys(result):
        if key in banned:
            raise Invalid(
                f"result.json holds the key {key}, which names content Trace never hands over"
            )
    for text in _strings(result):
        if len(text) > LONGEST:
            raise Invalid(
                f"result.json holds a string of {len(text)} characters, past the {LONGEST} "
                "the handover allows"
            )


def check_bundle(target: Path) -> Checked:
    """Check the bundle at ``target`` in section 11.2's order; ``NotABundle`` when there is no
    bundle to check, ``Invalid`` with the first failing line otherwise."""
    if not target.exists():
        raise NotABundle(f"there is no folder at {target}")
    if not target.is_dir():
        raise NotABundle(f"{target} is not a folder")
    handover = target / "handover.json"
    if not handover.is_file():
        raise NotABundle(f"{target} holds no handover.json, so it is not a bundle")
    try:
        doc = json.loads(handover.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Invalid("handover.json is not JSON") from None
    files = _check_listed(target, doc)
    _check_descriptor(target)
    verb = str(doc["verb"])
    result = _check_result(target, verb)
    _check_report(target, result)
    _check_content(result)
    if (target / REPORT_PAGE).is_file():
        _check_report_page(target / REPORT_PAGE, result)
    runs = 1 if verb == "where" else len(result["runs"])
    sentence = (
        f"{target} holds what it promises: a {verb} verdict over "
        f"{'one run' if runs == 1 else f'{runs} runs'}, {files} files of the digests and sizes "
        "listed, result.json with every promised key, and nothing Trace does not hand over"
    )
    return Checked(verb=verb, files=files, runs=runs, sentence=sentence)


# ---------- the HTML report's checks (section 11.7) ----------


class _PageReader(HTMLParser):
    """What section 11.7 asks of ``report.html``: the first failing line, and the text of the
    first ``<h1>``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.failing: str | None = None
        self.h1: str | None = None
        self._in_h1 = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.failing is None and tag in _FORBIDDEN:
            self.failing = f"{REPORT_PAGE} holds a <{tag}> element"
        for name, value in attrs:
            if self.failing is None and value is not None and _SCHEME.match(value):
                self.failing = (
                    f"{REPORT_PAGE}'s <{tag}> has an attribute {name} that names a scheme"
                )
        if tag == "h1" and self.h1 is None and not self._in_h1:
            self._in_h1 = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._in_h1:
            self._in_h1 = False
            self.h1 = "".join(self._text)

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self._text.append(data)


def _check_report_page(path: Path, result: Mapping[str, Any]) -> None:
    """``report.html``, when the bundle holds one: it parses; it holds no script, link, frame,
    object or embed; no attribute names a scheme; its first heading is the verdict line
    ``result.json`` promises."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        raise Invalid(f"{REPORT_PAGE} is not UTF-8 text") from None
    reader = _PageReader()
    try:
        reader.feed(text)
        reader.close()
    except Exception:  # noqa: BLE001 - whatever the parser raises, the page is not HTML
        raise Invalid(f"{REPORT_PAGE} cannot be read as HTML") from None
    if reader.failing is not None:
        raise Invalid(reader.failing)
    if reader.h1 != f"{result['verdict']}  {result['sentence']}":
        raise Invalid(f"{REPORT_PAGE}'s first heading is not the verdict line result.json promises")
