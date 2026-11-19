"""TF25-33 to TF25-46: the raw-saving pull (the folder a pull saves is the one TF22's resolver
reads; the LangSmith pull's TF24-33 to TF24-46 in Braintrust's words). No test here reaches
the network: ``pulling.send`` is replaced by a transport that answers each request with the
response Braintrust gave to that request (``api/requests.json``), and every socket connection
is refused while it runs.

- TF25-33: what is asked. ``braintrust:PROJECT/EXPERIMENT`` in the files' place asks for the
  project's experiments (``GET /v1/experiment?project_name=PROJECT``) and then for the events
  of the one named (``GET /v1/experiment/{id}/fetch?limit=1000``), following the answer's
  cursor until a page comes back empty, each with the key as a bearer token, and nothing else:
  no request narrows the events to a window, so every event is read however old.
- TF25-34: what is saved, before anything is read: ``raw.jsonl`` (the events, one a line, in
  the order returned) and ``pull.json`` (``poisson.raw-pull/1``: the tool, when, the address,
  the endpoint, whether the text was left out, and the file with its digest and its rows) under
  ``STORE/.poisson/raw/braintrust/RUN/``, and nothing else there; TF22's resolver reads the
  folder as a pull of ``braintrust``.
- TF25-35: the content and the run's own metadata are measured and left out by default: no
  input, output, expected value, traceback or comment is in the raw copy, nor the paths of the
  machine that ran the experiment (``context``), nor the audit trail, nor a step's metadata
  beyond the model's name and provider; each span carries ``_poisson_input_chars`` and
  ``_poisson_output_chars``, and each root its input's key; an error keeps its class alone,
  with the kind its words said beside it, so the saved folder reads to the same kinds.
  ``--keep-raw-text`` saves the events as the API returned them and says so.
- TF25-36: the pull is the file reader on the saved folder: its run is, record for record and
  column for column, the import of the committed fetch; its summary names ``raw.jsonl`` with
  the digest ``pull.json`` lists, carries a ``pull`` block and one ``- pulled:`` line, and ends
  with the fix check as every import does.
- TF25-37: the saved folder is read again with no key and no request: under another run name,
  with the tool named or not, and with other flags (the case by the record, by a metadata key
  or by the input; the outcome by the error), each the run the committed fetch gives with those
  flags.
- TF25-38: paging. In pages of 25 the fetch follows ``cursor``, asks again after a short page,
  and stops at the empty one; the run is the one a single page gives. An empty page ends the
  pull whatever it names; a cursor that repeats is a failure.
- TF25-39: a raw copy is never written over: a second pull under a name the store holds is
  refused before any request; a pull whose read was refused leaves its raw copy, and pulling
  that name again is refused naming the folder and the command that reads it.
- TF25-40: refused before any request, exit 1, nothing written: no key, an address naming no
  project or no experiment, the service's own host asked over http. A wrong command
  line exits 2: an address beside files, no ``--run``, ``--keep-raw-text`` or ``--page-size``
  without an address, a page size that is not 1 to 1000.
- TF25-41: the service says no, exit 1, nothing saved: no experiment of that name in the
  project; a key refused (401, 403), which names the variable and never the key.
- TF25-42: a failure after the pull began, exit 3, nothing saved and no folder left: at each
  request, a 500, an answer that is not JSON, an answer of another shape.
- TF25-43: a 429 is waited out and asked again: the wait is the answer's ``Retry-After`` where
  given, and grows where it is not; the run is the one an unthrottled pull gives.
- TF25-44: the key is printed nowhere and written nowhere; ``BRAINTRUST_API_URL`` moves every
  request to that host.
- TF25-45: ``pulling.send`` is the only code in the package that reaches the network, standard
  library only; an import of files calls it never.
- TF25-46: ``--json`` on a pull is one document, whose ``pull`` block TF25-36 holds.

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
from tf25_support import (
    API, CONTENT, ENDPOINT_VARIABLE, EVENTS, EXACT, EXPERIMENT_ID, EXPERIMENTS, EXPORTS, FETCH, HOST, ITEM, KEY,
    KEY_VARIABLE, LISTING, PLANTED_KEY, PROJECT, VERSIONS, Transport, address, bt_argv, by_error, columns, end_cursors,
    export, imported, is_root, never, pulling, raw_folder, raw_lines, recs, refused, rows_of, snapshot,
    stored_bytes, tally, tries, wrong_line,
)


def _pull(root: Path, name: str = "baseline", run: str = "r", *extra: Any, transport: Transport | None = None,
          argv: Any = None, **env: Any) -> tuple[dict[str, Any], Transport, list[float]]:
    with pulling(transport, **env) as (sent, waits):
        data = imported((argv or bt_argv)(address(name), root, run, *extra))
    return data, sent, waits


def _raw_dirs(root: Path) -> list[str]:
    base = root / ".poisson" / "raw"
    return sorted(str(p.relative_to(base)) for p in base.rglob("*")) if base.exists() else []


def _nothing_saved(root: Path, run: str = "r") -> bool:
    return not (root / run).exists() and _raw_dirs(root) in ([], ["braintrust"])


# ---------- TF25-33 ----------


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_33_the_pull_asks_for_the_experiment_and_its_events(tmp_path: Path, name: str) -> None:
    _, sent, waits = _pull(tmp_path / "st", name)
    assert sent.paths() == [LISTING, FETCH, FETCH]
    assert waits == []
    listing, first, last = sent.calls
    assert listing["url"] == f"{HOST}/v1/experiment?project_name={PROJECT}"
    exp_id = EXPERIMENT_ID[name]
    assert first["url"] == f"{HOST}/v1/experiment/{exp_id}/fetch?limit=1000"
    # every whole answer ends with a cursor: the pull asks once more, and the empty page ends it
    assert sent.queries()[2] == {"limit": "1000", "cursor": end_cursors()[exp_id]}
    assert last["url"].startswith(f"{HOST}/v1/experiment/{exp_id}/fetch?")
    for call in sent.calls:
        assert call["method"] == "GET" and call["body"] is None
        headers = {k.lower(): v for k, v in call["headers"].items()}
        assert headers["authorization"] == f"Bearer {PLANTED_KEY}"
        assert PLANTED_KEY not in call["url"]


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_33_no_request_narrows_the_events_to_a_window(tmp_path: Path, name: str) -> None:
    """Nothing asked bounds the events by time, by version or by a filter: the fetch is asked
    for the experiment whole, and every event of it is saved."""
    _, sent, _ = _pull(tmp_path / "st", name)
    assert sent.queries()[0] == {"project_name": PROJECT}
    for query in sent.queries()[1:]:
        assert set(query) <= {"limit", "cursor"}, query
    assert len(raw_lines(tmp_path / "st", "r")) == EVENTS[name]


# ---------- TF25-34 ----------


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_tf25_34_the_raw_copy_and_its_record(tmp_path: Path, name: str) -> None:
    from datetime import datetime

    from poisson_trace.ingest.folder import resolve

    root = tmp_path / "st"
    _pull(root, name, "first run")
    folder = raw_folder(root, "first run")
    assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
    assert _raw_dirs(root) == ["braintrust", "braintrust/first run", "braintrust/first run/pull.json", "braintrust/first run/raw.jsonl"]
    doc = json.loads((folder / "pull.json").read_text(encoding="utf-8"))
    assert set(doc) == {"schema", "tool", "pulled_at", "source_uri", "endpoint", "raw_text_stripped", "files"}
    assert doc["schema"] == "poisson.raw-pull/1" and doc["tool"] == "braintrust"
    assert doc["source_uri"] == address(name) and doc["raw_text_stripped"] is True
    assert doc["endpoint"] == f"{HOST}/v1/experiment/{EXPERIMENT_ID[name]}/fetch", doc["endpoint"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["pulled_at"]) and datetime.fromisoformat(doc["pulled_at"][:-1])
    raw = (folder / "raw.jsonl").read_bytes()
    assert doc["files"] == [{"path": "raw.jsonl", "sha256": hashlib.sha256(raw).hexdigest(), "rows": EVENTS[name]}]
    lines = raw_lines(root, "first run")
    assert len(lines) == EVENTS[name] and raw.endswith(b"\n")
    assert [r["id"] for r in lines] == [r["id"] for r in rows_of(export(name, "fetch")[0])]
    assert all("span_id" in r and "root_span_id" in r and "span_attributes" in r for r in lines)
    found = resolve(folder)
    assert (found.kind, found.tool, [p.name for p in found.files]) == ("pull", "braintrust", ["raw.jsonl"])


# ---------- TF25-35 ----------

#: What a stripped event does not carry: the content, the paths of the machine that ran the
#: experiment, and the audit trail (which repeats the metadata written and who wrote it).
STRIPPED = ("input", "output", "expected", "context", "audit_data")
#: What a step's metadata keeps: the model's name and its provider.
STEP_METADATA = {"model", "provider"}
#: The kind each captured error's words say, by its class: a timeout, a 429, and a complaint
#: about a reply.
WORDS_SAY = {"TimeoutError": "timeout", "RuntimeError": "rate_limit", "ValueError": None}


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_35_the_content_is_measured_and_left_out(tmp_path: Path, version: str) -> None:
    root = tmp_path / "st"
    _pull(root, version)
    lines = raw_lines(root, "r")
    source = {r["id"]: r for r in rows_of(export(version, "fetch")[0])}
    assert len(lines) == len(source)
    errors = 0
    for event in lines:
        was = source[event["id"]]
        assert not [key for key in STRIPPED if key in event], event["id"]
        assert event["comments"] is None
        for stamp, key in (("_poisson_input_chars", "input"), ("_poisson_output_chars", "output")):
            assert event[stamp] is None if was[key] is None else isinstance(event[stamp], int), (event["id"], stamp)
        if is_root(was):
            case = was["input"]["case"]
            assert event["_poisson_input_chars"] == len(case) + len(ITEM[case])
            assert event["_poisson_input_key"] == KEY[case]
            assert event["metadata"] == was["metadata"]
        else:
            assert "_poisson_input_key" not in event
            assert event["metadata"] is None or set(event["metadata"]) <= STEP_METADATA, event["metadata"]
            if was["span_attributes"]["type"] == "llm":
                assert event["metadata"] == {"model": "gpt-4.1-mini", "provider": "openai"}
        if was["error"]:
            # an error's own words may quote a reply: its class is kept, and the kind its words say
            errors += 1
            assert re.fullmatch(r"[A-Za-z_][\w.]*", event["error"]) and event["error"] in WORDS_SAY, event["error"]
            assert was["error"].rstrip().splitlines()[-1].startswith(event["error"] + ":")
            assert event["_poisson_error_kind"] == WORDS_SAY[event["error"]], event
        else:
            assert not event.get("error") and event.get("_poisson_error_kind") is None
        # everything that is not content is as the API returned it
        for key, value in was.items():
            if key not in (*STRIPPED, "error", "comments", "metadata"):
                assert event[key] == value, (event["id"], key)
    assert errors == {"baseline": 3, "candidate": 4}[version]
    held = stored_bytes(root)
    for text in (*CONTENT, "caller_filename", "site-packages", "max_tokens", "temperature"):
        assert text.encode() not in held, text
    for item in ITEM.values():
        assert item.encode() not in held, item


def test_tf25_35_a_comment_is_left_out_of_the_raw_copy(tmp_path: Path) -> None:
    """No capture holds a comment (none was made in the page), so the fetch's answer is given
    one here on every event: none is in the raw copy or the store, and ``--keep-raw-text``
    keeps it in the raw copy alone."""
    said = "the reviewer wrote: this answer leaks the customer's address"
    whole = json.loads((API / "slice-baseline.fetch.json").read_text(encoding="utf-8"))
    for event in whole["events"]:
        event["comments"] = [{"text": said, "created": "2026-11-09T21:00:00Z"}]
    answer = (200, {}, json.dumps(whole).encode("utf-8"))
    _pull(tmp_path / "st", "baseline", transport=Transport({2: answer}))
    assert all(event["comments"] is None for event in raw_lines(tmp_path / "st", "r"))
    assert said.encode() not in stored_bytes(tmp_path / "st")
    _pull(tmp_path / "kept", "baseline", "r", "--keep-raw-text", transport=Transport({2: answer}))
    assert said.encode() in (raw_folder(tmp_path / "kept", "r") / "raw.jsonl").read_bytes()
    assert said.encode() not in stored_bytes(tmp_path / "kept" / "r")
    assert recs(tmp_path / "kept", "r") == recs(tmp_path / "st", "r")


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_35_keep_raw_text_saves_the_events_as_the_api_returned_them(tmp_path: Path, version: str) -> None:
    kept, _, _ = _pull(tmp_path / "kept", version, "r", "--keep-raw-text")
    plain, _, _ = _pull(tmp_path / "plain", version)
    assert raw_lines(tmp_path / "kept", "r") == rows_of(export(version, "fetch")[0])
    doc = json.loads((raw_folder(tmp_path / "kept", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["raw_text_stripped"] is False and kept["pull"]["raw_text_stripped"] is False
    assert plain["pull"]["raw_text_stripped"] is True
    # the lengths stamped are the lengths measured: both read to the same run
    assert recs(tmp_path / "kept", "r") == recs(tmp_path / "plain", "r")
    # and the run's own folder holds no text either way
    assert not [t for t in CONTENT if t.encode() in stored_bytes(tmp_path / "kept" / "r")]


# ---------- TF25-36 ----------


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
def test_tf25_36_the_pulled_run_is_the_import_of_the_same_answer_as_a_file(tmp_path: Path, version: str, keep: bool) -> None:
    pulled, _, _ = _pull(tmp_path / "pulled", version, "r", *(["--keep-raw-text"] if keep else []))
    files = imported(bt_argv(export(version, "fetch"), tmp_path / "files", "r"))
    _same_run(tmp_path / "pulled", tmp_path / "files")
    for key in ("rows", "cases", "repeats", "outcomes", "no_outcome", "counts", "started", "declared", "tool"):
        assert pulled[key] == files[key], key
    assert {case: r["score"] for case, r in recs(tmp_path / "pulled", "r").items()} == EXACT[version]


@pytest.mark.parametrize("name", ["old", "new"])
def test_tf25_36_and_of_the_lookup_fixture(tmp_path: Path, name: str) -> None:
    _pull(tmp_path / "pulled", name)
    imported(bt_argv(export(name, "fetch"), tmp_path / "files", "r"))
    assert tries(tmp_path / "pulled", "r") == tries(tmp_path / "files", "r")


def test_tf25_36_the_summary_says_what_was_pulled(tmp_path: Path) -> None:
    root = tmp_path / "st"
    with pulling() as (_, _waits):
        data = imported(bt_argv(address("candidate"), root, "new"))
        text = run_import(bt_argv(address("baseline"), root, "old"))
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
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    # an import of files says nothing of a pull
    plain = run_import(by_error(export("baseline", "fetch"), tmp_path / "other", "r"))
    assert plain.code == 0 and "- pulled: " not in plain.out
    assert "pull" not in imported(by_error(export("baseline", "fetch"), tmp_path / "other", "r2"))


# ---------- TF25-37 ----------

AGAIN = {
    "by the record and the error": {"case": "record", "outcome": "error", "cut": None},
    "by a metadata key and the score": {"case": "metadata:case"},
    "by the input and the error": {"case": "input", "outcome": "error", "cut": None},
    "by the record and another score": {"case": "record", "outcome": "score:gave_answer"},
}


@pytest.mark.parametrize("keep", [False, True])
def test_tf25_37_the_saved_folder_reads_again_with_no_key_and_no_request(tmp_path: Path, keep: bool) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "r", *(["--keep-raw-text"] if keep else []))
    folder = raw_folder(root, "r")
    before = snapshot(folder)
    with pulling(never(), key=None):
        again = imported(bt_argv(folder, root, "again"))
        unnamed = run_import([str(folder), "--store", str(root), "--run", "unnamed", "--case-from", "input",
                              "--outcome-from", "score:exact", "--cut", "0.5", "--below", "--json"])
        elsewhere = imported(bt_argv(folder, tmp_path / "elsewhere", "r"))
        assert unnamed.code == 0, unnamed.err
        assert recs(root, "again") == recs(root, "r") == recs(root, "unnamed") == recs(tmp_path / "elsewhere", "r")
        assert again["files"][0]["name"] == "raw.jsonl" and "pull" not in again and "pull" not in elsewhere
        for label, flags in AGAIN.items():
            run = label.replace(" ", "-")
            saved = imported(bt_argv(folder, root, run, **flags))
            files = imported(bt_argv(export("baseline", "fetch"), tmp_path / "files", run, **flags))
            _same_run(root, tmp_path / "files", run, run)
            for key in ("rows", "cases", "outcomes", "no_outcome", "counts", "declared"):
                assert saved[key] == files[key], (label, key)
    assert snapshot(folder) == before


# ---------- TF25-38 ----------


def test_tf25_38_in_pages_the_fetch_follows_the_cursor_to_the_empty_page(tmp_path: Path) -> None:
    paged, sent, _ = _pull(tmp_path / "paged", "candidate", "r", "--page-size", "25")
    whole, once, _ = _pull(tmp_path / "whole", "candidate")
    # the fourth page holds 13 events, fewer than asked for, and a cursor: the pull asks again
    assert sent.paths() == [LISTING, *[FETCH] * 5]
    queries = sent.queries()[1:]
    assert [q["limit"] for q in queries] == ["25"] * 5 and "cursor" not in queries[0]
    pages = [json.loads((API / f"slice-candidate.fetch.page-{n}.json").read_text()) for n in (1, 2, 3, 4)]
    assert [q["cursor"] for q in queries[1:]] == [p["cursor"] for p in pages]
    assert len(once.calls) == 3
    assert len(raw_lines(tmp_path / "paged", "r")) == 88
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    assert paged["counts"] == whole["counts"] and paged["counts"]["events"] == 88
    assert [row["id"] for row in raw_lines(tmp_path / "paged", "r")] == [row["id"] for row in raw_lines(tmp_path / "whole", "r")]


def test_tf25_38_an_empty_page_ends_the_pull_whatever_it_names(tmp_path: Path) -> None:
    script = {3: (200, {}, json.dumps({"events": [], "cursor": "still-a-cursor"}).encode())}
    data, sent, _ = _pull(tmp_path / "st", "baseline", transport=Transport(script))
    assert sent.paths() == [LISTING, FETCH, FETCH] and data["counts"]["events"] == 85


def test_tf25_38_a_page_with_no_cursor_ends_the_pull(tmp_path: Path) -> None:
    whole = json.loads((API / "slice-baseline.fetch.json").read_text(encoding="utf-8"))
    script = {2: (200, {}, json.dumps({"events": whole["events"]}).encode())}
    data, sent, _ = _pull(tmp_path / "st", "baseline", transport=Transport(script))
    assert sent.paths() == [LISTING, FETCH] and data["counts"]["events"] == 85


def test_tf25_38_a_cursor_that_repeats_is_a_failure_and_never_a_loop(tmp_path: Path) -> None:
    page = (API / "slice-candidate.fetch.page-2.json").read_bytes()
    script = {n: (200, {}, page) for n in range(3, 60)}
    with pulling(Transport(script)) as (sent, _):
        result = run_import(bt_argv(address("candidate"), tmp_path / "st", "r", "--page-size", "25"))
    assert result.code == 3 and "nothing was saved" in result.err, result.err
    assert len(sent.calls) <= 6, len(sent.calls)
    assert _nothing_saved(tmp_path / "st")


# ---------- TF25-39 ----------


def test_tf25_39_a_name_the_store_holds_is_refused_before_any_request(tmp_path: Path) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "old")
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(bt_argv(address("candidate"), root, "old")))
        assert sent.calls == []
    assert "old" in line, line
    assert snapshot(root) == before
    # the same for a name a file import took, which left no raw copy to stand in the way
    imported(by_error(export("baseline", "fetch"), root, "from-a-file"))
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(bt_argv(address("candidate"), root, "from-a-file")))
        assert sent.calls == []
    assert "from-a-file" in line, line
    assert snapshot(root) == before


def test_tf25_39_a_raw_copy_is_never_written_over(tmp_path: Path) -> None:
    """A pull whose read is then refused (no root has the score named) keeps what it pulled:
    the raw copy is the pull. Pulling under that name again is refused, naming the folder and
    the command that reads it; that command, with a key the roots do have, writes the run."""
    root = tmp_path / "st"
    with pulling() as (sent, _):
        first = run_import(bt_argv(address("baseline"), root, "old", outcome="score:no_such_key"))
        assert first.code == 1 and len(sent.calls) == 3, first.err
        folder = raw_folder(root, "old")
        assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
        assert not (root / "old").exists()
        before = snapshot(folder)
        again = run_import(bt_argv(address("baseline"), root, "old"))
        line = refused(again)
        assert len(sent.calls) == 3, "no request is made for a pull that is already saved"
    assert str(folder) in line, line
    nexts = [following[len("  next: "):] for following in again.err.splitlines()[1:]]
    assert len(nexts) == 1 and nexts[0].startswith("poisson-trace import braintrust ") and str(folder) in nexts[0], again.err
    for flag in ("--case-from input", "--outcome-from score:exact", "--cut 0.5", "--below"):
        assert flag in nexts[0], nexts[0]
    assert snapshot(folder) == before
    with pulling(never(), key=None):
        data = imported(bt_argv(folder, root, "old"))
    assert tally(data) == {"met": 6, "missed": 3} and snapshot(folder) == before


# ---------- TF25-40 ----------


@pytest.mark.parametrize("key", [None])
def test_tf25_40_no_key_is_refused_naming_the_variable(tmp_path: Path, key: str | None) -> None:
    with pulling(key=key) as (sent, _):
        line = refused(run_import(bt_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert KEY_VARIABLE in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("named", ["braintrust:", "braintrust:trace-fixture", "braintrust:trace-fixture/", "braintrust:/slice-baseline", "braintrust: / "])
def test_tf25_40_an_address_naming_no_project_or_no_experiment_is_refused(tmp_path: Path, named: str) -> None:
    with pulling() as (sent, _):
        line = refused(run_import(bt_argv(named, tmp_path / "st", "r")))
        assert sent.calls == []
    assert "braintrust:PROJECT/EXPERIMENT" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("endpoint", ["http://api.braintrust.dev"])
def test_tf25_40_the_key_goes_over_https_or_to_this_machine_only(tmp_path: Path, endpoint: str) -> None:
    with pulling(endpoint=endpoint) as (sent, _):
        line = refused(run_import(bt_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert ENDPOINT_VARIABLE in line and PLANTED_KEY not in line, line
    assert not (tmp_path / "st").exists()


WRONG: dict[str, Any] = {
    "an address beside a file": lambda root: bt_argv([address("baseline"), *export("baseline", "fetch")], root, "r"),
    "two addresses": lambda root: bt_argv([address("baseline"), address("candidate")], root, "r"),
    "no run name": lambda root: bt_argv(address("baseline"), root, None),
    "keep-raw-text with files": lambda root: bt_argv(export("baseline", "fetch"), root, "r", "--keep-raw-text"),
    "page-size with files": lambda root: bt_argv(export("baseline", "fetch"), root, "r", "--page-size", "25"),
    "a page size of 0": lambda root: bt_argv(address("baseline"), root, "r", "--page-size", "0"),
    "a page size of 1001": lambda root: bt_argv(address("baseline"), root, "r", "--page-size", "1001"),
    "a page size that is no number": lambda root: bt_argv(address("baseline"), root, "r", "--page-size", "many"),
}


@pytest.mark.parametrize("label", list(WRONG))
def test_tf25_40_a_wrong_command_line_exits_2_and_asks_nothing(tmp_path: Path, label: str) -> None:
    with pulling() as (sent, _):
        wrong_line(run_import(WRONG[label](tmp_path / "st")))
        assert sent.calls == []
    assert not (tmp_path / "st").exists()


# ---------- TF25-41 ----------


@pytest.mark.parametrize("named", [f"braintrust:{PROJECT}/no-such-experiment", "braintrust:no-such-project/slice-baseline"])
def test_tf25_41_no_experiment_of_that_name(tmp_path: Path, named: str) -> None:
    script = {} if PROJECT in named else {1: (200, {}, b'{"objects": []}')}
    with pulling(Transport(script)) as (sent, _):
        line = refused(run_import(bt_argv(named, tmp_path / "st", "r")))
        assert sent.paths() == [LISTING]
    assert named.split("/", 1)[1] in line and named.split(":", 1)[1].split("/")[0] in line, line
    assert _nothing_saved(tmp_path / "st")


def test_tf25_41_an_experiment_s_name_is_matched_whole(tmp_path: Path) -> None:
    """``slice`` is the start of two experiments' names and the name of none."""
    with pulling() as (sent, _):
        line = refused(run_import(bt_argv(f"braintrust:{PROJECT}/slice", tmp_path / "st", "r")))
        assert sent.paths() == [LISTING]
    assert "slice" in line, line
    assert _nothing_saved(tmp_path / "st")


@pytest.mark.parametrize(("at", "status"), [(1, 401), (1, 403), (2, 401), (3, 401)])
def test_tf25_41_a_key_the_service_refuses(tmp_path: Path, status: int, at: int) -> None:
    body = json.dumps({"detail": f"Invalid token {PLANTED_KEY}"}).encode()
    with pulling(Transport({at: (status, {}, body)})) as (sent, _):
        result = run_import(bt_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    line = refused(result)
    assert KEY_VARIABLE in line and str(status) in line and PLANTED_KEY not in result.err, result.err
    assert _nothing_saved(tmp_path / "st")


# ---------- TF25-42 ----------

FAILURES: dict[str, Any] = {
    "a 500": (500, {}, b"Internal Server Error"),
    "an answer that is not JSON": (200, {}, b"<html>sign in</html>"),
    "an answer of another shape": (200, {}, b'"ok"'),
}


@pytest.mark.parametrize(("at", "label"), [(at, label) for at in (1, 2, 3) for label in FAILURES])
def test_tf25_42_a_failure_after_the_pull_began_exits_3_and_saves_nothing(tmp_path: Path, label: str, at: int) -> None:
    with pulling(Transport({at: FAILURES[label]})) as (sent, _):
        result = run_import(bt_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    assert result.code == 3 and result.out == "", result.out + result.err
    lines = result.err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("error: ") and "Traceback" not in result.err, result.err
    assert "nothing was saved" in lines[0] and PLANTED_KEY not in result.err, result.err
    assert _nothing_saved(tmp_path / "st")


# ---------- TF25-43 ----------


def test_tf25_43_a_429_is_waited_out_and_asked_again(tmp_path: Path) -> None:
    script = {2: (429, {"Retry-After": "7"}, b"{}"), 3: (429, {}, b""), 4: (429, {"retry-after": "2.5"}, b""), 6: (429, {}, b"")}
    throttled, sent, waits = _pull(tmp_path / "throttled", "candidate", transport=Transport(script))
    plain, _, none = _pull(tmp_path / "plain", "candidate")
    assert sent.paths() == [LISTING, *[FETCH] * 6]
    assert none == [] and len(waits) == 4
    assert waits[0] == 7 and waits[2] == 2.5
    assert 0 < waits[1] <= 60 and 0 < waits[3] <= 60, waits
    asked = [(c["method"], c["url"], c["body"]) for c in sent.calls[1:5]]
    assert all(a == asked[0] for a in asked), "the same request is asked again"
    assert sent.calls[5]["url"] == sent.calls[6]["url"]
    assert recs(tmp_path / "throttled", "r") == recs(tmp_path / "plain", "r")
    assert raw_lines(tmp_path / "throttled", "r") == raw_lines(tmp_path / "plain", "r")
    assert throttled["counts"] == plain["counts"]


def test_tf25_43_the_listing_is_waited_out_too(tmp_path: Path) -> None:
    script = {1: (429, {"Retry-After": "3"}, b"")}
    data, sent, waits = _pull(tmp_path / "st", "baseline", transport=Transport(script))
    assert sent.paths() == [LISTING, LISTING, FETCH, FETCH] and waits == [3]
    assert tally(data) == {"met": 6, "missed": 3}


# ---------- TF25-44 ----------


@pytest.mark.parametrize("extra", [(), ("--keep-raw-text",), ("--json",)])
def test_tf25_44_the_key_is_printed_nowhere_and_written_nowhere(tmp_path: Path, extra: tuple[str, ...]) -> None:
    with pulling() as (_, _waits):
        result = run_import([*bt_argv(address("candidate"), tmp_path / "st", "r"), *extra])
    assert result.code == 0, result.err
    assert PLANTED_KEY not in result.out + result.err
    held = stored_bytes(tmp_path / "st")
    for piece in (PLANTED_KEY, PLANTED_KEY[:16], PLANTED_KEY[-12:], "Bearer "):
        assert piece.encode() not in held, piece
    assert KEY_VARIABLE.encode() not in held


@pytest.mark.parametrize("endpoint", ["https://api-eu.braintrust.dev"])
def test_tf25_44_the_endpoint_variable_moves_every_request(tmp_path: Path, endpoint: str) -> None:
    host = endpoint.rstrip("/")
    data, sent, _ = _pull(tmp_path / "st", "baseline", transport=Transport(host=host), endpoint=endpoint)
    assert len(sent.calls) == 3 and all(c["url"].startswith(host + "/v1/experiment") for c in sent.calls)
    doc = json.loads((raw_folder(tmp_path / "st", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["endpoint"].startswith(host + "/v1/experiment/"), doc["endpoint"]
    assert tally(data) == {"met": 6, "missed": 3}


def test_tf25_44_langsmith_s_key_and_endpoint_are_not_braintrust_s(tmp_path: Path) -> None:
    """Each puller reads its own key and its own endpoint: LangSmith's variables set and
    Braintrust's key not is a refusal that asks nothing, and LangSmith's endpoint moves no
    Braintrust request."""
    import os

    with pulling(key=None) as (sent, _):
        os.environ["LANGSMITH_API_KEY"] = "lsv2_pt_another_key_entirely_0000"
        line = refused(run_import(bt_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == [] and KEY_VARIABLE in line and "lsv2_pt" not in line
    with pulling() as (sent, _):
        os.environ["LANGSMITH_ENDPOINT"] = "https://langsmith.example.internal"
        imported(bt_argv(address("baseline"), tmp_path / "st", "r"))
        assert all(c["url"].startswith(HOST + "/") for c in sent.calls)


# ---------- TF25-45 ----------


def test_tf25_45_an_import_of_files_asks_nothing(tmp_path: Path) -> None:
    with pulling(never(), key=None):
        for kind in EXPORTS:
            imported(by_error(export("baseline", kind), tmp_path / kind, "r"))
