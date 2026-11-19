"""TF25-1 to TF25-3: the committed Braintrust captures, and the facts the reader's shapes rest on
(``tests/fixtures/PROVENANCE.md``). These hold the files, not the reader.

- TF25-1: every capture the provenance lists is there and reads: the four experiments' fetch
  (18, 18, 85 and 88 span events), the three BTQL shapes of each, the candidate's fetch and
  spans query in pages of 25 (25, 25, 25, 13 and none), the page's JSON and CSV of each (6, 6,
  10 and 10 rows), the experiments' listing and the list of the 28 requests made.
- TF25-2: what the shapes rest on. In the span shape the root's ``scores`` is null and each
  score is on a child span of type ``score``; the summary and the page's rows carry them. The
  fetch and the ``spans`` query hold the same events in the same order, ``traces`` the same in
  another. The page's rows carry no id of any kind, and its CSV holds the same rows with nine
  columns as cells of JSON. An errored case has a traceback on its step, its task and its root,
  a null output, no score span, and a root whose metadata is null. The slice's roots carry the
  dataset record's id; the lookup fixture's carry none. A whole fetch ends with a cursor, and
  the page a cursor at the end is answered with has no event and no cursor.
- TF25-3: the facts of Braintrust's exports that the captures correct or sharpen: no row holds a
  ``dataset_record_id`` (the record is ``origin.id``); a span's total is ``metrics.tokens`` and
  a summary row's ``metrics.total_tokens``; the summary's ``metrics.duration`` is the task
  span's, not the root's; the summary cuts an error short, so its class is not in that shape;
  the page's classification is a string of JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tf25_support import (
    API, CASES, CSV_JSON, EVENTS, EXPERIMENT_ID, EXPERIMENTS, EXPORTS, LOOKUP, PAGED, ROW_EXPORTS, SPAN_EXPORTS, UI, VERSIONS,
    end_cursors, export, is_root, roots, rows_of, span_type, trace_rows,
)

ROWS = {"old": 6, "new": 6, "slice-baseline": 10, "slice-candidate": 10}
ID_KEYS = ("id", "span_id", "root_span_id", "span_parents", "experiment_id", "project_id", "origin", "_xact_id", "_pagination_key")


# ---------- TF25-1 ----------


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_1_every_export_of_every_experiment_is_committed_and_reads(name: str) -> None:
    for kind in EXPORTS:
        (path,) = export(name, kind)
        assert path.is_file(), path
        rows = rows_of(path)
        assert len(rows) == (EVENTS[name] if kind in SPAN_EXPORTS else ROWS[name]), (kind, len(rows))
    doc = json.loads(export(name, "fetch")[0].read_text(encoding="utf-8"))
    assert set(doc) == {"events", "cursor"}
    for kind in ("btql-spans", "btql-traces", "summary"):
        doc = json.loads(export(name, kind)[0].read_text(encoding="utf-8"))
        assert {"data", "schema", "cursor"} <= set(doc), (kind, sorted(doc))


def test_tf25_1_the_candidate_s_pages() -> None:
    for kind in PAGED:
        sizes = [len(rows_of(p)) for p in export("candidate", kind)]
        assert sizes == [25, 25, 25, 13, 0], (kind, sizes)
        paged = [r["id"] for p in export("candidate", kind) for r in rows_of(p)]
        whole = [r["id"] for r in rows_of(export("candidate", "fetch" if kind == "fetch-pages" else "btql-spans")[0])]
        assert paged == whole, kind


def test_tf25_1_the_listing_and_the_requests() -> None:
    listing = json.loads((API / "experiments.json").read_text(encoding="utf-8"))
    assert {o["name"]: o["id"] for o in listing["objects"]} == EXPERIMENT_ID
    requests = json.loads((API / "requests.json").read_text(encoding="utf-8"))
    assert len(requests) == 28 and [r["status"] for r in requests].count(429) == 1
    assert all(r["file"] is None for r in requests if r["status"] != 200)
    assert all((API / r["file"]).is_file() for r in requests if r["status"] == 200)
    assert all("Authorization" not in json.dumps(r) and "sk-" not in json.dumps(r) for r in requests)
    assert sorted(p.name for p in UI.iterdir()) == sorted(f"{name}.{ext}" for name in EXPERIMENTS for ext in ("csv", "json"))


# ---------- TF25-2 ----------


@pytest.mark.parametrize("name", EXPERIMENTS)
@pytest.mark.parametrize("kind", SPAN_EXPORTS)
def test_tf25_2_in_the_span_shape_the_scores_are_on_child_spans(name: str, kind: str) -> None:
    rows = rows_of(export(name, kind)[0])
    tops = [r for r in rows if is_root(r)]
    assert len(tops) == ROWS[name] and all(r["is_root"] is True and r["scores"] is None for r in tops)
    assert all(span_type(r) == "eval" for r in tops)
    scored = [r for r in rows if r["scores"]]
    assert scored and all(span_type(r) == "score" and not is_root(r) for r in scored)
    assert all(len(r["span_parents"]) == 1 for r in rows if not is_root(r))
    assert {span_type(r) for r in rows} <= {"eval", "task", "function", "tool", "llm", "score", "classifier"}


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_2_the_three_span_exports_hold_the_same_events(name: str) -> None:
    fetch, spans, traces = (rows_of(export(name, kind)[0]) for kind in SPAN_EXPORTS)
    assert fetch == spans
    assert sorted(traces, key=lambda r: r["id"]) == sorted(fetch, key=lambda r: r["id"])
    assert [r["id"] for r in traces] != [r["id"] for r in fetch]


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_2_the_summary_and_the_page_s_rows_carry_the_scores_and_the_page_s_no_id(name: str) -> None:
    summary = rows_of(export(name, "summary")[0])
    assert all("comparison_key" in r and "span_type_info" in r and r["id"] and r["span_id"] for r in summary)
    assert {r["id"] for r in summary} == {r["id"] for r in rows_of(export(name, "fetch")[0]) if is_root(r)}
    for kind in ("ui-json", "ui-csv"):
        rows = rows_of(export(name, kind)[0])
        assert not [key for r in rows for key in ID_KEYS if key in r], kind
        assert all(isinstance(r["scores"], dict) and isinstance(r["metrics"], dict) for r in rows), kind
    page, table = rows_of(export(name, "ui-json")[0]), rows_of(export(name, "ui-csv")[0])
    for a, b in zip(page, table, strict=True):
        for key in CSV_JSON:
            # the JSON leaves out an error key where there was none; the CSV has the column
            assert a.get(key) == b.get(key), key
        assert str(a["created"]) == b["created"]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_2_an_errored_case(version: str) -> None:
    bad = {"baseline": "c08", "candidate": "c09"}[version]
    rows = rows_of(export(version, "fetch")[0])
    root, *under = trace_rows(rows, bad)
    assert root["error"].startswith("Traceback (most recent call last):") and root["output"] is None
    assert root["metadata"] is None and root["origin"]["id"] == bad and root["tags"] == [version]
    assert not [r for r in under if span_type(r) in ("score", "classifier")]
    errored = [span_type(r) for r in under if r["error"]]
    assert errored == {"baseline": ["task", "tool"], "candidate": ["task", "function"]}[version], errored
    for kind in ROW_EXPORTS:
        row = roots(rows_of(export(version, kind)[0]))[bad]
        assert row["error"] and row["output"] is None and row["metadata"] is None, kind
        assert not [v for v in (row["scores"] or {}).values() if v is not None], kind
    # every other root carries the script's metadata, and its record
    for case, other in roots(rows).items():
        if case != bad:
            assert other["metadata"] == {"case": case, "version": version} and other["error"] is None


def test_tf25_2_the_record_s_id_is_on_the_slice_s_roots_and_not_the_lookup_s() -> None:
    for version in VERSIONS:
        for kind in (*SPAN_EXPORTS, "summary"):
            tops = roots(rows_of(export(version, kind)[0]))
            assert {case: r["origin"]["id"] for case, r in tops.items()} == {case: case for case in CASES}, kind
    for name in LOOKUP:
        rows = rows_of(export(name, "fetch")[0])
        assert all(r["origin"] is None for r in rows if is_root(r))
        assert sorted(r["input"] for r in rows if is_root(r)) == ["q1", "q1", "q2", "q2", "q3", "q3"]


def test_tf25_2_a_whole_fetch_ends_with_a_cursor_and_the_end_s_page_is_empty() -> None:
    ends = end_cursors()
    assert all(isinstance(c, str) and c for c in ends.values()) and len(set(ends.values())) == 4
    pages = [json.loads(p.read_text(encoding="utf-8")) for p in export("candidate", "fetch-pages")]
    assert pages[3]["cursor"] == ends[EXPERIMENT_ID["slice-candidate"]] and len(pages[3]["events"]) == 13
    assert pages[4] == {"events": []}
    requests = json.loads((API / "requests.json").read_text(encoding="utf-8"))
    asked = [r["url"] for r in requests if r["file"] == "slice-candidate.fetch.page-5.json"]
    assert asked == [f"https://api.braintrust.dev/v1/experiment/{EXPERIMENT_ID['slice-candidate']}/fetch?limit=25&cursor={pages[3]['cursor']}"]


# ---------- TF25-3 ----------


def test_tf25_3_no_row_holds_a_dataset_record_id() -> None:
    for path in sorted(Path(API).glob("*.json")) + sorted(Path(UI).glob("*.json")):
        assert '"dataset_record_id"' not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_3_what_the_summary_says_differently(version: str) -> None:
    spans = rows_of(export(version, "fetch")[0])
    summary = roots(rows_of(export(version, "summary")[0]))
    for case, root in roots(spans).items():
        row: Any = summary[case]
        task = next(r for r in trace_rows(spans, case)[1:] if span_type(r) == "task")
        llm = [r for r in trace_rows(spans, case)[1:] if span_type(r) == "llm"]
        assert row["metrics"]["start"] == root["metrics"]["start"] and row["metrics"]["end"] == root["metrics"]["end"]
        assert row["metrics"]["duration"] == task["metrics"]["duration"] != root["metrics"]["duration"], case
        assert "tokens" not in row["metrics"] and "total_tokens" in row["metrics"]
        if llm:
            assert "total_tokens" not in llm[0]["metrics"] and row["metrics"]["total_tokens"] == llm[0]["metrics"]["tokens"]
            assert row["metrics"]["time_to_first_token"] == llm[0]["metrics"]["time_to_first_token"]
            assert row["metrics"]["estimated_cost"] == llm[0]["metrics"]["estimated_cost"]
        else:
            # no model call: the summary writes 0 tokens where the spans write nothing
            assert row["metrics"]["total_tokens"] == 0 and row["metrics"]["estimated_cost"] is None
        if root["error"]:
            assert row["error"].endswith("...") and len(row["error"]) < len(root["error"]), case
            assert not row["error"].rstrip(".").splitlines()[-1].startswith(("TimeoutError", "ValueError"))


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_3_the_page_writes_a_classification_as_a_string_of_json(version: str) -> None:
    spans = roots(rows_of(export(version, "fetch")[0]))
    for kind in ("ui-json", "ui-csv"):
        for case, row in roots(rows_of(export(version, kind)[0])).items():
            held = (row["classifications"] or {}).get("failure_kind")
            want = (spans[case]["classifications"] or {}).get("failure_kind")
            assert (held is None) == (want is None), (kind, case)
            if want is not None:
                assert isinstance(held, str) and json.loads(held) == want, (kind, case)
