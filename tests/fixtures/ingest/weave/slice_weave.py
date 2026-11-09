"""Trace fixture for Weave, the paid slice: one stock-desk agent in two versions (baseline,
candidate) over the same ten examples, on gpt-4.1-mini, so each call's token usage is logged
under a model name Weave knows and `summary.costs` can fill.

Each example runs four ops under `StockDesk.predict`: find_policy, check_stock, the model call
(recorded by Weave's own OpenAI patch), parse_answer. The failures are planted and the same on
every run:

  baseline   c03, c06  the stock table is stale, so the answer is wrong
             c08       check_stock raises TimeoutError, so predict errors
             c10       find_policy finds nothing, so the model answers "unknown"
  candidate  c04       check_stock is refused once (429) and retried: a failed step, a passing case
             c06       the stock table is still stale, so the answer is wrong
             c09       the reply is cut at three tokens, so parse_answer raises ValueError

After each evaluation the script adds human-style feedback through the SDK to that evaluation's
`predict_and_score` calls: a thumbs-up or thumbs-down reaction on every case, and a note on each
case that did not pass.

Run with `python slice_weave.py`; `python slice_weave.py feedback <evaluate call id>...` adds the
feedback alone to evaluations already run (no model call). It needs WANDB_API_KEY and OPENAI_API_KEY. Every model call is
counted into the file CAPTURE_LEDGER names, and a call that could take the total past
CAPTURE_CAP_USD (default 0.25) is refused before it is made."""
import asyncio
import json
import os
import sys
import threading

import weave
from openai import OpenAI
from weave import Evaluation, Model

MODEL = "gpt-4.1-mini"
PRICE_IN, PRICE_OUT = 0.40e-6, 1.60e-6  # dollars a token, gpt-4.1-mini list price
MAX_IN, MAX_OUT = 400, 40  # the most one call here can use
CAP = float(os.environ.get("CAPTURE_CAP_USD", "0.25"))
LEDGER = os.environ.get("CAPTURE_LEDGER", "ledger-weave.jsonl")
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
EXAMPLES = [{"id": case, "case": case, "item": item, "expected": "reorder" if true < threshold else "hold"}
            for case, item, true, _, threshold in TABLE]
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
    row = {"platform": "weave", "version": version, "case": case, "model": reply.model,
           "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
           "usd": usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT}
    with _lock, open(LEDGER, "a") as out:
        out.write(json.dumps(row) + "\n")
    return reply


@weave.op()
def find_policy(item: str, version: str) -> list:
    if version == "baseline" and item == "seal":
        return []
    return [f"Reorder {item} when stock is below {POLICY[item]}."]


@weave.op()
def check_stock(item: str, version: str) -> int:
    if version == "baseline" and item == "spindle":
        raise TimeoutError("check_stock timed out after 2.0s")
    if version == "candidate" and item == "flange":
        _attempts[item] = _attempts.get(item, 0) + 1
        if _attempts[item] == 1:
            raise RuntimeError("429 rate limit exceeded for check_stock")
    return (STALE if item in STALE_IN[version] else TRUE)[item]


@weave.op()
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


class StockDesk(Model):
    version: str

    @weave.op()
    def predict(self, case: str, item: str) -> str:
        version = self.version
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
        reply = complete(OpenAI(), version, case, max_tokens=3 if (version, case) == ("candidate", "c09") else MAX_OUT,
                         messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return parse_answer(reply.choices[0].message.content, version)


@weave.op()
def exact(expected: str, output: str | None) -> dict:
    return {"exact": output == expected}


@weave.op()
def gave_answer(output: str | None) -> dict:
    return {"gave_answer": output is not None and output != "unknown"}


def add_feedback(client, evaluate_call_id: str) -> int:
    """A thumb on every case of this evaluation, and a note on each that did not pass."""
    expected = {e["case"]: e["expected"] for e in EXAMPLES}
    count = 0
    for call in client.get_calls(filter={"parent_ids": [evaluate_call_id]}):
        if "predict_and_score" not in call.op_name:
            continue
        case = call.inputs["example"]["case"]
        output = call.output.get("output") if hasattr(call.output, "get") else None
        passed = output == expected[case]
        call.feedback.add_reaction("👍" if passed else "👎")
        if not passed:
            call.feedback.add_note("errored before an answer" if output is None else f"answered {output}, expected {expected[case]}")
        count += 1
    return count


def main():
    client = weave.init("trace-fixture")
    if sys.argv[1:2] == ["feedback"]:  # feedback alone, on evaluations already run
        ids = sys.argv[2:]
    else:
        ids = []
        for version in ("baseline", "candidate"):
            ev = Evaluation(name=f"trace-fixture-slice-{version}", dataset=EXAMPLES, scorers=[exact, gave_answer])
            summary, call = asyncio.run(ev.evaluate.call(ev, StockDesk(version=version)))
            print(version, call.id, summary)
            ids.append(call.id)
        client.flush()  # the calls must reach the server before they can be listed
    for call_id in ids:
        print(call_id, "feedback on", add_feedback(client, call_id), "cases")
    client.flush()


if __name__ == "__main__":
    main()
