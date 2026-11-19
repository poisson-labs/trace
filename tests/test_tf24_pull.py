"""TF24-33 to TF24-46: the raw-saving pull (the raw copy saved before anything is read, its text
left out by default; the folder a pull saves is the one TF22's resolver reads). No test here
reaches the network: ``pulling.send`` is replaced by a transport that answers each request with
the response LangSmith gave to that request (``api/requests.json``), and every socket connection
is refused while it runs.

- TF24-33: what is asked. ``langsmith:NAME`` in the files' place asks for the project or
  experiment by name (``GET /api/v1/sessions``), its runs (``POST /api/v2/runs/query`` with the
  committed request's body) and its feedback records (``GET /api/v1/feedback``), in that order,
  each with the key in ``x-api-key``, and nothing else.
- TF24-34: what is saved, before anything is read: ``raw.jsonl`` (the runs, then the feedback
  records, one a line) and ``pull.json`` (``poisson.raw-pull/1``: the tool, when, the address,
  the endpoint, whether the text was left out, and the file with its digest and its rows) under
  ``STORE/.poisson/raw/langsmith/RUN/``, and nothing else there; TF22's resolver reads the
  folder as a pull of ``langsmith``.
- TF24-35: the text is measured and left out by default: no input, output, preview, traceback
  or comment is in the raw copy; each run carries ``_poisson_input_chars`` and
  ``_poisson_output_chars``, and each root its input's key; an error keeps its class alone,
  with the kind its words said beside it, so the saved folder reads to the same kinds.
  ``--keep-raw-text`` saves the rows as the API returned them and says so.
- TF24-36: the pull is the file reader on the saved folder: its run is, record for record and
  column for column, the import of the committed v2 answer and feedback list; its summary names
  ``raw.jsonl`` with the digest ``pull.json`` lists, carries a ``pull`` block and one
  ``- pulled:`` line, and ends with the fix check as every import does.
- TF24-37: the saved folder is read again with no key and no request: under another run name,
  with the tool named or not, and with other flags (the case by input, the outcome by status).
- TF24-38: paging. In pages of 25 the runs follow ``next_cursor`` and the feedback its offset,
  and the run is the one a single page gives.
- TF24-39: a raw copy is never written over: a second pull under a name the store holds is
  refused before any request; a pull whose read was refused leaves its raw copy, and pulling
  that name again is refused naming the folder and the command that reads it.
- TF24-40: refused before any request, exit 1, nothing written: no key, an empty key, an
  address naming nothing, an endpoint that is not https. A wrong command line exits 2: an
  address beside files, no ``--run``, ``--keep-raw-text`` or ``--page-size`` without an address,
  a page size that is not 1 to 100.
- TF24-41: the service says no, exit 1, nothing saved: no project of that name; a key refused
  (401, 403), which names the variable and never the key.
- TF24-42: a failure after the pull began, exit 3, nothing saved and no folder left: a 500, an
  answer that is not JSON, the connection failing, 429 on every try.
- TF24-43: a 429 is waited out and asked again: the wait is the answer's ``Retry-After`` where
  given, and grows where it is not; the run is the one an unthrottled pull gives.
- TF24-44: the key is printed nowhere and written nowhere; ``LANGSMITH_ENDPOINT`` moves every
  request to that host, https or this machine alone.
- TF24-45: ``pulling.send`` is the only code in the package that reaches the network, standard
  library only; an import of files calls it never. The scan of the package holds this for the
  three readers that pull (LangSmith, Braintrust, Weave), none of which imports its service's
  SDK.
- TF24-46: ``--json`` on a pull is one document; a pull that failed exits 3 with nothing on
  stdout and the error in a line on stderr.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf21_support import run_import
from tf24_support import (
    API, CASES, CONTENT, ENDPOINT_VARIABLE, EXACT, EXPERIMENT, FEEDBACK, HOST, ITEM, KEY_VARIABLE, PLANTED_KEY, RUNS,
    SESSION, VERSIONS, Transport, address, by_status, columns, export, feedback_file, imported, ls_argv, pulling,
    raw_folder, raw_lines, recs, refused, rows_of, run_id, snapshot, stored_bytes, tally, wrong_line,
)


def _pull(root: Path, version: str = "baseline", run: str = "r", *extra: Any, transport: Transport | None = None,
          argv: Any = None, **env: Any) -> tuple[dict[str, Any], Transport, list[float]]:
    with pulling(transport, **env) as (sent, waits):
        data = imported((argv or ls_argv)(address(version), root, run, *extra))
    return data, sent, waits


def _raw_dirs(root: Path) -> list[str]:
    base = root / ".poisson" / "raw"
    return sorted(str(p.relative_to(base)) for p in base.rglob("*")) if base.exists() else []


# ---------- TF24-33 ----------


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_33_the_pull_asks_for_the_session_its_runs_and_its_feedback(tmp_path: Path, version: str) -> None:
    _, sent, waits = _pull(tmp_path / "st", version)
    assert sent.paths() == ["GET /api/v1/sessions", "POST /api/v2/runs/query", "GET /api/v1/feedback"]
    assert waits == []
    first, runs, feedback = sent.calls
    assert first["url"] == f"{HOST}/api/v1/sessions?name={EXPERIMENT[version]}" and first["body"] is None
    body = json.loads(runs["body"].decode("utf-8"))
    committed = next(e["body"] for e in json.loads((API / "requests.json").read_text()) if e["file"] == f"{version}.runs-v2.json")
    assert body["project_ids"] == [SESSION[version]] and body["page_size"] == 100
    # the committed request, and a lower bound on the runs' start: with none, LangSmith answers
    # with the runs of the last day alone, as a live pull shows. The bound
    # is at or before the project's own start, which the sessions answer gives.
    assert sorted(body["selects"]) == sorted(committed["selects"]) and set(body) == {*committed, "min_start_time"}
    began = json.loads((API / f"{version}.session.json").read_text())[0]["start_time"]
    since = body["min_start_time"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", since) and since[:19] <= began[:19], (since, began)
    assert f"session={SESSION[version]}" in feedback["url"] and "limit=100" in feedback["url"]
    for call in sent.calls:
        headers = {k.lower(): v for k, v in call["headers"].items()}
        assert headers["x-api-key"] == PLANTED_KEY
        assert PLANTED_KEY not in call["url"]


# ---------- TF24-34 ----------


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_34_the_raw_copy_and_its_record(tmp_path: Path, version: str) -> None:
    from datetime import datetime

    from poisson_trace.ingest.folder import resolve

    root = tmp_path / "st"
    _pull(root, version, "first run")
    folder = raw_folder(root, "first run")
    assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
    assert _raw_dirs(root) == ["langsmith", "langsmith/first run", "langsmith/first run/pull.json", "langsmith/first run/raw.jsonl"]
    doc = json.loads((folder / "pull.json").read_text(encoding="utf-8"))
    assert set(doc) == {"schema", "tool", "pulled_at", "source_uri", "endpoint", "raw_text_stripped", "files"}
    assert doc["schema"] == "poisson.raw-pull/1" and doc["tool"] == "langsmith"
    assert doc["source_uri"] == address(version) and doc["raw_text_stripped"] is True
    assert doc["endpoint"].startswith(HOST + "/api/"), doc["endpoint"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["pulled_at"]) and datetime.fromisoformat(doc["pulled_at"][:-1])
    raw = (folder / "raw.jsonl").read_bytes()
    assert doc["files"] == [{"path": "raw.jsonl", "sha256": hashlib.sha256(raw).hexdigest(), "rows": RUNS[version] + FEEDBACK[version]}]
    lines = raw_lines(root, "first run")
    assert len(lines) == RUNS[version] + FEEDBACK[version] and raw.endswith(b"\n")
    runs, records = lines[:RUNS[version]], lines[RUNS[version]:]
    assert sorted(r["id"] for r in runs) == sorted(run_id(r) for r in rows_of(export(version, "v2")[0]))
    assert all("run_type" in r for r in runs) and all("feedback_source" in r and "run_type" not in r for r in records)
    assert sorted(r["id"] for r in records) == sorted(f["id"] for f in json.loads(feedback_file(version).read_text()))
    found = resolve(folder)
    assert (found.kind, found.tool, [p.name for p in found.files]) == ("pull", "langsmith", ["raw.jsonl"])


# ---------- TF24-35 ----------

# the manifest is left out too: empty in the captures, it is the serialised
# component, which in a LangChain app can hold a prompt template
STRIPPED = ("inputs", "outputs", "inputs_preview", "outputs_preview", "error_preview", "manifest")
#: The kind each captured error's words say, by its class: a timeout, a 429, and a parser's complaint.
WORDS_SAY = {"TimeoutError": "timeout", "RuntimeError": "rate_limit", "ValueError": None}


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_35_the_text_is_measured_and_left_out(tmp_path: Path, version: str) -> None:
    root = tmp_path / "st"
    _pull(root, version)
    lines = raw_lines(root, "r")
    runs = [r for r in lines if "run_type" in r]
    source = {run_id(r): r for r in rows_of(export(version, "v2")[0])}
    for run in runs:
        assert not [key for key in STRIPPED if key in run], run["id"]
        assert isinstance(run["_poisson_input_chars"], int) and isinstance(run["_poisson_output_chars"], int), run["id"]
        if run["is_root"]:
            case = run["metadata"]["ls_example_case"]
            assert run["_poisson_input_chars"] == len(case) + len(ITEM[case])
            assert re.fullmatch(r"input:[0-9a-f]{12}", run["_poisson_input_key"]), run
        was = source[run["id"]].get("error")
        if was:
            # an error's own words may quote a reply: its class is kept, and the kind its words say
            assert run["error"] == was.split("(", 1)[0] and re.fullmatch(r"[A-Za-z_][\w.]*", run["error"]), run["error"]
            assert run["_poisson_error_kind"] == WORDS_SAY[run["error"]], run
        else:
            assert not run.get("error") and run.get("_poisson_error_kind") is None
        for event in run.get("events") or []:
            assert set(event) <= {"name", "time"}, event
        # everything that is not text is as the API returned it
        for key, value in source[run["id"]].items():
            if key not in (*STRIPPED, "error", "events"):
                assert run[key] == value, (run["id"], key)
    for record in (r for r in lines if "feedback_source" in r and "run_type" not in r):
        assert record["comment"] is None and record.get("correction") is None
        assert record["key"] and "score" in record and "value" in record
    held = stored_bytes(root)
    for text in (*CONTENT, "no stock policy", "stale"):
        assert text.encode() not in held, text
    for item in ITEM.values():
        assert item.encode() not in held, item
    comments = sorted({f["comment"] for f in json.loads(feedback_file(version).read_text()) if f["comment"]})
    assert comments and not [c for c in comments if c.encode() in held]


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_35_keep_raw_text_saves_the_rows_as_the_api_returned_them(tmp_path: Path, version: str) -> None:
    kept, _, _ = _pull(tmp_path / "kept", version, "r", "--keep-raw-text")
    plain, _, _ = _pull(tmp_path / "plain", version)
    lines = raw_lines(tmp_path / "kept", "r")
    assert lines[:RUNS[version]] == rows_of(export(version, "v2")[0])
    assert lines[RUNS[version]:] == json.loads(feedback_file(version).read_text(encoding="utf-8"))
    doc = json.loads((raw_folder(tmp_path / "kept", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["raw_text_stripped"] is False and kept["pull"]["raw_text_stripped"] is False
    assert plain["pull"]["raw_text_stripped"] is True
    # the lengths stamped are the lengths measured: both read to the same run
    assert recs(tmp_path / "kept", "r") == recs(tmp_path / "plain", "r")
    # and the run's own folder holds no text either way
    assert not [t for t in CONTENT if t.encode() in stored_bytes(tmp_path / "kept" / "r")]


# ---------- TF24-36 ----------


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_36_the_pulled_run_is_the_import_of_the_same_answers_as_files(tmp_path: Path, version: str) -> None:
    pulled, _, _ = _pull(tmp_path / "pulled", version)
    files = imported(ls_argv([*export(version, "v2"), feedback_file(version)], tmp_path / "files", "r"))
    assert recs(tmp_path / "pulled", "r") == recs(tmp_path / "files", "r")
    a, b = columns(tmp_path / "pulled", "r"), columns(tmp_path / "files", "r")
    for case in CASES:
        for key in ("outcome", "error", "t", "wall_time", "config_hash"):
            assert a[case][key] == b[case][key] or (a[case][key] != a[case][key] and b[case][key] != b[case][key]), (case, key)
        assert a[case]["trace"] == b[case]["trace"], case
    for key in ("rows", "cases", "repeats", "outcomes", "no_outcome", "counts", "started", "declared", "tool"):
        assert pulled[key] == files[key], key
    assert {case: r["score"] for case, r in recs(tmp_path / "pulled", "r").items()} == EXACT[version]


def test_tf24_36_the_summary_says_what_was_pulled(tmp_path: Path) -> None:
    root = tmp_path / "st"
    with pulling() as (_, _waits):
        data = imported(ls_argv(address("candidate"), root, "new"))
        text = run_import(ls_argv(address("baseline"), root, "old"))
    folder = raw_folder(root, "new")
    doc = json.loads((folder / "pull.json").read_text(encoding="utf-8"))
    assert data["files"] == [{"name": "raw.jsonl", "sha256": doc["files"][0]["sha256"]}]
    assert data["pull"]["source_uri"] == address("candidate") and data["pull"]["folder"] == str(folder)
    assert data["pull"]["raw_text_stripped"] is True
    assert list(data).index("pull") < list(data).index("next")
    assert data["next"].startswith("poisson-trace fix-check OLD NEW ") and "--event missed" in data["next"]
    assert tally(data) == {"met": 8, "missed": 2}
    assert text.code == 0 and text.out.startswith("ok  wrote run old to "), text.out + text.err
    said = [line for line in text.out.splitlines() if line.startswith("- pulled: ")]
    assert len(said) == 1 and address("baseline") in said[0] and str(raw_folder(root, "old")) in said[0], text.out
    assert text.out.rstrip("\n").splitlines()[-1].startswith("next: poisson-trace fix-check OLD NEW"), text.out
    # an import of files says nothing of a pull
    plain = run_import(by_status(export("baseline", "v2"), tmp_path / "other", "r"))
    assert plain.code == 0 and "- pulled: " not in plain.out
    assert "pull" not in imported(by_status(export("baseline", "v2"), tmp_path / "other", "r2"))


# ---------- TF24-37 ----------


def _forbidden() -> Transport:
    class Never(Transport):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a request was made")

    return Never()


@pytest.mark.parametrize("keep", [False, True])
def test_tf24_37_the_saved_folder_reads_again_with_no_key_and_no_request(tmp_path: Path, keep: bool) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "r", *(["--keep-raw-text"] if keep else []))
    folder = raw_folder(root, "r")
    before = snapshot(folder)
    with pulling(_forbidden(), key=None):
        again = imported(ls_argv(folder, root, "again"))
        unnamed = run_import([str(folder), "--store", str(root), "--run", "unnamed", "--case-from", "metadata:ls_example_case",
                              "--outcome-from", "feedback:exact", "--cut", "0.5", "--below", "--json"])
        by_input = imported(by_status(folder, root, "by-input", case="input"))
        elsewhere = imported(ls_argv(folder, tmp_path / "elsewhere", "r"))
    assert unnamed.code == 0, unnamed.err
    assert recs(root, "again") == recs(root, "r") == recs(root, "unnamed") == recs(tmp_path / "elsewhere", "r")
    assert again["files"][0]["name"] == "raw.jsonl" and "pull" not in again and "pull" not in elsewhere
    assert by_input["cases"] == 10 and tally(by_input) == {"met": 9, "missed": 1}
    assert all(re.fullmatch(r"input:[0-9a-f]{12}", case) for case in recs(root, "by-input"))
    stripped, kept = recs(root, "by-input"), None
    if keep:
        kept = imported(by_status(export("baseline", "v2"), tmp_path / "files", "r", case="input"))
        assert sorted(stripped) == sorted(recs(tmp_path / "files", "r")) and kept["cases"] == 10
    assert snapshot(folder) == before


def test_tf24_37_a_raw_copy_changed_after_the_pull_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline")
    folder = raw_folder(root, "r")
    raw = folder / "raw.jsonl"
    raw.chmod(0o644)
    raw.write_bytes(raw.read_bytes() + b"\n")
    line = refused(run_import(ls_argv(folder, root, "again")))
    assert "raw.jsonl" in line and "sha256" in line, line
    assert not (root / "again").exists()


# ---------- TF24-38 ----------


def test_tf24_38_in_pages_the_runs_follow_the_cursor_and_the_feedback_its_offset(tmp_path: Path) -> None:
    paged, sent, _ = _pull(tmp_path / "paged", "candidate", "r", "--page-size", "25")
    whole, once, _ = _pull(tmp_path / "whole", "candidate")
    paths = sent.paths()
    assert paths[0] == "GET /api/v1/sessions" and paths[1:4] == ["POST /api/v2/runs/query"] * 3
    assert paths[4:] in (["GET /api/v1/feedback"] * 2, ["GET /api/v1/feedback"] * 3), paths
    bodies = [json.loads(c["body"].decode("utf-8")) for c in sent.calls[1:4]]
    assert [b["page_size"] for b in bodies] == [25, 25, 25] and "cursor" not in bodies[0]
    pages = [json.loads((API / f"candidate.runs-v2.page-{n}.json").read_text()) for n in (1, 2)]
    assert [b.get("cursor") for b in bodies[1:]] == [p["next_cursor"] for p in pages]
    offsets = [re.search(r"offset=(\d+)", c["url"]) for c in sent.calls[4:]]
    assert [int(m.group(1)) if m else 0 for m in offsets] == [0, 25, 50][:len(offsets)]
    assert len(once.calls) == 3
    assert len(raw_lines(tmp_path / "paged", "r")) == 51 + 41
    assert recs(tmp_path / "paged", "r") == recs(tmp_path / "whole", "r")
    assert paged["counts"] == whole["counts"] and paged["counts"]["runs"] == 51 and paged["counts"]["feedback records"] == 41
    assert sorted(row["id"] for row in raw_lines(tmp_path / "paged", "r")) == sorted(row["id"] for row in raw_lines(tmp_path / "whole", "r"))


# ---------- TF24-39 ----------


def test_tf24_39_a_name_the_store_holds_is_refused_before_any_request(tmp_path: Path) -> None:
    root = tmp_path / "st"
    _pull(root, "baseline", "old")
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(ls_argv(address("candidate"), root, "old")))
        assert sent.calls == []
    assert "old" in line, line
    assert snapshot(root) == before
    # the same for a name a file import took, which left no raw copy to stand in the way
    imported(by_status(export("baseline", "v2"), root, "from-a-file"))
    before = snapshot(root)
    with pulling() as (sent, _):
        line = refused(run_import(ls_argv(address("candidate"), root, "from-a-file")))
        assert sent.calls == []
    assert "from-a-file" in line, line
    assert snapshot(root) == before


def test_tf24_39_a_raw_copy_is_never_written_over(tmp_path: Path) -> None:
    """A pull whose read is then refused (no root has the score named) keeps what it pulled:
    the raw copy is the pull. Pulling under that name again is refused, naming the folder and
    the command that reads it; that command, with a key the roots do have, writes the run."""
    root = tmp_path / "st"
    with pulling() as (sent, _):
        first = run_import(ls_argv(address("baseline"), root, "old", outcome="feedback:no_such_key"))
        assert first.code == 1 and len(sent.calls) == 3, first.err
        folder = raw_folder(root, "old")
        assert sorted(p.name for p in folder.iterdir()) == ["pull.json", "raw.jsonl"]
        assert not (root / "old").exists()
        before = snapshot(folder)
        again = run_import(ls_argv(address("baseline"), root, "old"))
        line = refused(again)
        assert len(sent.calls) == 3, "no request is made for a pull that is already saved"
    assert str(folder) in line, line
    nexts = [following[len("  next: "):] for following in again.err.splitlines()[1:]]
    assert len(nexts) == 1 and nexts[0].startswith("poisson-trace import langsmith ") and str(folder) in nexts[0], again.err
    assert snapshot(folder) == before
    with pulling(_forbidden(), key=None):
        data = imported(ls_argv(folder, root, "old"))
    assert tally(data) == {"met": 6, "missed": 4} and snapshot(folder) == before


# ---------- TF24-40 ----------


@pytest.mark.parametrize("key", [None, "", "   "])
def test_tf24_40_no_key_is_refused_naming_the_variable(tmp_path: Path, key: str | None) -> None:
    with pulling(key=key) as (sent, _):
        line = refused(run_import(ls_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert KEY_VARIABLE in line, line
    assert not (tmp_path / "st").exists()


def test_tf24_40_an_address_naming_nothing_is_refused(tmp_path: Path) -> None:
    with pulling() as (sent, _):
        line = refused(run_import(ls_argv("langsmith:", tmp_path / "st", "r")))
        assert sent.calls == []
    assert "langsmith:" in line, line
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("endpoint", ["http://example.com", "http://api.smith.langchain.com", "ftp://127.0.0.1/x", "smith.langchain.com"])
def test_tf24_40_the_key_goes_over_https_or_to_this_machine_only(tmp_path: Path, endpoint: str) -> None:
    with pulling(endpoint=endpoint) as (sent, _):
        line = refused(run_import(ls_argv(address("baseline"), tmp_path / "st", "r")))
        assert sent.calls == []
    assert ENDPOINT_VARIABLE in line and PLANTED_KEY not in line, line
    assert not (tmp_path / "st").exists()


WRONG: dict[str, Any] = {
    "an address beside a file": lambda root: ls_argv([address("baseline"), *export("baseline", "v2")], root, "r"),
    "two addresses": lambda root: ls_argv([address("baseline"), address("candidate")], root, "r"),
    "no run name": lambda root: ls_argv(address("baseline"), root, None),
    "keep-raw-text with files": lambda root: ls_argv(export("baseline", "v2"), root, "r", "--keep-raw-text"),
    "page-size with files": lambda root: ls_argv(export("baseline", "v2"), root, "r", "--page-size", "25"),
    "a page size of 0": lambda root: ls_argv(address("baseline"), root, "r", "--page-size", "0"),
    "a page size of 101": lambda root: ls_argv(address("baseline"), root, "r", "--page-size", "101"),
    "a page size that is no number": lambda root: ls_argv(address("baseline"), root, "r", "--page-size", "many"),
}


@pytest.mark.parametrize("label", list(WRONG))
def test_tf24_40_a_wrong_command_line_exits_2_and_asks_nothing(tmp_path: Path, label: str) -> None:
    with pulling() as (sent, _):
        wrong_line(run_import(WRONG[label](tmp_path / "st")))
        assert sent.calls == []
    assert not (tmp_path / "st").exists()


# ---------- TF24-41 ----------


def test_tf24_41_no_project_of_that_name(tmp_path: Path) -> None:
    with pulling(Transport({1: (200, {}, b"[]")})) as (sent, _):
        line = refused(run_import(ls_argv("langsmith:no-such-experiment", tmp_path / "st", "r")))
        assert sent.paths() == ["GET /api/v1/sessions"]
    assert "no-such-experiment" in line, line
    assert not (tmp_path / "st" / "r").exists() and _raw_dirs(tmp_path / "st") in ([], ["langsmith"])


@pytest.mark.parametrize(("at", "status"), [(1, 401), (1, 403), (2, 401), (3, 401)])
def test_tf24_41_a_key_the_service_refuses(tmp_path: Path, status: int, at: int) -> None:
    body = json.dumps({"detail": f"Invalid token {PLANTED_KEY}"}).encode()
    with pulling(Transport({at: (status, {}, body)})) as (sent, _):
        result = run_import(ls_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    line = refused(result)
    assert KEY_VARIABLE in line and str(status) in line and PLANTED_KEY not in result.err, result.err
    assert not (tmp_path / "st" / "r").exists() and _raw_dirs(tmp_path / "st") in ([], ["langsmith"])


# ---------- TF24-42 ----------

FAILURES: dict[str, Any] = {
    "a 500": (500, {}, b"Internal Server Error"),
    "a 502 of html": (502, {"Content-Type": "text/html"}, b"<html>bad gateway</html>"),
    "an answer that is not JSON": (200, {}, b"<html>sign in</html>"),
    "an answer of another shape": (200, {}, b'"ok"'),
    "the connection failing": ConnectionResetError(54, "Connection reset by peer"),
    "a timeout": TimeoutError("timed out"),
}


#: Every failure at the first request after the pull began; at the next, one the transport
#: answers and the two this reader's own reading of the answer gives.
FAILED_AT = [*((2, label) for label in FAILURES),
             *((3, label) for label in ("a 500", "an answer that is not JSON", "an answer of another shape"))]


@pytest.mark.parametrize(("at", "label"), FAILED_AT)
def test_tf24_42_a_failure_after_the_pull_began_exits_3_and_saves_nothing(tmp_path: Path, label: str, at: int) -> None:
    with pulling(Transport({at: FAILURES[label]})) as (sent, _):
        result = run_import(ls_argv(address("baseline"), tmp_path / "st", "r"))
        assert len(sent.calls) == at
    assert result.code == 3 and result.out == "", result.out + result.err
    lines = result.err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("error: ") and "Traceback" not in result.err, result.err
    assert "nothing was saved" in lines[0] and PLANTED_KEY not in result.err, result.err
    assert not (tmp_path / "st" / "r").exists() and _raw_dirs(tmp_path / "st") in ([], ["langsmith"])


def test_tf24_42_a_429_on_every_try_stops_after_a_few(tmp_path: Path) -> None:
    script = {n: (429, {"Retry-After": "1"}, b"{}") for n in range(2, 40)}
    with pulling(Transport(script)) as (sent, waits):
        result = run_import(ls_argv(address("baseline"), tmp_path / "st", "r"))
    assert result.code == 3 and "429" in result.err and "nothing was saved" in result.err, result.err
    assert 3 <= len(sent.calls) - 1 <= 10, len(sent.calls)
    assert len(waits) == len(sent.calls) - 2 and all(w == 1 for w in waits), waits
    assert not (tmp_path / "st" / "r").exists() and _raw_dirs(tmp_path / "st") in ([], ["langsmith"])


# ---------- TF24-43 ----------


def test_tf24_43_a_429_is_waited_out_and_asked_again(tmp_path: Path) -> None:
    script = {2: (429, {"Retry-After": "7"}, b"{}"), 3: (429, {}, b""), 4: (429, {"retry-after": "2.5"}, b""), 6: (429, {}, b"")}
    throttled, sent, waits = _pull(tmp_path / "throttled", "candidate", transport=Transport(script))
    plain, _, none = _pull(tmp_path / "plain", "candidate")
    assert sent.paths() == ["GET /api/v1/sessions", *["POST /api/v2/runs/query"] * 4, *["GET /api/v1/feedback"] * 2]
    assert none == [] and len(waits) == 4
    assert waits[0] == 7 and waits[2] == 2.5
    assert 0 < waits[1] <= 60 and 0 < waits[3] <= 60, waits
    asked = [(c["method"], c["url"], c["body"]) for c in sent.calls[1:5]]
    assert all(a == asked[0] for a in asked), "the same request is asked again"
    assert recs(tmp_path / "throttled", "r") == recs(tmp_path / "plain", "r")
    assert raw_lines(tmp_path / "throttled", "r") == raw_lines(tmp_path / "plain", "r")
    assert throttled["counts"] == plain["counts"]


def test_tf24_43_the_wait_grows_when_the_answer_names_none(tmp_path: Path) -> None:
    script = {2: (429, {}, b""), 3: (429, {}, b""), 4: (429, {}, b"")}
    _, _, waits = _pull(tmp_path / "st", "baseline", transport=Transport(script))
    assert len(waits) == 3 and waits[0] > 0 and waits[0] < waits[1] < waits[2] <= 120, waits


# ---------- TF24-44 ----------


@pytest.mark.parametrize("extra", [(), ("--keep-raw-text",), ("--json",)])
def test_tf24_44_the_key_is_printed_nowhere_and_written_nowhere(tmp_path: Path, extra: tuple[str, ...]) -> None:
    with pulling() as (_, _waits):
        result = run_import([*ls_argv(address("candidate"), tmp_path / "st", "r"), *extra])
    assert result.code == 0, result.err
    assert PLANTED_KEY not in result.out + result.err
    held = stored_bytes(tmp_path / "st")
    for piece in (PLANTED_KEY, PLANTED_KEY[:16], PLANTED_KEY[-12:]):
        assert piece.encode() not in held, piece
    assert KEY_VARIABLE.encode() not in held


@pytest.mark.parametrize("endpoint", ["https://eu.api.smith.langchain.com", "https://langsmith.example.internal/", "http://127.0.0.1:1984", "http://localhost:1984"])
def test_tf24_44_the_endpoint_variable_moves_every_request(tmp_path: Path, endpoint: str) -> None:
    host = endpoint.rstrip("/")
    data, sent, _ = _pull(tmp_path / "st", "baseline", transport=Transport(host=host), endpoint=endpoint)
    assert len(sent.calls) == 3 and all(c["url"].startswith(host + "/api/") for c in sent.calls)
    doc = json.loads((raw_folder(tmp_path / "st", "r") / "pull.json").read_text(encoding="utf-8"))
    assert doc["endpoint"].startswith(host + "/api/"), doc["endpoint"]
    assert tally(data) == {"met": 6, "missed": 4}


# ---------- TF24-45 ----------

NETWORK = ("urllib.request", "urllib3", "http.client", "socket", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib")


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


#: Each reader that pulls, with the packages of its service's own SDK, none of which it imports.
SDKS: dict[str, tuple[str, ...]] = {
    "langsmith": ("langsmith", "langchain", "langchain_core", "poisson_prove"),
    "braintrust": ("braintrust", "braintrust_core", "autoevals", "openai", "poisson_prove"),
    "weave": ("weave", "wandb", "openai", "poisson_prove"),
}


def test_tf24_45_one_function_reaches_the_network(tmp_path: Path) -> None:
    """The package is scanned once for the three readers that pull (TF25-45 and TF26-45
    leave the scan to this test)."""
    import sys
    from importlib import import_module

    import poisson_trace
    from poisson_trace.ingest import pulling as module

    package = Path(poisson_trace.__file__).parent
    reaching = sorted(
        str(p.relative_to(package)) for p in package.rglob("*.py")
        if any(name == net or name.startswith(net + ".") for name in _imports(p) for net in NETWORK)
    )
    assert reaching == ["ingest/pulling.py"], reaching
    stdlib = set(sys.stdlib_module_names)
    for reader, sdk in SDKS.items():
        for path in (Path(module.__file__), Path(import_module(f"poisson_trace.ingest.{reader}").__file__ or "")):
            for name in _imports(path):
                top = name.split(".")[0]
                assert top in stdlib or top == "poisson_trace", (path.name, name)
                assert top not in sdk, (path.name, name)
    assert callable(module.send) and callable(module.sleep)
    # the module's top level reaches for nothing: the network is imported inside send
    top = {n for node in ast.parse(Path(module.__file__).read_text(encoding="utf-8")).body for n in _top(node)}
    assert not [n for n in top if any(n == net or n.startswith(net + ".") for net in NETWORK)], top


def _top(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module]
    return []


def test_tf24_45_an_import_of_files_asks_nothing(tmp_path: Path) -> None:
    with pulling(_forbidden(), key=None):
        for kind in ("v1", "v2", "cli-runs", "cli-traces", "ui"):
            imported(by_status(export("baseline", kind), tmp_path / kind, "r"))


# ---------- TF24-46 ----------


def test_tf24_46_json_is_one_document_done_or_failed(tmp_path: Path) -> None:
    with pulling() as (_, _waits):
        done = run_import([*ls_argv(address("baseline"), tmp_path / "st", "r"), "--json"])
    assert done.code == 0 and done.err == "" and json.loads(done.out)["verdict"] == "ok"
    with pulling(Transport({2: (500, {}, b"")})) as (_, _waits):
        failed = run_import([*ls_argv(address("baseline"), tmp_path / "st2", "r"), "--json"])
    assert failed.code == 3 and failed.out == "" and failed.err.startswith("error: "), failed.out + failed.err
