"""TF26-1 to TF26-3: the committed Weave captures, and the facts the reader's shapes rest on (spec
section 18.3.4; ``tests/fixtures/PROVENANCE.md``, "Added for the Weave captures"; the captures'
log and its gaps). These pass on main: they hold the files, not the reader.

- TF26-1: every capture the provenance lists is there and reads: the four evaluations' answers
  (20, 20, 78 and 81 calls), each again with its example expanded, the candidate's with neither
  include flag and in pages of 40 (40, 40, 1 and none), the project's root calls, the Traces
  page's downloads in its four formats for both views (4 rows, and 32: 6, 6, 10 and 10), and
  the list of the 14 requests made.
- TF26-2: what the shapes rest on. A ``predict_and_score`` call holds the verdict in its
  ``output`` and a reference to its dataset row in ``inputs.example``; the expanded answer and
  the page's JSON hold the row itself with its ``_ref``, the same row digest in both versions;
  the page's table holds the row's values as columns and no reference. Costs and feedback are
  under ``summary.weave`` and only where asked for: the plain answer and every one of the
  page's downloads hold neither. A case whose model raised is ``descendant_error`` with a null
  output and no score, its own ``exception`` null; a case that retried a failed step is
  ``descendant_error`` too, and answered. The page's downloads hold no call under a row. The
  page's JSON and JSON Lines hold the same calls, and its CSV and TSV the same cells. The
  transport's one rule that is not a capture is checked against the one request the captures
  hold both ways: the lines of the whole answer are the pages Weave answered with.
- TF26-3: the facts the spec states that the captures correct or sharpen: costs are at
  ``summary.weave.costs.<model>`` and feedback at ``summary.weave.feedback`` (not
  ``summary.costs`` and ``summary.feedback``); the page offers no Parquet; the page's table
  holds a model's total tokens and no prompt or completion count; a scorer's output is true or
  false, under the scorer's name twice; the lookup fixture's output is a reference, not text;
  no call holds a time to first token; only the model's call is marked with a kind.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tf26_support import (
    API, CALL_ID, CALLS, CASES, DIGEST, EVALUATE, EVALUATION, EXACT, LLM_OP, MODEL, NAMES, PROJECT_ID, QUESTIONS, RETRIED, ROOTS_ONLY, ROW,
    SHOWN, TRACE_ID, UI, UI_CALLS, UI_TABLES, VERSIONS, Transport, calls_of, case_of, cells_of, export, model_call, of_evaluation, op,
    picked, rows_by_case, under, work_calls,
)

ROWS = {"old": 6, "new": 6, "baseline": 10, "candidate": 10}


# ---------- TF26-1 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf26_1_every_answer_of_every_evaluation_is_committed_and_reads(name: str) -> None:
    for kind in ("pull", "expanded"):
        (path,) = export(name, kind)
        calls = calls_of(path)
        assert len(calls) == CALLS[name], (kind, len(calls))
        assert [c["started_at"] for c in calls] == sorted(c["started_at"] for c in calls), "sorted by its start"
        assert {c["trace_id"] for c in calls} == {TRACE_ID[name]} and {c["project_id"] for c in calls} == {PROJECT_ID}
        root = calls[0]
        assert root["id"] == CALL_ID[name] and root["parent_id"] is None and op(root) == EVALUATE
        assert root["display_name"] == SHOWN[name] and EVALUATION[name] in root["inputs"]["self"]
        assert len(of_evaluation(calls, name)) == ROWS[name]


def test_tf26_1_the_candidate_s_plain_answer_and_its_pages() -> None:
    assert len(calls_of(export("candidate", "plain")[0])) == 81
    pages = export("candidate", "pages")
    assert [len(calls_of(p)) for p in pages] == [40, 40, 1, 0]
    assert pages[3].read_bytes() == b""
    whole = [c["id"] for c in calls_of(export("candidate", "pull")[0])]
    assert [c["id"] for p in pages for c in calls_of(p)] == whole


def test_tf26_1_the_root_calls_and_the_requests() -> None:
    roots = calls_of(API / "roots.jsonl")
    assert [c["id"] for c in roots] == [CALL_ID[name] for name in NAMES]
    assert all(op(c) == EVALUATE and c["parent_id"] is None for c in roots)
    table = json.loads((API / "requests.json").read_text(encoding="utf-8"))
    assert len(table) == 14 and all(e["status"] == 200 and e["method"] == "POST" for e in table)
    assert {e["url"] for e in table} == {"https://trace.wandb.ai/calls/stream_query"}
    assert sorted(e["file"] for e in table) == sorted(p.name for p in API.iterdir() if p.name != "requests.json")
    # every request but the plain one asked for costs and feedback; none bounded the calls by time
    for entry in table:
        body = entry["body"]
        plain = ".plain." in entry["file"]
        assert body["include_costs"] is (not plain) and body["include_feedback"] is (not plain), entry["file"]
        assert set(body) <= {"project_id", "sort_by", "include_costs", "include_feedback", "filter", "expand_columns", "limit", "offset"}
        assert body["project_id"] == PROJECT_ID and body["sort_by"] == [{"field": "started_at", "direction": "asc"}]


def test_tf26_1_the_page_s_downloads_in_four_formats_for_both_views() -> None:
    assert sorted(p.name for p in UI.iterdir()) == sorted(
        f"{view}.{ext}" for view in ("predict-and-score", "traces-roots") for ext in ("csv", "tsv", "json", "jsonl"))
    for kind in UI_CALLS:
        calls = calls_of(export("baseline", kind)[0])
        assert len(calls) == 32 and all(op(c) == ROW for c in calls)
        assert {name: len(of_evaluation(calls, name)) for name in NAMES} == ROWS
    assert len(list(UI.iterdir())) == 8
    for kind in UI_TABLES:
        fields, rows = cells_of(export("baseline", kind)[0])
        assert len(rows) == 32 and len(fields) == 65
        assert picked("old", kind), "the page's download holds every evaluation, so a command on it picks one"
    assert not list(UI.glob("*.parquet")), "the page offers no Parquet"
    for path in ROOTS_ONLY[1:3]:
        assert [op(c) for c in calls_of(path)] == [EVALUATE] * 4
    for path in ROOTS_ONLY[3:]:
        fields, rows = cells_of(path)
        assert len(rows) == 4 and len(fields) == 47 and "parent_id" not in fields


# ---------- TF26-2 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf26_2_a_row_holds_its_verdict_and_a_reference_to_its_dataset_row(name: str) -> None:
    plain = of_evaluation(calls_of(export(name, "pull")[0]), name)
    expanded = of_evaluation(calls_of(export(name, "expanded")[0]), name)
    page = of_evaluation(calls_of(export(name, "ui-json")[0]), name)
    assert [c["id"] for c in plain] == [c["id"] for c in expanded] == [c["id"] for c in page]
    for ref, row, shown in zip(plain, expanded, page, strict=True):
        assert set(ref["output"]) == {"output", "scores", "model_latency"}
        assert isinstance(ref["inputs"]["example"], str) and ref["inputs"]["example"].startswith("weave:///")
        example = row["inputs"]["example"]
        assert example["_ref"] == ref["inputs"]["example"] and "/attr/rows/id/" in example["_ref"]
        assert shown["inputs"]["example"] == example
        assert DIGEST[example["id"]] == example["_ref"].rsplit("/", 1)[1]
        # the answers differ in the example alone
        assert {k: v for k, v in row.items() if k != "inputs"} == {k: v for k, v in ref.items() if k != "inputs"}


def test_tf26_2_both_versions_ran_the_same_dataset_rows() -> None:
    for a, b, cases in (("baseline", "candidate", CASES), ("old", "new", QUESTIONS)):
        left = {case_of(c): c["inputs"]["example"] for c in of_evaluation(calls_of(export(a, "pull")[0]), a)}
        right = {case_of(c): c["inputs"]["example"] for c in of_evaluation(calls_of(export(b, "pull")[0]), b)}
        assert left == right and sorted(left) == list(cases)


def test_tf26_2_costs_and_feedback_are_there_only_where_asked_for() -> None:
    asked = calls_of(export("candidate", "pull")[0])
    plain = calls_of(export("candidate", "plain")[0])
    page = calls_of(export("candidate", "ui-json")[0])
    assert all("feedback" in c["summary"]["weave"] for c in asked)
    assert sum(1 for c in asked if "costs" in c["summary"]["weave"]) == 31
    for call in (*plain, *page):
        assert "costs" not in call["summary"]["weave"] and "feedback" not in call["summary"]["weave"], call["id"]
    # the token counts are there either way
    assert [c["summary"].get("usage") for c in plain] == [c["summary"].get("usage") for c in asked]
    for kind in UI_TABLES:
        fields, rows = cells_of(export("candidate", kind)[0])
        held = [f for f in fields if f.startswith(("summary.weave.costs.", "summary.weave.feedback."))]
        assert len(held) > 20 and all(row[f] == "" for row in rows for f in held), kind


@pytest.mark.parametrize("version", VERSIONS)
def test_tf26_2_an_errored_case_and_a_retried_one(version: str) -> None:
    calls = calls_of(export(version, "pull")[0])
    rows = rows_by_case(calls, version)
    bad = next(case for case, score in EXACT[version].items() if score is None)
    row = rows[bad]
    assert row["summary"]["weave"]["status"] == "descendant_error" and row["exception"] is None
    assert row["output"]["output"] is None and row["output"]["scores"] == {}
    model = model_call(calls, row)
    assert model["summary"]["weave"]["status"] == "error" and json.loads(model["exception"])["type"]
    assert [op(c) for c in under(calls, row)] == [op(model)], "no scorer ran on a case whose model raised"
    assert work_calls(calls, row)[-1]["summary"]["weave"]["status"] == "error"
    if version == RETRIED[0]:
        again = rows[RETRIED[1]]
        assert again["summary"]["weave"]["status"] == "descendant_error" and again["output"]["output"] == "hold"
        assert again["output"]["scores"] == {"exact": {"exact": True}, "gave_answer": {"gave_answer": True}}
        assert model_call(calls, again)["summary"]["weave"]["status"] == "descendant_error"
    for case, other in rows.items():
        if case not in (bad, RETRIED[1] if version == RETRIED[0] else None):
            assert other["summary"]["weave"]["status"] == "success", case


def test_tf26_2_the_page_s_downloads_hold_the_rows_alone_and_agree_with_each_other() -> None:
    as_json, as_lines = calls_of(export("baseline", "ui-json")[0]), calls_of(export("baseline", "ui-jsonl")[0])
    assert as_json == as_lines
    assert all(c["exception"] is None for c in as_json)
    ids = {c["id"] for c in as_json}
    assert not [c for c in as_json if c["parent_id"] in ids], "no call under a row"
    (csv_fields, csv_rows), (tsv_fields, tsv_rows) = cells_of(export("baseline", "ui-csv")[0]), cells_of(export("baseline", "ui-tsv")[0])
    assert csv_fields == tsv_fields and csv_rows == tsv_rows
    assert [r["id"] for r in csv_rows] == [c["id"] for c in as_json]
    assert "inputs.example._ref" not in csv_fields and "exception" not in csv_fields
    for row, call in zip(csv_rows, as_json, strict=True):
        example = {k: v for k, v in call["inputs"]["example"].items() if k != "_ref"}
        assert {k: row[f"inputs.example.{k}"] for k in example} == example
        assert row["summary.weave.status"] == call["summary"]["weave"]["status"]
        assert float(row["output.model_latency"]) == call["output"]["model_latency"]


def test_tf26_2_the_lines_of_a_whole_answer_are_the_pages_weave_answered_with() -> None:
    """The one answer the tests' transport gives that is no capture: a request with a limit
    and an offset is answered with those lines of the committed answer to the request without
    them. For the candidate's trace in pages of 40, which the captures hold both ways, that is
    byte for byte what Weave answered."""
    table = json.loads((API / "requests.json").read_text(encoding="utf-8"))
    whole = next(e for e in table if e["file"] == "trace-fixture-slice-candidate.jsonl")
    paged = [e for e in table if ".page-" in e["file"]]
    assert [(e["body"]["limit"], e["body"]["offset"]) for e in paged] == [(40, 0), (40, 40), (40, 80), (40, 120)]
    lines = (API / whole["file"]).read_bytes().splitlines(keepends=True)
    for entry in paged:
        body = entry["body"]
        assert {k: v for k, v in body.items() if k not in ("limit", "offset")} == whole["body"]
        assert b"".join(lines[body["offset"]:body["offset"] + body["limit"]]) == (API / entry["file"]).read_bytes(), entry["file"]
    # and the transport answers a page of another size from the same lines
    sent = Transport()
    answer = sent.answer("POST", "https://trace.wandb.ai/calls/stream_query", json.dumps({**whole["body"], "limit": 7, "offset": 77}).encode())
    assert answer == b"".join(lines[77:81]) and len(answer.splitlines()) == 4


# ---------- TF26-3 ----------


def test_tf26_3_costs_and_feedback_are_under_summary_weave() -> None:
    for name in NAMES:
        for call in calls_of(export(name, "pull")[0]):
            assert "costs" not in call["summary"] and "feedback" not in call["summary"], call["id"]
            assert isinstance(call["summary"]["weave"]["feedback"], list)
    row = rows_by_case(calls_of(export("baseline", "pull")[0]), "baseline")["c01"]
    cost = row["summary"]["weave"]["costs"][MODEL]
    assert cost["prompt_tokens_total_cost"] > 0 and cost["completion_tokens_total_cost"] > 0
    assert cost["prompt_token_cost_unit"] == cost["completion_token_cost_unit"] == "USD"
    assert row["summary"]["usage"][MODEL]["requests"] == 1
    types = {f["feedback_type"] for call in calls_of(export("baseline", "pull")[0]) for f in call["summary"]["weave"]["feedback"]}
    assert types == {"wandb.reaction.1", "wandb.note.1", "wandb.runnable.exact", "wandb.runnable.gave_answer"}


def test_tf26_3_the_page_s_table_holds_a_total_and_no_prompt_or_completion_count() -> None:
    for kind in UI_TABLES:
        fields, _ = cells_of(export("baseline", kind)[0])
        usage = [f for f in fields if f.startswith(f"summary.usage.{MODEL}.")]
        assert f"summary.usage.{MODEL}.total_tokens" in usage and f"summary.usage.{MODEL}.requests" in usage
        assert not [f for f in usage if f.endswith((".prompt_tokens", ".completion_tokens"))], usage
    row = rows_by_case(calls_of(export("baseline", "ui-json")[0]), "baseline")["c01"]
    assert row["summary"]["usage"][MODEL]["prompt_tokens"] == 71, "the page's JSON holds them"


def test_tf26_3_a_scorer_s_output_is_true_or_false_and_the_lookup_s_answer_a_reference() -> None:
    values: set[Any] = set()
    for name in NAMES:
        for row in of_evaluation(calls_of(export(name, "pull")[0]), name):
            for scorer, out in row["output"]["scores"].items():
                assert list(out) == [scorer]
                values.add(out[scorer])
    assert values == {True, False}
    for name in ("old", "new"):
        for kind in ("pull", "expanded", "ui-json"):
            for row in of_evaluation(calls_of(export(name, kind)[0]), name):
                assert str(row["output"]["output"]).startswith("weave:///"), (name, kind)
        _, cells = cells_of(export(name, "ui-csv")[0])
        assert all(r["output.output"].startswith("weave:///") for r in cells if r["parent_id"] == CALL_ID[name])


def test_tf26_3_no_time_to_first_token_and_one_kind() -> None:
    kinds: dict[str, set[Any]] = {}
    for name in NAMES:
        for call in calls_of(export(name, "pull")[0]):
            assert "first_token" not in json.dumps(call) and "ttft" not in json.dumps(call).lower()
            kinds.setdefault(op(call), set()).add(call["attributes"]["weave"].get("kind"))
    assert kinds[LLM_OP] == {"llm"}
    assert all(held == {None} for name, held in kinds.items() if name != LLM_OP), kinds
