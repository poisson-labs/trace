"""Inspect AI logs: the ``.eval`` archive, the ``.json`` log, and an unpacked ``.eval`` folder.

A ``.json`` log is one object (``version``, ``status``, ``eval``, ``samples`` among its keys),
read with the standard library. A ``.eval`` log is a zip whose members (``header.json``,
``samples/<id>_epoch_<n>.json``, ``summaries.json``, ``reductions.json``, a ``_journal/``
folder) are Zstandard-compressed, which ``zipfile`` cannot read before Python 3.14: each member
is read past its local header and decompressed with the ``zstandard`` package, the optional
extra ``poisson-trace[inspect]``, imported only when a ``.eval`` is read. An unpacked log is a
folder holding ``header.json`` beside ``samples/``. A log is read whole into memory, and one
over 200 MB is refused, naming its size, before it is read. Nothing is imported from Inspect.

A sample is one row; its case is its ``id`` as text; its epochs are its repeats in epoch order.
The outcome is the scorer's value: Inspect's letters by default (``C`` met; ``I``, ``P`` and
``N`` missed; any other value refused, the values listed), a number at a declared cut, or the
values declared to mean a failure. ``--scorer`` names the scorer when a sample holds several. A
log whose status is ``error`` is refused with its message's first line; a sample with an error
has no outcome and is censored.

The signals read of a sample: its total and working time, the lengths of its input (when it is text)
and of its output's completion, its tokens summed over every model (cached and reasoning tokens
where Inspect records them), its ``model`` events as LLM calls and its ``tool`` events as tool
calls, and every score as a number by Inspect's own reading of its letters. Its failure kind comes
from its limit, its stop reason and its tool errors. Nothing of an input, a target, a message, an
output, an event's content or a score's answer or explanation is kept, nor an error's text.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
import zipfile
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, ToolCallRecord
from poisson_trace.ingest.taxonomy import CONTEXT, RATE_LIMIT, TIMEOUT, retry_storm
from poisson_trace.look import why

DESCRIPTION = """\
Read an Inspect AI log (a .eval file, a .json file, or a .eval unpacked into a folder) and
write it as one new run. Each sample is one row; its epochs are its repeats. The outcome is the
scorer's value: Inspect's letters by default (C passed; I, P and N failed), or a number at a
cut, or the values you name as failures. A .eval file needs the zstandard package: pip install
'poisson-trace[inspect]'. A log is read whole into memory, and one over 200 MB is refused. No
input, target, message, output or explanation is kept.
"""
EXAMPLE = "poisson-trace import inspect logs/old.eval --store trace-store --run old"

TOOL = "inspect"
OUTCOMES: tuple[str, ...] = ("correct", "score", "value")
LETTERS: Mapping[str, float] = {"C": 1.0, "P": 0.5, "I": 0.0, "N": 0.0}
ERROR = "error"
NO_SCORE = "no score"
#: The largest log read, whole, into memory.
LIMIT_MB = 200
_LIMIT = LIMIT_MB * 1024 * 1024
# a zip member's method that is Zstandard, as Inspect writes it
_ZSTD = 93
ZSTD_REFUSAL = (
    "this .eval file is Zstandard-compressed; pip install 'poisson-trace[inspect]', or convert "
    "it with: inspect log convert FILE --to json"
)
# the kinds a sample's own record gives
_LIMIT_KINDS: Mapping[str, str] = {
    "time": "timeout",
    "working": "timeout",
    "token": "context_overflow",
    "cost": "context_overflow",
}
_STOP_KINDS: Mapping[str, str] = {
    "max_tokens": "context_overflow",
    "model_length": "context_overflow",
    "content_filter": "guardrail_blocked",
}
_BLOCKED = ("approval", "permission")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scorer",
        metavar="NAME",
        help="the scorer whose value is the outcome (default: the log's one scorer; required "
        "when a sample holds several)",
    )
    parser.add_argument(
        "--outcome",
        choices=OUTCOMES,
        default=OUTCOMES[0],
        metavar="correct|score|value",
        help="correct: Inspect's letters, C passed and I, P or N failed; score: a number at "
        "--cut; value: the values --failed names failed (default: correct)",
    )
    parser.add_argument(
        "--cut",
        metavar="X",
        help="with --outcome score, the score a sample must reach (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")
    parser.add_argument(
        "--failed",
        action="append",
        metavar="V",
        help="with --outcome value, a value that means a failure, repeatable (no default)",
    )


def usage(ns: argparse.Namespace) -> str | None:
    """Why the command line is still wrong, or None: each outcome form with its own flags and
    without the others'."""
    sided = ns.cut is not None or ns.below or ns.above
    if ns.outcome != "score" and sided:
        return "--cut, --below and --above read a score: give --outcome score"
    if ns.outcome != "value" and ns.failed:
        return "--failed names the values that mean a failure: give --outcome value"
    if ns.outcome == "score":
        if ns.cut is None:
            return "--outcome score needs --cut X, with --below or --above"
        if _number(ns.cut) is None:
            return f"--cut takes a number, not {ns.cut}"
        if ns.below == ns.above:
            return (
                f"--cut {ns.cut} needs exactly one side: --below if a score under it missed, "
                "--above if a score over it missed"
            )
    if ns.outcome == "value" and not ns.failed:
        return "--outcome value needs --failed V, a value that means a failure"
    return None


def _number(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# ---------- reading a log ----------


@dataclass(frozen=True)
class _Log:
    """One log: its name and digest as the summary lists it, its header and its samples."""

    path: Path
    name: str
    sha256: str
    header: Mapping[str, Any]
    samples: list[Mapping[str, Any]]


def _not_a_log(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not an Inspect log: {what}")


def _size_checked(path: Path, size: int) -> None:
    if size > _LIMIT:
        raise Refusal(
            f"{path} is {size / (1024 * 1024):,.1f} MB, and this reader reads a log whole into "
            f"memory, at most {LIMIT_MB} MB; convert it to .json with inspect log convert and "
            "split its samples, or import fewer of them"
        )


def _load(path: Path) -> _Log:
    try:
        folder = path.is_dir()
    except (OSError, ValueError):
        folder = False
    if folder:
        return _unpacked(path)
    lowered = path.name.lower()
    if not lowered.endswith((".eval", ".json")):
        raise Refusal(
            f"{path} is not an Inspect log this reader reads: it reads a .eval file, a .json "
            "file, or a .eval unpacked into a folder"
        )
    try:
        _size_checked(path, path.stat().st_size)
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    digest = hashlib.sha256(raw).hexdigest()
    if lowered.endswith(".eval"):
        header, samples = _archive(path, raw)
    else:
        header, samples = _json_log(path, raw)
    return _Log(path, path.name, digest, header, samples)


def _decoded(path: Path, raw: bytes, what: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Refusal(f"{path} is damaged: {what} is not JSON that can be read") from None


def _json_log(path: Path, raw: bytes) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    if not raw.strip():
        raise _not_a_log(path, "it is empty")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _not_a_log(path, "it is not JSON that can be read") from None
    if not isinstance(doc, Mapping) or not isinstance(doc.get("eval"), Mapping):
        raise _not_a_log(path, "it is not an object with an eval block")
    samples = doc.get("samples")
    if samples is None:
        samples = []
    if not isinstance(samples, list):
        raise _not_a_log(path, "its samples are not a list")
    return doc, samples


def _member(raw: bytes, info: zipfile.ZipInfo) -> bytes:
    """A member's stored bytes, read past its local header."""
    at = info.header_offset
    if raw[at : at + 4] != b"PK\x03\x04":
        raise ValueError("no local header")
    n, m = struct.unpack("<HH", raw[at + 26 : at + 30])
    start = at + 30 + n + m
    return raw[start : start + info.compress_size]


def _archive(path: Path, raw: bytes) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    """The header and the samples of a ``.eval`` archive, each member decompressed."""
    if not raw:
        raise _not_a_log(path, "it is empty")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        raise _not_a_log(path, "it is not a zip archive, as a .eval log is") from None
    wanted = {
        i.filename: i
        for i in infos
        if i.filename == "header.json"
        or (i.filename.startswith("samples/") and i.filename.endswith(".json"))
    }
    if "header.json" not in wanted:
        raise _not_a_log(path, "it holds no header.json")
    decompress = None
    if any(i.compress_type == _ZSTD for i in wanted.values()):
        try:
            import zstandard
        except ImportError:
            raise Refusal(ZSTD_REFUSAL) from None
        decompress = zstandard.ZstdDecompressor()
    members: dict[str, Any] = {}
    for name in sorted(wanted, key=_member_order):
        info = wanted[name]
        try:
            if info.compress_type == _ZSTD:
                assert decompress is not None
                data = decompress.decompressobj().decompress(_member(raw, info))
            elif info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                data = archive.read(info)
            else:
                raise Refusal(
                    f"{path} is damaged: its member {name} is compressed in a way this reader "
                    "does not take"
                )
        except Refusal:
            raise
        except Exception:
            raise Refusal(f"{path} is damaged: its member {name} cannot be read") from None
        if zlib.crc32(data) != info.CRC:
            raise Refusal(f"{path} is damaged: its member {name} does not match its checksum")
        members[name] = _decoded(path, data, f"its member {name}")
    header = members.pop("header.json")
    if not isinstance(header, Mapping) or not isinstance(header.get("eval"), Mapping):
        raise _not_a_log(path, "its header.json has no eval block")
    return header, [members[name] for name in members]


def _member_order(name: str) -> tuple[int, str]:
    return (0 if name == "header.json" else 1, name)


def _unpacked(folder: Path) -> _Log:
    """An unpacked ``.eval``: ``header.json`` and ``samples/*.json``, read as plain JSON. Its
    digest is the SHA-256 of the files' ``sha256  path`` lines, in the order of their paths."""
    files = [folder / "header.json"]
    try:
        files += sorted(
            (p for p in (folder / "samples").iterdir() if p.name.endswith(".json") and p.is_file()),
            key=lambda p: p.name,
        )
        _size_checked(folder, sum(p.stat().st_size for p in files))
        held = {p: p.read_bytes() for p in files}
    except OSError as e:
        raise Refusal(f"{folder} could not be read: {why(e)}") from e
    lines = []
    for p in files:
        lines.append(f"{hashlib.sha256(held[p]).hexdigest()}  {p.relative_to(folder).as_posix()}\n")
    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    header = _decoded(folder, held[files[0]], "its header.json")
    if not isinstance(header, Mapping) or not isinstance(header.get("eval"), Mapping):
        raise _not_a_log(folder, "its header.json has no eval block")
    samples = [
        _decoded(folder, held[p], f"its sample {p.relative_to(folder).as_posix()}")
        for p in files[1:]
    ]
    return _Log(folder, f"{folder.name}/", digest, header, samples)


# ---------- the samples ----------


def _first_line(text: Any) -> str:
    lines = text.splitlines() if isinstance(text, str) else []
    return lines[0].strip() if lines and lines[0].strip() else "no message"


def _checked_status(log: _Log) -> None:
    if log.header.get("status") == "error":
        error = log.header.get("error")
        message = error.get("message") if isinstance(error, Mapping) else None
        raise Refusal(
            f"{log.path} is an Inspect log that stopped with an error, so its samples are not a "
            f"whole run: {_first_line(message)}"
        )


def _sample(path: Path, held: Any) -> Mapping[str, Any]:
    if not isinstance(held, Mapping):
        raise _not_a_log(path, "a sample in it is not an object")
    sid = held.get("id")
    if isinstance(sid, bool) or not isinstance(sid, (str, int)) or sid == "":
        raise _not_a_log(path, "a sample in it has no id")
    epoch = held.get("epoch", 1)
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise _not_a_log(path, f"the sample {sid} has no epoch numbered from 1")
    return held


def _scores(sample: Mapping[str, Any]) -> Mapping[str, Any]:
    scores = sample.get("scores")
    return scores if isinstance(scores, Mapping) else {}


def _value(score: Any) -> Any:
    return score.get("value") if isinstance(score, Mapping) else None


def _as_number(value: Any) -> float | None:
    """A score's value as a number: a number as it is, a letter by Inspect's own reading."""
    if isinstance(value, str):
        return LETTERS.get(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _shown(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _scorer(given: str | None, samples: Sequence[Mapping[str, Any]], where: str) -> str | None:
    held = list(dict.fromkeys(str(k) for s in samples for k in _scores(s)))
    if given is not None:
        if given not in held:
            listed = ", ".join(held) if held else "none"
            raise Refusal(f"{where} holds no scorer {given}; its scorers are {listed}")
        return given
    if len(held) > 1:
        raise Refusal(
            f"{where} holds {len(held)} scorers, {', '.join(held)}: name the one whose value is "
            "the outcome with --scorer"
        )
    return held[0] if held else None


@dataclass(frozen=True)
class _Reading:
    scorer: str | None
    form: str
    cut: Cut | None
    failed: tuple[str, ...]


def _outcome(path: Path, reading: _Reading, value: Any, values: Sequence[Any]) -> str:
    scorer = reading.scorer
    if reading.form == "correct":
        if not isinstance(value, str) or value not in LETTERS:
            listed = ", ".join(_shown(v) for v in dict.fromkeys(values))
            raise Refusal(
                f"{path}'s {scorer} scorer gives {_shown(value)}, which --outcome correct does "
                f"not read: it reads Inspect's letters C (passed), I, P and N (failed); the "
                f"values here are {listed}, so give --outcome value --failed V or --outcome score"
            )
        return MET if value == "C" else MISSED
    if reading.form == "score":
        assert reading.cut is not None
        number = _seconds_or_score(value)
        if number is None:
            raise Refusal(
                f"{path}'s {scorer} scorer gives {_shown(value)}, not a number, so --outcome "
                "score cannot read it; give --outcome correct for Inspect's letters"
            )
        return reading.cut.outcome(number)
    text = value if isinstance(value, str) else _shown(value)
    return MISSED if text in reading.failed else MET


def _seconds_or_score(value: Any) -> float | None:
    """A finite number as a float; None for anything else, a boolean included."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _tool_calls(events: Any) -> tuple[ToolCallRecord, ...] | None:
    """The ``tool`` events as tool calls, in order: their function's name, whether they
    errored and the error's type, and their working time. None when the sample keeps no
    events; an empty list when it keeps events and none is a tool's."""
    if not isinstance(events, list):
        return None
    calls = []
    for event in events:
        if not isinstance(event, Mapping) or event.get("event") != "tool":
            continue
        name = event.get("function")
        error = event.get("error")
        kind = error.get("type") if isinstance(error, Mapping) else None
        working = event.get("working_time")
        duration = (
            float(working)
            if not isinstance(working, bool)
            and isinstance(working, (int, float))
            and math.isfinite(working)
            and working >= 0
            else None
        )
        calls.append(
            ToolCallRecord(
                name=name if isinstance(name, str) and name else "tool",
                status="error" if error is not None else "ok",
                duration_s=duration,
                error_type=kind if isinstance(kind, str) else None,
            )
        )
    return tuple(calls)


def _sum(usage: Sequence[Mapping[str, Any]], key: str) -> int | None:
    held = [
        u[key]
        for u in usage
        if not isinstance(u.get(key), bool) and isinstance(u.get(key), int) and u[key] >= 0
    ]
    return sum(held) if held else None


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _signals(sample: Mapping[str, Any], scorer: str | None) -> dict[str, Any]:
    held = sample.get("model_usage")
    models = held.values() if isinstance(held, Mapping) else ()
    usage = [u for u in models if isinstance(u, Mapping)]
    events = sample.get("events")
    given = sample.get("input")
    output = sample.get("output")
    completion = output.get("completion") if isinstance(output, Mapping) else None
    scores = {
        str(name): number
        for name, score in _scores(sample).items()
        if (number := _as_number(_value(score))) is not None
    }
    return {
        "wall_time_s": _seconds(sample.get("total_time")),
        "working_time_s": _seconds(sample.get("working_time")),
        "input_chars": len(given) if isinstance(given, str) else None,
        "output_chars": len(completion) if isinstance(completion, str) else None,
        "input_tokens": _sum(usage, "input_tokens"),
        "output_tokens": _sum(usage, "output_tokens"),
        "total_tokens": _sum(usage, "total_tokens"),
        "cached_tokens": _sum(usage, "input_tokens_cache_read"),
        "reasoning_tokens": _sum(usage, "reasoning_tokens"),
        "llm_calls": (
            sum(1 for e in events if isinstance(e, Mapping) and e.get("event") == "model")
            if isinstance(events, list)
            else None
        ),
        "tool_calls": _tool_calls(events),
        "scores": scores,
        "score": None if scorer is None else scores.get(scorer),
    }


def _stop_reason(sample: Mapping[str, Any]) -> str | None:
    output = sample.get("output")
    choices = output.get("choices") if isinstance(output, Mapping) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    reason = first.get("stop_reason") if isinstance(first, Mapping) else None
    return reason if isinstance(reason, str) else None


def _error_kind(text: str) -> str:
    """An errored sample's kind, from its error's text: a timeout, a rate limit or a context
    overflow where the text says so, else a crash. The text is kept nowhere."""
    for pattern, kind in (
        (TIMEOUT, "timeout"),
        (RATE_LIMIT, "rate_limit"),
        (CONTEXT, "context_overflow"),
    ):
        if pattern.search(text):
            return kind
    return "crash"


def _failed_kind(sample: Mapping[str, Any], row: Row) -> str | None:
    """A failed sample's kind from its own record, in precedence order: its limit, its stop reason,
    its tool errors' types. None where the record names none, which the rules then read (a tool
    error, or a wrong answer)."""
    limit = sample.get("limit")
    limited = limit.get("type") if isinstance(limit, Mapping) else None
    stop = _stop_reason(sample)
    tool_errors = [c.error_type for c in row.tool_calls or () if c.status == "error"]
    if _LIMIT_KINDS.get(str(limited)) == "timeout" or "timeout" in tool_errors:
        return "timeout"
    if (
        _LIMIT_KINDS.get(str(limited)) == "context_overflow"
        or _STOP_KINDS.get(str(stop)) == "context_overflow"
    ):
        return "context_overflow"
    if limited == "message":
        return "loop_detected" if retry_storm(row) else "step_limit"
    if stop == "content_filter" or any(t in _BLOCKED for t in tool_errors):
        return "guardrail_blocked"
    return None


def _row(path: Path, sample: Mapping[str, Any], reading: _Reading, values: Sequence[Any]) -> Row:
    case = str(sample["id"])
    signals = _signals(sample, reading.scorer)
    detail = {"epoch": sample.get("epoch", 1)}
    error = sample.get("error")
    if error is not None:
        message = error.get("message") if isinstance(error, Mapping) else error
        return Row(
            case,
            None,
            ERROR,
            detail=detail,
            result="censored",
            failure_kind=_error_kind(message if isinstance(message, str) else ""),
            **signals,
        )
    score = _scores(sample).get(reading.scorer) if reading.scorer is not None else None
    if score is None:
        return Row(case, None, NO_SCORE, detail=detail, result="censored", **signals)
    outcome = _outcome(path, reading, _value(score), values)
    if outcome == MET:
        return Row(case, MET, None, detail=detail, result="pass", **signals)
    row = Row(
        case, MISSED, None, detail=detail, result="fail", error_span_kind="grader", **signals
    )
    kind = _failed_kind(sample, row)
    return row if kind is None else replace(row, failure_kind=kind)


def _created(path: Path, header: Mapping[str, Any]) -> str | None:
    stamp = header["eval"].get("created")
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        raise Refusal(f'{path} holds an eval.created that is not a time: "{stamp}"') from None
    if at.tzinfo is None or at.utcoffset() is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC).replace(tzinfo=None).isoformat() + "Z"


def _file_time(path: Path) -> str:
    try:
        modified = path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    return datetime.fromtimestamp(modified, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(ns: argparse.Namespace) -> Run:
    logs = [_load(Path(f)) for f in ns.files]
    for log in logs:
        _checked_status(log)
    where = ", ".join(str(log.path) for log in logs)
    held = [(log, _sample(log.path, s)) for log in logs for s in log.samples]
    form = str(getattr(ns, "outcome", "correct"))
    cut = None
    if form == "score":
        value = _number(ns.cut)
        assert value is not None
        cut = Cut(value, "below" if ns.below else "above")
    scorer = _scorer(getattr(ns, "scorer", None), [s for _, s in held], where)
    failed = tuple(dict.fromkeys(getattr(ns, "failed", None) or ()))
    reading = _Reading(scorer, form, cut, failed)
    values = [
        _value(_scores(s)[scorer]) for _, s in held if scorer is not None and scorer in _scores(s)
    ]
    # a sample's epochs are its repeats in epoch order, whatever the order written
    ordered = sorted(held, key=lambda pair: int(pair[1].get("epoch", 1)))
    rows = [_row(log.path, s, reading, values) for log, s in ordered]
    starts = [s for log in logs if (s := _created(log.path, log.header)) is not None]
    if starts:
        started, started_from = min(starts), "file"
    else:
        started, started_from = _file_time(logs[0].path), "file time"
    first = logs[0].header["eval"]
    declared: dict[str, Any] = {"scorer": scorer, "outcome": form}
    if cut is not None:
        declared.update({"cut": cut.cut, "side": cut.side})
    if failed:
        declared["failed"] = list(failed)
    for key in ("model", "task"):
        if isinstance(first.get(key), str):
            declared[key] = first[key]
    epochs = max((int(s.get("epoch", 1)) for _, s in held), default=0)
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared=declared,
        files=tuple({"name": log.name, "sha256": log.sha256} for log in logs),
        counts={
            "samples": len({str(s["id"]) for _, s in held}),
            "epochs": epochs,
            "samples that errored": sum(1 for _, s in held if s.get("error") is not None),
        },
    )


# ---------- for init ----------


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is an Inspect log, else None; it never raises. A
    ``.eval`` zip holding ``header.json`` and samples (its names are read, not its members), or
    a ``.json`` object with Inspect's ``version``, ``status`` and ``eval`` block."""
    try:
        found = Path(path)
        name = found.name.lower()
        if not name.endswith((".eval", ".json")) or not found.is_file():
            return None
        if name.endswith(".eval"):
            with zipfile.ZipFile(found) as archive:
                names = archive.namelist()
            samples = [n for n in names if n.startswith("samples/") and n.endswith(".json")]
            if "header.json" not in names:
                return None
            return f"an Inspect .eval log, {len(samples)} samples"
        doc = json.loads(found.read_bytes().decode("utf-8"))
        if not isinstance(doc, Mapping):
            return None
        block = doc.get("eval")
        if not (
            isinstance(block, Mapping)
            and isinstance(block.get("task"), str)
            and "version" in doc
            and "status" in doc
        ):
            return None
        listed = doc.get("samples")
        held = len(listed) if isinstance(listed, list) else 0
        return f"an Inspect .json log of the task {block['task']}, {held} samples"
    except Exception:
        return None
