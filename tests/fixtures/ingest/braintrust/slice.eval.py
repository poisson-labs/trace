"""Trace fixture for Braintrust, the paid slice: one stock-desk agent in two versions (baseline,
candidate) over the same ten dataset records, on gpt-4.1-mini, so token and cost metrics fill.

Each case runs four steps under the task: find_policy (a function span), check_stock (a tool
span), the model call (an llm span, through braintrust.wrap_openai), parse_answer (a function
span). The failures are planted and the same on every run:

  baseline   c03, c06  the stock table is stale, so the answer is wrong
             c08       check_stock raises TimeoutError, so the task errors
             c10       find_policy finds nothing, so the model answers "unknown"
  candidate  c04       check_stock is refused once (429) and retried: a failed step, a passing case
             c06       the stock table is still stale, so the answer is wrong
             c09       the reply is cut at three tokens, so parse_answer raises ValueError

Run with `braintrust eval slice.eval.py`. It needs BRAINTRUST_API_KEY and OPENAI_API_KEY. Every
model call is counted into the file CAPTURE_LEDGER names, and a call that could take the total
past CAPTURE_CAP_USD (default 0.25) is refused before it is made."""
import json
import os
import threading

from braintrust import Eval, init_dataset, traced, wrap_openai
from braintrust.score import Classification
from openai import OpenAI

MODEL = "gpt-4.1-mini"
PRICE_IN, PRICE_OUT = 0.40e-6, 1.60e-6  # dollars a token, gpt-4.1-mini list price
MAX_IN, MAX_OUT = 400, 40  # the most one call here can use
CAP = float(os.environ.get("CAPTURE_CAP_USD", "0.25"))
LEDGER = os.environ.get("CAPTURE_LEDGER", "ledger-braintrust.jsonl")
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


def complete(client, version: str, case: str, **kwargs):
    with _lock:
        if spent() + MAX_IN * PRICE_IN + MAX_OUT * PRICE_OUT > CAP:
            raise SystemExit(f"spend cap {CAP} would be crossed; stopping before the call")
    reply = client.chat.completions.create(model=MODEL, temperature=0, **kwargs)
    usage = reply.usage
    row = {"platform": "braintrust", "version": version, "case": case, "model": reply.model,
           "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
           "usd": usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT}
    with _lock, open(LEDGER, "a") as out:
        out.write(json.dumps(row) + "\n")
    return reply


@traced(type="function")
def find_policy(item: str, version: str) -> list:
    if version == "baseline" and item == "seal":
        return []
    return [f"Reorder {item} when stock is below {POLICY[item]}."]


@traced(type="tool")
def check_stock(item: str, version: str) -> int:
    if version == "baseline" and item == "spindle":
        raise TimeoutError("check_stock timed out after 2.0s")
    if version == "candidate" and item == "flange":
        _attempts[item] = _attempts.get(item, 0) + 1
        if _attempts[item] == 1:
            raise RuntimeError("429 rate limit exceeded for check_stock")
    return (STALE if item in STALE_IN[version] else TRUE)[item]


@traced(type="function")
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
    client = wrap_openai(OpenAI())

    def task(input, hooks):
        item, case = input["item"], input["case"]
        hooks.metadata["version"] = version
        hooks.tags = [version]
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
        user = f"Item: {item}\nStock: {stock}\nPolicy: {policy[0] if policy else '(none found)'}"
        reply = complete(client, version, case, max_tokens=3 if (version, case) == ("candidate", "c09") else MAX_OUT,
                         messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return parse_answer(reply.choices[0].message.content, version)

    return task


def exact(input, output, expected):
    return 1.0 if output == expected else 0.0


def gave_answer(input, output, expected):
    return 0.0 if output == "unknown" else 1.0


def kind(input, output, expected):
    if output == expected:
        return None
    return Classification(id="abstained" if output == "unknown" else "wrong_answer", name="failure_kind")


def records():
    dataset = init_dataset("trace-fixture", name="stock-10")
    if not list(dataset):
        for case, item, true, _, threshold in TABLE:
            dataset.insert(id=case, input={"case": case, "item": item},
                           expected="reorder" if true < threshold else "hold", metadata={"case": case})
        dataset.flush()
        dataset = init_dataset("trace-fixture", name="stock-10")
    return dataset


DATA = records()
for version in ("baseline", "candidate"):
    Eval("trace-fixture", experiment_name=f"slice-{version}", data=DATA, task=agent(version),
         scores=[exact, gave_answer], classifiers=[kind], metadata={"version": version, "model": MODEL},
         max_concurrency=2)
