"""The ``--verdicts FILE`` join: outcomes, scores and feedback another source gave, joined onto
the rows a reader read (spec section 18.2 option B and 18.2.1 layers 1 and 2, SG5; FI10, FI11,
FI17 to FI20).

A verdicts file is a ``.csv`` with the columns ``case``, ``input``, ``outcome``, ``score`` and
``failure_kind``, or a ``.jsonl`` with those keys and ``scores`` and ``feedback`` objects. Each
row names a ``case``, an ``input``, or both; an outcome is ``pass`` or ``fail``, a failure kind
one of the 13. Any other column or key refuses the file, as do two rows for one case or one
input.

A row joins every try of the case it names. When its case names no case, it joins by input: the
key ``input:`` and the first 12 hex characters of the SHA-256 of the canonical input (a string's
UTF-8 bytes as written; anything else as compact JSON with sorted keys), given as the row's
``case`` or computed from its ``input``, matched against the keys the reader computed from the
inputs it read (only readers that read an input have them). A case match comes first.

A verdict fills what the source left out and must agree with what it recorded: a value that
differs is refused, naming the case, and nothing is written. A filled outcome is written as
``met`` or ``missed`` and the try's no-outcome reason is cleared. The file's own text, its
``input`` cells above all, is never kept: only the joined values reach the rows.

Standard library only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED
from poisson_trace.ingest.rows import FAILURE_KINDS, Refusal, Row

#: The columns of a ``.csv`` verdicts file, and the keys of a ``.jsonl`` one.
COLUMNS: tuple[str, ...] = ("case", "input", "outcome", "score", "failure_kind")
KEYS: tuple[str, ...] = (*COLUMNS, "scores", "feedback")
#: The outcomes a verdict gives.
OUTCOMES: tuple[str, ...] = ("pass", "fail")
#: How a case key made from an input begins.
INPUT_PREFIX = "input:"
_HEX = 12
_WORD = {"pass": MET, "fail": MISSED}


def input_case(value: Any) -> str:
    """The case key of an input: ``input:`` and the first 12 hex characters of the SHA-256 of
    its canonical form, a string's UTF-8 bytes exactly as written (no trimming, no case
    folding, no normalisation), anything else as compact JSON with sorted keys (FI18)."""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return INPUT_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HEX]


@dataclass(frozen=True)
class Verdict:
    """One row of the file, checked: where it is, what it names and what it gives."""

    line: int
    case: str | None
    input: str | None  # the input's key, never its text
    outcome: str | None
    score: float | None
    failure_kind: str | None
    scores: Mapping[str, float]
    feedback: Mapping[str, float | str | bool]


@dataclass(frozen=True)
class Joined:
    """The rows with the verdicts joined, in their order, and how the file's rows matched:
    ``read`` rows, ``by_case`` joined by case, ``by_input`` by input, ``unmatched`` none."""

    rows: tuple[Row, ...]
    read: int
    by_case: int
    by_input: int
    unmatched: int


# ---------- reading the file ----------


def _bad(path: Path, line: int, why: str) -> Refusal:
    return Refusal(f"line {line} of the verdicts file {path} {why}; nothing was written")


def _number(path: Path, line: int, what: str, value: Any, text: bool = False) -> float:
    """A number: in a CSV, a cell's text; in JSON Lines, a JSON number."""
    if isinstance(value, bool):
        raise _bad(path, line, f"gives {what} {json.dumps(value)}, which is not a number")
    if isinstance(value, str) and text:
        try:
            out = float(value)
        except ValueError:
            raise _bad(
                path, line, f"gives {what} {json.dumps(value)}, which is not a number"
            ) from None
    elif isinstance(value, (int, float)):
        out = float(value)
    else:
        raise _bad(path, line, f"gives {what} {json.dumps(value)}, which is not a number")
    if not math.isfinite(out):
        raise _bad(
            path, line, f"gives {what} {json.dumps(str(value))}, which is not a finite number"
        )
    return out


def _verdict(path: Path, line: int, cells: Mapping[str, Any], text: bool) -> Verdict:
    """One row's cells checked (``text``: a CSV's, every cell text); an empty cell (or a JSON
    null) gives nothing."""

    def given(key: str) -> Any:
        value = cells.get(key)
        return None if value is None or value == "" else value

    case = given("case")
    if case is not None and not isinstance(case, str):
        raise _bad(path, line, f"gives the case {json.dumps(case)}, which is not text")
    raw_input = given("input")
    if case is None and raw_input is None:
        raise _bad(path, line, "names no case and no input")
    outcome = given("outcome")
    if outcome is not None and outcome not in OUTCOMES:
        raise _bad(
            path, line, f"gives the outcome {json.dumps(outcome)}; an outcome is pass or fail"
        )
    score = given("score")
    kind = given("failure_kind")
    if kind is not None and kind not in FAILURE_KINDS:
        raise _bad(
            path, line, f"gives the failure kind {json.dumps(kind)}, which is not one of the 13"
        )
    if kind is not None and outcome == "pass":
        raise _bad(path, line, "gives a failure kind with the outcome pass")
    scores: dict[str, float] = {}
    held = cells.get("scores")
    if held is not None:
        if not isinstance(held, Mapping):
            raise _bad(path, line, "gives scores that are not an object of names and numbers")
        for name, value in held.items():
            scores[str(name)] = _number(path, line, f"the score {name}", value)
    feedback: dict[str, float | str | bool] = {}
    held = cells.get("feedback")
    if held is not None:
        if not isinstance(held, Mapping):
            raise _bad(path, line, "gives feedback that is not an object of names and values")
        for name, value in held.items():
            if isinstance(value, (bool, str)):
                feedback[str(name)] = value
            elif isinstance(value, (int, float)) and math.isfinite(value):
                feedback[str(name)] = float(value)
            else:
                raise _bad(
                    path, line, f"gives the feedback {name} a value that is not a number, text or "
                    "true or false"
                )
    return Verdict(
        line=line,
        case=case,
        input=None if raw_input is None else input_case(raw_input),
        outcome=outcome,
        score=None if score is None else _number(path, line, "the score", score, text),
        failure_kind=kind,
        scores=scores,
        feedback=feedback,
    )


def _text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except (OSError, ValueError):
        raise Refusal(f"the verdicts file {path} could not be read; nothing was written") from None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Refusal(f"the verdicts file {path} is not UTF-8 text; nothing was written") from None


def _csv(path: Path) -> list[Verdict]:
    reader = csv.reader(io.StringIO(_text(path), newline=""), strict=True)
    out: list[Verdict] = []
    header: list[str] | None = None
    at = 0
    try:
        for cells in reader:
            line, at = at + 1, reader.line_num
            if not cells or (len(cells) == 1 and not cells[0].strip()):
                continue
            if header is None:
                header = cells
                unknown = [c for c in header if c not in COLUMNS]
                if unknown:
                    raise _bad(
                        path, line, f"names the column {json.dumps(unknown[0])}; a verdicts "
                        f"file's columns are {', '.join(COLUMNS)}"
                    )
                if len(set(header)) != len(header):
                    raise _bad(path, line, "names one column twice")
                if "case" not in header and "input" not in header:
                    raise _bad(path, line, "names neither a case column nor an input column")
                continue
            if len(cells) > len(header):
                raise _bad(path, line, f"has {len(cells)} cells and the header names {len(header)}")
            out.append(_verdict(path, line, dict(zip(header, cells, strict=False)), True))
    except csv.Error:
        raise _bad(path, at + 1, "cannot be read as CSV") from None
    return out


def _jsonl(path: Path) -> list[Verdict]:
    out: list[Verdict] = []
    for line, text in enumerate(_text(path).split("\n"), start=1):
        if not text.strip():
            continue
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            raise _bad(path, line, "is not JSON") from None
        if not isinstance(doc, Mapping):
            raise _bad(path, line, "is not a JSON object")
        unknown = [k for k in doc if k not in KEYS]
        if unknown:
            raise _bad(
                path, line, f"has the key {json.dumps(unknown[0])}; a verdict's keys are "
                f"{', '.join(KEYS)}"
            )
        out.append(_verdict(path, line, doc, False))
    return out


def read(path: Path) -> list[Verdict]:
    """Every row of the verdicts file, checked; a file that is not one is refused."""
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".jsonl"):
        raise Refusal(
            f"the verdicts file {path} is neither .csv nor .jsonl, the two kinds of verdicts "
            "file this install reads; nothing was written"
        )
    verdicts = _csv(path) if suffix == ".csv" else _jsonl(path)
    if not verdicts:
        raise Refusal(f"the verdicts file {path} holds no row; nothing was written")
    for key in ("case", "input"):
        seen: dict[str, int] = {}
        for v in verdicts:
            value = v.case if key == "case" else (v.input if v.case is None else None)
            if value is None:
                continue
            if value in seen:
                raise _bad(
                    path, v.line, f"gives a second verdict for the {key} line {seen[value]} "
                    "gives; a file gives one verdict for each"
                )
            seen[value] = v.line
    return verdicts


# ---------- joining ----------


def _apply(row: Row, v: Verdict, path: Path) -> Row:
    """``row`` with what the verdict fills; a verdict that differs from what the row recorded
    is refused, naming the case."""

    def differs(what: str, recorded: Any, given: Any) -> Refusal:
        return Refusal(
            f"line {v.line} of the verdicts file {path} gives the case {row.case} {what} "
            f"{json.dumps(given)}, and the source recorded {json.dumps(recorded)}; a verdict "
            "fills what the source left out and never overturns it, so nothing was written"
        )

    changed: dict[str, Any] = {}
    result = row.result
    if v.outcome is not None:
        recorded = row.result
        if recorded is None and row.outcome in (MET, MISSED):
            recorded = "pass" if row.outcome == MET else "fail"
        if recorded is None:
            result = v.outcome
            changed.update(outcome=_WORD[v.outcome], error=None, result=v.outcome)
        elif recorded != v.outcome:
            raise differs("the outcome", recorded, v.outcome)
    if v.score is not None:
        if row.score is None:
            changed["score"] = v.score
        elif row.score != v.score:
            raise differs("the score", row.score, v.score)
    if v.failure_kind is not None:
        if row.failure_kind is None:
            if result not in ("fail", "censored"):
                raise Refusal(
                    f"line {v.line} of the verdicts file {path} gives the case {row.case} the "
                    f"failure kind {v.failure_kind}, and its outcome is "
                    f"{'pass' if result == 'pass' else 'not recorded'}; only a failed try has "
                    "a failure kind, so nothing was written"
                )
            changed["failure_kind"] = v.failure_kind
        elif row.failure_kind != v.failure_kind:
            raise differs("the failure kind", row.failure_kind, v.failure_kind)
    for field, given in (("scores", v.scores), ("feedback", v.feedback)):
        held = dict(getattr(row, field))
        for name, value in given.items():
            if name not in held:
                held[name] = value
            elif held[name] != value:
                raise differs(f"the {'score' if field == 'scores' else 'feedback'} {name}",
                              held[name], value)
        if held != dict(getattr(row, field)):
            changed[field] = held
    return replace(row, **changed) if changed else row


def join(rows: Sequence[Row], path: Path | str, inputs: Mapping[str, str] | None = None) -> Joined:
    """The verdicts of the file at ``path`` joined onto ``rows``; ``inputs`` maps a row's case
    to its input key, for the readers that read an input. Refused, with nothing joined: a file
    that is not one, a row matching two cases, two rows for one case, a verdict that differs
    from what the source recorded, and a file none of whose rows match a case."""
    path = Path(path)
    verdicts = read(path)
    cases = set(dict.fromkeys(row.case for row in rows))
    by_key: dict[str, list[str]] = {}
    for case, key in (inputs or {}).items():
        if case in cases:
            by_key.setdefault(key, []).append(case)
    target: dict[str, Verdict] = {}
    by_case = by_input = unmatched = 0
    for v in verdicts:
        if v.case is not None and v.case in cases:
            hits, how = [v.case], "case"
        else:
            keys = [k for k in (v.case, v.input) if k is not None and k.startswith(INPUT_PREFIX)]
            hits, how = next(([*by_key[k]] for k in keys if k in by_key), []), "input"
        if not hits:
            unmatched += 1
            continue
        if len(hits) > 1:
            raise Refusal(
                f"line {v.line} of the verdicts file {path} matches {len(hits)} cases by its "
                f"input ({', '.join(sorted(hits)[:3])}{', …' if len(hits) > 3 else ''}); a "
                "verdict joins one case, so nothing was written"
            )
        (case,) = hits
        if case in target:
            raise Refusal(
                f"lines {target[case].line} and {v.line} of the verdicts file {path} both give "
                f"a verdict for the case {case}; a file gives one verdict for each, so nothing "
                "was written"
            )
        target[case] = v
        if how == "case":
            by_case += 1
        else:
            by_input += 1
    if not target:
        raise Refusal(
            f"no row of the verdicts file {path} matches a case of the run, by case or by input; "
            "nothing was written"
        )
    joined = tuple(
        _apply(row, target[row.case], path) if row.case in target else row for row in rows
    )
    return Joined(joined, len(verdicts), by_case, by_input, unmatched)


def block(path: Path | str, joined: Joined) -> dict[str, Any]:
    """What an import records of a join (FI20): the file's name and digest and the counts;
    never its path or its text."""
    path = Path(path)
    return {
        "name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": joined.read,
        "by_case": joined.by_case,
        "by_input": joined.by_input,
        "unmatched": joined.unmatched,
    }
