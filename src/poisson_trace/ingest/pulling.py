"""The pull that saves a raw copy first: a tool's runs asked of its API, saved under the store
as the API returned them, and only then read (spec section 18.3.2).

``send`` is the one function in the package that reaches the network, and ``sleep`` the one
wait between tries; a test replaces both. Everything else here is the LangSmith pull, in the
order it happens:

1. Before any request: the address names a project or experiment, the store holds no run and
   no raw copy of that name (a raw copy is never written over), the key is set, and the
   endpoint is https, or http to this machine alone. Each is a refusal with nothing written.
2. The requests: the project by name (``GET /api/v1/sessions``), its runs (``POST
   /api/v2/runs/query``, following ``next_cursor``), its feedback records (``GET
   /api/v1/feedback``, by ``offset``). Asked with no lower bound, LangSmith's runs query
   answers with the runs started in the last day alone, so every runs query carries one
   (``min_start_time``): a day before the project's own start, which the sessions answer
   gives, and before which none of its runs began. A 429 is waited out and asked again, a
   few times. A key
   the service refuses, or no project of that name, is a refusal; any other failure after the
   pull began is ``look.Failed``. Either way nothing is saved and no folder is left.
3. The raw copy: ``STORE/.poisson/raw/langsmith/RUN/`` holds ``raw.jsonl`` (the runs, then
   the feedback records, one a line) and ``pull.json`` (``poisson.raw-pull/1``), written
   whole or not at all. By default the text is measured and left out (``strip_run``,
   ``strip_feedback``); ``--keep-raw-text`` saves the rows as the API returned them.

The key is read from ``LANGSMITH_API_KEY`` alone, sent in the ``x-api-key`` header, and is
never printed and never written: no message here quotes a response's body, which may repeat
it. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace import look
from poisson_trace.ingest.folder import PULL, PULL_SCHEMA
from poisson_trace.ingest.rows import Refusal

#: Where LangSmith's API is, unless ``LANGSMITH_ENDPOINT`` names another host.
LANGSMITH_API = "https://api.smith.langchain.com"
KEY_VARIABLE = "LANGSMITH_API_KEY"
ENDPOINT_VARIABLE = "LANGSMITH_ENDPOINT"
RAW = "raw.jsonl"

#: How many times one request is asked while the service answers 429, and the waits between.
TRIES = 5
FIRST_WAIT_S = 1.0
LONGEST_WAIT_S = 120.0
TIMEOUT_S = 60.0

_NOTHING_SAVED = "nothing was saved"

#: The fields of a run the v2 query is asked for: every one it offers.
SELECTS: tuple[str, ...] = (
    "ID",
    "NAME",
    "RUN_TYPE",
    "STATUS",
    "START_TIME",
    "END_TIME",
    "LATENCY_SECONDS",
    "FIRST_TOKEN_TIME",
    "ERROR",
    "ERROR_PREVIEW",
    "EXTRA",
    "METADATA",
    "EVENTS",
    "INPUTS",
    "INPUTS_PREVIEW",
    "OUTPUTS",
    "OUTPUTS_PREVIEW",
    "MANIFEST",
    "PARENT_RUN_IDS",
    "PROJECT_ID",
    "TRACE_ID",
    "THREAD_ID",
    "DOTTED_ORDER",
    "IS_ROOT",
    "REFERENCE_EXAMPLE_ID",
    "REFERENCE_DATASET_ID",
    "TOTAL_TOKENS",
    "PROMPT_TOKENS",
    "COMPLETION_TOKENS",
    "TOTAL_COST",
    "PROMPT_COST",
    "COMPLETION_COST",
    "PROMPT_TOKEN_DETAILS",
    "COMPLETION_TOKEN_DETAILS",
    "PROMPT_COST_DETAILS",
    "COMPLETION_COST_DETAILS",
    "PRICE_MODEL_ID",
    "TAGS",
    "APP_PATH",
    "ATTACHMENTS",
    "THREAD_EVALUATION_TIME",
    "IS_IN_DATASET",
    "LAST_QUEUED_AT",
    "SHARE_URL",
    "FEEDBACK_STATS",
    "LS_USER_ID",
)


# ---------- the two seams ----------


def send(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    """One HTTP request: the status, the answer's headers and its body. The one function in
    the package that reaches the network. An answer that is not 200 is returned, not raised;
    a connection that fails raises ``OSError``. A redirect is never followed: the key is in
    the headers, and it goes only to the host that was asked."""
    import http.client
    import urllib.error
    import urllib.request

    class _Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    opener = urllib.request.build_opener(_Stay)
    request = urllib.request.Request(url, method=method, data=body, headers=dict(headers))
    try:
        with opener.open(request, timeout=timeout) as reply:
            return int(reply.status), dict(reply.headers.items()), reply.read()
    except urllib.error.HTTPError as answered:
        with answered:
            return int(answered.code), dict(answered.headers.items()), answered.read()
    except http.client.HTTPException as e:
        # an answer that broke off part way: a failed connection, as the caller reads it
        raise ConnectionError(type(e).__name__) from e


def sleep(seconds: float) -> None:
    """The one wait between tries."""
    time.sleep(seconds)


# ---------- before any request ----------


def endpoint() -> str:
    """Where the requests go: LangSmith's API, or the host ``LANGSMITH_ENDPOINT`` names (the
    EU region, a company's own host), which must be https, or http to this machine alone,
    since the key goes with every request."""
    given = os.environ.get(ENDPOINT_VARIABLE, "").strip().rstrip("/")
    if not given:
        return LANGSMITH_API
    try:
        parts = urllib.parse.urlsplit(given)
        host = parts.hostname or ""
    except ValueError:
        parts, host = None, ""
    here = host in ("localhost", "::1") or host.startswith("127.")
    scheme = "" if parts is None else parts.scheme
    if host and (scheme == "https" or (scheme == "http" and here)):
        return given
    raise Refusal(
        f"{ENDPOINT_VARIABLE} is {given}, and the key is sent only over https, or over http "
        "to this machine: give an https address"
    )


def key_is_set() -> bool:
    """Whether ``LANGSMITH_API_KEY`` holds a key. The key itself goes nowhere but a request."""
    return bool(os.environ.get(KEY_VARIABLE, "").strip())


def raw_folder(store: Path, run: str) -> Path:
    """Where a pull of LangSmith under the run name ``run`` keeps its raw copy."""
    return store / ".poisson" / "raw" / "langsmith" / run


# ---------- the requests ----------


class _Service:
    """LangSmith's API at one endpoint, asked with one key."""

    def __init__(self, base: str, key: str) -> None:
        self.base = base
        self._headers = {"x-api-key": key, "Accept": "application/json"}

    def ask(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        """The JSON the service answers to one request. A 429 is waited out and the same
        request asked again: the wait is the answer's ``Retry-After`` where it gives one,
        else one that doubles."""
        url = self.base + path
        headers = dict(self._headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        asked = f"{method} {path.split('?', 1)[0]}"
        wait = FIRST_WAIT_S
        for attempt in range(1, TRIES + 1):
            try:
                status, answered, raw = send(method, url, headers, data, TIMEOUT_S)
            except OSError as e:
                raise look.Failed(
                    f"the pull failed: the connection to {self.base} failed on {asked} "
                    f"({look.why(e)}); {_NOTHING_SAVED}"
                ) from None
            if status != 429:
                break
            if attempt == TRIES:
                raise look.Failed(
                    f"the pull failed: LangSmith answered 429 (too many requests) {TRIES} times "
                    f"on {asked}; {_NOTHING_SAVED}"
                )
            named = _retry_after(answered)
            sleep(min(wait if named is None else named, LONGEST_WAIT_S))
            wait *= 2
        if status in (401, 403):
            raise Refusal(
                f"LangSmith refused the key in {KEY_VARIABLE} ({status} on {asked}); "
                f"{_NOTHING_SAVED}"
            )
        if status != 200:
            raise look.Failed(
                f"the pull failed: LangSmith answered {status} on {asked}; {_NOTHING_SAVED}"
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise look.Failed(
                f"the pull failed: LangSmith's answer to {asked} is not JSON; {_NOTHING_SAVED}"
            ) from None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """The seconds a 429's ``Retry-After`` names, or None when it names none."""
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                return None
            return seconds if seconds >= 0 and seconds == seconds else None
    return None


def _not_the_shape(asked: str, what: str) -> look.Failed:
    return look.Failed(
        f"the pull failed: LangSmith's answer to {asked} is not {what}; {_NOTHING_SAVED}"
    )


#: How long before the project's own start the runs are asked from: room for a run stamped by
#: a clock that ran behind the one that stamped the project.
EARLIER_S = 24 * 60 * 60


def _session(service: _Service, name: str) -> tuple[str, str]:
    """The id of the project or experiment named ``name``, and the time its runs are asked
    from: a day before its own start."""
    query = urllib.parse.urlencode({"name": name})
    found = service.ask("GET", f"/api/v1/sessions?{query}")
    if not isinstance(found, list):
        raise _not_the_shape("GET /api/v1/sessions", "a list of projects")
    held = [s for s in found if isinstance(s, Mapping) and s.get("id")]
    named = [s for s in held if s.get("name") == name] or held
    if not named:
        raise Refusal(
            f"LangSmith holds no project or experiment named {name} that this key can read; "
            f"{_NOTHING_SAVED}"
        )
    if len(named) > 1:
        raise Refusal(
            f"LangSmith holds {len(named)} projects or experiments named {name}, and a pull "
            f"reads one; {_NOTHING_SAVED}"
        )
    from poisson_trace.ingest.langsmith import nanoseconds

    began = nanoseconds(named[0].get("start_time"))
    if began is None:
        # without it the runs query would look back one day and no further, in silence
        raise _not_the_shape("GET /api/v1/sessions", "a project with its start time")
    since = datetime.fromtimestamp(began // 1_000_000_000 - EARLIER_S, UTC)
    return str(named[0]["id"]), since.strftime("%Y-%m-%dT%H:%M:%SZ")


def _runs(
    service: _Service, session: str, since: str, page_size: int
) -> list[Mapping[str, Any]]:
    """Every run of the project started since ``since``, a page at a time, following the
    answer's ``next_cursor``. The lower bound is sent with every page: left out, LangSmith
    answers with the last day's runs alone."""
    asked = "POST /api/v2/runs/query"
    runs: list[Mapping[str, Any]] = []
    cursor: Any = None
    while True:
        body: dict[str, Any] = {
            "project_ids": [session],
            "selects": list(SELECTS),
            "page_size": page_size,
            "min_start_time": since,
        }
        if cursor:
            body["cursor"] = cursor
        page = service.ask("POST", "/api/v2/runs/query", body)
        items = page.get("items") if isinstance(page, Mapping) else None
        if not isinstance(items, list) or not all(isinstance(i, Mapping) for i in items):
            raise _not_the_shape(asked, "a page of runs")
        runs.extend(items)
        following = page.get("next_cursor")
        if not following or not items:
            return runs
        if following == cursor:
            raise _not_the_shape(asked, "a new page (its cursor repeats)")
        cursor = following


def _feedback(service: _Service, session: str, page_size: int) -> list[Mapping[str, Any]]:
    """Every feedback record of the project, a page at a time, by offset."""
    records: list[Mapping[str, Any]] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({"session": session, "limit": page_size, "offset": offset})
        page = service.ask("GET", f"/api/v1/feedback?{query}")
        if not isinstance(page, list) or not all(isinstance(r, Mapping) for r in page):
            raise _not_the_shape("GET /api/v1/feedback", "a list of feedback records")
        records.extend(page)
        if len(page) < page_size:
            return records
        offset += page_size


# ---------- what is left out of the raw copy ----------

# what a run holds that is text or can hold it: its inputs and outputs, their previews, and
# its manifest, the serialised component, which in a LangChain app can hold a prompt template
_TEXT = ("inputs", "outputs", "inputs_preview", "outputs_preview", "error_preview", "manifest")


def strip_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """The run as the raw copy keeps it by default: its inputs, outputs and previews measured
    and removed, and its manifest removed; an event its name and time; an error its class
    alone, since an error's own words can quote a reply. Stamped beside them: the lengths, a
    root's input key (so the saved copy still reads with ``--case-from input``) and the kind
    the error's words said (so it reads to the same failure kinds)."""
    from poisson_trace.ingest import langsmith

    out = dict(run)
    out[langsmith.INPUT_CHARS] = langsmith.chars(run.get("inputs"))
    out[langsmith.OUTPUT_CHARS] = langsmith.chars(run.get("outputs"))
    if run.get("is_root") and run.get("inputs") is not None:
        out[langsmith.INPUT_KEY] = langsmith.input_key(run["inputs"])
    for key in _TEXT:
        out.pop(key, None)
    error = out.get("error")
    if isinstance(error, str) and error:
        out[langsmith.ERROR_KIND] = langsmith.error_kind(error)
        out["error"] = langsmith.error_class(error) or ""
    events = out.get("events")
    if isinstance(events, list):
        out["events"] = [
            {k: v for k, v in event.items() if k in ("name", "time")}
            for event in events
            if isinstance(event, Mapping)
        ]
    return out


def strip_feedback(record: Mapping[str, Any]) -> dict[str, Any]:
    """The feedback record as the raw copy keeps it by default: its comment and its
    correction emptied."""
    out = dict(record)
    for key in ("comment", "correction"):
        if key in out:
            out[key] = None
    return out


# ---------- the pull ----------


@dataclass(frozen=True)
class Pulled:
    """What a pull saved: its folder, the files to read, and what the summary says of it."""

    folder: Path
    files: tuple[Path, ...]
    summary: Mapping[str, Any]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pull_langsmith(
    address: str,
    store: Path,
    run: str | None,
    *,
    keep_raw_text: bool,
    page_size: int,
    flags: Sequence[str] = (),
) -> Pulled:
    """Pull the project or experiment ``langsmith:NAME`` names and save its raw copy under
    ``store`` for the run ``run``. Nothing is read here: the caller reads the files saved.
    ``flags`` are the reader's flags of this call, for the command that reads a raw copy
    already there."""
    name = address.split(":", 1)[1] if ":" in address else ""
    if not name.strip():
        raise Refusal(
            f"{address} names no project or experiment: write langsmith:NAME, the name "
            "LangSmith shows for it"
        )
    if run is None:
        raise Refusal("a pull needs --run NAME: the raw copy is kept under the run's name")
    folder = raw_folder(store, run)
    if os.path.lexists(store / run):
        raise Refusal(
            f"the store {store} already holds a run named {run}; an import writes a new run "
            "and never adds to one, so pull under another name. Nothing was asked of LangSmith"
        )
    if os.path.lexists(folder):
        raise Refusal(
            f"{folder} already holds a pull, and a raw copy is never written over: read the "
            "saved copy, or pull under another run name",
            look.command(
                "poisson-trace",
                "import",
                "langsmith",
                look.word(str(folder)),
                look.option("--store", str(store)),
                look.option("--run", run),
                *flags,
            ),
        )
    if not key_is_set():
        raise Refusal(
            f"{KEY_VARIABLE} is not set, and a pull from LangSmith needs your key: set it in "
            "the environment, or export the runs to a file and import that"
        )
    base = endpoint()
    service = _Service(base, os.environ[KEY_VARIABLE].strip())
    session, since = _session(service, name)
    runs = _runs(service, session, since, page_size)
    if not runs:
        raise Refusal(f"the project or experiment {name} holds no run; {_NOTHING_SAVED}")
    feedback = _feedback(service, session, page_size)
    rows = [run_ if keep_raw_text else strip_run(run_) for run_ in runs]
    rows += [record if keep_raw_text else strip_feedback(record) for record in feedback]
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    record = {
        "schema": PULL_SCHEMA,
        "tool": "langsmith",
        "pulled_at": _now(),
        "source_uri": address,
        "endpoint": f"{base}/api/v2/runs/query",
        "raw_text_stripped": not keep_raw_text,
        "files": [{"path": RAW, "sha256": hashlib.sha256(raw).hexdigest(), "rows": len(rows)}],
    }
    _save(folder, raw, record)
    return Pulled(
        folder=folder,
        files=(folder / RAW,),
        summary={
            "source_uri": address,
            "folder": str(folder),
            "runs": len(runs),
            "feedback": len(feedback),
            "raw_text_stripped": not keep_raw_text,
        },
    )


def _save(folder: Path, raw: bytes, record: Mapping[str, Any]) -> None:
    """The raw copy and its record, whole or not at all: written beside where they go, then
    moved into place, and left read-only, since a raw copy is never written over."""
    held = folder.with_name(f".{folder.name}.partial")
    try:
        folder.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(held):
            # what a pull that was killed mid-save left: never a raw copy, and ours by its name
            shutil.rmtree(held)
        held.mkdir()
    except OSError as e:
        raise look.Failed(
            f"the pull failed: {folder.parent} cannot hold the raw copy ({look.why(e)}); "
            f"{_NOTHING_SAVED}"
        ) from None
    try:
        (held / RAW).write_bytes(raw)
        (held / PULL).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        for name in (RAW, PULL):
            (held / name).chmod(0o444)
        os.rename(held, folder)
    except BaseException as e:
        shutil.rmtree(held, ignore_errors=True)
        if isinstance(e, OSError):
            raise look.Failed(
                f"the pull failed: the raw copy could not be saved to {folder} ({look.why(e)}); "
                f"{_NOTHING_SAVED}"
            ) from None
        raise
