"""Shared helpers for TF21's tests: normalised signals, the failure taxonomy and the five
existing readers. Not collected.

What these tests exercise, in one place (each test file's docstring says which part it holds):

``poisson_trace.ingest.rows``
    ``RESULTS``, ``UNITS``, ``ToolCallRecord``, ``SpanRecord``, and ``Row`` widened by keyword-only fields
    after today's six positional ones (``case, outcome, error, score, spans, detail``), which
    keep their order and meaning so every reader and every frozen test built on them stands.
    ``Row.outcome`` stays the word written to Prove's outcome column; the normalised verdict
    is ``Row.result``: ``"pass"``, ``"fail"``, ``"censored"`` or ``None``.
``poisson_trace.ingest.taxonomy``
    ``FAILURE_KINDS`` (the 13, in precedence order), ``SIGNALS`` (the 3), ``Rule``,
    ``Budgets``, ``kind_of(row, rules=())``, ``signals_of(row, budgets=None)``,
    ``classify(row, rules=(), budgets=None) -> Row`` and ``taxonomy_sha256(rules, budgets)``.
``poisson_trace.ingest.writer``
    ``trace_signals(row, repeat) -> dict`` (the ``poisson.trace-signals/1`` record) and the
    mapping of a row onto Prove 0.1.2's store.
``poisson_trace.ingest.prove``
    ``read_rows(root, run_id, failed) -> tuple[Row, ...]``: a stored run as normalised rows,
    from ``meta["trace_signals"]`` for a run Trace imported, from Prove's own columns and trace
    for a run Prove swept.
``poisson_trace.ingest.tries``
    ``tries_of(rows) -> dict[str, tuple[Try, ...]]`` and ``version_of(rows, name, label="old",
    cap_s=None) -> Version``: the plain per-case inputs ``stats/continuous.py`` takes.
``poisson_trace.config``
    ``Config.signals`` (``case_field``, ``outcome_field``, ``score_field``, ``cut``,
    ``cost_field``), ``Config.budgets`` and ``Config.rules``, read from ``[signals]``,
    ``[signals.budgets]`` and ``[[taxonomy.rules]]``.

The built-in rules, in precedence order, as these tests read them (``ref_kind`` below
is the reference the reader tests check against). Only a row whose result is ``"fail"`` or
``"censored"`` gets a kind. ``text`` is the row's ``error_type`` and ``error``, joined.

1. ``timeout``            text matches ``TIMEOUT``.
2. ``rate_limit``         text matches ``RATE_LIMIT``.
3. ``context_overflow``   text matches ``CONTEXT``.
4. ``loop_detected``      a retry storm (``ref_retry_storm``, or ``retry_storm`` among the
                          row's signals) and steps >= horizon.
5. ``step_limit``         steps and horizon recorded, horizon > 0, steps >= horizon.
6. ``guardrail_blocked``  ``error_span_kind == "gate"``, or text matches ``GUARDRAIL``.
7. ``tool_error``         ``error_span_kind == "tool"``, or a tool call ended ``"error"``.
8. ``retrieval_error``    ``error_span_kind`` is ``"retrieval"`` or ``"retriever"``, or the
                          scores hold a ``*context_recall`` of 0.0 and a ``*context_precision``
                          of 0.0.
9. ``format_error``       ``error_span_kind == "parser"``, or text matches ``FORMAT``.
10. ``abstained``         no error and no error type, and ``output_chars == 0`` (recorded).
11. ``crash``             an ``error_type`` that is not an assertion, ``error_span_kind ==
                          "lifecycle"``, or an error that starts ``infra:``.
12. ``wrong_answer``      result ``"fail"`` and a grader said so: a score, a scores map, an
                          assertion ``error_type``, or ``error_span_kind == "grader"``.
13. ``unclassified_error`` everything else.

The signals: ``retry_storm`` is ``ref_retry_storm``; ``over_budget`` is a declared budget
strictly exceeded (``wall_time_s``, ``total_tokens``, ``cost_usd``), a kind of ``timeout``,
``context_overflow`` or ``step_limit``, or steps >= horizon; ``gave_up`` is a kind of
``abstained``, or ``output_chars == 0`` with steps < horizon. ``classify`` keeps the signals a
row already holds and adds these, in ``SIGNALS`` order; it keeps a kind the source gave.

User rules from ``[[taxonomy.rules]]`` are tried first, in the order written; the first that
matches gives the kind. A user rule's conditions all hold for it to match.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
INGEST = FIXTURES / "ingest"
HUMANEVAL = FIXTURES / "humaneval"
TAU2 = FIXTURES / "tau2"
CS = FIXTURES / "cs"
PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
STARTED = "2026-09-05T18:54:07Z"

# ---------- the shape ----------

RESULTS = ("pass", "fail", "censored")
FAILURE_KINDS = (
    "timeout", "rate_limit", "context_overflow", "loop_detected", "step_limit",
    "guardrail_blocked", "tool_error", "retrieval_error", "format_error", "abstained",
    "crash", "wrong_answer", "unclassified_error",
)
SIGNALS = ("gave_up", "retry_storm", "over_budget")
# Prove 0.1.2's span kinds (poisson_prove.trace.KINDS), and the kinds a source names that are
# not spans of Prove's
PROVE_KINDS = ("llm", "tool", "retrieval", "db", "http", "agent", "other")
ERROR_SPAN_KINDS = (*PROVE_KINDS, "retriever", "parser", "grader", "gate", "step", "lifecycle")

# every signal field Row adds, its kind, and its unit
INT_FIELDS = (
    "input_chars", "output_chars", "input_tokens", "output_tokens", "cached_tokens",
    "reasoning_tokens", "total_tokens", "steps", "horizon", "llm_calls", "retries",
)
FLOAT_FIELDS = ("wall_time_s", "working_time_s", "ttft_s", "cost_usd")
TEXT_FIELDS = ("failure_kind", "error_type", "error_span_kind", "result")
UNITS = {
    "wall_time_s": "seconds", "working_time_s": "seconds", "ttft_s": "seconds",
    "input_chars": "characters", "output_chars": "characters",
    "input_tokens": "tokens", "output_tokens": "tokens", "cached_tokens": "tokens",
    "reasoning_tokens": "tokens", "total_tokens": "tokens", "cost_usd": "US dollars",
    "steps": "steps", "horizon": "steps", "llm_calls": "calls", "retries": "tries",
}
NEW_FIELDS = (
    "repeat", "result", "failure_kind", "error_type", "error_span_kind", "wall_time_s",
    "working_time_s", "ttft_s", "input_chars", "output_chars", "input_tokens", "output_tokens",
    "cached_tokens", "reasoning_tokens", "total_tokens", "cost_usd", "steps", "horizon",
    "llm_calls", "tool_calls", "retries", "scores", "feedback", "signals", "span_records",
)
OLD_FIELDS = ("case", "outcome", "error", "score", "spans", "detail")

# the poisson.trace-signals/1 record, its keys in this order
RECORD_SCHEMA = "poisson.trace-signals/1"
RECORD_KEYS = (
    "schema", "case", "repeat", "outcome", "failure_kind", "error_type", "error_span_kind",
    "wall_time_s", "working_time_s", "ttft_s", "input_chars", "output_chars", "input_tokens",
    "output_tokens", "cached_tokens", "reasoning_tokens", "total_tokens", "cost_usd", "steps",
    "horizon", "llm_calls", "tool_call_count", "tool_error_count", "tool_calls", "retries",
    "score", "scores", "feedback", "signals",
)
TOOL_CALL_KEYS = ("name", "status", "duration_s", "error_type", "attempt")
ERROR_MAX = 240

# ---------- the built-in rules' patterns (one set for every source) ----

TIMEOUT = re.compile(r"(?i)time[ _-]?out|timed[ _-]?out|ETIMEDOUT")
RATE_LIMIT = re.compile(r"(?i)\b429\b|rate[ _-]?limit")
CONTEXT = re.compile(
    r"(?i)context[ _-]?length|context[ _-]?window|max_tokens|model_length|token[ _-]?limit"
    r"|cost[ _-]?limit"
)
GUARDRAIL = re.compile(r"(?i)content[ _-]?filter|guardrail|moderation")
FORMAT = re.compile(r"JSONDecodeError|ValidationError|SchemaError")
ASSERTION = re.compile(r"^(?:[\w.]+\.)?Assert(?:ion)?Error$")


def _text(row: Any) -> str:
    return " ".join(str(x) for x in (row.error_type, row.error) if x is not None)


def _scores_retrieval(scores: Mapping[str, float]) -> bool:
    recall = [v for k, v in scores.items() if k.endswith("context_recall")]
    precision = [v for k, v in scores.items() if k.endswith("context_precision")]
    return any(v == 0.0 for v in recall) and any(v == 0.0 for v in precision)


def ref_retry_storm(row: Any) -> bool:
    """Three or more retries, or three or more consecutive calls to one tool of which at
    least two ended in an error."""
    if row.retries is not None and row.retries >= 3:
        return True
    calls = list(row.tool_calls or ())
    for i in range(len(calls)):
        j = i
        while j < len(calls) and calls[j].name == calls[i].name:
            j += 1
        run = calls[i:j]
        if len(run) >= 3 and sum(1 for c in run if c.status == "error") >= 2:
            return True
    return False


def ref_kind(row: Any) -> str | None:
    """The reference: the kind the built-in rules give ``row`` (no user rules)."""
    if row.result not in ("fail", "censored"):
        return None
    text = _text(row)
    steps, horizon = row.steps, row.horizon
    at_cap = steps is not None and horizon is not None and horizon > 0 and steps >= horizon
    calls = row.tool_calls or ()
    if TIMEOUT.search(text):
        return "timeout"
    if RATE_LIMIT.search(text):
        return "rate_limit"
    if CONTEXT.search(text):
        return "context_overflow"
    if (ref_retry_storm(row) or "retry_storm" in row.signals) and at_cap:
        return "loop_detected"
    if at_cap:
        return "step_limit"
    if row.error_span_kind == "gate" or GUARDRAIL.search(text):
        return "guardrail_blocked"
    if row.error_span_kind == "tool" or any(c.status == "error" for c in calls):
        return "tool_error"
    if row.error_span_kind in ("retrieval", "retriever") or _scores_retrieval(row.scores):
        return "retrieval_error"
    if row.error_span_kind == "parser" or FORMAT.search(text):
        return "format_error"
    if row.error is None and row.error_type is None and row.output_chars == 0:
        return "abstained"
    asserted = row.error_type is not None and ASSERTION.match(row.error_type) is not None
    if (
        (row.error_type is not None and not asserted)
        or row.error_span_kind == "lifecycle"
        or (row.error is not None and row.error.startswith("infra:"))
    ):
        return "crash"
    if row.result == "fail" and (
        row.score is not None or bool(row.scores) or asserted or row.error_span_kind == "grader"
    ):
        return "wrong_answer"
    return "unclassified_error"


# ---------- running the import ----------


@dataclass(frozen=True)
class Result:
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


def run_import(argv: Sequence[Any]) -> Result:
    """``poisson_trace.ingest.cli.main`` in-process, both streams captured."""
    from poisson_trace.ingest.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return Result(code=int(code), out=out.getvalue(), err=err.getvalue())


# Every committed import fixture as an import reads it, without --store and --run. These are
# the imports the existing frozen tests make of the same files.
IMPORTS: dict[str, list[str]] = {
    "deepeval-a": ["deepeval", str(INGEST / "deepeval" / "humaneval-a.json.gz"),
                   "--metric", "Tests Passed", "--cut", "recorded", "--case", "name"],
    "deepeval-b": ["deepeval", str(INGEST / "deepeval" / "humaneval-b.json.gz"),
                   "--metric", "Tests Passed", "--cut", "recorded", "--case", "name"],
    "junit-a": ["junit", str(INGEST / "junit" / "humaneval-a.xml")],
    "junit-b": ["junit", str(INGEST / "junit" / "humaneval-b.xml")],
    "junit-suite": ["junit", str(INGEST / "junit" / "trace-suite-1.xml"),
                    str(INGEST / "junit" / "trace-suite-2.xml")],
    "ragas-base": ["ragas", str(INGEST / "ragas" / "rag-base.jsonl"), "--metric",
                   "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"],
    "ragas-raft": ["ragas", str(INGEST / "ragas" / "rag-raft.jsonl"), "--metric",
                   "faithfulness", "--cut", "0.5", "--below", "--case-column", "case"],
    "ragas-causal": ["ragas", str(INGEST / "ragas" / "memory-causal.jsonl.gz"), "--metric",
                     "id_based_context_recall", "--cut", "0.5", "--below", "--case-column",
                     "user_input"],
    "ragas-strong": ["ragas", str(INGEST / "ragas" / "memory-strong.jsonl.gz"), "--metric",
                     "id_based_context_recall", "--cut", "0.5", "--below", "--case-column",
                     "user_input"],
    "table-a": ["table", str(INGEST / "table" / "humaneval-a.csv"), "--case-column", "case",
                "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed",
                "crashed"],
    "table-b": ["table", str(INGEST / "table" / "humaneval-b.csv"), "--case-column", "case",
                "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed",
                "crashed"],
}
# the few the pull-request lane imports whole; the slow lane imports every one
FAST = ("junit-a", "junit-suite", "ragas-base", "ragas-causal")


def do_import(key: str, root: Path, run: str | None = None, *extra: Any) -> Result:
    argv = [*IMPORTS[key], "--store", str(root), "--run", run or key, "--started", STARTED,
            "--json", *extra]
    result = run_import(argv)
    assert result.code == 0, result.out + result.err
    return result


# ---------- reading the store back ----------


def _null(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def frame(root: Path, run: str) -> Any:
    from poisson_prove.store import Store

    return Store(root).read(run, meta=True, trace="full")


def records(root: Path, run: str) -> list[dict[str, Any]]:
    """``meta["trace_signals"]`` of every stored row, ordered by case then repeat."""
    out = [dict(m["trace_signals"]) for m in frame(root, run)["meta"]]
    return sorted(out, key=lambda r: (r["case"], r["repeat"]))


def canonical(x: Any) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=str).encode("utf-8")


def verb_view(root: Path, run: str) -> dict[str, Any]:
    """Everything of a stored run a Trace verb reads (cli._load and the runs listing):
    the outcome, error, config and config_hash columns, the seed and replicate, the trace
    envelope, the tally, and the manifest apart from the import block TF21 widens."""
    from poisson_prove.store import Store

    store = Store(root)
    df = store.read(run, meta=False, trace="envelope")
    rows = []
    for r in df.to_dict("records"):
        rows.append([
            _null(r["outcome"]), _null(r["error"]), r["config"], r["config_hash"],
            int(r["seed"]), int(r["replicate_index"]), _null(r["trace"]),
        ])
    rows.sort(key=lambda x: canonical(x))
    manifest = store.manifest(run).to_dict()
    env = dict(manifest.get("environment") or {})
    imported = dict(env.get("import") or {})
    for key in ("taxonomy_sha256", "taxonomy"):
        imported.pop(key, None)
    env["import"] = imported
    manifest["environment"] = env
    manifest.pop("created_at", None)
    manifest.pop("run_id", None)
    return {"rows": rows, "tally": store.tally(run).to_dict(), "manifest": manifest}


def digest(x: Any) -> str:
    return hashlib.sha256(canonical(x)).hexdigest()


def json_without_store(result: Result, root: Path) -> str:
    """The import's --json output with the store's path, which differs per test, taken out."""
    return result.out.replace(str(root), "<store>")


def counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))
