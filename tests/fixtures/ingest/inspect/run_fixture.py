"""Two Inspect runs with the mock model, as an old and a new version, written as .eval and .json."""
from inspect_ai import eval
from inspect_ai.model import get_model, ModelOutput
from fixture_task import trace_fixture

def model(outputs):
    return get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", o) for o in outputs])

# old: q1 right, q2 wrong, q3 wrong; epoch 2: q1 right, q2 right, q3 wrong
eval(trace_fixture(), model=model(["banana", "nope", "nope", "banana", "apple", "nope"]), epochs=2,
     log_dir="logs", log_format="eval", log_realtime=False, display="none")
# new: all right but q3 once
eval(trace_fixture(), model=model(["banana", "apple", "pear", "banana", "apple", "nope"]), epochs=2,
     log_dir="logs", log_format="json", log_realtime=False, display="none")
