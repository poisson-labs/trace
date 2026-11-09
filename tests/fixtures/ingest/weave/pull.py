"""Pull the raw call stream for the trace-fixture project from Weave's service API and save each
response body byte for byte. Needs WANDB_API_KEY; standard library only.

    python pull.py <entity>/trace-fixture <out-dir>

Every request is POST https://trace.wandb.ai/calls/stream_query (basic auth, user `api`), with
`include_costs: true` and `include_feedback: true` unless said otherwise, sorted by `started_at`.
Saved:
  roots.jsonl                 the root calls alone (`filter.trace_roots_only`): one per evaluation
  <evaluation>.jsonl          every call of that evaluation's trace (`filter.trace_ids`), for each of
                              trace-fixture-old, trace-fixture-new, trace-fixture-slice-baseline,
                              trace-fixture-slice-candidate
  <evaluation>.expanded.jsonl  the same with `expand_columns: ["inputs.example"]`, so each
                              predict_and_score call carries its dataset row inline in place of
                              the reference to it
  <evaluation>.plain.jsonl    the slice-candidate trace again with neither include flag, to show
                              what a pull that forgets them gets
  <evaluation>.page-N.jsonl   the slice-candidate trace again in pages of 40 (`limit`, `offset`)
requests.json lists every request made, in order, with its body, its status and the file the
response went to; no header is recorded."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URL = "https://trace.wandb.ai/calls/stream_query"
project, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
log = []


def call(file: str, **body) -> list:
    body = {"project_id": project, "sort_by": [{"field": "started_at", "direction": "asc"}],
            "include_costs": True, "include_feedback": True} | body
    token = base64.b64encode(("api:" + os.environ["WANDB_API_KEY"]).encode()).decode()
    request = urllib.request.Request(URL, method="POST", data=json.dumps(body).encode(), headers={
        "Authorization": "Basic " + token, "Content-Type": "application/json", "Accept": "application/jsonl"})
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with urllib.request.urlopen(request, timeout=120) as reply:
            status, raw = reply.status, reply.read()
    except urllib.error.HTTPError as refused:
        status, raw = refused.code, refused.read()
    (out / file).write_bytes(raw)
    log.append({"at": at, "method": "POST", "url": URL, "body": body, "status": status, "file": file})
    if status != 200:
        raise SystemExit(f"{status}, body kept in {file}")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


roots = call("roots.jsonl", filter={"trace_roots_only": True})
for root in roots:
    if "Evaluation.evaluate" not in root["op_name"]:
        continue
    name = root["inputs"]["self"].rsplit("/", 1)[-1].split(":")[0]  # the Evaluation object's name
    call(f"{name}.jsonl", filter={"trace_ids": [root["trace_id"]]})
    call(f"{name}.expanded.jsonl", filter={"trace_ids": [root["trace_id"]]}, expand_columns=["inputs.example"])
    if name == "trace-fixture-slice-candidate":
        call(f"{name}.plain.jsonl", filter={"trace_ids": [root["trace_id"]]}, include_costs=False, include_feedback=False)
        page = 0
        while call(f"{name}.page-{page + 1}.jsonl", filter={"trace_ids": [root["trace_id"]]}, limit=40, offset=40 * page):
            page += 1
(out / "requests.json").write_text(json.dumps(log, indent=1) + "\n")
print(len(log), "requests")
