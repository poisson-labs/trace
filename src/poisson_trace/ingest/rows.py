"""What a reader hands the writer: one row per case read, and the run they make.

A ``Row`` keeps today's six positional fields (``case``, ``outcome``, ``error``, ``score``,
``spans``, ``detail``) and adds the normalised signals of spec section 18.4.1 as keyword-only
fields after them. ``outcome`` stays the word written to Prove's outcome column; the normalised
verdict is ``result`` (``pass``, ``fail``, ``censored`` or ``None`` for an unscored row). A
signal left ``None`` was not recorded by the source; ``0`` is a recorded zero. An error is cut to
240 characters, and no field holds a prompt, a completion or a tool's arguments.

Standard library only.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import KW_ONLY, dataclass, field
from typing import Any

# where a run's start was read: given on the command line, the time in the first file's name,
# the earliest span's, the first file's modification time, or a time the tool wrote in the file
STARTED_FROM: tuple[str, ...] = ("given", "file name", "earliest span", "file time", "file")

#: The normalised verdicts (section 18.4.1's ``outcome``, kept as ``Row.result``).
RESULTS: tuple[str, ...] = ("pass", "fail", "censored")
#: The 13 terminal failure kinds, in precedence order (section 18.5.1).
FAILURE_KINDS: tuple[str, ...] = (
    "timeout",
    "rate_limit",
    "context_overflow",
    "loop_detected",
    "step_limit",
    "guardrail_blocked",
    "tool_error",
    "retrieval_error",
    "format_error",
    "abstained",
    "crash",
    "wrong_answer",
    "unclassified_error",
)
#: The 3 non-exclusive behavioural signals, in the order a row lists them.
SIGNALS: tuple[str, ...] = ("gave_up", "retry_storm", "over_budget")
#: The span kinds of the Prove Trace reads, which a ``SpanRecord`` takes.
PROVE_KINDS: tuple[str, ...] = ("llm", "tool", "retrieval", "db", "http", "agent", "other")
#: The kinds a source may name as where its error happened: Prove's, and the words other sources
#: use for a span that is not one of Prove's (section 18.1 item 10).
ERROR_SPAN_KINDS: tuple[str, ...] = (
    *PROVE_KINDS,
    "retriever",
    "parser",
    "grader",
    "gate",
    "step",
    "lifecycle",
)
#: What a tool call ended as.
TOOL_STATUSES: tuple[str, ...] = ("ok", "error")

#: The signal fields that are counts (whole numbers from zero).
COUNT_SIGNALS: tuple[str, ...] = (
    "input_chars",
    "output_chars",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "total_tokens",
    "steps",
    "horizon",
    "llm_calls",
    "retries",
)
#: The signal fields that are amounts (non-negative numbers).
AMOUNT_SIGNALS: tuple[str, ...] = ("wall_time_s", "working_time_s", "ttft_s", "cost_usd")
#: Each numeric signal and its unit.
UNITS: Mapping[str, str] = {
    "wall_time_s": "seconds",
    "working_time_s": "seconds",
    "ttft_s": "seconds",
    "input_chars": "characters",
    "output_chars": "characters",
    "input_tokens": "tokens",
    "output_tokens": "tokens",
    "cached_tokens": "tokens",
    "reasoning_tokens": "tokens",
    "total_tokens": "tokens",
    "cost_usd": "US dollars",
    "steps": "steps",
    "horizon": "steps",
    "llm_calls": "calls",
    "retries": "tries",
}
#: The most of an error that is kept (IC7).
ERROR_MAX = 240


def zone_of(started: str) -> dict[str, str]:
    """The name and the offset from UTC (``UTC+02:00``) of this machine's zone at the instant
    ``started``, an ISO-8601 time: the zone a time in a file's name is read in."""
    from datetime import datetime

    local = datetime.fromisoformat(started.replace("Z", "+00:00")).astimezone()
    offset = local.strftime("%z")
    return {"name": local.strftime("%Z"), "offset": f"UTC{offset[:3]}:{offset[3:5]}"}


# The longest text that is its own case id.
_OWN_ID = 80


class Refusal(Exception):
    """One sentence, exit 1, nothing written; under it, the commands to run next, if any."""

    def __init__(self, sentence: str, *nexts: str) -> None:
        super().__init__(sentence)
        self.nexts = nexts


# ---------- checks on a field ----------


def count(name: str, value: Any) -> int | None:
    """``value`` as a count (a whole number from zero), or None when it is None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} is a count, a whole number, not {value!r}")
    if value < 0:
        raise ValueError(f"{name} is a count and cannot be {value}")
    return value


def amount(name: str, value: Any) -> float | None:
    """``value`` as an amount (a finite number from zero), or None when it is None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} is a number, not {value!r}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} is a number and cannot be {value!r}")
    if out < 0.0:
        raise ValueError(f"{name} cannot be below zero; it is {value!r}")
    return out


def _word(name: str, value: Any, words: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} is one of {', '.join(words)}, not {value!r}")
    if value not in words:
        raise ValueError(f"{name} is one of {', '.join(words)}, not {value!r}")
    return value


def _text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} is text, not {value!r}")
    return value


def _try(name: str, value: Any) -> int:
    """A try number: a whole number from one."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} is a try number, a whole number from 1, not {value!r}")
    if value < 1:
        raise ValueError(f"{name} is a try number from 1, not {value}")
    return value


def _scores(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise TypeError(f"scores is a mapping of names to numbers, not {value!r}")
    out: dict[str, float] = {}
    for key, score in value.items():
        if not isinstance(key, str):
            raise TypeError(f"a score is named by text, not {key!r}")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(f"the score {key} is a number, not {score!r}")
        if not math.isfinite(score):
            raise ValueError(f"the score {key} is a number, not {score!r}")
        out[key] = float(score)
    return out


def _feedback(value: Any) -> dict[str, float | str | bool]:
    if not isinstance(value, Mapping):
        raise TypeError(f"feedback is a mapping of names to values, not {value!r}")
    out: dict[str, float | str | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"feedback is named by text, not {key!r}")
        if isinstance(item, (bool, str)):
            out[key] = item
        elif isinstance(item, (int, float)) and math.isfinite(item):
            out[key] = float(item)
        else:
            raise TypeError(f"the feedback {key} is a number, text or true/false, not {item!r}")
    return out


def _signals(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"signals is a list drawn from {', '.join(SIGNALS)}, not {value!r}")
    given = list(value)
    for word in given:
        if word not in SIGNALS:
            raise ValueError(f"a signal is one of {', '.join(SIGNALS)}, not {word!r}")
    if len(set(given)) != len(given):
        raise ValueError(f"a signal is listed once; given {given!r}")
    return tuple(s for s in SIGNALS if s in given)


def _records(name: str, value: Any, kind: type) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, Mapping)) or not isinstance(value, Iterable):
        raise TypeError(f"{name} is a list of {kind.__name__}, not {value!r}")
    out = tuple(value)
    for item in out:
        if not isinstance(item, kind):
            raise TypeError(f"{name} holds {kind.__name__} records, not {item!r}")
    return out


# ---------- the shape (section 18.4.1) ----------


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call: its name, how it ended, its time, the error's type and which try it was.
    Never the tool's arguments or what it returned (IC7)."""

    name: str
    status: str
    duration_s: float | None = None
    error_type: str | None = None
    attempt: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(f"a tool call is named by text, not {self.name!r}")
        _word("a tool call's status", self.status, TOOL_STATUSES)
        if self.status is None:
            raise ValueError("a tool call's status is ok or error")
        object.__setattr__(self, "duration_s", amount("duration_s", self.duration_s))
        _text("error_type", self.error_type)
        _try("attempt", self.attempt)


@dataclass(frozen=True)
class SpanRecord:
    """One span as the Prove Trace reads stores it (SA1): its identity, kind, name and times,
    then every optional field Prove's span has, ``None`` where the span did not record it.
    ``tokens`` is the span's total; ``input_tokens`` and ``output_tokens`` are its ``in`` and
    ``out``."""

    span_id: str
    parent_id: str | None
    kind: str
    name: str
    start_ns: int
    end_ns: int | None
    tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    code: str | None = None
    operation: str | None = None
    step_name: str | None = None
    outcome: str | None = None
    outcome_by: str | None = None
    attempt: int | None = None
    gate: str | None = None
    truncated: str | None = None
    bytes_original: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.span_id, str) or not self.span_id:
            raise ValueError(f"a span is identified by text, not {self.span_id!r}")
        _text("parent_id", self.parent_id)
        if self.kind not in PROVE_KINDS:
            raise ValueError(f"a span's kind is one of {', '.join(PROVE_KINDS)}, not {self.kind!r}")
        if not isinstance(self.name, str):
            raise TypeError(f"a span is named by text, not {self.name!r}")
        if isinstance(self.start_ns, bool) or not isinstance(self.start_ns, int):
            raise TypeError(f"start_ns is a whole number of nanoseconds, not {self.start_ns!r}")
        if self.end_ns is not None:
            if isinstance(self.end_ns, bool) or not isinstance(self.end_ns, int):
                raise TypeError(f"end_ns is a whole number of nanoseconds, not {self.end_ns!r}")
            if self.end_ns < self.start_ns:
                raise ValueError(
                    f"a span cannot end ({self.end_ns}) before it starts ({self.start_ns})"
                )
        for name in ("tokens", "input_tokens", "output_tokens", "bytes_original"):
            count(name, getattr(self, name))
        object.__setattr__(self, "cost_usd", amount("cost_usd", self.cost_usd))
        for name in (
            "error", "code", "operation", "step_name", "outcome", "outcome_by", "gate", "truncated"
        ):
            _text(name, getattr(self, name))
        if self.attempt is not None:
            _try("attempt", self.attempt)


@dataclass(frozen=True)
class Row:
    """One try of one case. The first six fields are today's, by position; the rest are the
    signals, by keyword (section 18.4.1, SA2)."""

    case: str
    outcome: str | None
    error: str | None
    score: float | None = None
    spans: tuple[Mapping[str, Any], ...] | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)
    _: KW_ONLY
    # identity: the repeat's number, None when only the order read says which it is
    repeat: int | None = None
    # the normalised verdict and the failure taxonomy
    result: str | None = None
    failure_kind: str | None = None
    error_type: str | None = None
    error_span_kind: str | None = None
    # duration, in seconds
    wall_time_s: float | None = None
    working_time_s: float | None = None
    ttft_s: float | None = None
    # input and output length, in characters, measured before the text was dropped
    input_chars: int | None = None
    output_chars: int | None = None
    # tokens
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    # cost, in US dollars
    cost_usd: float | None = None
    # step structure, tool calls and retries
    steps: int | None = None
    horizon: int | None = None
    llm_calls: int | None = None
    tool_calls: tuple[ToolCallRecord, ...] | None = None
    retries: int | None = None
    # eval scores and human feedback
    scores: Mapping[str, float] = field(default_factory=dict)
    feedback: Mapping[str, float | str | bool] = field(default_factory=dict)
    # the behavioural signals, and the spans as records apart from the spans the writer stores
    signals: tuple[str, ...] = ()
    span_records: tuple[SpanRecord, ...] | None = None

    def __post_init__(self) -> None:
        put = object.__setattr__
        if isinstance(self.error, str) and len(self.error) > ERROR_MAX:
            put(self, "error", self.error[:ERROR_MAX])
        put(self, "repeat", count("repeat", self.repeat))
        _word("result", self.result, RESULTS)
        _word("failure_kind", self.failure_kind, FAILURE_KINDS)
        if self.failure_kind is not None and self.result not in ("fail", "censored"):
            raise ValueError(
                f"only a row whose result is fail or censored has a failure kind; this one's "
                f"result is {self.result!r}"
            )
        _text("error_type", self.error_type)
        _word("error_span_kind", self.error_span_kind, ERROR_SPAN_KINDS)
        for name in AMOUNT_SIGNALS:
            put(self, name, amount(name, getattr(self, name)))
        for name in COUNT_SIGNALS:
            count(name, getattr(self, name))
        if (
            self.total_tokens is None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            put(self, "total_tokens", self.input_tokens + self.output_tokens)
        put(self, "tool_calls", _records("tool_calls", self.tool_calls, ToolCallRecord))
        put(self, "scores", _scores(self.scores))
        put(self, "feedback", _feedback(self.feedback))
        put(self, "signals", _signals(self.signals))
        put(self, "span_records", _records("span_records", self.span_records, SpanRecord))


@dataclass(frozen=True)
class Run:
    name: str
    tool: str
    rows: tuple[Row, ...]
    started: str
    started_from: str
    declared: Mapping[str, Any]
    files: tuple[Mapping[str, str], ...]
    counts: Mapping[str, int] = field(default_factory=dict)  # the reader's own, as printed
    # the outcome column's cells as written, each with its rows (a table read by --failed)
    cells: Mapping[str, int] = field(default_factory=dict)
    # what the summary adds to where the start came from, such as a zone the file left out
    started_note: str | None = None


def digest_id(text: str) -> str:
    """``sha256:`` and the first 16 hex characters of the SHA-256 of the text's UTF-8 bytes:
    an identity that holds nothing of the text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def case_id(text: str) -> str:
    """The text itself when it is printable and at most 80 characters, else its digest. An
    empty text identifies nothing and raises ``ValueError``."""
    if text == "":
        raise ValueError("an empty text is not a case")
    if len(text) <= _OWN_ID and text.isprintable():
        return text
    return digest_id(text)
