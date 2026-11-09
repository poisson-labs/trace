"""Pull the raw REST responses for the trace-fixture experiments from Braintrust and save each
response body byte for byte under api/. Needs BRAINTRUST_API_KEY; standard library only.

    python pull.py <out-dir>

Saved, for each of the four experiments (old, new, slice-baseline, slice-candidate):
  <name>.fetch.json           GET  /v1/experiment/{id}/fetch?limit=1000
  <name>.btql-spans.json      POST /btql  select: * | from: experiment('{id}') spans | limit: 1000
  <name>.btql-traces.json     POST /btql  the same from `traces`
  <name>.btql-summary.json    POST /btql  the same from `summary`
and once: experiments.json (GET /v1/experiment?project_name=trace-fixture), and for
slice-candidate the same fetch and the same spans query in pages of 25 (…fetch.page-N.json,
…btql-spans.page-N.json), following the cursor each response returns. requests.json lists every
request made, in order, with its status and the file its body went to; no header is recorded.
A request the rate limit refuses (429) is listed with no file and asked again after the wait."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.braintrust.dev"
PROJECT = "trace-fixture"
NAMES = ("old", "new", "slice-baseline", "slice-candidate")
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
log = []


def call(method: str, path: str, file: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, method=method, data=data, headers={
        "Authorization": "Bearer " + os.environ["BRAINTRUST_API_KEY"], "Content-Type": "application/json"})
    while True:
        at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with urllib.request.urlopen(request, timeout=60) as reply:
                status, raw = reply.status, reply.read()
        except urllib.error.HTTPError as refused:
            status, raw = refused.code, refused.read()
            if status == 429:  # the rate limit: note it, wait as told, ask again
                wait = float(refused.headers.get("Retry-After") or 20)
                log.append({"at": at, "method": method, "url": API + path, "body": body, "status": 429, "file": None})
                time.sleep(min(wait, 120) + 1)
                continue
        break
    time.sleep(2)
    (out / file).write_bytes(raw)
    log.append({"at": at, "method": method, "url": API + path, "body": body, "status": status, "file": file})
    if status != 200:
        raise SystemExit(f"{method} {path}: {status}, body kept in {file}")
    return raw


listing = json.loads(call("GET", "/v1/experiment?" + urllib.parse.urlencode({"project_name": PROJECT}), "experiments.json"))
ids = {e["name"]: e["id"] for e in listing["objects"]}
for name in NAMES:
    eid = ids[name]
    call("GET", f"/v1/experiment/{eid}/fetch?limit=1000", f"{name}.fetch.json")
    for shape in ("spans", "traces", "summary"):
        call("POST", "/btql", f"{name}.btql-{shape}.json",
             {"query": f"select: * | from: experiment('{eid}') {shape} | limit: 1000", "fmt": "json"})

eid, cursor, page = ids["slice-candidate"], None, 1
while True:
    query = {"limit": 25} | ({"cursor": cursor} if cursor else {})
    got = json.loads(call("GET", f"/v1/experiment/{eid}/fetch?" + urllib.parse.urlencode(query), f"slice-candidate.fetch.page-{page}.json"))
    cursor, page = got.get("cursor"), page + 1
    if not got["events"] or not cursor:
        break
cursor, page = None, 1
while True:
    text = f"select: * | from: experiment('{eid}') spans | limit: 25" + (f" | cursor: '{cursor}'" if cursor else "")
    got = json.loads(call("POST", "/btql", f"slice-candidate.btql-spans.page-{page}.json", {"query": text, "fmt": "json"}))
    cursor, page = got.get("cursor"), page + 1
    if not got["data"] or not cursor:
        break
(out / "requests.json").write_text(json.dumps(log, indent=1) + "\n")
print(len(log), "requests")
