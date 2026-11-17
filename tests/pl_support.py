"""Shared helpers for the Prove label kinds pair's tests (PL): Trace reads a failure kind for a
try of a run Prove swept from the outcome label the try carries. Not collected.

The problem, as main c981832 has it: a Prove rollout that records only its outcome label
(``wrong_state``, ``malformed_call``, the labels a team declares as failures) is counted as a
failure and filed under ``unclassified_error``, because the Prove reader (``ingest/prove.py``)
turns the label into pass or fail and never into a kind, and the built-in rules give
``wrong_answer`` only to a try with a score, an assertion error or a grader step. On the
three-tools recipe every one of the old version's 1,320 lost-token failures, each labelled
``wrong_state`` by the task's checker, reads ``unclassified_error``.

The rule, as this pair's Session A froze it (each reading is a ruling owed, ``rulings.md`` in
the vault log ``trace-labels-a``):

1. **The order**. A failed or errored try of a run Prove swept gets its kind from the
   first of these that gives one:

   a. the kind the rollout recorded itself: ``meta["trace_signals"]`` a record with the
      schema ``poisson.trace-signals/1`` and no ``case`` (the whole record Trace's own import
      writes carries ``case`` and is read as an import, as on main), whose ``failure_kind`` is
      one of the 13 kinds. Main does not read it: a rollout's own record of that schema makes
      the reader raise ``KeyError: 'case'``;
   b. Prove's own word ``timeout`` on a try short of its step cap: ``timeout``, as main reads
      it (SA3 reading 6, ruled 2026-11-03);
   c. the team's own ``[[taxonomy.rules]]`` in ``trace.toml``, the first that matches in the
      order written, as an import tries them before every built-in rule (LK-9, ruled no
      2026-11-16: section 18.5.3's rules apply to every source). Prove records no named
      metric, so ``when_metric_below`` matches no such try;
   d. the built-in rules that find a cause on the try's record, in their order, as main has
      them: ``timeout``, ``rate_limit``, ``context_overflow``, ``loop_detected``,
      ``step_limit``, ``guardrail_blocked``, ``tool_error``, ``retrieval_error``,
      ``format_error``, ``abstained``, ``crash``;
   e. the try's outcome label: the kind ``trace.toml`` names for it under ``[taxonomy.labels]``,
      else the kind the label gives by its name (``LABEL_KINDS``);
   f. the last two built-in rules, as main has them: ``wrong_answer`` for a graded try, else
      ``unclassified_error``.

   A passing try has no kind, whatever it recorded.
2. **The defaults**: ``DEFAULTS`` below, every entry. A label is matched as Prove stored
   it, letter for letter.
3. **The team's own**: ``[taxonomy.labels]`` in ``trace.toml``, each line a label and
   the kind it names in quotes; it wins over a default. Checked as every table is: a fault is
   refused in one sentence naming the file and the line (``FAULTS``). ``doctor``'s config line
   names the kinds the table gives.
4. **Said once**: where a failed try of a run Prove swept counts as
   ``unclassified_error`` because its label has no kind and no rule of the team's matched it, ``fix-check``, ``compare`` and
   ``changes`` say so once, in their ``Failures by kind`` section (``note``), and their
   ``--json`` names the labels and how many such tries each run has
   (``failure_taxonomy_diff.labels_without_kind``).
5. **The digest**: the digest of a run Prove swept is the built-in rules' as on main,
   or, under ``[[taxonomy.rules]]``, ``[signals.budgets]`` or a ``[taxonomy.labels]`` table,
   ``taxonomy_sha256(rules, budgets, labels)``, which holds them all; a run under none of them
   has main's digest. An import's digest never holds the table.
6. **Where it applies**: runs Prove swept. An import's kinds were decided at the import
   and do not move.
7. **The budgets** (LK-26, budgets ruled no 2026-11-16): ``[signals.budgets]`` apply to a
   run Prove swept as to an import: a try strictly over one has ``over_budget``, read from its
   wall time (Prove's ``wall_time``, on every try), its total tokens (its steps' tokens in and
   out together, recorded only when both are) and its cost (the rollout's own
   ``meta["cost_usd"]``, a number). A signal a try does not record is never over. The kind
   does not move.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tf0_support import Ran, trace

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
FIXTURES = TESTS / "fixtures"
TAU2 = FIXTURES / "tau2"
CS = FIXTURES / "cs"
HUMANEVAL = FIXTURES / "humaneval"
PROVE_013 = FIXTURES / "prove-stores" / "prove-0.1.3"
EXAMPLE = REPO / "examples" / "three-tools"
STARTED = "2026-11-16T09:00:00Z"
SIGNALS_SCHEMA = "poisson.trace-signals/1"

#: The 13 kinds, in section 18.5.1's order.
KINDS: tuple[str, ...] = (
    "timeout", "rate_limit", "context_overflow", "loop_detected", "step_limit", "guardrail_blocked", "tool_error",
    "retrieval_error", "format_error", "abstained", "crash", "wrong_answer", "unclassified_error",
)
#: The kinds the rules that find a cause give (1c), in their order.
CAUSES: tuple[str, ...] = KINDS[:11]

#: The labels Poisson Tasks 0.4.2's checker gives a failure, each with the kind it gives by
#: its name (``poisson_tasks.outcomes.MEANING`` says what each means).
TASKS_LABELS: dict[str, str] = {
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
#: Every default: each kind's own name gives that kind, and Tasks' labels as above. Nothing
#: else has a default.
DEFAULTS: dict[str, str] = {**{k: k for k in KINDS}, **TASKS_LABELS}

#: The kinds a team may name, as the note lists them.
KIND_LIST = "timeout, rate_limit, context_overflow, loop_detected, step_limit, guardrail_blocked, tool_error, " \
            "retrieval_error, format_error, abstained, crash or wrong_answer"
BARE = re.compile(r"[A-Za-z0-9_-]+")


def toml_key(label: str) -> str:
    """A label as a key of ``trace.toml``: bare when it is letters, digits, ``-`` and ``_``,
    else in double quotes with TOML's escapes."""
    if BARE.fullmatch(label):
        return label
    return json.dumps(label, ensure_ascii=False)


def listed(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def note(labels: Sequence[str]) -> str:
    """The one paragraph ``Failures by kind`` gives the labels with no kind, sorted."""
    labels = sorted(labels)
    if len(labels) == 1:
        first = f"Trace has no kind for the label {labels[0]}, so its failed tries count as unclassified_error."
    else:
        first = f"Trace has no kind for the labels {listed(labels)}, so their failed tries count as unclassified_error."
    return (f"{first} To name a label's kind, add it to trace.toml under [taxonomy.labels], as "
            f'{toml_key(labels[0])} = "KIND", where KIND is {KIND_LIST}.')


# ---------- small Prove stores, written through Prove's own store ----------


@dataclass(frozen=True)
class Try:
    """One episode: its task, its outcome label (None for an errored try, which then has
    ``error``), its steps and cap, a score, its own ``meta`` beside the trace, and its spans
    (each a dict of ``Span``'s fields; a tool span with no error when none is given)."""

    task: str
    outcome: str | None
    t: float | None = 1.0
    horizon: float | None = 32.0
    confidence: float | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    spans: Sequence[Mapping[str, Any]] | None = None
    replicate: int = 0


def own(kind: Any, **more: Any) -> dict[str, Any]:
    """A rollout's own record of its signals: the schema, a kind, nothing else unless asked."""
    return {"trace_signals": {"schema": SIGNALS_SCHEMA, "failure_kind": kind, **more}}


def prove_run(root: Path, run_id: str, tries: Sequence[Try], name: str | None = None, axis: str = "task") -> Path:
    """A complete run of ``tries`` in the Prove store at ``root`` (made when not there), its one
    axis named ``axis`` (``case`` pairs it with an import's run, whose condition is its case)."""
    from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash
    from poisson_prove.trace import Span, Trace

    store = Store(root)
    store.create_run(RunManifest(run_id=run_id, target_id="agent", t_unit="steps", run_salt="5eed",
                                 axis_types={axis: "categorical"}, backend="local", environment={},
                                 created_at=STARTED, name=name))
    records = []
    for i, t in enumerate(tries):
        config = {axis: t.task}
        meta: dict[str, Any] = dict(t.meta)
        if t.error is None:
            given = t.spans if t.spans is not None else [{"kind": "tool", "name": "submit"}]
            spans = tuple(
                Span(**{"span_id": f"{n:016x}", "parent_id": None, "name": "step", "start_ns": n + 1, "end_ns": n + 2, **s})
                for n, s in enumerate(given)
            )
            meta["trace"] = Trace(spans=spans, source="record").to_dict()
        records.append(EpisodeRecord(
            run_id=run_id, config_hash=config_hash(config), config=config, seed=i, replicate_index=t.replicate,
            outcome=t.outcome, t=None if t.error else t.t, horizon=None if t.error else t.horizon,
            confidence=None if t.error else t.confidence, meta=meta, error=t.error, wall_time=1.0, backend_meta={},
        ))
    store.append(run_id, records)
    store.mark_complete(run_id)
    return root


def read_one(tmp: Path, t: Try, failed: Sequence[str] | None = None, labels: Mapping[str, str] | None = None) -> Any:
    """The one row of a run of the try ``t``, read with its label as the failure word."""
    from poisson_trace.ingest.prove import read_rows

    root = prove_run(tmp / "store", "r", [t])
    words = list(failed) if failed is not None else ([t.outcome] if t.outcome else [])
    if labels is None:
        rows = read_rows(root, "r", failed=words)
    else:
        rows = read_rows(root, "r", failed=words, labels=labels)
    assert len(rows) == 1
    return rows[0]


# ---------- the commands ----------


def config(folder: Path, store: str, failed: Sequence[str], labels: str | None = None, extra: str = "") -> Path:
    """A ``trace.toml`` in ``folder`` naming ``store`` and the failures, with ``labels`` (the
    text of a ``[taxonomy.labels]`` table's lines) when given."""
    text = f'version = 1\n\n[store]\npath = "{store}"\n\n[events]\nfailed = {json.dumps(list(failed))}\n'
    if labels is not None:
        text += f"\n[taxonomy.labels]\n{labels}"
    text += extra
    path = folder / "trace.toml"
    path.write_text(text, encoding="utf-8")
    return path


def run(argv: Sequence[Any]) -> Ran:
    return trace([str(a) for a in argv])


def two_runs(tmp: Path, old: Sequence[Try], new: Sequence[Try], axis: str = "task") -> Path:
    """A Prove store of two runs named ``old`` and ``new``, in ``tmp/store``."""
    root = tmp / "store"
    prove_run(root, "20261116T090000Z-0001", old, name="old", axis=axis)
    prove_run(root, "20261116T090100Z-0002", new, name="new", axis=axis)
    return root


VERBS = ("fix-check", "compare", "changes")
#: Each verb as the tests run it, on the two runs ``old`` and ``new``.
ARGS = {
    "fix-check": ["fix-check", "old", "new", "--inputs", "all", "--max-mde", "0.9"],
    "compare": ["compare", "old", "new", "--max-mde-hr", "9"],
    "changes": ["changes", "old", "new"],
}
#: The keys the JSON gives each run in ``failure_taxonomy_diff``.
ARMS = {"fix-check": ("old", "new"), "compare": ("a", "b"), "changes": ("a", "b")}
HEADING = "## Failures by kind"


def section(text: str) -> list[str]:
    """The lines of ``Failures by kind``, its heading to the line before the next heading."""
    lines = text.split("\n")
    assert lines.count(HEADING) == 1, text
    at = lines.index(HEADING)
    end = next((i for i in range(at + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    out = lines[at:end]
    while out and not out[-1].strip():
        out.pop()
    return out


def kind_rows(lines: Sequence[str]) -> dict[str, list[str]]:
    """The first table of a section, each row's cells by its kind."""
    rows: dict[str, list[str]] = {}
    started = False
    for line in lines:
        if line.startswith("| kind |"):
            started = True
            continue
        if started and line.startswith("|---"):
            continue
        if started and line.startswith("| "):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0]] = cells[1:]
        elif started:
            break
    return rows


__all__ = ["REPO", "Ran"]
