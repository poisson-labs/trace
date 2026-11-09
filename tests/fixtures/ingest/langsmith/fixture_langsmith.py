"""Trace fixture for LangSmith: one stock-desk agent in two versions (baseline, candidate) run as
two experiments over the same ten-example dataset, on gpt-4.1-mini, so LangSmith computes token
counts and costs.

Each example is one trace: a chain run (the target) holding a retriever run (find_policy), a tool
run (check_stock), an llm run (the model call, streamed, through langsmith.wrappers.wrap_openai) and a
parser run (parse_answer). The failures are planted and the same on every run:

  baseline   c03, c06  the stock table is stale, so the answer is wrong
             c08       check_stock raises TimeoutError, so the trace ends in error
             c10       find_policy finds nothing, so the model answers "unknown"
  candidate  c04       check_stock is refused once (429) and retried: a failed step, a passing case
             c06       the stock table is still stale, so the answer is wrong
             c09       the reply is cut at three tokens, so parse_answer raises ValueError

Feedback on each root run:
  exact          from the evaluator `evaluate()` runs (code; LangSmith records it as a model score)
  judge_correct  `create_feedback(..., feedback_source_type="model")`, a 0 or 1 from a second
                 gpt-4.1-mini call that compares the answer with the expected one; not given to a
                 run that errored, so those roots have no judge score
  thumbs         `create_feedback` with the default source (`api`): 1 or 0, with a comment on a 0;
                 this stands for the human thumb (a thumb clicked in the UI has source `app`)
  review         a categorical value with no score: ok, wrong_answer, abstained or errored

Run with `python fixture_langsmith.py`; `python fixture_langsmith.py feedback <experiment> <version>`
adds the three hand-made feedback keys alone to an experiment already run. It needs LANGSMITH_API_KEY and OPENAI_API_KEY. Every
model call (agent and judge) is counted into the file CAPTURE_LEDGER names, and a call that could
take the total past CAPTURE_CAP_USD (default 0.50) is refused before it is made. It prints the
dataset id and the two experiments' names and ids, which pull.py takes."""
import json
import os
import sys
import threading
import time

from langsmith import Client, traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI

MODEL = "gpt-4.1-mini"
DATASET = "trace-fixture-stock-10"
PRICE_IN, PRICE_OUT = 0.40e-6, 1.60e-6  # dollars a token, gpt-4.1-mini list price
MAX_IN, MAX_OUT = 400, 40  # the most one call here can use
CAP = float(os.environ.get("CAPTURE_CAP_USD", "0.50"))
LEDGER = os.environ.get("CAPTURE_LEDGER", "ledger-langsmith.jsonl")
_lock = threading.Lock()

# case, item, true stock, stale stock, reorder threshold
TABLE = [("c01", "widget", 14, 14, 10), ("c02", "gasket", 3, 3, 8), ("c03", "valve", 5, 9, 6),
         ("c04", "flange", 20, 20, 12), ("c05", "bearing", 2, 2, 4), ("c06", "coupling", 7, 4, 5),
         ("c07", "washer", 30, 30, 25), ("c08", "spindle", 1, 1, 3), ("c09", "bracket", 11, 11, 9),
         ("c10", "seal", 6, 6, 10)]
TRUE = {item: n for _, item, n, _, _ in TABLE}
STALE = {item: n for _, item, _, n, _ in TABLE}
POLICY = {item: t for _, item, _, _, t in TABLE}
STALE_IN = {"baseline": {"valve", "coupling"}, "candidate": {"coupling"}}
_attempts: dict = {}


def spent() -> float:
    if not os.path.exists(LEDGER):
        return 0.0
    return sum(json.loads(line)["usd"] for line in open(LEDGER) if line.strip())


def complete(client, version: str, case: str, role: str = "agent", stream: bool = False, **kwargs) -> str:
    with _lock:
        if spent() + MAX_IN * PRICE_IN + MAX_OUT * PRICE_OUT > CAP:
            raise SystemExit(f"spend cap {CAP} would be crossed; stopping before the call")
    if stream:  # streamed, so LangSmith records the time of the first token
        text, usage, model = "", None, MODEL
        for chunk in client.chat.completions.create(model=MODEL, temperature=0, stream=True,
                                                    stream_options={"include_usage": True}, **kwargs):
            model = chunk.model or model
            usage = chunk.usage or usage
            if chunk.choices and chunk.choices[0].delta.content:
                text += chunk.choices[0].delta.content
    else:
        reply = client.chat.completions.create(model=MODEL, temperature=0, **kwargs)
        text, usage, model = reply.choices[0].message.content, reply.usage, reply.model
    row = {"platform": "langsmith", "version": version, "case": case, "role": role, "model": model,
           "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
           "usd": usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT}
    with _lock, open(LEDGER, "a") as out:
        out.write(json.dumps(row) + "\n")
    return text


@traceable(run_type="retriever")
def find_policy(item: str, version: str) -> list:
    if version == "baseline" and item == "seal":
        return []
    return [{"page_content": f"Reorder {item} when stock is below {POLICY[item]}.", "type": "Document",
             "metadata": {"source": "reorder-policy"}}]


@traceable(run_type="tool")
def check_stock(item: str, version: str) -> int:
    if version == "baseline" and item == "spindle":
        raise TimeoutError("check_stock timed out after 2.0s")
    if version == "candidate" and item == "flange":
        _attempts[item] = _attempts.get(item, 0) + 1
        if _attempts[item] == 1:
            raise RuntimeError("429 rate limit exceeded for check_stock")
    return (STALE if item in STALE_IN[version] else TRUE)[item]


@traceable(run_type="parser")
def parse_answer(text: str, version: str) -> str:
    if version == "candidate":
        try:
            word = json.loads(text)["action"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"reply is not the JSON asked for: {text!r}") from exc
    else:
        word = text
    word = str(word).strip().strip(".").lower()
    if word not in ("reorder", "hold", "unknown"):
        raise ValueError(f"reply is not one of the three words: {text!r}")
    return word


def agent(version: str):
    llm = wrap_openai(OpenAI())

    def stock_desk(inputs: dict) -> dict:
        item, case = inputs["item"], inputs["case"]
        policy = find_policy(item, version)
        try:
            stock = check_stock(item, version)
        except RuntimeError:
            stock = check_stock(item, version)  # one retry
        if version == "candidate":
            form = 'Reply with JSON only, {"action": "reorder"} or {"action": "hold"} or {"action": "unknown"}.'
        else:
            form = "Reply with one word only: reorder, hold or unknown."
        system = ("You are a stock desk. Decide from the policy and the stock count given. "
                  "If no policy is given, the answer is unknown. " + form)
        user = f"Item: {item}\nStock: {stock}\nPolicy: {policy[0]['page_content'] if policy else '(none found)'}"
        text = complete(llm, version, case, stream=True,
                        max_tokens=3 if (version, case) == ("candidate", "c09") else MAX_OUT,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return {"answer": parse_answer(text, version)}

    return stock_desk


def exact(outputs: dict, reference_outputs: dict) -> bool:
    return (outputs or {}).get("answer") == reference_outputs["expected"]


def dataset(client: Client):
    if client.has_dataset(dataset_name=DATASET):
        return client.read_dataset(dataset_name=DATASET)
    made = client.create_dataset(DATASET, description="Trace fixture: ten stock-desk cases.")
    client.create_examples(dataset_id=made.id, examples=[
        {"inputs": {"case": case, "item": item}, "outputs": {"expected": "reorder" if true < threshold else "hold"},
         "metadata": {"case": case}} for case, item, true, _, threshold in TABLE])
    return made


def add_feedback(client: Client, experiment: str, version: str) -> int:
    judge = OpenAI()  # not wrapped: the judge's calls are not traced
    expected_of = {case: "reorder" if true < threshold else "hold" for case, _, true, _, threshold in TABLE}
    for _ in range(60):  # a run is listed before it is whole: wait until all ten roots have ended
        roots = list(client.list_runs(project_name=experiment, is_root=True))
        if len(roots) == len(TABLE) and all(run.end_time and run.status != "pending" for run in roots):
            break
        time.sleep(5)
    else:
        raise SystemExit(f"{experiment}: the ten root runs were not all in after five minutes")
    for run in roots:
        case = run.inputs["case"]
        expected, answer = expected_of[case], (run.outputs or {}).get("answer")
        if run.error or answer is None:
            label = "errored"
        else:
            verdict = complete(judge, version, case, role="judge", max_tokens=1, messages=[
                {"role": "system", "content": "Reply 1 if the answer is the expected decision, else 0. One character only."},
                {"role": "user", "content": f"Expected: {expected}\nAnswer: {answer}"}])
            verdict = verdict.strip()
            client.create_feedback(run.id, key="judge_correct", score=1 if verdict == "1" else 0,
                                   feedback_source_type="model", source_info={"model": MODEL, "raw": verdict})
            label = "ok" if answer == expected else "abstained" if answer == "unknown" else "wrong_answer"
        client.create_feedback(run.id, key="thumbs", score=1 if label == "ok" else 0,
                               comment=None if label == "ok" else f"{label}: answered {answer}, expected {expected}")
        client.create_feedback(run.id, key="review", value=label)
    return len(roots)


def main():
    client = Client()
    if sys.argv[1:2] == ["feedback"]:  # feedback alone, on an experiment already run: feedback <experiment> <version>
        print("feedback on", add_feedback(client, sys.argv[2], sys.argv[3]), "root runs")
        client.flush()
        return
    data = dataset(client)
    print("dataset", data.name, data.id)
    for version in ("baseline", "candidate"):
        results = client.evaluate(agent(version), data=DATASET, evaluators=[exact],
                                  experiment_prefix=f"trace-fixture-{version}",
                                  metadata={"version": version, "model": MODEL}, max_concurrency=2)
        client.flush()
        name = results.experiment_name
        project = client.read_project(project_name=name)
        print("experiment", version, name, project.id)
        print("feedback on", add_feedback(client, name, version), "root runs")
        client.flush()


if __name__ == "__main__":
    main()
