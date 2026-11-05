"""promptfoo results, as ``promptfoo eval -o results.json`` (or ``.jsonl``) writes them.

One promptfoo file holds every prompt by every provider by every test, so one import reads one
version: one prompt, picked by ``--prompt`` (its label, or its number counting from 1), and one
provider, picked by ``--provider`` when the file has more than one. Each result of that prompt
and provider is one row. The JSON file (``results.results`` a list, ``results.timestamp`` its
start) and the JSON Lines file (one result per line, no start) are told by their extension;
promptfoo's CSV puts the prompts side by side under repeated column names and is refused,
pointing at the JSON export.

The case is a named test variable (``--case var:NAME``) or the test's position (``--case
test``, ``test:<testIdx>``); results sharing a case are its repeats in the order read. A result
is ``missed`` when promptfoo's ``success`` is false and ``met`` when true, or read from its
``score`` at a declared cut. A result promptfoo marks as an error (``failureReason`` 2) has no
outcome: its error's text gives its failure kind by section 18.5.2 (a timeout, a rate limit, a
context overflow, else a crash) and is kept nowhere. A failed assertion takes its kind from the
first failed assertion's type.

The signals read of a result: ``latencyMs`` as the wall time, the lengths of the prompt sent and
of the answer, ``response.tokenUsage``'s prompt, completion and total tokens (and its cached and
reasoning tokens where present), ``response.cost`` and the scores. Nothing of a prompt, an
answer, a variable but the case, an error or a grader's reason is kept; the prompt's label is
printed and recorded, since it is how the version is named (RD2).

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, case_id
from poisson_trace.ingest.taxonomy import CONTEXT, RATE_LIMIT, TIMEOUT
from poisson_trace.look import why

DESCRIPTION = """\
Read promptfoo's results (promptfoo eval -o results.json, or results.jsonl) and write one
prompt's results as one new run. One file holds every prompt, so one import reads one version:
--prompt names it by its label or its number, counting from 1, and --provider names the
provider when the file has more than one. Each result is one row: met when promptfoo passed it,
missed when it did not, or read from its score at a cut. A result promptfoo marks as an error
has no outcome. No prompt, answer, variable but the case, error or grader's reason is kept.
"""
EXAMPLE = (
    "poisson-trace import promptfoo results.json --store trace-store --run old --prompt 1 "
    "--case var:case"
)

TOOL = "promptfoo"
OUTCOMES: tuple[str, ...] = ("success", "score")
ERROR = "error"
# promptfoo's failureReason: 1 a failed assertion, 2 an error
_ASSERT, _ERROR = 1, 2
# the failure kind each failed assertion type gives (section 18.5.2); any other, a wrong answer
_ASSERTED: Mapping[str, str] = {
    "is-json": "format_error",
    "is-xml": "format_error",
    "is-sql": "format_error",
    "is-valid-function-call": "format_error",
    "regex": "format_error",
    "is-refusal": "abstained",
    "guardrails": "guardrail_blocked",
    "moderation": "guardrail_blocked",
    "function-call": "tool_error",
    "context-recall": "retrieval_error",
    "context-relevance": "retrieval_error",
}
_CSV = "promptfoo eval -o results.json"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prompt",
        metavar="LABEL|N",
        help="the prompt this version is: its label, or its number counting from 1 (default: "
        "the file's one prompt; required when it has several)",
    )
    parser.add_argument(
        "--provider",
        metavar="ID",
        help="the provider whose results to read, by its id (default: the file's one provider; "
        "required when it has several)",
    )
    parser.add_argument(
        "--case",
        required=True,
        metavar="var:NAME|test",
        help="what identifies a test across the two versions: var:NAME, the test variable NAME, "
        "or test, the test's position in the file (no default)",
    )
    parser.add_argument(
        "--outcome",
        choices=OUTCOMES,
        default=OUTCOMES[0],
        metavar="success|score",
        help="success: promptfoo's own pass or fail; score: the result's score at --cut "
        "(default: success)",
    )
    parser.add_argument(
        "--cut",
        metavar="X",
        help="with --outcome score, the score a result must reach (no default)",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")


def usage(ns: argparse.Namespace) -> str | None:
    """Why the command line is still wrong, or None: a case in one of its two forms, and a cut
    with exactly one side when, and only when, the outcome is read from the score."""
    case = str(ns.case)
    if case != "test" and not (case.startswith("var:") and len(case) > len("var:")):
        return f"--case takes var:NAME or test, not {case}"
    sided = ns.cut is not None or ns.below or ns.above
    if ns.outcome != "score":
        return "--cut, --below and --above read a score: give --outcome score" if sided else None
    if ns.cut is None:
        return "--outcome score needs --cut X, with --below or --above"
    if _number(ns.cut) is None:
        return f"--cut takes a number, not {ns.cut}"
    if ns.below == ns.above:
        return (
            f"--cut {ns.cut} needs exactly one side: --below if a score under it missed, "
            "--above if a score over it missed"
        )
    return None


def _number(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# ---------- reading a file ----------


@dataclass(frozen=True)
class _File:
    """One promptfoo file: its results, and its start when it records one."""

    path: Path
    sha256: str
    results: list[Mapping[str, Any]]
    timestamp: str | None
    prompts: Sequence[Any]


def _form(path: Path) -> str:
    """``json`` or ``jsonl``, by the extension; a CSV is refused for the JSON export."""
    name = path.name.lower()
    if name.endswith(".csv"):
        raise Refusal(
            f"{path} is promptfoo's CSV, which sets the prompts side by side under repeated "
            f"column names; export the JSON instead ({_CSV}) and import that"
        )
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".json"):
        return "json"
    raise Refusal(
        f"{path} is not a promptfoo results file: this reader reads .json and .jsonl "
        f"({_CSV})"
    )


def _not_promptfoo(path: Path, what: str) -> Refusal:
    return Refusal(f"{path} is not a promptfoo results file: {what}")


def _load(path: Path) -> _File:
    form = _form(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _not_promptfoo(path, "it is not UTF-8 text") from None
    if not text.strip():
        raise _not_promptfoo(path, "it is empty")
    if form == "json":
        return _json_file(path, digest, text)
    return _jsonl_file(path, digest, text)


def _json_file(path: Path, digest: str, text: str) -> _File:
    try:
        doc = json.loads(text)
    except ValueError:
        raise _not_promptfoo(path, "it is not JSON that can be read") from None
    held = doc.get("results") if isinstance(doc, Mapping) else None
    results = held.get("results") if isinstance(held, Mapping) else None
    if not isinstance(held, Mapping) or not isinstance(results, list):
        raise _not_promptfoo(path, "it holds no results.results list")
    for at, result in enumerate(results):
        _check_result(path, result, f"result {at + 1}")
    stamp = held.get("timestamp")
    prompts = held.get("prompts")
    return _File(
        path,
        digest,
        results,
        stamp if isinstance(stamp, str) and stamp else None,
        prompts if isinstance(prompts, list) else [],
    )


def _jsonl_file(path: Path, digest: str, text: str) -> _File:
    results: list[Mapping[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
        except ValueError:
            raise _not_promptfoo(path, f"line {number} is not JSON") from None
        _check_result(path, result, f"line {number}")
        results.append(result)
    return _File(path, digest, results, None, [])


def _check_result(path: Path, result: Any, where: str) -> None:
    """A result is an object with the prompt's and the test's numbers and a success."""
    if not isinstance(result, Mapping):
        raise _not_promptfoo(path, f"its {where} is not a JSON object")
    for key in ("promptIdx", "testIdx"):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _not_promptfoo(path, f"its {where} has no {key}")
    if not isinstance(result.get("success"), bool):
        raise _not_promptfoo(path, f"its {where} has no success true or false")


# ---------- which version ----------


def _label(result: Mapping[str, Any], prompts: Sequence[Any]) -> str:
    """The prompt's label: the result's own, else the file's prompt list's, else its number."""
    prompt = result.get("prompt")
    label = prompt.get("label") if isinstance(prompt, Mapping) else None
    if isinstance(label, str) and label:
        return label
    idx = int(result["promptIdx"])
    if idx < len(prompts) and isinstance(prompts[idx], Mapping):
        listed = prompts[idx].get("label")
        if isinstance(listed, str) and listed:
            return listed
    return f"prompt {idx + 1}"


def _provider(result: Mapping[str, Any]) -> str:
    provider = result.get("provider")
    if isinstance(provider, Mapping):
        provider = provider.get("id")
    return provider if isinstance(provider, str) and provider else "(none)"


def _listed(labels: Mapping[int, str]) -> str:
    return "; ".join(
        f"{idx + 1}: {json.dumps(label, ensure_ascii=False)}" for idx, label in labels.items()
    )


def _prompt(given: str | None, labels: Mapping[int, str], files: str) -> int:
    """The prompt picked: by its label first, then by its number counting from 1."""
    if given is None:
        if len(labels) == 1:
            return next(iter(labels))
        raise Refusal(
            f"{files} holds {len(labels)} prompts, and one import is one version: name one with "
            f"--prompt, by its label or its number ({_listed(labels)})"
        )
    for idx, label in labels.items():
        if label == given:
            return idx
    number = given.strip()
    if number.isdigit() and int(number) - 1 in labels:
        return int(number) - 1
    raise Refusal(
        f"{files} holds no prompt {json.dumps(given, ensure_ascii=False)}; its prompts are "
        f"{_listed(labels)}"
    )


def _provider_picked(given: str | None, ids: Sequence[str], files: str) -> str:
    shown = ", ".join(ids)
    if given is None:
        if len(ids) == 1:
            return ids[0]
        raise Refusal(
            f"{files} holds the results of {len(ids)} providers, {shown}, and one import is one "
            "version: name one with --provider"
        )
    if given not in ids:
        raise Refusal(f"{files} holds no provider {given}; its providers are {shown}")
    return given


# ---------- one result as a row ----------


def _case(path: Path, rule: str, result: Mapping[str, Any]) -> str:
    if rule == "test":
        return f"test:{result['testIdx']}"
    name = rule[len("var:") :]
    held = result.get("vars")
    if not isinstance(held, Mapping) or name not in held or held[name] in (None, ""):
        raise Refusal(
            f"{path} holds a result (test {int(result['testIdx']) + 1}) without the variable "
            f"{name}, so --case var:{name} cannot identify it"
        )
    value = held[name]
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return case_id(text)


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _amount(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) and out >= 0.0 else None


def _signals(result: Mapping[str, Any]) -> dict[str, Any]:
    """What the result records of the signals; ``None`` where it records nothing."""
    response = result.get("response")
    response = response if isinstance(response, Mapping) else {}
    usage = response.get("tokenUsage")
    usage = usage if isinstance(usage, Mapping) else {}
    details = usage.get("completionDetails")
    details = details if isinstance(details, Mapping) else {}
    prompt = result.get("prompt")
    sent = prompt.get("raw") if isinstance(prompt, Mapping) else None
    output = response.get("output")
    latency = _amount(result.get("latencyMs"))
    named = result.get("namedScores")
    scores = {
        str(k): float(v)
        for k, v in (named.items() if isinstance(named, Mapping) else ())
        if not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    }
    return {
        "wall_time_s": None if latency is None else latency / 1000.0,
        "input_chars": len(sent) if isinstance(sent, str) else None,
        "output_chars": len(output) if isinstance(output, str) else None,
        "input_tokens": _count(usage.get("prompt")),
        "output_tokens": _count(usage.get("completion")),
        "total_tokens": _count(usage.get("total")),
        "cached_tokens": _count(usage.get("cached")),
        "reasoning_tokens": _count(details.get("reasoning")),
        "cost_usd": _amount(response.get("cost")),
        "scores": scores,
    }


def _score(result: Mapping[str, Any]) -> float | None:
    score = result.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return float(score) if math.isfinite(score) else None


def _error_kind(result: Mapping[str, Any]) -> str:
    """An error result's kind, from its text by section 18.5.2; the text is not kept."""
    response = result.get("response")
    texts = [result.get("error"), response.get("error") if isinstance(response, Mapping) else None]
    text = " ".join(t for t in texts if isinstance(t, str))
    for pattern, kind in (
        (TIMEOUT, "timeout"),
        (RATE_LIMIT, "rate_limit"),
        (CONTEXT, "context_overflow"),
    ):
        if pattern.search(text):
            return kind
    return "crash"


def _asserted_kind(result: Mapping[str, Any]) -> str | None:
    """A failed result's kind from its first failed assertion's type, or None to leave it to
    the rules (a wrong answer, since the result is scored)."""
    grading = result.get("gradingResult")
    components = grading.get("componentResults") if isinstance(grading, Mapping) else None
    for component in components if isinstance(components, list) else ():
        if not isinstance(component, Mapping) or component.get("pass") is not False:
            continue
        assertion = component.get("assertion")
        kind = assertion.get("type") if isinstance(assertion, Mapping) else None
        return _ASSERTED.get(kind) if isinstance(kind, str) else None
    return None


def _row(path: Path, rule: str, cut: Cut | None, result: Mapping[str, Any]) -> Row:
    case = _case(path, rule, result)
    signals = _signals(result)
    score = _score(result)
    detail = {"case": rule}
    if result.get("failureReason") == _ERROR:
        return Row(
            case,
            None,
            ERROR,
            score,
            None,
            detail,
            result="censored",
            failure_kind=_error_kind(result),
            **signals,
        )
    if cut is None:
        outcome = MET if result["success"] else MISSED
    else:
        if score is None:
            raise Refusal(
                f"{path} holds a result (test {int(result['testIdx']) + 1}) with no score, so "
                "--outcome score cannot read it"
            )
        outcome = cut.outcome(score)
    if outcome == MET:
        return Row(case, MET, None, score, None, detail, result="pass", **signals)
    return Row(
        case,
        MISSED,
        None,
        score,
        None,
        detail,
        result="fail",
        failure_kind=_asserted_kind(result),
        error_span_kind="grader",
        **signals,
    )


# ---------- the start ----------


def _utc(path: Path, stamp: str) -> str:
    try:
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        raise Refusal(f'{path} holds a timestamp that is not a time: "{stamp}"') from None
    if at.tzinfo is None or at.utcoffset() is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC).replace(tzinfo=None).isoformat() + "Z"


def _file_time(path: Path) -> str:
    try:
        modified = path.stat().st_mtime
    except OSError as e:
        raise Refusal(f"{path} could not be read: {why(e)}") from e
    return datetime.fromtimestamp(modified, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- the import ----------


def read(ns: argparse.Namespace) -> Run:
    rule = str(ns.case)
    cut = None
    if getattr(ns, "outcome", "success") == "score":
        value = _number(ns.cut)
        assert value is not None
        cut = Cut(value, "below" if ns.below else "above")
    loaded = [_load(Path(f)) for f in ns.files]
    files = ", ".join(str(f.path) for f in loaded)
    every = [(f, r) for f in loaded for r in f.results]
    labels: dict[int, str] = {}
    for f, r in every:
        labels.setdefault(int(r["promptIdx"]), _label(r, f.prompts))
    labels = dict(sorted(labels.items()))
    if not labels:
        raise Refusal(f"{files} holds no result, so there is nothing to read")
    picked = _prompt(getattr(ns, "prompt", None), labels, files)
    ids = list(dict.fromkeys(_provider(r) for _, r in every))
    provider = _provider_picked(getattr(ns, "provider", None), ids, files)
    rows = [
        _row(f.path, rule, cut, r)
        for f, r in every
        if int(r["promptIdx"]) == picked and _provider(r) == provider
    ]
    stamps = [f.timestamp for f in loaded if f.timestamp is not None]
    if stamps:
        started, started_from = min(_utc(loaded[0].path, s) for s in stamps), "file"
    else:
        started, started_from = _file_time(loaded[0].path), "file time"
    by_prompt = Counter(int(r["promptIdx"]) for _, r in every)
    by_provider = Counter(_provider(r) for _, r in every)
    counts = {
        f"results of prompt {idx + 1} ({label})": by_prompt[idx] for idx, label in labels.items()
    }
    counts.update({f"results of provider {pid}": by_provider[pid] for pid in ids})
    declared: dict[str, Any] = {
        "case": rule,
        "prompt": labels[picked],
        "provider": provider,
        "outcome": "score" if cut is not None else "success",
    }
    if cut is not None:
        declared.update({"cut": cut.cut, "side": cut.side})
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared=declared,
        files=tuple({"name": f.path.name, "sha256": f.sha256} for f in loaded),
        counts=counts,
    )


# ---------- for init ----------


def looks_like(path: Path | str) -> str | None:
    """One line describing ``path`` when it is a promptfoo results file, else None; it never
    raises. A ``.json`` file whose ``results.results`` is a list of promptfoo results, or a
    ``.jsonl`` file whose first line is one."""
    try:
        found = Path(path)
        name = found.name.lower()
        if not name.endswith((".json", ".jsonl")) or not found.is_file():
            return None
        if name.endswith(".jsonl"):
            with open(found, "rb") as f:
                first = b""
                for line in f:
                    if line.strip():
                        first = line
                        break
            result = json.loads(first.decode("utf-8"))
            if not _is_result(result):
                return None
            return "promptfoo results, one result per line"
        doc = json.loads(found.read_bytes().decode("utf-8"))
        held = doc.get("results") if isinstance(doc, Mapping) else None
        results = held.get("results") if isinstance(held, Mapping) else None
        if not isinstance(results, list) or not results or not _is_result(results[0]):
            return None
        prompts = len({r.get("promptIdx") for r in results if isinstance(r, Mapping)})
        return f"promptfoo results, {len(results)} results of {prompts} prompts"
    except Exception:
        return None


def _is_result(result: Any) -> bool:
    return (
        isinstance(result, Mapping)
        and all(k in result for k in ("promptIdx", "testIdx", "success", "provider"))
        and isinstance(result.get("success"), bool)
    )
