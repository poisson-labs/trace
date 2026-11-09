"""Trace fixture for Braintrust: two Evals, an old and a new version, over the same six cases.
`braintrust eval --no-send-logs fixture.eval.py` runs them locally and prints summaries only (no
per-row file); run with logs sent, against an account, to export each experiment from the UI."""
from braintrust import Eval

CASES = [{"input": "q1", "expected": "banana"}, {"input": "q2", "expected": "apple"},
         {"input": "q3", "expected": "pear"}] * 2

def exact(input, output, expected):
    return 1.0 if output == expected else 0.0

def old(input):
    return {"q1": "banana", "q2": "nope", "q3": "nope"}[input]

def new(input):
    return {"q1": "banana", "q2": "apple", "q3": "pear"}[input]

Eval("trace-fixture", experiment_name="old", data=lambda: CASES, task=old, scores=[exact])
Eval("trace-fixture", experiment_name="new", data=lambda: CASES, task=new, scores=[exact])
