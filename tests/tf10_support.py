"""Shared helpers for TF10's tests: the promptfoo, Inspect and OpenAI Evals readers. Not collected.

What the build provides, in one place (each test file's docstring says which invariant it holds):

``poisson_trace.ingest.promptfoo``, ``poisson_trace.ingest.inspect``, ``poisson_trace.ingest.openai_evals``
    Three reader modules of the shape ``ingest/cli.py`` documents (``add_arguments``, ``read``,
    ``DESCRIPTION``, ``EXAMPLE``, ``usage``), each with ``looks_like(path) -> str | None``. The
    tools are named ``promptfoo``, ``inspect`` and ``openai-evals`` on the command line; the
    third's module is ``openai_evals`` (a module name cannot hold a hyphen), so the import maps
    the tool's name to its module by turning ``-`` into ``_``. They import nothing from
    the tools themselves, and nothing from ``poisson_prove`` (the writer is the one module under
    ``ingest/`` that does, IC8).
``pyproject.toml``
    The optional extra ``inspect`` holding ``zstandard``, and ``zstandard`` among the ``dev``
    extra's packages so the suite reads the ``.eval`` fixture.
``docs/integrations/{promptfoo,inspect,openai-evals}.md`` and ``docs/recipes/from-{promptfoo,inspect,openai-evals}.md``
    The three pages and the three recipes.

The readings these tests hold:

promptfoo
    The ``.json`` file (``results.results`` a list) and the ``.jsonl`` file (one result per line)
    are this reader's, told by the extension. The ``.csv`` is refused, naming the JSON export
    (``promptfoo eval -o results.json``): the table reader refuses it too, since it repeats its
    column names. One import is one prompt and one provider: ``--prompt`` names the prompt
    by its label or by its number counting from 1 (``promptIdx`` + 1), ``--provider`` by its id;
    neither is needed when the file holds one; several and none named is refused with the labels
    (or ids) listed; a label or number the file does not hold is refused the same way. The
    label is printed and recorded in ``declared`` even when promptfoo made it from the prompt's
    own text. ``--case var:NAME`` takes the test variable ``NAME`` (text as written,
    through ``case_id``); ``--case test`` takes ``test:<testIdx>``. ``--outcome success`` (the
    default): ``success`` true met, false missed; ``--outcome score --cut X --below|--above``:
    the row's ``score`` at the cut, a score equal to the cut meeting it. A row whose
    ``failureReason`` is 2 has no outcome (its reason word ``error``) and is censored; its error
    text is stored and printed nowhere, but its kind comes from it: timed out
    or ETIMEDOUT a timeout, 429 or rate limit a rate limit, context_length or max_tokens a
    context overflow, else a crash. A row whose ``failureReason`` is 1 takes its kind from the
    first failed ``gradingResult.componentResults[].assertion.type``: ``is-json``, ``is-xml``,
    ``is-sql``, ``is-valid-function-call`` and ``regex`` a format error; ``is-refusal``
    abstained; ``guardrails`` and ``moderation`` guardrail blocked; ``function-call`` a tool
    error; ``context-recall`` and ``context-relevance`` a retrieval error; any other a wrong
    answer. The start is ``results.timestamp`` (from ``file``) in the JSON file; the JSON Lines
    file has none, so it is ``--started`` or the file time. The signals: ``latencyMs`` / 1000 the
    wall time; the lengths of ``prompt.raw`` and ``response.output``; ``response.tokenUsage``'s
    ``prompt``, ``completion`` and ``total`` the input, output and total tokens, its ``cached``
    and ``completionDetails.reasoning`` the cached and reasoning tokens where present (the
    fixture's provider records neither, so they are not recorded, while its zeros are recorded
    zeros); ``response.cost`` the cost; ``score`` the score and the row's ``namedScores`` the
    scores. ``numRequests`` is not read (it mixes turns and retries). Nothing else is recorded.
inspect
    A ``.json`` log is read with the standard library; a ``.eval`` log with ``zipfile`` and the
    ``zstandard`` package, without which it is refused in one line. A log over 200 MB
    is refused naming its size, before it is read. A sample is a row; its case is its ``id`` as
    text; its epochs are its repeats in epoch order. ``--outcome correct`` (the default) reads
    the scorer's letters, ``C`` met and ``I``, ``P`` and ``N`` missed, any other value refused
    with the values listed; ``--outcome score --cut X --below|--above`` a number at the cut;
    ``--outcome value --failed V ...`` the values that mean failure. ``--scorer`` is required,
    with the scorers listed, when a sample holds more than one score; a scorer no sample holds
    is refused the same way. Each score is also kept as a number by Inspect's own reading of
    its letters (``C`` 1.0, ``P`` 0.5, ``I`` and ``N`` 0.0), the read scorer's as the score. A
    log whose ``status`` is ``error`` is refused with its ``error.message``'s first line; a
    sample with ``error`` set has no outcome (its reason word ``error``) and is censored, a
    crash unless its text says a timeout, a rate limit or a context overflow; the text is kept
    nowhere. A sample's ``limit.type`` ``time`` or ``working`` is a timeout, ``token`` or
    ``cost`` a context overflow, ``message`` a step limit; its ``output.choices[0].stop_reason``
    ``max_tokens`` or ``model_length`` a context overflow and ``content_filter`` guardrail
    blocked; a ``tool`` event with an ``error`` a tool error, a timeout when the error's
    ``type`` is ``timeout``, guardrail blocked when it is ``approval`` or ``permission``. The
    start is ``eval.created``; ``eval.model``, ``eval.task`` and the scorer read go into
    ``declared``. The signals: ``total_time`` and ``working_time``; the length of ``input`` when
    it is text, and of ``output.completion``; ``model_usage`` summed over the models
    (``input_tokens``, ``output_tokens``, ``total_tokens``, and ``input_tokens_cache_read`` and
    ``reasoning_tokens`` where present); the ``model`` events counted as LLM calls; the ``tool``
    events as tool calls (none recorded is an empty list, not a missing one). No cost (Inspect
    keeps none). Nothing else is recorded.
openai-evals
    A JSON Lines record: a ``spec`` line, a ``final_report`` line, then events. A ``match``
    event is a row, ``data.correct`` false missed and true met, its case ``sample_id``; the
    ``match`` events of one ``sample_id`` are its repeats in ``event_id`` order; every other
    event type is counted by type and is not a row. A record with no ``spec`` line or no
    ``match`` event is refused, and so is a line that is not JSON or a ``match`` event whose
    ``data.correct`` is not true or false, each naming the file and the line. The start is
    ``spec.created_at``, read as UTC when it carries no zone, which the summary says;
    ``spec.eval_name`` and ``spec.completion_fns`` go into ``declared``. The signals: the length
    of a ``match`` event's ``data.sampled`` when it is text (the fixture writes no ``sampling``
    event), ``data.score`` as the score where present; nothing else. A missed row is a wrong
    answer, or abstained when ``data.sampled`` is empty.

Every row of the three is classified by TF21's one rule set: the kind each test expects is the
one ``ref_kind`` (``tf21_support``) gives the row as the reader records it, or, where a reading
above names a kind the row's fields do not lead the rules to, that kind as the source's own
No prompt, answer, expected or sampled text, no variable but the case, no error
text and no grader's reason is written or printed.
"""

from __future__ import annotations

import copy
import io
import json
import shutil
import struct
import zipfile
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tf21_support import INGEST, Result, records, run_import

PROMPTFOO = INGEST / "promptfoo"
INSPECT = INGEST / "inspect"
OPENAI = INGEST / "openai-evals"
PF_JSON = PROMPTFOO / "results.json"
PF_JSONL = PROMPTFOO / "results.jsonl"
PF_CSV = PROMPTFOO / "results.csv"
IN_EVAL = INSPECT / "2026-10-07T04-23-47-00-00_trace-fixture_CV3jq8f7FTjwkaYb3zj3m2.eval"
IN_JSON = INSPECT / "2026-10-07T04-23-51-00-00_trace-fixture_2nSEDuHHzKiTUjJW3kXknY.json"
OE_OLD = OPENAI / "old.jsonl"
OE_NEW = OPENAI / "new.jsonl"

# the tools as the command line names them, and the module each reader is
TOOLS: dict[str, str] = {"promptfoo": "promptfoo", "inspect": "inspect", "openai-evals": "openai_evals"}
# every reader, in the order the import's READERS names them
PRESENT = ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals")
STARTED = "2026-10-07T04:00:00Z"
PF_LABELS = ("old: {{text}}", "new: {{text}} with the word banana")
ZSTD_REFUSAL = (
    "error: this .eval file is Zstandard-compressed; pip install 'poisson-trace[inspect]', or "
    "convert it with: inspect log convert FILE --to json"
)
# the record's keys that none of the three sources records
NEVER = ("ttft_s", "steps", "horizon", "retries")


def module(tool: str) -> Any:
    from importlib import import_module

    return import_module(f"poisson_trace.ingest.{TOOLS.get(tool, tool)}")


def looks_like(tool: str, path: Path) -> Any:
    return module(tool).looks_like(path)


# ---------- argv ----------


def pf_argv(files: Sequence[Path | str] | Path | str, root: Path, run: str, *extra: Any,
            prompt: str | None = "1", case: str | None = "var:case") -> list[str]:
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    argv = ["promptfoo", *[str(p) for p in paths], "--store", str(root), "--run", run]
    if prompt is not None:
        argv += ["--prompt", prompt]
    if case is not None:
        argv += ["--case", case]
    return [*argv, *[str(e) for e in extra]]


def in_argv(files: Sequence[Path | str] | Path | str, root: Path, run: str, *extra: Any) -> list[str]:
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    return ["inspect", *[str(p) for p in paths], "--store", str(root), "--run", run, *[str(e) for e in extra]]


def oe_argv(files: Sequence[Path | str] | Path | str, root: Path, run: str, *extra: Any) -> list[str]:
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    return ["openai-evals", *[str(p) for p in paths], "--store", str(root), "--run", run, *[str(e) for e in extra]]


def imported(argv: Sequence[Any]) -> dict[str, Any]:
    """The import's ``--json`` summary of a run that was written."""
    result = run_import([*argv, "--json"])
    assert result.code == 0, result.out + result.err
    data: dict[str, Any] = json.loads(result.out)
    assert data["schema"] == "poisson-trace.import/1" and data["verdict"] == "ok", data
    return data


def refused(result: Result) -> str:
    """Exit 1, nothing on stdout, one ``error:`` line with only ``  next:`` lines under it."""
    assert result.code == 1 and result.out == "", result.out + result.err
    lines = result.err.splitlines()
    assert lines and lines[0].startswith("error: "), result.err
    assert all(line.startswith("  next: ") for line in lines[1:]), result.err
    return lines[0]


def wrong_line(result: Result) -> str:
    """Exit 2, nothing on stdout, an ``error:`` line."""
    assert result.code == 2 and result.out == "", result.out + result.err
    lines = [line for line in result.err.splitlines() if line.startswith("error: ")]
    assert lines, result.err
    return lines[0]


def recs(root: Path, run: str) -> list[dict[str, Any]]:
    return records(root, run)


class _AsRow:
    """A stored record read as ``ref_kind`` reads a row (it takes attributes)."""

    def __init__(self, rec: Mapping[str, Any], error: str | None) -> None:
        self.__dict__.update({k: v for k, v in rec.items() if k != "outcome"})
        self.result = rec["outcome"]
        self.error = error
        self.signals = tuple(rec["signals"])
        self.scores = rec["scores"]
        calls = rec.get("tool_calls")
        self.tool_calls = None if calls is None else tuple(_Call(c) for c in calls)


class _Call:
    def __init__(self, call: Mapping[str, Any]) -> None:
        self.__dict__.update(call)


def ref_kind_of(rec: Mapping[str, Any], error: str | None = None) -> str | None:
    """The kind TF21's reference gives a stored record (``tf21_support.ref_kind``)."""
    from tf21_support import ref_kind

    return ref_kind(_AsRow(rec, error))


def stored_bytes(root: Path) -> bytes:
    """Every file of the store, and every Parquet part decoded cell by cell."""
    import pyarrow.parquet as pq

    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out.append(path.read_bytes())
        if path.suffix == ".parquet":
            out.append(json.dumps(pq.read_table(path).to_pylist(), default=str).encode("utf-8"))
    return b"\n".join(out)


# ---------- promptfoo files, read and edited ----------


def pf_doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PF_JSON.read_text(encoding="utf-8"))
    return doc


def pf_lines() -> list[dict[str, Any]]:
    return [json.loads(line) for line in PF_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]


def pf_results(doc: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = list((doc or pf_doc())["results"]["results"])
    return out


def write_pf(path: Path, edit: Callable[[dict[str, Any]], None]) -> Path:
    """The committed JSON file with ``edit`` applied to a deep copy of it."""
    doc = copy.deepcopy(pf_doc())
    edit(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def write_pf_lines(path: Path, edit: Callable[[list[dict[str, Any]]], None]) -> Path:
    rows = copy.deepcopy(pf_lines())
    edit(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def pf_row(doc: Mapping[str, Any], prompt_idx: int, test_idx: int) -> dict[str, Any]:
    return next(r for r in doc["results"]["results"] if r["promptIdx"] == prompt_idx and r["testIdx"] == test_idx)


def pf_as_error(row: dict[str, Any], text: str) -> None:
    """One result turned into an error row as promptfoo writes one: ``failureReason`` 2 and the
    error's text where promptfoo puts it."""
    row["failureReason"] = 2
    row["success"] = False
    row["score"] = 0
    row["error"] = text
    row["response"] = {"error": text}
    row["gradingResult"] = None


def pf_assertion(row: dict[str, Any], kind: str) -> None:
    """One failed result's one assertion given another type."""
    row["testCase"]["assert"][0]["type"] = kind
    row["gradingResult"]["componentResults"][0]["assertion"]["type"] = kind


# ---------- Inspect logs, read and edited ----------


def _member_bytes(archive: Path, info: zipfile.ZipInfo) -> bytes:
    """A member's stored bytes, read past its local header: ``zipfile`` cannot open them."""
    with open(archive, "rb") as f:
        f.seek(info.header_offset)
        head = f.read(30)
        n, m = struct.unpack("<HH", head[26:30])
        f.seek(info.header_offset + 30 + n + m)
        return f.read(info.compress_size)


def eval_members(archive: Path = IN_EVAL) -> dict[str, Any]:
    """Every JSON member of a ``.eval`` archive, decompressed with ``zstandard``, by name."""
    import zstandard

    out: dict[str, Any] = {}
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            raw = zstandard.ZstdDecompressor().decompressobj().decompress(_member_bytes(archive, info))
            out[info.filename] = json.loads(raw.decode("utf-8"))
    return out


def eval_samples(archive: Path = IN_EVAL) -> list[dict[str, Any]]:
    members = eval_members(archive)
    return [members[name] for name in sorted(members) if name.startswith("samples/")]


def in_doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(IN_JSON.read_text(encoding="utf-8"))
    return doc


def write_in(path: Path, edit: Callable[[dict[str, Any]], None]) -> Path:
    """The committed ``.json`` log with ``edit`` applied to a deep copy of it."""
    doc = copy.deepcopy(in_doc())
    edit(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def write_eval(path: Path, edit: Callable[[dict[str, Any]], None] | None = None,
               members: Callable[[dict[str, bytes]], None] | None = None) -> Path:
    """The committed ``.eval`` archive rewritten member by member, each Zstandard-compressed as
    Inspect writes them (compress type 93), with ``edit`` applied to its decoded members first."""
    import zstandard

    decoded = eval_members()
    if edit is not None:
        edit(decoded)
    raw = {name: json.dumps(value).encode("utf-8") for name, value in decoded.items()}
    if members is not None:
        members(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in raw.items():
            packed = zstandard.ZstdCompressor().compress(data)
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 7, 4, 23, 47))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, packed)
    blob = bytearray(buf.getvalue())
    _set_method(blob, 93, {name: (len(data), zlib.crc32(data)) for name, data in raw.items()})
    path.write_bytes(bytes(blob))
    return path


def _set_method(blob: bytearray, method: int, sizes: Mapping[str, tuple[int, int]]) -> None:
    """Mark every entry's compression method, and its uncompressed size and CRC, in the local
    headers and the central directory, so the archive reads as Inspect's does."""
    at = 0
    while True:
        i = blob.find(b"PK\x03\x04", at)
        if i < 0:
            break
        n, m = struct.unpack("<HH", blob[i + 26:i + 30])
        name = blob[i + 30:i + 30 + n].decode()
        struct.pack_into("<H", blob, i + 8, method)
        struct.pack_into("<I", blob, i + 14, sizes[name][1])
        struct.pack_into("<I", blob, i + 22, sizes[name][0])
        at = i + 30 + n + m
    at = 0
    while True:
        i = blob.find(b"PK\x01\x02", at)
        if i < 0:
            break
        n, m, k = struct.unpack("<HHH", blob[i + 28:i + 34])
        name = blob[i + 46:i + 46 + n].decode()
        struct.pack_into("<H", blob, i + 10, method)
        struct.pack_into("<I", blob, i + 16, sizes[name][1])
        struct.pack_into("<I", blob, i + 24, sizes[name][0])
        at = i + 46 + n + m + k


def sample_of(doc: Mapping[str, Any], sid: str, epoch: int) -> dict[str, Any]:
    return next(s for s in doc["samples"] if s["id"] == sid and s["epoch"] == epoch)


def letter_float(value: Any) -> float:
    """Inspect's own reading of its letters as numbers."""
    return {"C": 1.0, "P": 0.5, "I": 0.0, "N": 0.0}[value]


# ---------- OpenAI Evals records, read and edited ----------


def oe_lines(path: Path = OE_OLD) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_oe(path: Path, edit: Callable[[list[dict[str, Any]]], None], source: Path = OE_OLD) -> Path:
    lines = copy.deepcopy(oe_lines(source))
    edit(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


def match_events(lines: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [line for line in lines if line.get("type") == "match"]


def copy_fixture(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest
