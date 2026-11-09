"""Trace fixture for Weave: two Evaluations, an old and a new version, over the same six examples.
Needs `weave.init` against a Weights & Biases account (free at the time of writing, not checked);
no model is called, so the run costs nothing. Run once, then export each evaluation's calls table
as JSON and CSV from the UI, and fetch the same calls once through the API, into this folder."""
import asyncio
import weave
from weave import Evaluation, Model

EXAMPLES = [{"id": "q1", "question": "q1", "expected": "banana"},
            {"id": "q2", "question": "q2", "expected": "apple"},
            {"id": "q3", "question": "q3", "expected": "pear"}] * 2

class Lookup(Model):
    answers: dict
    @weave.op()
    def predict(self, question: str) -> str:
        return self.answers[question]

@weave.op()
def exact(expected: str, output: str) -> dict:
    return {"exact": output == expected}

def main():
    weave.init("trace-fixture")
    old = Lookup(answers={"q1": "banana", "q2": "nope", "q3": "nope"})
    new = Lookup(answers={"q1": "banana", "q2": "apple", "q3": "pear"})
    for name, model in (("old", old), ("new", new)):
        ev = Evaluation(name=f"trace-fixture-{name}", dataset=EXAMPLES, scorers=[exact])
        print(name, asyncio.run(ev.evaluate(model)))

if __name__ == "__main__":
    main()
