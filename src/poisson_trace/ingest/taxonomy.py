"""The failure taxonomy: one rule set over the normalised ``Row`` for every source.

Every row whose result is ``fail`` or ``censored`` gets one of the 13 terminal failure kinds of
spec section 18.5.1, by the first rule that matches in precedence order; every row, passing or
not, gets the behavioural signals that hold for it. The rules read the row's own fields, so what
a reader puts into the row decides the kind (SA3): section 18.5.2's per-source table says what
each reader records, and this module classifies what it finds. A kind the source itself gave
(a table's ``failure_kind`` column, a Prove run's own word) is kept. User rules from
``trace.toml``'s ``[[taxonomy.rules]]`` are tried first, in the order written, and every
condition of a rule must hold for it to match (SG12).

A reader may also give the kinds its outcome labels name (``labels``): a failed try no rule
found a cause for takes the kind of its label, before the two rules that find none
(``wrong_answer`` for a graded try, else ``unclassified_error``). Only the Prove reader gives
them: ``LABEL_KINDS`` holds its defaults, and a team's ``[taxonomy.labels]`` adds to them.

``taxonomy_sha256`` is the digest an import records beside what it declared, so a verdict can say
which rules classified a run (SA5, SA9).

Standard library and ``rows`` only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from poisson_trace.ingest.rows import (
    ERROR_SPAN_KINDS,
    FAILURE_KINDS,
    SIGNALS,
    Row,
    ToolCallRecord,
    amount,
    count,
)

__all__ = [
    "FAILURE_KINDS",
    "SIGNALS",
    "LABEL_KINDS",
    "SCHEMA",
    "Budgets",
    "Rule",
    "classify",
    "kind_of",
    "signals_of",
    "taxonomy_sha256",
]

#: The schema the digest names: it names this built-in rule set, so a later change to the
#: built-ins is a new schema and a new digest.
SCHEMA = "poisson.trace-taxonomy/1"
#: The conditions a user rule may set; at least one.
CONDITIONS: tuple[str, ...] = ("when_error_matches", "when_span_kind", "when_metric_below")
#: The budgets a config may declare, and the signal fields they bound.
BUDGETS: tuple[str, ...] = ("max_wall_time_s", "max_total_tokens", "max_cost_usd")

# the text rules (section 18.5.2, read as one set): the error's type and the error, joined
TIMEOUT = re.compile(r"(?i)time[ _-]?out|timed[ _-]?out|ETIMEDOUT")
RATE_LIMIT = re.compile(r"(?i)\b429\b|rate[ _-]?limit")
CONTEXT = re.compile(
    r"(?i)context[ _-]?length|context[ _-]?window|max_tokens|model_length|token[ _-]?limit"
    r"|cost[ _-]?limit"
)
GUARDRAIL = re.compile(r"(?i)content[ _-]?filter|guardrail|moderation")
FORMAT = re.compile(r"JSONDecodeError|ValidationError|SchemaError")
ASSERTION = re.compile(r"^(?:[\w.]+\.)?Assert(?:ion)?Error$")
#: An error Prove's executor writes for a harness failure.
INFRA = "infra:"
#: The kinds that are a budget hit (over_budget holds on them).
CAP_KINDS: tuple[str, ...] = ("timeout", "context_overflow", "step_limit")
#: A retry storm: this many retries, or this many calls in a row to one tool with this many
#: of them failed.
STORM_RETRIES = 3
STORM_RUN = 3
STORM_FAILED = 2
#: The kind an outcome label of a run Prove swept gives by its name, matched letter for letter:
#: each kind's own name, and the nine labels Poisson Tasks' checker gives a failure. Nothing
#: else has a default; a team names its own under ``[taxonomy.labels]``.
LABEL_KINDS: Mapping[str, str] = MappingProxyType(
    {
        **{kind: kind for kind in FAILURE_KINDS},
        "wrong_state": "wrong_answer",
        "overshoot": "wrong_answer",
        "collateral_mutation": "wrong_answer",
        "malformed_call": "format_error",
        "turn_limit": "step_limit",
        "wall_timeout": "timeout",
        "api_error": "crash",
        "verifier_error": "crash",
        "replay_mismatch": "crash",
    }
)


@dataclass(frozen=True)
class Budgets:
    """Soft budgets from ``[signals.budgets]``: a row strictly over one has the ``over_budget``
    signal. Each is a number from zero, or None when not declared."""

    max_wall_time_s: float | None = None
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_wall_time_s", amount("max_wall_time_s", self.max_wall_time_s))
        count("max_total_tokens", self.max_total_tokens)
        object.__setattr__(self, "max_cost_usd", amount("max_cost_usd", self.max_cost_usd))

    def to_dict(self) -> dict[str, Any]:
        """The budgets set, by name."""
        return {name: getattr(self, name) for name in BUDGETS if getattr(self, name) is not None}


@dataclass(frozen=True)
class Rule:
    """A user rule: the kind it gives, and the conditions that must all hold. ``when_error_matches``
    is a regular expression searched in the error's type and the error; ``when_span_kind`` is the
    kind of span the error happened in; ``when_metric_below`` is ``{metric, cut}``, a score
    strictly under the cut."""

    failure_kind: str
    when_error_matches: str | None = None
    when_span_kind: str | None = None
    when_metric_below: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.failure_kind not in FAILURE_KINDS:
            raise ValueError(
                f"a rule's failure_kind is one of {', '.join(FAILURE_KINDS)}, not "
                f"{self.failure_kind!r}"
            )
        if all(getattr(self, name) is None for name in CONDITIONS):
            raise ValueError(f"a rule needs at least one of {', '.join(CONDITIONS)}")
        if self.when_error_matches is not None:
            if not isinstance(self.when_error_matches, str):
                raise TypeError("when_error_matches is a regular expression in quotes")
            try:
                re.compile(self.when_error_matches)
            except re.error as e:
                raise ValueError(
                    f"when_error_matches is not a regular expression ({e})"
                ) from None
        if self.when_span_kind is not None and self.when_span_kind not in ERROR_SPAN_KINDS:
            raise ValueError(
                f"when_span_kind is one of {', '.join(ERROR_SPAN_KINDS)}, not "
                f"{self.when_span_kind!r}"
            )
        if self.when_metric_below is not None:
            object.__setattr__(self, "when_metric_below", _metric_below(self.when_metric_below))

    def matches(self, row: Row) -> bool:
        """Whether every condition of the rule holds for ``row``."""
        if self.when_error_matches is not None and not re.search(
            self.when_error_matches, _text(row)
        ):
            return False
        if self.when_span_kind is not None and row.error_span_kind != self.when_span_kind:
            return False
        if self.when_metric_below is not None:
            metric, cut = self.when_metric_below["metric"], self.when_metric_below["cut"]
            score = row.scores.get(metric)
            if score is None or not score < cut:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """The rule's set fields, by name, as the digest reads them."""
        out: dict[str, Any] = {"failure_kind": self.failure_kind}
        for name in CONDITIONS:
            value = getattr(self, name)
            if value is not None:
                out[name] = dict(value) if isinstance(value, Mapping) else value
        return out


def _metric_below(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"metric", "cut"}:
        raise ValueError('when_metric_below is { metric = "NAME", cut = X }')
    metric, cut = value["metric"], value["cut"]
    if not isinstance(metric, str) or not metric:
        raise ValueError("when_metric_below names its metric in quotes")
    if isinstance(cut, bool) or not isinstance(cut, (int, float)) or not math.isfinite(cut):
        raise ValueError(f"when_metric_below's cut is a number, not {cut!r}")
    return {"metric": metric, "cut": cut}


def taxonomy_sha256(
    rules: Sequence[Rule], budgets: Budgets | None, labels: Mapping[str, str] | None = None
) -> str:
    """SHA-256 of the compact, key-sorted JSON of the schema, the rules in order (each its set
    fields) and the budgets set (SA9). Signal field mappings are not in it. ``labels`` is a
    team's ``[taxonomy.labels]`` table, which only a run Prove swept is classified by: it is in
    the document only when it names a label, so every digest without a table is as it was."""
    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "rules": [rule.to_dict() for rule in rules],
        "budgets": {} if budgets is None else budgets.to_dict(),
    }
    if labels:
        doc["labels"] = dict(labels)
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- the built-in rules ----------


def _text(row: Row) -> str:
    return " ".join(x for x in (row.error_type, row.error) if x is not None)


def _at_cap(row: Row) -> bool:
    """Steps and the horizon both recorded, a horizon above zero, and steps at or past it."""
    return (
        row.steps is not None
        and row.horizon is not None
        and row.horizon > 0
        and row.steps >= row.horizon
    )


def _retrieval_scores(scores: Mapping[str, float]) -> bool:
    recall = [v for k, v in scores.items() if k.endswith("context_recall")]
    precision = [v for k, v in scores.items() if k.endswith("context_precision")]
    return any(v == 0.0 for v in recall) and any(v == 0.0 for v in precision)


def _asserted(row: Row) -> bool:
    return row.error_type is not None and ASSERTION.match(row.error_type) is not None


def retry_storm(row: Row) -> bool:
    """Three or more retries, or three or more consecutive calls to one tool of which at least
    two ended in an error."""
    if row.retries is not None and row.retries >= STORM_RETRIES:
        return True
    calls: Sequence[ToolCallRecord] = row.tool_calls or ()
    at = 0
    while at < len(calls):
        end = at
        while end < len(calls) and calls[end].name == calls[at].name:
            end += 1
        run = calls[at:end]
        if len(run) >= STORM_RUN and sum(1 for c in run if c.status == "error") >= STORM_FAILED:
            return True
        at = end
    return False


def _built_in(row: Row, labels: Mapping[str, str] | None = None) -> str:
    """The kind the built-in rules give a failed or censored row, in precedence order. With
    ``labels``, a failed row no rule found a cause for takes the kind its outcome label names
    there, before the two rules that find none."""
    text = _text(row)
    at_cap = _at_cap(row)
    calls = row.tool_calls or ()
    if TIMEOUT.search(text):
        return "timeout"
    if RATE_LIMIT.search(text):
        return "rate_limit"
    if CONTEXT.search(text):
        return "context_overflow"
    if at_cap and (retry_storm(row) or "retry_storm" in row.signals):
        return "loop_detected"
    if at_cap:
        return "step_limit"
    if row.error_span_kind == "gate" or GUARDRAIL.search(text):
        return "guardrail_blocked"
    if row.error_span_kind == "tool" or any(c.status == "error" for c in calls):
        return "tool_error"
    if row.error_span_kind in ("retrieval", "retriever") or _retrieval_scores(row.scores):
        return "retrieval_error"
    if row.error_span_kind == "parser" or FORMAT.search(text):
        return "format_error"
    if row.error is None and row.error_type is None and row.output_chars == 0:
        return "abstained"
    if (
        (row.error_type is not None and not _asserted(row))
        or row.error_span_kind == "lifecycle"
        or (row.error is not None and row.error.startswith(INFRA))
    ):
        return "crash"
    if labels and row.result == "fail" and row.outcome is not None and row.outcome in labels:
        return labels[row.outcome]
    graded = (
        row.score is not None
        or bool(row.scores)
        or _asserted(row)
        or row.error_span_kind == "grader"
    )
    if row.result == "fail" and graded:
        return "wrong_answer"
    return "unclassified_error"


def kind_of(
    row: Row, rules: Sequence[Rule] = (), labels: Mapping[str, str] | None = None
) -> str | None:
    """The failure kind of ``row``: None unless its result is ``fail`` or ``censored``; the kind
    the source gave, when it gave one; else the first user rule that matches, in the order
    written; else the built-in rules in precedence order, the kind ``labels`` names for the
    row's outcome label among them."""
    if row.result not in ("fail", "censored"):
        return None
    if row.failure_kind is not None:
        return row.failure_kind
    for rule in rules:
        if rule.matches(row):
            return rule.failure_kind
    return _built_in(row, labels)


def signals_of(row: Row, budgets: Budgets | None = None) -> tuple[str, ...]:
    """The behavioural signals that hold for ``row``, in ``SIGNALS`` order: ``gave_up`` for an
    abstention, or an empty output with steps left; ``retry_storm`` as ``retry_storm`` reads it;
    ``over_budget`` for a declared budget strictly exceeded, a kind that is a budget hit, or
    steps at the horizon."""
    kind = row.failure_kind if row.failure_kind is not None else kind_of(row)
    found: set[str] = set()
    if kind == "abstained" or (
        row.output_chars == 0
        and row.steps is not None
        and row.horizon is not None
        and row.steps < row.horizon
    ):
        found.add("gave_up")
    if retry_storm(row):
        found.add("retry_storm")
    if kind in CAP_KINDS or _at_cap(row) or _over(row, budgets):
        found.add("over_budget")
    return tuple(s for s in SIGNALS if s in found)


def _over(row: Row, budgets: Budgets | None) -> bool:
    if budgets is None:
        return False
    for budget, signal in (
        ("max_wall_time_s", "wall_time_s"),
        ("max_total_tokens", "total_tokens"),
        ("max_cost_usd", "cost_usd"),
    ):
        limit, value = getattr(budgets, budget), getattr(row, signal)
        if limit is not None and value is not None and value > limit:
            return True
    return False


def classify(
    row: Row,
    rules: Sequence[Rule] = (),
    budgets: Budgets | None = None,
    *,
    labels: Mapping[str, str] | None = None,
) -> Row:
    """``row`` with its failure kind and its signals filled: the kind from ``kind_of``, the
    signals it already holds plus those of ``signals_of``, in ``SIGNALS`` order. Nothing else
    changes."""
    kind = kind_of(row, rules, labels)
    classified = row if kind == row.failure_kind else replace(row, failure_kind=kind)
    found = set(classified.signals) | set(signals_of(classified, budgets))
    signals = tuple(s for s in SIGNALS if s in found)
    if signals == tuple(classified.signals):
        return classified
    return replace(classified, signals=signals)
