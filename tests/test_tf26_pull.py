"""TF26-33 to TF26-46: the raw-saving pull (spec section 18.3.2, SG9 and SG2; the folder a pull
saves is the one TF22's resolver reads; the two finished pairs' rules for a pull: no silent
window, what the raw copy leaves out, never written over). No test here reaches the network:
``pulling.send`` is replaced by a transport that answers each request with the response Weave
gave to that request (``api/requests.json``), and every socket connection is refused while it
runs.

- TF26-33: what is asked. ``weave:ENTITY/PROJECT/EVALUATION`` in the files' place asks ``POST
  /calls/stream_query`` for the project's root calls and then for every call of the
  evaluation's trace with its example expanded, each oldest first, in pages by ``limit`` and
  ``offset`` until a page comes back empty, each with the key as basic auth under the user
  ``api``, each asking for costs and for feedback, and nothing else: no request bounds the
  calls by time, so every call is read however old.
- TF26-34: what is saved, before anything is read: ``raw.jsonl`` (the calls, one a line, in the
  order returned) and ``pull.json`` (``poisson.raw-pull/1``: the tool, when, the address, the
  endpoint, whether the text was left out, and the file with its digest and its rows) under
  ``STORE/.poisson/raw/weave/RUN/``, and nothing else there; TF22's resolver reads the folder
  as a pull of ``weave``.
- TF26-35: the content and the run's own metadata are measured and left out by default: no
  input, output, prompt, traceback or note is in the raw copy, nor who ran the calls or on what
  machine. Of a call's inputs the references that say which evaluation and which model stay,
  and of a row's example the reference to its dataset row; of a row's output the scores that
  are numbers or true or false and Weave's figure for the model's run; an exception keeps its
  class alone, with the kind its words said beside it; the attributes keep the call's kind
  alone; a feedback entry keeps what it is and when, and a reaction its name. Each call
  carries ``_poisson_input_chars`` and ``_poisson_output_chars``, and each row its input's
  key. ``--keep-raw-text`` saves the calls as the API returned them and says so.
- TF26-36: the pull is the file reader on the saved folder: its run is, record for record and
  column for column, the import of the committed expanded answer; its summary names
  ``raw.jsonl`` with the digest ``pull.json`` lists, carries a ``pull`` block and one ``-
  pulled:`` line, and ends with the fix check as every import does.
- TF26-37: the saved folder is read again with no key and no request: under another run name,
  with the tool named or not, and with other flags (the case by the row's reference or by the
  input; the outcome by the status or by another scorer), each the run the committed answer
  gives with those flags. A key of the row needs the row, which the default raw copy leaves
  out: it is refused naming ``--keep-raw-text``, and read from a copy kept whole.
- TF26-38: paging. In pages of 40 each query is asked until its page comes back empty; the run
  is the one a single page gives. The offset moves by the calls received, so a service that
  answers with fewer than asked loses none; an answer that repeats is a failure, never a loop.
- TF26-39: a raw copy is never written over: a second pull under a name the store holds is
  refused before any request; a pull whose read was refused leaves its raw copy, and pulling
  that name again is refused naming the folder and the command that reads it.
- TF26-40: refused before any request, exit 1, nothing written: no key, an address naming no
  entity, project or evaluation, the service's own host asked over http. A wrong
  command line exits 2: an address beside files, no ``--run``, ``--keep-raw-text`` or
  ``--page-size`` without an address, a page size that is not 1 to 1000.
- TF26-41: the service says no, exit 1, nothing saved: no evaluation of that name in the
  project; a name several runs share, naming each; a key refused (401, 403), which names the
  variable and never the key. An evaluation is named by its name, by the name Weave shows for
  its run, or by its call's id.
- TF26-42: a failure after the pull began, exit 3, nothing saved and no folder left: at each
  request, a status that is not 200 (a 404 at the first, a 500 at the others), an answer that
  is not JSON Lines, a line that is no call.
- TF26-43: a 429 is waited out and asked again: the wait is the answer's ``Retry-After`` where
  given, and grows where it is not; the run is the one an unthrottled pull gives.
- TF26-44: the key is printed nowhere and written nowhere, whole or as its basic-auth token;
  ``WF_TRACE_SERVER_URL`` moves every request to that host and the path under it; the other
  pullers' keys and endpoints are not Weave's.
- TF26-45: ``pulling.send`` is the only code in the package that reaches the network, standard
  library only; an import of files calls it never.
- TF26-46: ``--json`` on a pull is one document, whose ``pull`` block TF26-36 holds.

What the three readers that pull share (one transport, one folder check, one import command) is
held once, in ``test_tf24_pull.py``: a raw copy changed after the pull is refused (TF24-37), a 429
on every try stops after a few (TF24-42), the wait grows when the answer names none (TF24-43), the
scan for the one function that reaches the network, which reads this reader's module too
(TF24-45), and ``--json`` on a pull done or failed (TF24-46). So is every value of a rule the
transport alone decides: a key that is empty or blank and every endpoint that is refused
(TF24-40), a 502, the connection failing and a timeout (TF24-42), an endpoint with a slash at its
end or on this machine (TF24-44). Here each of those rules is held on one value, with this
reader's variable and host.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf21_support import run_import
from tf26_support import (
    API, CALL_ID, CALLS, CASES, CONTENT, ENDPOINT_VARIABLE, EVALUATION, EXACT, EXPORTS, HOST, ITEM, KEY, KEY_VARIABLE, LOOKUP_EXPECTED,
    NAMES, PLANTED_KEY, PROJECT_ID, QUERY, ROOTS, ROW, SHOWN, TRACE, TRACE_ID, VERSIONS, WHOLE, Transport, address, basic, by_status,
    calls_of, case_of, columns, export, imported, input_chars, never, of, op, pulling, raw_folder, raw_lines, recs, refused,
    rows_by_case, snapshot, stored_bytes, tally, tries, wrong_line, wv_argv,
)

BODY_KEYS = {"project_id", "sort_by", "include_costs", "include_feedback", "filter", "expand_columns", "limit", "offset"}


def _pull(root: Path, name: str = "baseline", run: str = "r", *extra: Any, transport: Transport | None = None,
          argv: Any = None, **env: Any) -> tuple[dict[str, Any], Transport, list[float]]:
    with pulling(transport, **env) as (sent, waits):
        data = imported((argv or wv_argv)(address(name), root, run, *extra))
    return data, sent, waits


def _raw_dirs(root: Path) -> list[str]:
    base = root / ".poisson" / "raw"
    return sorted(str(p.relative_to(base)) for p in base.rglob("*")) if base.exists() else []


def _nothing_saved(root: Path, run: str = "r") -> bool:
    return not (root / run).exists() and _raw_dirs(root) in ([], ["weave"])


# ---------- TF26-33 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf26_33_the_pull_asks_for_the_root_calls_and_then_for_the_evaluation_s_trace(tmp_path: Path, name: str) -> None:
    _, sent, waits = _pull(tmp_path / "st", name)
    # each query is asked until a page comes back empty
    assert sent.kinds() == WHOLE and waits == []
    roots, roots_end, first, last = sent.bodies()
    for body in sent.bodies():
        assert body["project_id"] == PROJECT_ID and body["sort_by"] == [{"field": "started_at", "direction": "asc"}]
        assert body["include_costs"] is True and body["include_feedback"] is True
        assert body["limit"] == 1000
    assert roots["filter"] == {"trace_roots_only": True} and (roots["offset"], roots_end["offset"]) == (0, 4)
    assert "expand_columns" not in roots
    for body in (first, last):
        assert body["filter"] == {"trace_ids": [TRACE_ID[name]]} and body["expand_columns"] == ["inputs.example"]
    assert (first["offset"], last["offset"]) == (0, CALLS[name])
    for call in sent.calls:
        assert call["method"] == "POST" and call["url"] == HOST + QUERY
        headers = {k.lower(): v for k, v in call["headers"].items()}
        assert headers["authorization"] == basic() and headers["content-type"] == "application/json"
        assert PLANTED_KEY not in call["url"] and PLANTED_KEY.encode() not in call["body"]


@pytest.mark.parametrize("name", NAMES)
def test_tf26_33_no_request_bounds_the_calls_by_time(tmp_path: Path, name: str) -> None:
    """Nothing asked bounds the calls by when they started, by a query or by a count short of
    all of them: each query is asked for every call it matches, and every call of the trace is
    saved."""
    _, sent, _ = _pull(tmp_path / "st", name)
    for body in sent.bodies():
        assert set(body) <= BODY_KEYS, set(body) - BODY_KEYS
        assert set(body["filter"]) in ({"trace_roots_only"}, {"trace_ids"}), body["filter"]
        assert "started" not in json.dumps(body["filter"]) and "query" not in body
    assert len(raw_lines(tmp_path / "st", "r")) == CALLS[name]


# ---------- TF26-34 ----------


@pytest.mark.parametrize("name", NAMES)
def test_tf26_34_the_raw_copy_and_its_record(tmp_path: Path, name: str) -> None:
    from datetime import datetime

    from poisson_trace.ingest.folder import resolve

    root = tmp_path / "st"
    _pull(root, name, "first run")
    folder = raw_folder(root, "first run")
    assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
    assert _raw_dirs(root) == ["weave", "weave/first run", "weave/first run/pull.json", "weave/first run/raw.jsonl"]
    doc = json.loads((folder / "pull.json").read_text(encoding="utf-8"))
    assert set(doc) == {"schema", "tool", "pulled_at", "source_uri", "endpoint", "raw_text_stripped", "files"}
    assert doc["schema"] == "poisson.raw-pull/1" and doc["tool"] == "weave"
    assert doc["source_uri"] == address(name) and doc["raw_text_stripped"] is True
    assert doc["endpoint"] == HOST + QUERY, doc["endpoint"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["pulled_at"]) and datetime.fromisoformat(doc["pulled_at"][:-1])
    raw = (folder / "raw.jsonl").read_bytes()
    assert doc["files"] == [{"path": "raw.jsonl", "sha256": hashlib.sha256(raw).hexdigest(), "rows": CALLS[name]}]
    lines = raw_lines(root, "first run")
    assert len(lines) == CALLS[name] and raw.endswith(b"\n")
    assert [c["id"] for c in lines] == [c["id"] for c in calls_of(export(name, "expanded")[0])]
    assert all("op_name" in c and "trace_id" in c and "started_at" in c for c in lines)
    found = resolve(folder)
    assert (found.kind, found.tool, [p.name for p in found.files]) == ("pull", "weave", ["raw.jsonl"])


# ---------- TF26-35 ----------

#: The kind each captured exception's words say, by its class: a timeout, a 429, and a
#: complaint about a reply.
WORDS_SAY = {"TimeoutError": "timeout", "RuntimeError": "rate_limit", "ValueError": None}
#: What a stripped call's summary and a stripped feedback entry may hold.
SUMMARY_KEPT = {"usage", "status_counts", "weave"}
FEEDBACK_KEPT = {"id", "feedback_type", "created_at", "weave_ref", "payload"}
#: The keys of a call that are as the API returned them.
AS_RETURNED = ("id", "project_id", "op_name", "display_name", "trace_id", "parent_id", "thread_id", "turn_id", "started_at", "ended_at",
               "deleted_at", "expire_at", "storage_size_bytes", "total_storage_size_bytes", "wb_run_step", "wb_run_step_end")


@pytest.mark.parametrize("version", VERSIONS)
def test_tf26_35_the_content_is_measured_and_left_out(tmp_path: Path, version: str) -> None:
    root = tmp_path / "st"
    _pull(root, version)
    lines = raw_lines(root, "r")
    source = {c["id"]: c for c in calls_of(export(version, "expanded")[0])}
    assert len(lines) == len(source)
    errors = 0
    for call in lines:
        was = source[call["id"]]
        for key in AS_RETURNED:
            assert call[key] == was[key], (call["id"], key)
        for stamp in ("_poisson_input_chars", "_poisson_output_chars"):
            assert stamp in call and (call[stamp] is None or isinstance(call[stamp], int)), (call["id"], stamp)
        # of the inputs: the references that say which evaluation and which model, and no value
        kept = {k: was["inputs"][k] for k in ("self", "model") if isinstance(was["inputs"].get(k), str) and was["inputs"][k].startswith("weave:///")}
        if op(was) == ROW:
            case = case_of(was)
            kept["example"] = {"_ref": was["inputs"]["example"]["_ref"]}
            assert call["_poisson_input_chars"] == input_chars(case) and call["_poisson_input_key"] == KEY[case]
            answer = was["output"]["output"]
            assert call["_poisson_output_chars"] == (None if answer is None else len(answer))
            assert call["output"] == {"scores": was["output"]["scores"], "model_latency": was["output"]["model_latency"]}
        else:
            assert "_poisson_input_key" not in call and call["output"] is None
            assert call["_poisson_output_chars"] is None if was["output"] is None else call["_poisson_output_chars"] >= 0
        assert call["inputs"] == kept, call["id"]
        if was["exception"]:
            # an exception's own words may quote a reply: its class is kept, and the kind its words say
            errors += 1
            held = json.loads(call["exception"])
            assert held == {"type": json.loads(was["exception"])["type"]} and held["type"] in WORDS_SAY, held
            assert call["_poisson_error_kind"] == WORDS_SAY[held["type"]], call
        else:
            assert not call.get("exception") and call.get("_poisson_error_kind") is None
        # who ran the call and on what machine is left out; the call's kind stays
        assert call["wb_user_id"] is None and call["wb_run_id"] is None
        marked = was["attributes"]["weave"].get("kind")
        assert call["attributes"] == ({"weave": {"kind": marked}} if marked else {}), call["attributes"]
        # the summary keeps the status, the counts, the tokens and the costs
        assert set(call["summary"]) <= SUMMARY_KEPT
        assert call["summary"].get("usage") == was["summary"].get("usage")
        assert call["summary"].get("status_counts") == was["summary"].get("status_counts")
        for key in ("status", "latency_ms", "costs", "trace_name", "display_name"):
            assert call["summary"]["weave"].get(key) == was["summary"]["weave"].get(key), (call["id"], key)
        for entry, original in zip(call["summary"]["weave"]["feedback"], was["summary"]["weave"]["feedback"], strict=True):
            assert set(entry) <= FEEDBACK_KEPT and entry["feedback_type"] == original["feedback_type"]
            if entry["feedback_type"] == "wandb.reaction.1":
                assert entry["payload"] == {"emoji": original["payload"]["emoji"], "alias": original["payload"]["alias"]}
            else:
                assert "payload" not in entry, entry
    assert errors == {"baseline": 2, "candidate": 3}[version]
    held = stored_bytes(root)
    for text in (*CONTENT, "max_tokens", "temperature", "sys_version", "os_version", "VXNlcjow", "traceback"):
        assert text.encode() not in held, text
    for word in ITEM.values():
        assert word.encode() not in held, word


@pytest.mark.parametrize("name", ["old", "new"])
def test_tf26_35_the_lookup_fixture_s_rows_and_answers_are_left_out_too(tmp_path: Path, name: str) -> None:
    _pull(tmp_path / "st", name)
    held = stored_bytes(tmp_path / "st")
    for word in LOOKUP_EXPECTED.values():
        assert word.encode() not in held, word
    for call in raw_lines(tmp_path / "st", "r"):
        if op(call) == ROW:
            # the model's answer is a reference in the file: there is no text to measure
            assert call["_poisson_output_chars"] is None and "output" not in call["output"]


def test_tf26_35_a_scorer_s_text_a_note_and_an_annotation_are_left_out_of_the_raw_copy(tmp_path: Path) -> None:
    """No capture holds a scorer that wrote text or a human's annotation, so the service's
    answer is given both here on every row: neither is in the raw copy or the store, and
    ``--keep-raw-text`` keeps them in the raw copy alone."""
    said = "the reviewer wrote: this answer leaks the customer's address"
    calls = calls_of(export("baseline", "expanded")[0])
    for call in calls:
        if op(call) == ROW:
            if call["output"]["scores"]:
                call["output"]["scores"]["judge"] = {"correct": True, "reason": said}
            call["summary"]["weave"]["feedback"].append({"id": "x", "feedback_type": "wandb.annotation.review", "payload": {"value": said}, "created_at": "2026-11-09T21:00:00Z"})
            call["attributes"]["note"] = said
            call["summary"]["debug"] = {"said": said}
    answer = (200, {}, "".join(json.dumps(c) + "\n" for c in calls).encode("utf-8"))
    _pull(tmp_path / "st", "baseline", transport=Transport({3: answer}))
    assert said.encode() not in stored_bytes(tmp_path / "st")
    row = next(c for c in raw_lines(tmp_path / "st", "r") if op(c) == ROW and c["output"]["scores"])
    assert row["output"]["scores"]["judge"] == {"correct": True} and row["attributes"] == {}
    assert set(row["summary"]) <= SUMMARY_KEPT
    _pull(tmp_path / "kept", "baseline", "r", "--keep-raw-text", transport=Transport({3: answer}))
    assert said.encode() in (raw_folder(tmp_path / "kept", "r") / "raw.jsonl").read_bytes()
    assert said.encode() not in stored_bytes(tmp_path / "kept" / "r")
    assert recs(tmp_path / "kept", "r") == recs(tmp_path / "st", "r")
    assert recs(tmp_path / "st", "r")["c01"]["scores"] == {"exact": 1.0, "gave_answer": 1.0, "judge.correct": 1.0}


@pytest.mark.parametrize("version", VERSIONS)
def test_tf26_35_keep_raw_text_saves_the_calls_as_the_api_returned_them(tmp_path: Path, version: str) -> None:
    kept, _, _ = _pull(tmp_path / "kept", version, "r", "--keep-raw-text")
    plain, _, _ = _pull(tmp_path / "plain", version)
    assert raw_lines(tmp_path / "kept", "r") == calls_of(export(version, "expanded")[0])
    doc = json.loads((raw_folder(tmp_path / "kept", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["raw_text_stripped"] is False and kept["pull"]["raw_text_stripped"] is False
    assert plain["pull"]["raw_text_stripped"] is True
    # the lengths stamped are the lengths measured: both read to the same run
    assert recs(tmp_path / "kept", "r") == recs(tmp_path / "plain", "r")
    # and the run's own folder holds no text either way
    assert not [t for t in CONTENT if t.encode() in stored_bytes(tmp_path / "kept" / "r")]


# ---------- TF26-36 ----------


def _same_run(a: Path, b: Path, run_a: str = "r", run_b: str = "r") -> None:
    assert recs(a, run_a) == recs(b, run_b)
    left, right = columns(a, run_a), columns(b, run_b)
    assert sorted(left) == sorted(right)
    for case in left:
        for key in ("outcome", "error", "t", "wall_time", "config_hash"):
            assert left[case][key] == right[case][key] or (left[case][key] != left[case][key] and right[case][key] != right[case][key]), (case, key)
        assert left[case]["trace"] == right[case]["trace"], case


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("keep", [False, True])
def test_tf26_36_the_pulled_run_is_the_import_of_the_same_answer_as_a_file(tmp_path: Path, version: str, keep: bool) -> None:
    pulled, _, _ = _pull(tmp_path / "pulled", version, "r", *(["--keep-raw-text"] if keep else []))
    files = imported(wv_argv(export(version, "expanded"), tmp_path / "files", "r"))
    _same_run(tmp_path / "pulled", tmp_path / "files")
    for key in ("rows", "cases", "repeats", "outcomes", "no_outcome", "counts", "started", "declared", "tool"):
        assert pulled[key] == files[key], key
    assert {case: r["score"] for case, r in recs(tmp_path / "pulled", "r").items()} == EXACT[version]
    # the pull always asks for costs and feedback and for the row, so the run holds all three
    stored = recs(tmp_path / "pulled", "r")
    assert stored["c01"]["cost_usd"] is not None and stored["c01"]["feedback"] == {"reaction": ":thumbs_up:"}
    assert stored["c01"]["input_chars"] == input_chars("c01") and pulled["counts"]["no cost recorded"] == 0


@pytest.mark.parametrize("name", ["old", "new"])
def test_tf26_36_and_of_the_lookup_fixture(tmp_path: Path, name: str) -> None:
    _pull(tmp_path / "pulled", name)
    imported(wv_argv(export(name, "expanded"), tmp_path / "files", "r"))
    assert tries(tmp_path / "pulled", "r") == tries(tmp_path / "files", "r")


@pytest.mark.parametrize("keep", [False, True])
def test_tf26_36_the_kind_an_exception_s_words_said_survives_the_stripping(tmp_path: Path, keep: bool) -> None:
    """The raw copy keeps an exception's class alone. Where the kind was in its words and not
    in its class, the kind is stamped beside it, so the saved copy reads to the same kind."""
    calls = calls_of(export("candidate", "expanded")[0])
    for call in calls:
        if call["exception"] and json.loads(call["exception"])["type"] == "ValueError":
            call["exception"] = json.dumps({"type": "RuntimeError", "message": "the provider said: rate limit exceeded", "traceback": []})
    answer = (200, {}, "".join(json.dumps(c) + "\n" for c in calls).encode("utf-8"))
    _pull(tmp_path / "st", "candidate", "r", *(["--keep-raw-text"] if keep else []), transport=Transport({3: answer}), argv=by_status)
    rec = recs(tmp_path / "st", "r")["c09"]
    assert rec["failure_kind"] == "rate_limit" and rec["error_type"] == "RuntimeError", rec
    with pulling(never(), key=None):
        imported(by_status(raw_folder(tmp_path / "st", "r"), tmp_path / "st", "again"))
    assert recs(tmp_path / "st", "again")["c09"]["failure_kind"] == "rate_limit"


def test_tf26_36_the_summary_says_what_was_pulled(tmp_path: Path) -> None:
    root = tmp_path / "st"
    with pulling() as (_, _waits):
        data = imported(wv_argv(address("candidate"), root, "new"))
        text = run_import(wv_argv(address("baseline"), root, "old"))
    folder = raw_folder(root, "new")
    doc = json.loads((folder / "pull.json").read_text(encoding="utf-8"))
    assert data["files"] == [{"name": "raw.jsonl", "sha256": doc["files"][0]["sha256"]}]
    assert data["pull"]["source_uri"] == address("candidate") and data["pull"]["folder"] == str(folder)
    assert data["pull"]["raw_text_stripped"] is True
    assert list(data).index("pull") < list(data).index("next")
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    assert tally(data) == {"met": 8, "missed": 1}
    assert text.code == 0 and text.out.startswith("ok  wrote run old to "), text.out + text.err
    said = [line for line in text.out.splitlines() if line.startswith("- pulled: ")]
    assert len(said) == 1 and address("baseline") in said[0] and str(raw_folder(root, "old")) in said[0], text.out
    assert "calls 78" in said[0] and "left out" in said[0], said[0]
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    # an import of files says nothing of a pull
    plain = run_import(by_status(export("baseline", "pull"), tmp_path / "other", "r"))
    assert plain.code == 0 and "- pulled: " not in plain.out
    assert "pull" not in imported(by_status(export("baseline", "pull"), tmp_path / "other", "r2"))


# ---------- TF26-37 ----------

AGAIN = {
    "by the row and the status": {"case": "example", "outcome": "status", "cut": None},
    "by the input and the score": {"case": "input"},
    "by the input and the status": {"case": "input", "outcome": "status", "cut": None},
    "by the row and another scorer": {"case": "example", "outcome": "score:gave_answer"},
    "by none and the score": {"case": "none"},
}


@pytest.mark.parametrize("keep", [False, True])
def test_tf26_37_the_saved_folder_reads_again_with_no_key_and_no_request(tmp_path: Path, keep: bool) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "r", *(["--keep-raw-text"] if keep else []))
    folder = raw_folder(root, "r")
    before = snapshot(folder)
    with pulling(never(), key=None):
        again = imported(wv_argv(folder, root, "again"))
        unnamed = run_import([str(folder), "--store", str(root), "--run", "unnamed", "--case-from", "example",
                              "--outcome-from", "score:exact", "--cut", "0.5", "--below", "--json"])
        elsewhere = imported(wv_argv(folder, tmp_path / "elsewhere", "r"))
        assert unnamed.code == 0, unnamed.err
        assert recs(root, "again") == recs(root, "r") == recs(root, "unnamed") == recs(tmp_path / "elsewhere", "r")
        assert again["files"][0]["name"] == "raw.jsonl" and "pull" not in again and "pull" not in elsewhere
        for label, flags in AGAIN.items():
            run = label.replace(" ", "-")
            saved = imported(wv_argv(folder, root, run, **flags))
            files = imported(wv_argv(export("baseline", "expanded"), tmp_path / "files", run, **flags))
            if flags["case"] != "none":
                _same_run(root, tmp_path / "files", run, run)
            for key in ("rows", "cases", "outcomes", "no_outcome", "counts", "declared"):
                assert saved[key] == files[key], (label, key)
    assert snapshot(folder) == before


def test_tf26_37_a_key_of_the_row_needs_the_row_which_the_default_raw_copy_leaves_out(tmp_path: Path) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "stripped")
    _pull(root, "baseline", "kept", "--keep-raw-text")
    with pulling(never(), key=None):
        line = refused(run_import(by_status(raw_folder(root, "stripped"), root, "x", case="example:case")))
        assert "example:case" in line and "--keep-raw-text" in line and "--case-from example" in line, line
        data = imported(by_status(raw_folder(root, "kept"), root, "y", case="example:case"))
    assert data["rows"] == 10 and sorted(columns(root, "y")) == list(CASES)
    # pulling by a key of the row, the copy must be kept whole for the read that follows: it is
    # refused before any request, so no raw copy is left under the name
    with pulling() as (sent, _waits):
        line = refused(run_import(by_status(address("candidate"), root, "z", case="example:case")))
        assert sent.calls == [] and "--keep-raw-text" in line and "example:case" in line, line
        assert not raw_folder(root, "z").exists() and not (root / "z").exists()
        imported(by_status(address("candidate"), root, "z", "--keep-raw-text", case="example:case"))
    assert sorted(columns(root, "z")) == list(CASES)


# ---------- TF26-38 ----------


@pytest.mark.parametrize(("size", "offsets"), [("40", [0, 40, 80, 81]), ("7", [*range(0, 78, 7), 81]), ("81", [0, 81]), ("1000", [0, 81])])
def test_tf26_38_in_pages_each_query_is_asked_until_its_page_comes_back_empty(tmp_path: Path, size: str, offsets: list[int]) -> None:
    paged, sent, _ = _pull(tmp_path / "paged", "candidate", "r", "--page-size", size)
    whole, once, _ = _pull(tmp_path / "whole", "candidate")
    assert once.kinds() == WHOLE
    trace = [b for b, kind in zip(sent.bodies(), sent.kinds(), strict=True) if kind == TRACE]
    roots = [b for b, kind in zip(sent.bodies(), sent.kinds(), strict=True) if kind == ROOTS]
    assert sent.kinds() == [ROOTS] * len(roots) + [TRACE] * len(trace)
    assert [b["limit"] for b in sent.bodies()] == [int(size)] * len(sent.calls)
    assert [b["offset"] for b in trace] == offsets
    assert [b["offset"] for b in roots] == ([0, 4] if int(size) >= 4 else [*range(0, 4, int(size)), 4])
    assert len(raw_lines(tmp_path / "paged", "r")) == 81
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    assert paged["counts"] == whole["counts"] and paged["counts"]["calls"] == 81
    assert raw_lines(tmp_path / "paged", "r") == raw_lines(tmp_path / "whole", "r")


def test_tf26_38_a_service_that_answers_with_fewer_than_asked_loses_none(tmp_path: Path) -> None:
    """A service that caps a page below the limit it was asked for: the offset moves by the
    calls received, so the next request starts where the last one ended, and a short page is
    not the end."""
    class Capped(Transport):
        def answer(self, method: str, url: str, body: bytes | None) -> bytes:
            assert body is not None
            return b"".join(super().answer(method, url, body).splitlines(keepends=True)[:25])

    data, sent, _ = _pull(tmp_path / "st", "candidate", transport=Capped())
    trace = [b["offset"] for b, kind in zip(sent.bodies(), sent.kinds(), strict=True) if kind == TRACE]
    assert trace == [0, 25, 50, 75, 81] and data["counts"]["calls"] == 81
    assert [c["id"] for c in raw_lines(tmp_path / "st", "r")] == [c["id"] for c in calls_of(export("candidate", "expanded")[0])]


def test_tf26_38_an_answer_that_repeats_is_a_failure_and_never_a_loop(tmp_path: Path) -> None:
    page = b"".join(export("candidate", "expanded")[0].read_bytes().splitlines(keepends=True)[:40])
    script = {n: (200, {}, page) for n in range(3, 60)}
    with pulling(Transport(script)) as (sent, _):
        result = run_import(wv_argv(address("candidate"), tmp_path / "st", "r", "--page-size", "40"))
    assert result.code == 3 and "nothing was saved" in result.err, result.err
    assert len(sent.calls) <= 6, len(sent.calls)
    assert _nothing_saved(tmp_path / "st")


# ---------- TF26-39 ----------


def test_tf26_39_a_name_the_store_holds_is_refused_before_any_request(tmp_path: Path) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "old")
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(wv_argv(address("candidate"), root, "old")))
        assert sent.calls == []
    assert "old" in line, line
    assert snapshot(root) == before
    # the same for a name a file import took, which left no raw copy to stand in the way
    imported(by_status(export("baseline", "pull"), root, "from-a-file"))
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(wv_argv(address("candidate"), root, "from-a-file")))
        assert sent.calls == []
    assert "from-a-file" in line, line
    assert snapshot(root) == before


def test_tf26_39_a_raw_copy_is_never_written_over(tmp_path: Path) -> None:
    """A pull whose read is then refused (no row has the score named) keeps what it pulled:
    the raw copy is the pull. Pulling under that name again is refused, naming the folder and
    the command that reads it; that command, with a scorer the rows do have, writes the run."""
    root = tmp_path / "st"
    with pulling() as (sent, _):
        first = run_import(wv_argv(address("baseline"), root, "old", outcome="score:no_such_scorer"))
        assert first.code == 1 and len(sent.calls) == 4, first.err
        folder = raw_folder(root, "old")
        assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
        assert not (root / "old").exists()
        before = snapshot(folder)
        again = run_import(wv_argv(address("baseline"), root, "old"))
        line = refused(again)
        assert len(sent.calls) == 4, "no request is made for a pull that is already saved"
    assert str(folder) in line, line
    nexts = [following[len("  next: "):] for following in again.err.splitlines()[1:]]
    assert len(nexts) == 1 and nexts[0].startswith("poisson-trace import weave ") and str(folder) in nexts[0], again.err
    for flag in ("--case-from example", "--outcome-from score:exact", "--cut 0.5", "--below"):
        assert flag in nexts[0], nexts[0]
    assert snapshot(folder) == before
    with pulling(never(), key=None):
        data = imported(wv_argv(folder, root, "old"))
    assert tally(data) == {"met": 6, "missed": 3} and snapshot(folder) == before


# ---------- TF26-40 ----------


@pytest.mark.parametrize("key", [None])
def test_tf26_40_no_key_is_refused_naming_the_variable(tmp_path: Path, key: str | None) -> None:
    with pulling(key=key) as (sent, _):
        line = refused(run_import(wv_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert KEY_VARIABLE in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("named", ["weave:", "weave:example-entity", "weave:example-entity/trace-fixture", "weave:example-entity/trace-fixture/",
                                   "weave:/trace-fixture/trace-fixture-old", "weave:example-entity//trace-fixture-old", "weave: / / "])
def test_tf26_40_an_address_naming_no_entity_project_or_evaluation_is_refused(tmp_path: Path, named: str) -> None:
    with pulling() as (sent, _):
        line = refused(run_import(wv_argv(named, tmp_path / "st", "r")))
        assert sent.calls == []
    assert "weave:ENTITY/PROJECT/EVALUATION" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("endpoint", ["http://trace.wandb.ai"])
def test_tf26_40_the_key_goes_over_https_or_to_this_machine_only(tmp_path: Path, endpoint: str) -> None:
    with pulling(endpoint=endpoint) as (sent, _):
        line = refused(run_import(wv_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert ENDPOINT_VARIABLE in line and PLANTED_KEY not in line, line
    assert not (tmp_path / "st").exists()


WRONG: dict[str, Any] = {
    "an address beside a file": lambda root: wv_argv([address("baseline"), *export("baseline", "pull")], root, "r"),
    "two addresses": lambda root: wv_argv([address("baseline"), address("candidate")], root, "r"),
    "no run name": lambda root: wv_argv(address("baseline"), root, None),
    "keep-raw-text with files": lambda root: wv_argv(export("baseline", "pull"), root, "r", "--keep-raw-text"),
    "page-size with files": lambda root: wv_argv(export("baseline", "pull"), root, "r", "--page-size", "40"),
    "a page size of 0": lambda root: wv_argv(address("baseline"), root, "r", "--page-size", "0"),
    "a page size of 1001": lambda root: wv_argv(address("baseline"), root, "r", "--page-size", "1001"),
    "a page size that is no number": lambda root: wv_argv(address("baseline"), root, "r", "--page-size", "many"),
}


@pytest.mark.parametrize("label", list(WRONG))
def test_tf26_40_a_wrong_command_line_exits_2_and_asks_nothing(tmp_path: Path, label: str) -> None:
    with pulling() as (sent, _):
        wrong_line(run_import(WRONG[label](tmp_path / "st")))
        assert sent.calls == []
    assert not (tmp_path / "st").exists()


# ---------- TF26-41 ----------


@pytest.mark.parametrize("named", [f"weave:{PROJECT_ID}/no-such-evaluation", "weave:example-entity/no-such-project/trace-fixture-old"])
def test_tf26_41_no_evaluation_of_that_name(tmp_path: Path, named: str) -> None:
    script = {} if PROJECT_ID in named else {1: (200, {}, b"")}
    with pulling(Transport(script)) as (sent, _):
        line = refused(run_import(wv_argv(named, tmp_path / "st", "r")))
        assert set(sent.kinds()) == {ROOTS}
    entity, project, evaluation = named.split(":", 1)[1].split("/", 2)
    assert evaluation in line and f"{entity}/{project}" in line, line
    assert _nothing_saved(tmp_path / "st")


def test_tf26_41_an_evaluation_s_name_is_matched_whole(tmp_path: Path) -> None:
    """``trace-fixture`` is the start of four evaluations' names and the name of none."""
    with pulling() as (sent, _):
        line = refused(run_import(wv_argv(f"weave:{PROJECT_ID}/trace-fixture", tmp_path / "st", "r")))
        assert sent.kinds() == [ROOTS, ROOTS]
    assert "trace-fixture" in line, line
    assert _nothing_saved(tmp_path / "st")


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("by", ["the name Weave shows", "the call's id"])
def test_tf26_41_an_evaluation_is_named_by_the_name_weave_shows_or_by_its_call_s_id(tmp_path: Path, version: str, by: str) -> None:
    word = SHOWN[version] if by == "the name Weave shows" else CALL_ID[version]
    with pulling() as (sent, _):
        data = imported(wv_argv(f"weave:{PROJECT_ID}/{word}", tmp_path / "st", "r"))
        assert sent.bodies()[2]["filter"] == {"trace_ids": [TRACE_ID[version]]}
    _pull(tmp_path / "named", version)
    assert recs(tmp_path / "st", "r") == recs(tmp_path / "named", "r") and data["pull"]["calls"] == CALLS[version]


def test_tf26_41_a_name_several_runs_share_is_refused_naming_each(tmp_path: Path) -> None:
    """One evaluation run against two models is two runs of one name. Built here: the root
    calls answered with the candidate's run renamed to the baseline's evaluation."""
    roots = calls_of(API / "roots.jsonl")
    roots[3]["inputs"]["self"] = roots[3]["inputs"]["self"].replace(EVALUATION["candidate"], EVALUATION["baseline"])
    answer = (200, {}, "".join(json.dumps(c) + "\n" for c in roots).encode("utf-8"))
    with pulling(Transport({1: answer})) as (sent, _):
        line = refused(run_import(wv_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.kinds() == [ROOTS, ROOTS]
        for version in VERSIONS:
            assert SHOWN[version] in line and CALL_ID[version] in line, line
        assert _nothing_saved(tmp_path / "st")
    # either run's own name picks it
    with pulling(Transport({1: answer})):
        data = imported(wv_argv(f"weave:{PROJECT_ID}/{SHOWN['candidate']}", tmp_path / "st", "r"))
    assert tally(data) == {"met": 8, "missed": 1}


def test_tf26_41_a_root_call_that_is_no_evaluation_is_not_one(tmp_path: Path) -> None:
    """A project's root calls are whatever was traced. One that is no ``Evaluation.evaluate``
    call is not an evaluation, whatever name Weave shows for it."""
    roots = calls_of(API / "roots.jsonl")
    other = json.loads(json.dumps(roots[0]))
    other["id"], other["trace_id"], other["display_name"] = "01a1c1ff-0000-7000-8000-000000000001", "01a1c1ff-0000-7000-8000-000000000002", "nightly"
    other["op_name"] = f"weave:///{PROJECT_ID}/op/nightly_job:abc"
    answer = (200, {}, "".join(json.dumps(c) + "\n" for c in [*roots, other]).encode("utf-8"))
    for word in ("nightly", other["id"]):
        with pulling(Transport({1: answer})) as (sent, _):
            line = refused(run_import(wv_argv(f"weave:{PROJECT_ID}/{word}", tmp_path / "st", "r")))
            assert set(sent.kinds()) == {ROOTS} and word in line and "no evaluation" in line, line
    assert _nothing_saved(tmp_path / "st")


@pytest.mark.parametrize(("at", "status"), [(1, 401), (1, 403), (2, 401), (3, 401), (4, 401)])
def test_tf26_41_a_key_the_service_refuses(tmp_path: Path, status: int, at: int) -> None:
    body = json.dumps({"detail": f"Invalid key {PLANTED_KEY}"}).encode()
    with pulling(Transport({at: (status, {}, body)})) as (sent, _):
        result = run_import(wv_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    line = refused(result)
    assert KEY_VARIABLE in line and str(status) in line and PLANTED_KEY not in result.err, result.err
    assert _nothing_saved(tmp_path / "st")


# ---------- TF26-42 ----------

FAILURES: dict[str, Any] = {
    "a 500": (500, {}, b"Internal Server Error"),
    "a 404": (404, {}, b'{"detail": "Not Found"}'),
    "an answer that is not JSON": (200, {}, b"<html>sign in</html>"),
    "a line that is no call": (200, {}, b'"ok"\n'),
    "a line that is an object and no call": (200, {}, b'{"detail": "nothing"}\n'),
}
#: At each request, one status that is not 200 (the 404 at the first, a 500 at the others) and
#: each answer this reader's own reading refuses.
FAILED_AT = [(at, label) for at in (1, 2, 3, 4) for label in FAILURES if label != ("a 500" if at == 1 else "a 404")]


@pytest.mark.parametrize(("at", "label"), FAILED_AT)
def test_tf26_42_a_failure_after_the_pull_began_exits_3_and_saves_nothing(tmp_path: Path, label: str, at: int) -> None:
    with pulling(Transport({at: FAILURES[label]})) as (sent, _):
        result = run_import(wv_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    assert result.code == 3 and result.out == "", result.out + result.err
    lines = result.err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("error: ") and "Traceback" not in result.err, result.err
    assert "nothing was saved" in lines[0] and PLANTED_KEY not in result.err, result.err
    assert _nothing_saved(tmp_path / "st")


# ---------- TF26-43 ----------


def test_tf26_43_a_429_is_waited_out_and_asked_again(tmp_path: Path) -> None:
    script = {3: (429, {"Retry-After": "7"}, b"{}"), 4: (429, {}, b""), 5: (429, {"retry-after": "2.5"}, b""), 7: (429, {}, b"")}
    throttled, sent, waits = _pull(tmp_path / "throttled", "candidate", transport=Transport(script))
    plain, _, none = _pull(tmp_path / "plain", "candidate")
    assert sent.kinds() == [ROOTS, ROOTS, *[TRACE] * 6]
    assert none == [] and len(waits) == 4
    assert waits[0] == 7 and waits[2] == 2.5
    assert 0 < waits[1] <= 60 and 0 < waits[3] <= 60, waits
    asked = [(c["method"], c["url"], c["body"]) for c in sent.calls[2:6]]
    assert all(a == asked[0] for a in asked), "the same request is asked again"
    assert sent.calls[6]["body"] == sent.calls[7]["body"]
    assert recs(tmp_path / "throttled", "r") == recs(tmp_path / "plain", "r")
    assert raw_lines(tmp_path / "throttled", "r") == raw_lines(tmp_path / "plain", "r")
    assert throttled["counts"] == plain["counts"]


def test_tf26_43_the_root_calls_are_waited_out_too(tmp_path: Path) -> None:
    script = {1: (429, {"Retry-After": "3"}, b"")}
    data, sent, waits = _pull(tmp_path / "st", "baseline", transport=Transport(script))
    assert sent.kinds() == [ROOTS, *WHOLE] and waits == [3]
    assert tally(data) == {"met": 6, "missed": 3}


# ---------- TF26-44 ----------


@pytest.mark.parametrize("extra", [(), ("--keep-raw-text",), ("--json",)])
def test_tf26_44_the_key_is_printed_nowhere_and_written_nowhere(tmp_path: Path, extra: tuple[str, ...]) -> None:
    with pulling() as (_, _waits):
        result = run_import([*wv_argv(address("candidate"), tmp_path / "st", "r"), *extra])
    assert result.code == 0, result.err
    token = basic()[len("Basic "):]
    for piece in (PLANTED_KEY, token):
        assert piece not in result.out + result.err
    held = stored_bytes(tmp_path / "st")
    for piece in (PLANTED_KEY, PLANTED_KEY[:16], PLANTED_KEY[-12:], token, token[:16], token[-12:], "Basic "):
        assert piece.encode() not in held, piece
    assert KEY_VARIABLE.encode() not in held


@pytest.mark.parametrize("endpoint", ["https://wandb.example.internal/traces/"])
def test_tf26_44_the_endpoint_variable_moves_every_request(tmp_path: Path, endpoint: str) -> None:
    host = endpoint.rstrip("/")
    data, sent, _ = _pull(tmp_path / "st", "baseline", transport=Transport(host=host), endpoint=endpoint)
    assert len(sent.calls) == 4 and all(c["url"] == host + QUERY for c in sent.calls)
    doc = json.loads((raw_folder(tmp_path / "st", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["endpoint"] == host + QUERY, doc["endpoint"]
    assert tally(data) == {"met": 6, "missed": 3}


def test_tf26_44_the_other_pullers_keys_and_endpoints_are_not_weave_s(tmp_path: Path) -> None:
    """Each puller reads its own key and its own endpoint: LangSmith's and Braintrust's set and
    Weave's key not is a refusal that asks nothing, and their endpoints, and W&B's own API's,
    move no Weave request."""
    import os

    with pulling(key=None) as (sent, _):
        os.environ["LANGSMITH_API_KEY"] = "lsv2_pt_another_key_entirely_0000"
        os.environ["BRAINTRUST_API_KEY"] = "sk-another-key-entirely-0000"
        line = refused(run_import(wv_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == [] and KEY_VARIABLE in line and "lsv2_pt" not in line and "sk-another" not in line
    with pulling() as (sent, _):
        os.environ["LANGSMITH_ENDPOINT"] = "https://langsmith.example.internal"
        os.environ["BRAINTRUST_API_URL"] = "https://braintrust.example.internal"
        os.environ["WANDB_BASE_URL"] = "https://api.wandb.example.internal"
        imported(wv_argv(address("baseline"), tmp_path / "st", "r"))
        assert all(c["url"] == HOST + QUERY for c in sent.calls)
        assert all({k.lower(): v for k, v in c["headers"].items()}["authorization"] == basic() for c in sent.calls)


# ---------- TF26-45 ----------


def test_tf26_45_an_import_of_files_asks_nothing(tmp_path: Path) -> None:
    with pulling(never(), key=None):
        for kind in EXPORTS:
            imported(of("baseline", kind, tmp_path / kind, "r", mode="status"))


def test_tf26_45_every_row_of_a_pull_is_one_the_committed_answer_holds(tmp_path: Path) -> None:
    _pull(tmp_path / "st", "baseline")
    rows = rows_by_case(calls_of(export("baseline", "expanded")[0]), "baseline")
    assert sorted(recs(tmp_path / "st", "r")) == sorted(rows) == list(CASES)
