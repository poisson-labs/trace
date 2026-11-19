"""Shared helpers for TF26's tests: the W&B Weave reader and its raw-saving API pull (spec
sections 6.3, 6.4a, 18.1 row 11, 18.3.1 to 18.3.4, 18.4 and 18.5.2; rulings SG2, SG9, SG10 and
SG18; the captures' rulings TC-1 to TC-11; TF21's and TF22's rulings, which this reader follows
as the others do; and the two finished pairs', LS-1 to LS-47, B-1 to B-8 and BT-1 to BT-44,
whose shape this pair keeps wherever Weave's files allow). Not collected.

What Session B builds, in one place (each test file's docstring says which invariant it holds):

``poisson_trace.ingest.weave``
    A reader module of the shape ``ingest/cli.py`` documents (``add_arguments``, ``read``,
    ``usage``, ``DESCRIPTION``, ``EXAMPLE``, ``looks_like``, ``stand_ins``), with ``SHAPES``
    naming the shapes it reads: ``call`` (one call an object: the answers of ``POST
    /calls/stream_query``, and the JSON and JSON Lines the Traces page downloads) and ``table``
    (one call a row, one value a column named by its dotted path: the page's CSV and TSV); and
    ``ADDRESS``, ``weave:``. It imports nothing from Weave's or W&B's packages or from
    ``poisson_prove``.
``poisson_trace.ingest.pulling``
    The Weave pull, through the two seams the other pulls already have and these tests replace:
    ``send(method, url, headers, body, timeout) -> (status, headers, body)``, the one function
    in the package that reaches the network, and ``sleep(seconds)``.
``docs/integrations/weave.md`` and ``docs/recipes/from-weave.md``
    The page and the recipe, of the other readers' shape.

The readings these tests hold (each is a yes/no in the session's rulings, WV-1 on):

the command
    ``poisson-trace import weave FILE [FILE ...] --store ROOT --run NAME --case-from (example |
    example:KEY | input | none) --outcome-from (status | score:KEY) [--cut X (--below |
    --above)] [--evaluation NAME]``. ``example`` is the dataset row the case was run on, by the
    row's own digest in the reference to it; ``example:KEY`` a key of that row; ``input``
    TF22's input key of the row's values (``input:`` and 12 hex characters), which is also what
    ``--verdicts`` joins by; ``status`` reads whether the case errored; ``score:KEY`` a
    scorer's output at the cut. Every outcome is written ``met`` or ``missed``.
the files
    ``.jsonl`` (a call a line; an empty file is the last page of a paged answer and holds no
    call), ``.json`` (a list of calls), ``.csv`` and ``.tsv`` (the page's table). A call given
    twice is refused, so pages of one answer are given together and two exports of one
    evaluation are not.
a row
    One ``Evaluation.predict_and_score`` call is one row. The rows of one evaluation are the
    calls whose parent is its ``Evaluation.evaluate`` call. Files that hold the rows of more
    than one evaluation are refused, naming each, unless ``--evaluation`` names the one to read
    (by the evaluation object's name, by the call's id, or by the name Weave shows for the
    call where the files hold it). A file that holds nothing but ``Evaluation.evaluate`` calls
    (the Traces page with no filter) is refused saying how to get the rows. Rows are in the
    order their calls started, so the tries of a case are its repeats in the order they ran.
the outcome
    A case errored when its call raised, or when something under it raised
    (``descendant_error``) and it holds no output and no score: the same test from every
    export, since every export holds the row's own status, output and scores.
    ``descendant_error`` alone is not an error: a step that failed and was retried under a
    case that answered is a pass. A case that errored has no score, so read by a score it has
    no outcome (reason ``no score``) and is censored.
scores and feedback
    A scorer's output under ``output.scores``: a number as it is, true as 1 and false as 0
    (counted in the summary where the outcome read one); named by its dotted path, and by its
    scorer alone where the scorer gave a value under its own name (``exact.exact`` is
    ``exact``), and asked for by either. A scorer's text is never kept. A reaction on the row's call is its feedback (``reaction``, its name); a note is
    never read. The scorers' outputs repeated as feedback on the model's call are not read.
signals
    Wall time is Weave's own figure for the model's run (``output.model_latency``), else the
    call's end less its start. Weave records no time to first token. Lengths are the
    characters of every value of the example (its ``_ref`` left out) and of the model's output;
    a reference in a value's place is not recorded. Tokens and cost are the call's own summary
    (``summary.usage.<model>``, ``summary.weave.costs.<model>``), summed over its models; a
    cost is recorded only where the export carries one, and the rows that record tokens and no
    cost are counted. From the calls under the row, where the files hold them: steps are the
    calls under the model's call with no call under them (the model's call itself where it has
    none); LLM calls the calls marked ``llm``; tool calls the calls marked ``tool``; a call
    that follows a failed call of the same op under the same parent is the next attempt and
    one retry. The scorers' calls are no step and no stored span. From the page's downloads
    (rows alone): the count of model calls from ``summary.usage``'s requests, and no step, tool
    call, retry or span.
failure kinds
    Through TF21's one rule set, from what the reader records: the exception's class as the
    error's type and the kind of the call that failed (``llm``, ``tool``, else ``other``),
    read from the last step that raised; a class or words saying a timeout, a rate limit or a
    context overflow give that kind as the source's own. The page's rows hold no exception,
    so an errored case there has no class and is unclassified.
the pull
    ``weave:ENTITY/PROJECT/EVALUATION`` in the files' place pulls the evaluation with
    ``WANDB_API_KEY`` (basic auth, user ``api``): ``POST /calls/stream_query`` for the
    project's root calls, then for every call of the evaluation's trace with its example
    expanded, each always with ``include_costs`` and ``include_feedback``, in pages by
    ``limit`` and ``offset`` until a page comes back empty, with nothing that bounds the calls
    by time; saves ``raw.jsonl`` (the calls, one a line) and ``pull.json`` under
    ``STORE/.poisson/raw/weave/RUN/``; then reads that folder with the file reader.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import shutil
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from tf21_support import INGEST, Result, records, run_import

WV = INGEST / "weave"
API = WV / "api"
UI = WV / "ui"
HOST = "https://trace.wandb.ai"
QUERY = "/calls/stream_query"
KEY_VARIABLE = "WANDB_API_KEY"
ENDPOINT_VARIABLE = "WF_TRACE_SERVER_URL"
#: A key no service ever issued: what the tests put in the environment, and look for afterwards.
PLANTED_KEY = "0f1e2d3c4b5a69788796a5b4c3d2e1f0aa55planted0"
ENTITY = "example-entity"
PROJECT = "trace-fixture"
PROJECT_ID = f"{ENTITY}/{PROJECT}"

EVALUATE = "Evaluation.evaluate"
ROW = "Evaluation.predict_and_score"

VERSIONS = ("baseline", "candidate")
LOOKUP = ("old", "new")
NAMES = (*LOOKUP, *VERSIONS)
#: The paid slice (ten dataset rows, one try each) and the lookup fixture (three rows, two tries
#: each), by a short name, with the evaluation object's name.
EVALUATION = {"old": "trace-fixture-old", "new": "trace-fixture-new", "baseline": "trace-fixture-slice-baseline", "candidate": "trace-fixture-slice-candidate"}
#: Each evaluation's ``Evaluation.evaluate`` call: its id, its trace's id and the name Weave shows.
CALL_ID = {
    "old": "01a1c1fe-e770-71bc-b51a-26161d46a267", "new": "01a1c1fe-e79c-7aa4-b7d8-221692d3ee20",
    "baseline": "01a1c1ff-2284-7c7c-bb3a-8952efef33a7", "candidate": "01a1c1ff-2bbb-7221-a0b3-98fe793f6940",
}
TRACE_ID = {
    "old": "01a1c1fe-e76e-7817-a336-454239eba743", "new": "01a1c1fe-e79c-74f0-94e4-85d34ca3a60b",
    "baseline": "01a1c1ff-2284-72e4-a62f-c0878cf8186f", "candidate": "01a1c1ff-2bba-7cc7-a8b2-b104a623be0c",
}
SHOWN = {"old": "eval-2026-11-09-dazzling-flower", "new": "eval-2026-11-09-daring-cloud", "baseline": "eval-2026-11-09-unique-pine", "candidate": "eval-2026-11-09-happy-wind"}
CASES = tuple(f"c{n:02d}" for n in range(1, 11))
QUESTIONS = ("q1", "q2", "q3")

#: Every export of one evaluation, by a short name. The service's answers hold the whole trace
#: of one evaluation: ``pull`` (costs and feedback asked for, the example a reference) and
#: ``expanded`` (the same with the example's row in the file). The Traces page's downloads hold
#: the rows alone, of all four evaluations in one file.
API_EXPORTS = ("pull", "expanded")
UI_CALLS = ("ui-json", "ui-jsonl")
UI_TABLES = ("ui-csv", "ui-tsv")
UI_EXPORTS = (*UI_CALLS, *UI_TABLES)
EXPORTS = (*API_EXPORTS, *UI_EXPORTS)
#: The exports the candidate alone also has: with neither include flag, and in pages of 40 (the
#: last page empty).
CANDIDATE_ONLY = ("plain", "pages")
#: The shape the reader names for each.
SHAPE = {"pull": "call", "expanded": "call", "plain": "call", "pages": "call", "ui-json": "call", "ui-jsonl": "call", "ui-csv": "table", "ui-tsv": "table"}
#: The exports that hold the dataset row itself, and those that hold the reference to it.
WITH_ROW = ("expanded", *UI_EXPORTS)
WITH_REF = ("pull", "expanded", "plain", "pages", *UI_CALLS)
_UI_FILE = {"ui-json": "predict-and-score.json", "ui-jsonl": "predict-and-score.jsonl", "ui-csv": "predict-and-score.csv", "ui-tsv": "predict-and-score.tsv"}
#: The page's download of its default view: one row an evaluation, which holds no case.
ROOTS_ONLY = (API / "roots.jsonl", UI / "traces-roots.json", UI / "traces-roots.jsonl", UI / "traces-roots.csv", UI / "traces-roots.tsv")


def evaluation(name: str) -> str:
    """The evaluation object's name: a short name's, or the name itself."""
    return EVALUATION.get(name, name)


def export(name: str, kind: str) -> list[Path]:
    """The files of one export of one evaluation (``name`` a short name)."""
    if kind == "pull":
        return [API / f"{evaluation(name)}.jsonl"]
    if kind == "expanded":
        return [API / f"{evaluation(name)}.expanded.jsonl"]
    if kind in CANDIDATE_ONLY:
        assert name == "candidate", "only the candidate was pulled plain and in pages"
        if kind == "plain":
            return [API / f"{evaluation(name)}.plain.jsonl"]
        return [API / f"{evaluation(name)}.page-{n}.jsonl" for n in (1, 2, 3, 4)]
    return [UI / _UI_FILE[kind]]


def default_case(kind: str) -> str:
    """A way to name the case that every row of the export can give: the reference to the
    dataset row where the export carries it, else the row's ``id``, which the table has as a
    column."""
    return "example" if kind in WITH_REF else "example:id"


# ---------- what the captures hold, written out (read off the files; see PROVENANCE.md) ----------

#: The item each case asks about and the answer the dataset expects (its row is ``{"id": CASE,
#: "case": CASE, "item": ITEM, "expected": EXPECTED}``), and the answer each version gave (None
#: where the case errored and the output is null).
ITEM = {"c01": "widget", "c02": "gasket", "c03": "valve", "c04": "flange", "c05": "bearing", "c06": "coupling", "c07": "washer", "c08": "spindle", "c09": "bracket", "c10": "seal"}
EXPECTED = {"c01": "hold", "c02": "reorder", "c03": "reorder", "c04": "hold", "c05": "reorder", "c06": "hold", "c07": "hold", "c08": "reorder", "c09": "hold", "c10": "reorder"}
ANSWER = {
    "baseline": {"c01": "hold", "c02": "reorder", "c03": "hold", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": None, "c09": "hold", "c10": "unknown"},
    "candidate": {"c01": "hold", "c02": "reorder", "c03": "reorder", "c04": "hold", "c05": "reorder", "c06": "reorder", "c07": "hold", "c08": "reorder", "c09": None, "c10": "reorder"},
}
#: The ``exact`` scorer's output of every case, true as 1 and false as 0; None where the case
#: errored, which no scorer ran on.
EXACT: dict[str, dict[str, float | None]] = {
    "baseline": {"c01": 1.0, "c02": 1.0, "c03": 0.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": None, "c09": 1.0, "c10": 0.0},
    "candidate": {"c01": 1.0, "c02": 1.0, "c03": 1.0, "c04": 1.0, "c05": 1.0, "c06": 0.0, "c07": 1.0, "c08": 1.0, "c09": None, "c10": 1.0},
}
#: The ``gave_answer`` scorer's: false where the answer was ``unknown``.
GAVE_ANSWER: dict[str, dict[str, float | None]] = {
    "baseline": {**dict.fromkeys(CASES, 1.0), "c08": None, "c10": 0.0},
    "candidate": {**dict.fromkeys(CASES, 1.0), "c09": None},
}
#: The case that errored, by version: the exception's class, the op that raised it, the kind of
#: step the reader records for it, and the failure kind TF21's rules reach where the exception
#: is in the file.
ERRORED = {
    "baseline": ("c08", "TimeoutError", "check_stock", "other", "timeout"),
    "candidate": ("c09", "ValueError", "parse_answer", "other", "crash"),
}
#: The candidate's case whose first stock check was refused and tried again: its call's status is
#: ``descendant_error``, and it answered and passed.
RETRIED = ("candidate", "c04")
#: Tokens (input, output, total) and cost in US dollars of each case's call; None where the case
#: made no model call.
USAGE: dict[str, dict[str, tuple[int, int, int, float] | None]] = {
    "baseline": {
        "c01": (71, 1, 72, 3.0000000350582923e-05), "c02": (71, 2, 73, 3.160000036928068e-05), "c03": (71, 1, 72, 3.0000000350582923e-05),
        "c04": (71, 1, 72, 3.0000000350582923e-05), "c05": (71, 2, 73, 3.160000036928068e-05), "c06": (71, 2, 73, 3.160000036928068e-05),
        "c07": (71, 1, 72, 3.0000000350582923e-05), "c08": None, "c09": (71, 1, 72, 3.0000000350582923e-05), "c10": (65, 1, 66, 2.760000032253629e-05),
    },
    "candidate": {
        "c01": (86, 6, 92, 4.400000051418829e-05), "c02": (86, 7, 93, 4.560000053288604e-05), "c03": (86, 7, 93, 4.560000053288604e-05),
        "c04": (86, 6, 92, 4.400000051418829e-05), "c05": (86, 7, 93, 4.560000053288604e-05), "c06": (86, 7, 93, 4.560000053288604e-05),
        "c07": (86, 6, 92, 4.400000051418829e-05), "c08": (86, 7, 93, 4.560000053288604e-05), "c09": (86, 3, 89, 3.920000045809502e-05),
        "c10": (86, 7, 93, 4.560000053288604e-05),
    },
}
#: Weave's own figure for the model's run, in seconds (``output.model_latency``).
LATENCY = {
    "baseline": {"c01": 2.191899061203003, "c02": 0.7834548950195312, "c03": 0.7000281810760498, "c04": 0.6410989761352539, "c05": 0.689913272857666,
                 "c06": 0.6715109348297119, "c07": 0.735914945602417, "c08": 0.027794837951660156, "c09": 0.6178498268127441, "c10": 0.99226975440979},
    "candidate": {"c01": 0.5018119812011719, "c02": 0.46494603157043457, "c03": 0.9024999141693115, "c04": 0.6272168159484863, "c05": 0.4825108051300049,
                  "c06": 0.4905862808227539, "c07": 0.5163478851318359, "c08": 0.7553730010986328, "c09": 0.546410083770752, "c10": 0.7072679996490479},
}
#: The calls under each case's model call, in start order, as (op, raised): every case is a
#: policy lookup, a stock check, a model call and a parse, but for these.
USUAL = (("find_policy", False), ("check_stock", False), ("openai.chat.completions.create", False), ("parse_answer", False))
STEPS = {
    ("baseline", "c08"): (("find_policy", False), ("check_stock", True)),
    ("candidate", "c04"): (("find_policy", False), ("check_stock", True), ("check_stock", False), ("openai.chat.completions.create", False), ("parse_answer", False)),
    ("candidate", "c09"): (("find_policy", False), ("check_stock", False), ("openai.chat.completions.create", False), ("parse_answer", True)),
}
LLM_OP = "openai.chat.completions.create"
MODEL = "gpt-4.1-mini-2025-04-14"
#: The reaction on each case's call; the cases with a thumbs-down also carry a note.
THUMBS_DOWN = {"baseline": ("c03", "c06", "c08", "c10"), "candidate": ("c06", "c09")}
#: The calls of each evaluation's trace.
CALLS = {"old": 20, "new": 20, "baseline": 78, "candidate": 81}
#: The start of each evaluation's first ``predict_and_score`` call, as the import says it.
EARLIEST = {"old": "2026-11-09T20:27:50.520290Z", "new": "2026-11-09T20:27:50.559047Z",
            "baseline": "2026-11-09T20:28:05.644964Z", "candidate": "2026-11-09T20:28:07.996188Z"}
#: The lookup fixture: each question's expected answer, and its ``exact`` in each evaluation
#: (both tries alike).
LOOKUP_EXPECTED = {"q1": "banana", "q2": "apple", "q3": "pear"}
LOOKUP_EXACT = {"old": {"q1": 1.0, "q2": 0.0, "q3": 0.0}, "new": {"q1": 1.0, "q2": 1.0, "q3": 1.0}}
#: Text of the captures that an import must keep nowhere: a prompt's, an input's, an error's, a
#: note's, and the paths and build strings of the machine that ran the evaluation.
CONTENT = (
    "You are a stock desk", "Reply with one word only", "Reorder bracket when stock is below",
    "check_stock timed out after 2.0s", "reply is not the JSON asked for", "rate limit exceeded for check_stock",
    "errored before an answer", "answered unknown, expected reorder", "finish_reason", "slice_weave.py", "/Users/user",
    "site-packages", "Darwin Kernel Version",
)


def steps(version: str, case: str) -> tuple[tuple[str, bool], ...]:
    return STEPS.get((version, case), USUAL)


def passed(version: str, cut: float = 0.5) -> dict[str, bool | None]:
    """Whether each case's ``exact`` met the cut read below; None where it has no score."""
    return {case: None if score is None else score >= cut for case, score in EXACT[version].items()}


def input_key(value: Any) -> str:
    """TF22's key of an input: ``input:`` and 12 hex characters of the SHA-256 of a string as
    written, or of anything else as compact JSON with sorted keys."""
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "input:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def example_row(case: str) -> dict[str, str]:
    """The dataset row of a case, as the files hold it (without its ``_ref``)."""
    if case in QUESTIONS:
        return {"id": case, "question": case, "expected": LOOKUP_EXPECTED[case]}
    return {"id": case, "case": case, "item": ITEM[case], "expected": EXPECTED[case]}


def input_chars(case: str) -> int:
    return sum(len(value) for value in example_row(case).values())


#: Each case's input key, and the case each key is.
KEY = {case: input_key(example_row(case)) for case in (*CASES, *QUESTIONS)}
CASE_OF = {key: case for case, key in KEY.items()}


def _digests() -> dict[str, str]:
    """Each case's dataset row digest, read off the references in the expanded answers."""
    out: dict[str, str] = {}
    for name in ("baseline", "old"):
        for line in export(name, "expanded")[0].read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            if op(call) == ROW:
                example = call["inputs"]["example"]
                out[example["id"]] = example["_ref"].rsplit("/", 1)[1]
    return out


def op(call: Mapping[str, Any]) -> str:
    """The op a call names: the last part of its ``op_name``, without the digest."""
    return str(call["op_name"]).rsplit("/", 1)[-1].split(":", 1)[0]


#: Each case's dataset row digest (the same in both versions: the row is the same row).
DIGEST = _digests()
CASE_OF.update({digest: case for case, digest in DIGEST.items()})


def named(case: str) -> str:
    """A stored case as the fixture names it: a row digest or an input's key as the case it is."""
    return CASE_OF.get(case, case)


# ---------- argv ----------


def wv_argv(files: Sequence[Path | str] | Path | str, root: Path | str, run: str | None, *extra: Any,
            case: str | None = "example", outcome: str | None = "score:exact",
            cut: str | None = "0.5", side: str | None = "--below") -> list[str]:
    """``weave FILE ... --store ROOT --run NAME`` with the reader's flags: the case from the
    reference to the dataset row, the outcome from the ``exact`` scorer at 0.5. Pass
    ``cut=None`` with an outcome that reads no score."""
    paths = [files] if isinstance(files, (str, Path)) else list(files)
    argv = ["weave", *[str(p) for p in paths], "--store", str(root)]
    if run is not None:
        argv += ["--run", run]
    if case is not None:
        argv += ["--case-from", case]
    if outcome is not None:
        argv += ["--outcome-from", outcome]
    if cut is not None and outcome is not None and outcome != "status":
        argv += ["--cut", cut]
        if side is not None:
            argv.append(side)
    return [*argv, *[str(e) for e in extra]]


def by_status(files: Sequence[Path | str] | Path | str, root: Path | str, run: str | None, *extra: Any, case: str = "example") -> list[str]:
    return wv_argv(files, root, run, *extra, case=case, outcome="status", cut=None)


def picked(name: str, kind: str) -> list[str]:
    """The flag that picks one evaluation out of an export that holds several: the page's
    downloads hold all four."""
    return ["--evaluation", evaluation(name)] if kind in UI_EXPORTS else []


def of(name: str, kind: str, root: Path | str, run: str | None, *extra: Any, mode: str = "exact", **flags: Any) -> list[str]:
    """The command that reads one export of one evaluation: its files, the evaluation picked
    where the file holds several, and a case every row of that export can give (unless
    ``case`` says another). ``mode`` ``status`` reads the outcome by the error."""
    flags.setdefault("case", default_case(kind))
    make = by_status if mode == "status" else wv_argv
    return make(export(name, kind), root, run, *picked(name, kind), *extra, **flags)


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
    assert "Traceback" not in result.err, result.err
    return lines[0]


def wrong_line(result: Result) -> str:
    """Exit 2, nothing on stdout, an ``error:`` line."""
    assert result.code == 2 and result.out == "", result.out + result.err
    lines = [line for line in result.err.splitlines() if line.startswith("error: ")]
    assert lines, result.err
    return lines[0]


def recs(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """The stored signals record of each case of a run with one try a case, by the fixture's
    name for the case."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records(root, run):
        case = named(rec["case"])
        assert case not in out, case
        out[case] = rec
    return out


def tries(root: Path, run: str) -> dict[tuple[str, int], dict[str, Any]]:
    """The stored signals record of each try of each case."""
    return {(named(rec["case"]), rec["repeat"]): rec for rec in records(root, run)}


def metas(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's whole ``meta`` as the store holds it."""
    from tf21_support import frame

    return {named(m["trace_signals"]["case"]): dict(m) for m in frame(root, run)["meta"]}


def columns(root: Path, run: str) -> dict[str, dict[str, Any]]:
    """Each case's stored columns a verb reads: ``outcome``, ``error``, ``t``, ``wall_time``."""
    from poisson_prove.store import Store

    df = Store(root).read(run, meta=False, trace="envelope")
    out = {}
    for r in df.to_dict("records"):
        out[named(r["config"]["case"])] = r
    return out


def outcomes(root: Path, run: str) -> dict[str, Any]:
    return {case: r["outcome"] for case, r in columns(root, run).items()}


def span_id(call_id: str) -> str:
    """A call's id as the store keeps it for a span: its hexadecimal digits, without the dashes
    Weave writes between them."""
    return call_id.replace("-", "")


def stored_spans(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    trace = row["trace"]
    held: list[dict[str, Any]] = (trace if isinstance(trace, dict) else json.loads(trace))["spans"]
    return held


def stored_bytes(root: Path) -> bytes:
    """Every file under ``root``, and every Parquet part decoded cell by cell."""
    import pyarrow.parquet as pq

    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out.append(path.read_bytes())
        if path.suffix == ".parquet":
            out.append(json.dumps(pq.read_table(path).to_pylist(), default=str).encode("utf-8"))
    return b"\n".join(out)


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def approx(a: Any, b: Any, tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def tally(data: Mapping[str, Any]) -> dict[str, int]:
    """The summary's outcomes that have a row."""
    return {word: n for word, n in data["outcomes"].items() if n}


# ---------- the captures, read and edited ----------


def calls_of(path: Path) -> list[dict[str, Any]]:
    """The calls a committed ``.jsonl`` or ``.json`` export holds."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    held: list[dict[str, Any]] = json.loads(text)
    return held


def cells_of(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """The header and the rows (cells as text) of a committed ``.csv`` or ``.tsv`` export."""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t" if path.suffix == ".tsv" else ",")
        return list(reader.fieldnames or []), [dict(r) for r in reader]


def of_evaluation(calls: Sequence[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """The ``predict_and_score`` calls of one evaluation, in the order they started."""
    held = [c for c in calls if op(c) == ROW and c["parent_id"] == CALL_ID[name]]
    return sorted(held, key=lambda c: c["started_at"])


def case_of(call: Mapping[str, Any]) -> str:
    """The fixture's name for the case a ``predict_and_score`` call ran: its row's ``id``, or
    the case its reference's digest is."""
    example = call["inputs"]["example"]
    if isinstance(example, dict) and "id" in example:
        return str(example["id"])
    ref = example if isinstance(example, str) else example["_ref"]
    return CASE_OF[ref.rsplit("/", 1)[1]]


def rows_by_case(calls: Sequence[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    """Each case's ``predict_and_score`` call, for an evaluation with one try a case."""
    return {case_of(c): c for c in of_evaluation(calls, name)}


def under(calls: Sequence[dict[str, Any]], call: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The calls directly under ``call``, in start order."""
    return sorted((c for c in calls if c["parent_id"] == call["id"]), key=lambda c: c["started_at"])


def model_call(calls: Sequence[dict[str, Any]], row: Mapping[str, Any]) -> dict[str, Any]:
    """The model's call under a row: the one made on the row's model."""
    return next(c for c in under(calls, row) if c["inputs"].get("self") == row["inputs"]["model"])


def work_calls(calls: Sequence[dict[str, Any]], row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The calls under the row's model call: the steps the agent took, in start order."""
    return under(calls, model_call(calls, row))


def exception(kind: str, message: str) -> str:
    """An exception as Weave saves one: a JSON object in a string."""
    return json.dumps({"type": kind, "message": message, "traceback": [{"filename": "/venv/lib/python3.12/site-packages/x.py", "line_number": 1, "function_name": "f", "text": "raise"}]})


def write_calls(path: Path, calls: Sequence[Mapping[str, Any]]) -> Path:
    """Calls written as a ``.jsonl`` file (one a line) or a ``.json`` file (a list)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".jsonl":
        path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in calls), encoding="utf-8")
    else:
        path.write_text(json.dumps(list(calls), ensure_ascii=False), encoding="utf-8")
    return path


def edited(tmp: Path, name: str, kind: str, edit: Callable[[list[dict[str, Any]]], None], stem: str = "edited") -> Path:
    """One export of calls (the service's answer, or the page's JSON or JSON Lines) with ``edit``
    applied to a deep copy of its calls, in a file of its own extension."""
    assert SHAPE[kind] == "call", kind
    source = export(name, kind)[0]
    calls = copy.deepcopy(calls_of(source))
    edit(calls)
    return write_calls(tmp / f"{stem}{source.suffix}", calls)


def edited_table(tmp: Path, kind: str, edit: Callable[[list[dict[str, str]]], None] | None = None,
                 header: Callable[[list[str]], list[str]] | None = None, stem: str = "edited") -> Path:
    """The page's table with ``edit`` applied to its rows (cells as text) and ``header`` to its
    columns, written back as the page writes it."""
    assert SHAPE[kind] == "table", kind
    source = export("baseline", kind)[0]
    fields, rows = cells_of(source)
    if edit is not None:
        edit(rows)
    if header is not None:
        fields = header(fields)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n", delimiter="\t" if source.suffix == ".tsv" else ",")
    writer.writeheader()
    writer.writerows(rows)
    path = tmp / f"{stem}{source.suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.getvalue(), encoding="utf-8")
    return path


def table_rows(rows: Sequence[dict[str, str]], name: str) -> dict[str, dict[str, str]]:
    """Each case's row of the page's table, for one evaluation of one try a case."""
    return {r["inputs.example.id"]: r for r in rows if r["parent_id"] == CALL_ID[name]}


def copy_fixture(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest


# ---------- the fake transport ----------


class Refuse(Exception):
    """A request the captures hold no answer to."""


def _without_page(body: Mapping[str, Any]) -> str:
    return json.dumps({k: v for k, v in body.items() if k not in ("limit", "offset")}, sort_keys=True)


class Transport:
    """Stands in for ``poisson_trace.ingest.pulling.send``: answers each request with the
    response Weave gave to that request, as ``api/requests.json`` records it, and keeps every
    call. A request that names a ``limit`` and an ``offset`` and that no capture answers as it
    stands is answered with those lines of the committed answer to the same request without
    them: for the one request the captures hold both ways (the candidate's trace, in pages of
    40) that is byte for byte what Weave answered (TF26-3 holds it). Any other request fails
    the test. ``script`` maps a count of calls (from 1) to a canned ``(status, headers, body)``
    or an exception to raise in its place; ``host`` is where the requests are expected to go."""

    def __init__(self, script: Mapping[int, Any] | None = None, host: str = HOST) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script = dict(script or {})
        self.host = host
        self.table = json.loads((API / "requests.json").read_text(encoding="utf-8"))

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
        assert isinstance(method, str) and isinstance(url, str), (method, url)
        assert body is None or isinstance(body, bytes), type(body)
        assert isinstance(timeout, (int, float)) and 0 < timeout <= 120, timeout
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        canned = self.script.get(len(self.calls))
        if isinstance(canned, BaseException):
            raise canned
        if canned is not None:
            return canned
        return 200, {"Content-Type": "application/jsonl"}, self.answer(method, url, body)

    def answer(self, method: str, url: str, body: bytes | None) -> bytes:
        assert url == self.host + QUERY, f"a request went to {url}, not to {self.host + QUERY}"
        assert method.upper() == "POST" and body is not None, (method, body)
        asked = json.loads(body.decode("utf-8"))
        assert isinstance(asked, dict), asked
        whole = json.dumps(asked, sort_keys=True)
        for entry in self.table:
            if entry["status"] == 200 and json.dumps(entry["body"], sort_keys=True) == whole:
                return (API / entry["file"]).read_bytes()
        limit, offset = asked.get("limit"), asked.get("offset")
        if isinstance(limit, int) and isinstance(offset, int) and limit > 0 and offset >= 0 and not isinstance(limit, bool):
            for entry in self.table:
                if entry["status"] == 200 and "limit" not in entry["body"] and json.dumps(entry["body"], sort_keys=True) == _without_page(asked):
                    lines = (API / entry["file"]).read_bytes().splitlines(keepends=True)
                    return b"".join(lines[offset:offset + limit])
        raise Refuse(f"the pull asked for something no capture answers: {method} {url} {body!r}")

    def bodies(self) -> list[dict[str, Any]]:
        """The JSON each call sent."""
        return [json.loads(c["body"].decode("utf-8")) for c in self.calls]

    def kinds(self) -> list[str]:
        """Each call as what it asked for: the project's root calls, or a trace's calls."""
        out = []
        for body in self.bodies():
            asked = body.get("filter") or {}
            out.append(ROOTS if asked == {"trace_roots_only": True} else TRACE if set(asked) == {"trace_ids"} else "other")
        return out


ROOTS = "the root calls"
TRACE = "a trace's calls"
#: A whole pull at the default page size: each query is asked until a page comes back empty.
WHOLE = [ROOTS, ROOTS, TRACE, TRACE]
#: The variables a pull might read, all taken out of the environment while a test pulls.
_VARIABLES = (KEY_VARIABLE, ENDPOINT_VARIABLE, "WANDB_BASE_URL", "WANDB_ENTITY", "WANDB_PROJECT", "WEAVE_DISABLED", "LANGSMITH_API_KEY",
              "LANGSMITH_ENDPOINT", "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT", "BRAINTRUST_API_KEY", "BRAINTRUST_API_URL")


@contextlib.contextmanager
def pulling(transport: Transport | Callable[..., Any] | None = None, key: str | None = PLANTED_KEY,
            endpoint: str | None = None) -> Iterator[tuple[Any, list[float]]]:
    """The pull's seams replaced for the block: ``pulling.send`` by ``transport`` (a new
    ``Transport`` when None), ``pulling.sleep`` by a recorder; the key and the endpoint set (or
    unset, when None) in the environment; and every socket connection refused, so that a pull
    that goes round the seam fails instead of reaching the network. Yields the transport and
    the list of waits asked for."""
    import socket
    from importlib import import_module

    module = import_module("poisson_trace.ingest.pulling")
    sender = Transport() if transport is None else transport
    waits: list[float] = []
    old_send, old_sleep = module.send, module.sleep
    saved = {name: os.environ.get(name) for name in _VARIABLES}

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a test reached for the network")

    old_connect, old_create = socket.socket.connect, socket.create_connection
    try:
        module.send = sender
        module.sleep = waits.append
        socket.socket.connect = no_network  # type: ignore[method-assign]
        socket.create_connection = no_network
        for name in saved:
            os.environ.pop(name, None)
        if key is not None:
            os.environ[KEY_VARIABLE] = key
        if endpoint is not None:
            os.environ[ENDPOINT_VARIABLE] = endpoint
        yield sender, waits
    finally:
        module.send, module.sleep = old_send, old_sleep
        socket.socket.connect = old_connect  # type: ignore[method-assign]
        socket.create_connection = old_create
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def never() -> Transport:
    """A transport that fails the test if anything is asked of it."""
    class Never(Transport):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a request was made")

    return Never()


def basic(key: str = PLANTED_KEY) -> str:
    """The ``Authorization`` header Weave's service takes: basic auth, the user ``api``."""
    import base64

    return "Basic " + base64.b64encode(f"api:{key}".encode()).decode("ascii")


def address(name: str) -> str:
    return f"weave:{PROJECT_ID}/{evaluation(name)}"


def raw_folder(root: Path, run: str) -> Path:
    return root / ".poisson" / "raw" / "weave" / run


def raw_lines(root: Path, run: str) -> list[dict[str, Any]]:
    text = (raw_folder(root, run) / "raw.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------- each export imported once, for the tests that only read it ----------

_WORLD: dict[tuple[Any, ...], tuple[Path, dict[str, Any]]] = {}
RUN = "r"


def world(factory: Any, name: str, kind: str, mode: str = "exact") -> tuple[Path, dict[str, Any]]:
    """The export ``kind`` of the evaluation ``name`` imported once into a store of its own as
    the run ``RUN``, with its ``--json`` summary: by the ``exact`` score at 0.5 (``mode``
    ``exact``) or by whether the case errored (``status``). Read-only: a test that writes
    takes its own."""
    key = (name, kind, mode)
    if key not in _WORLD:
        root = factory.mktemp(f"wv-{name}-{kind}-{mode}") / "st"
        _WORLD[key] = (root, imported(of(name, kind, root, RUN, mode=mode)))
    return _WORLD[key]
