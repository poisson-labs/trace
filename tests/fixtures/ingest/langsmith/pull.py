"""Pull the raw REST responses for the two trace-fixture experiments from LangSmith and save each
response body byte for byte. Needs LANGSMITH_API_KEY; standard library only.

    python pull.py <out-dir> <baseline experiment name> <candidate experiment name>

Saved once:
  dataset.json, examples.json     GET /api/v1/datasets?name=trace-fixture-stock-10 and
                                  GET /api/v1/examples?dataset={id}: what a run's
                                  reference_example_id points at
and for each experiment, under the name `baseline` or `candidate`:
  <name>.session.json             GET  /api/v1/sessions?name={experiment}
  <name>.runs-v2.json             POST /api/v2/runs/query  project_ids, every select field, page_size 100
  <name>.runs-v2.subtree.json     the same with `include_subtree_usage: true`, which adds each run's
                                  tokens and cost summed over the runs under it
  <name>.runs-v1.json             POST /api/v1/runs/query  session, limit 100
  <name>.feedback.json            GET  /api/v1/feedback?session={id}&limit=100
and for candidate the same three again in pages of 25, following `next_cursor` (v2),
`cursors.next` (v1) and `offset` (feedback): candidate.runs-v2.page-N.json,
candidate.runs-v1.page-N.json, candidate.feedback.page-N.json. requests.json lists every request
made, in order, with its body, its status and the file the response went to; no header is
recorded."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.smith.langchain.com"
SELECTS = ["ID", "NAME", "RUN_TYPE", "STATUS", "START_TIME", "END_TIME", "LATENCY_SECONDS", "FIRST_TOKEN_TIME",
           "ERROR", "ERROR_PREVIEW", "EXTRA", "METADATA", "EVENTS", "INPUTS", "INPUTS_PREVIEW", "OUTPUTS",
           "OUTPUTS_PREVIEW", "MANIFEST", "PARENT_RUN_IDS", "PROJECT_ID", "TRACE_ID", "THREAD_ID", "DOTTED_ORDER",
           "IS_ROOT", "REFERENCE_EXAMPLE_ID", "REFERENCE_DATASET_ID", "TOTAL_TOKENS", "PROMPT_TOKENS",
           "COMPLETION_TOKENS", "TOTAL_COST", "PROMPT_COST", "COMPLETION_COST", "PROMPT_TOKEN_DETAILS",
           "COMPLETION_TOKEN_DETAILS", "PROMPT_COST_DETAILS", "COMPLETION_COST_DETAILS", "PRICE_MODEL_ID", "TAGS",
           "APP_PATH", "ATTACHMENTS", "THREAD_EVALUATION_TIME", "IS_IN_DATASET", "LAST_QUEUED_AT", "SHARE_URL",
           "FEEDBACK_STATS", "LS_USER_ID"]
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
log = []


def call(method: str, path: str, file: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, method=method, data=data, headers={
        "x-api-key": os.environ["LANGSMITH_API_KEY"], "Content-Type": "application/json"})
    while True:
        at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with urllib.request.urlopen(request, timeout=60) as reply:
                status, raw = reply.status, reply.read()
        except urllib.error.HTTPError as refused:
            status, raw = refused.code, refused.read()
            if status == 429:  # the rate limit: note it, wait, ask again
                log.append({"at": at, "method": method, "url": API + path, "body": body, "status": 429, "file": None})
                time.sleep(float(refused.headers.get("Retry-After") or 10) + 1)
                continue
        break
    time.sleep(1.2)  # under the documented 10 requests in 10 seconds
    (out / file).write_bytes(raw)
    log.append({"at": at, "method": method, "url": API + path, "body": body, "status": status, "file": file})
    if status != 200:
        raise SystemExit(f"{method} {path}: {status}, body kept in {file}")
    return json.loads(raw)


def get(path: str, file: str, **query):
    return call("GET", path + "?" + urllib.parse.urlencode(query), file)


dataset = get("/api/v1/datasets", "dataset.json", name="trace-fixture-stock-10")[0]
get("/api/v1/examples", "examples.json", dataset=dataset["id"], limit=100)
for name, experiment in (("baseline", sys.argv[2]), ("candidate", sys.argv[3])):
    sid = get("/api/v1/sessions", f"{name}.session.json", name=experiment)[0]["id"]
    call("POST", "/api/v2/runs/query", f"{name}.runs-v2.json", {"project_ids": [sid], "selects": SELECTS, "page_size": 100})
    call("POST", "/api/v2/runs/query", f"{name}.runs-v2.subtree.json",
         {"project_ids": [sid], "selects": SELECTS, "page_size": 100, "include_subtree_usage": True})
    call("POST", "/api/v1/runs/query", f"{name}.runs-v1.json", {"session": [sid], "limit": 100})
    get("/api/v1/feedback", f"{name}.feedback.json", session=sid, limit=100)
    if name != "candidate":
        continue
    cursor, page = None, 1
    while True:
        body = {"project_ids": [sid], "selects": SELECTS, "page_size": 25} | ({"cursor": cursor} if cursor else {})
        got = call("POST", "/api/v2/runs/query", f"{name}.runs-v2.page-{page}.json", body)
        cursor, page = got.get("next_cursor"), page + 1
        if not cursor:
            break
    cursor, page = None, 1
    while True:
        body = {"session": [sid], "limit": 25} | ({"cursor": cursor} if cursor else {})
        got = call("POST", "/api/v1/runs/query", f"{name}.runs-v1.page-{page}.json", body)
        cursor, page = (got.get("cursors") or {}).get("next"), page + 1
        if not cursor or not got["runs"]:
            break
    page = 1
    while get("/api/v1/feedback", f"{name}.feedback.page-{page}.json", session=sid, limit=25, offset=25 * (page - 1)):
        page += 1
(out / "requests.json").write_text(json.dumps(log, indent=1) + "\n")
print(len(log), "requests")
