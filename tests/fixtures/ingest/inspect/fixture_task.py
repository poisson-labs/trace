from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

@task
def trace_fixture():
    return Task(
        dataset=[
            Sample(id="q1", input="Say banana.", target="banana"),
            Sample(id="q2", input="Say apple.", target="apple"),
            Sample(id="q3", input="Say pear.", target="pear"),
        ],
        solver=[generate()],
        scorer=includes(),
    )
