# Tasks, Prove and Trace together

Your agent works through tools in several steps. You changed how it carries a value from one
step to the next, and you want to know whether it now fails less. This recipe answers that with
three tools. [Poisson Tasks](https://github.com/poisson-labs/tasks) makes tasks whose right
answer is known, [Prove](https://github.com/poisson-labs/prove) runs the old and the new version
on them, and Trace says whether the new one fails less and at which step the old one died. It
runs on the files in `examples/three-tools/` of a clone, each block from the clone's root, with
no model and no key, and it costs nothing. The install's second line fetches a file Tasks needs.

<!-- skip reason="installs from the package index, which the docs check does not reach" -->
```
pip install poisson-trace poisson-tasks==0.4.2 'pytest>=9.2.0'
poisson-tasks doctor --fix --yes
```

## 1. Tasks makes the tasks

A task is a request, the tools to meet it with, and a checker that says whether the calls an
agent made left the record where the request asked. `generate` makes 20 tasks at two levels of
the `depth` knob, which differ only in the number of steps a task needs:

<!-- command -->
```
poisson-tasks generate --knob depth --levels 1,3 --tasks-per-level 10 --out tasks/
diff -r tasks examples/three-tools/tasks
```

<!-- excerpt exit=0 -->
```
ok  generated 20 tasks: depth at 1 and 3, 10 tasks each, no model and no network
```

`diff` printed nothing: what `generate` wrote is, byte for byte, the committed tasks the rest of
the page runs on. `--show` prints one task whole. This is the answer to a three-step task:

<!-- command -->
```
poisson-tasks generate --arm depth:d3 --show
```

<!-- excerpt exit=0 -->
```
the reference solution
  1. submit_review_purchase(record_id="able-sheet-shopping-question", entry_code="public")
     -> 000001 ok           484a96b1ac1cc22e078d9482a37e79b6
  2. submit_sample_purchase(record_id="able-sheet-shopping-question", chain_token="484a96b1ac1cc22e078d9482a37e79b6")
     -> 000002 ok           db9f24adc0a40e574fbfb5b2f9a0a927
  3. submit_measure_purchase(record_id="able-sheet-shopping-question", chain_token="db9f24adc0a40e574fbfb5b2f9a0a927")
     -> 000003 ok           0191720f98825ead58ef942c16ed5579
```

## 2. Prove runs the agent, before and after

Each step after the first must pass on the token the step before returned. `agent.py` in
`examples/three-tools/` is a stand-in for your agent, and it calls no model: it reads each call
from the task's answer, with a comment where your model call would go. Its `before` version
loses the token on some later steps and stops there, and its `after` version never does.

`prove_rollout.py` is what Prove calls: one version on one task, judged by the task's own checker.
The spec files differ only in the version. One `--salt` on both sweeps makes every count repeat.

<!-- command -->
```
cd examples/three-tools && poisson-prove sweep prove-before.toml --name "agent before" --salt 7f3a2c --yes
```

<!-- excerpt exit=0 -->
```
plan  5,200 rollouts of agent: 20 cells x 260 replicates on local, $0 (local)
```

<!-- command -->
```
cd examples/three-tools && poisson-prove sweep prove-after.toml --name "agent after" --salt 7f3a2c --yes
```

<!-- excerpt exit=0 varies -->
```
done  5,200 rollouts in run "agent after" (complete) in …
```

## 3. Trace reads Prove's runs

`init` finds the store Prove wrote and asks which outcomes are failures. The answer typed here
takes the one it offers, `wrong_state`: the checker's label for a record left in the wrong place.
[Check a fix](check-a-fix.md) explains the two flags `fix-check` is given.

<!-- command tty answers="1" -->
```
cd examples/three-tools && poisson-trace init
```

<!-- excerpt exit=0 -->
```
ok  wrote trace.toml: store prove-runs (2 runs), failures wrong_state
```

<!-- command -->
```
cd examples/three-tools && poisson-trace fix-check "agent before" "agent after" --inputs all --max-mde 0.20
```

<!-- excerpt exit=0 -->
```
different  the new version failed less often
```

<!-- command -->
```
cd examples/three-tools && poisson-trace where "agent before"
```

<!-- excerpt exit=0 -->
```
| step | at risk | failed | not yet failed | 95% band |
|---|---|---|---|---|
| 2 | 2,600 | 779 | 0.850 | 0.787 – 0.912 |
| 3 | 1,821 | 541 | 0.746 | 0.643 – 0.852 |
```

The new version fails less. `where` places each failed try of the old version at the step it
stopped: none at step 1, and the rest at step 2 or step 3. It died where it lost the token.

## 4. The same answer from your own tests

`test_agent.py` is the team's own pytest file: the same tasks, the same checker, several tries of
each. Run it on each version (it writes its JUnit report even when tests fail) and import both:

<!-- command -->
```
cd examples/three-tools
AGENT=before pytest test_agent.py --junitxml before.xml > /dev/null
AGENT=after pytest test_agent.py --junitxml after.xml > /dev/null
poisson-trace import junit before.xml --store tests-runs --run "tests before" --case name > /dev/null
poisson-trace import junit after.xml --store tests-runs --run "tests after" --case name > /dev/null
poisson-trace fix-check "tests before" "tests after" --store tests-runs --event missed --inputs all --max-mde 0.20
```

<!-- excerpt exit=0 -->
```
different  the new version failed less often
```

## What this does not do

- The stand-in is not an agent, and a real agent's runs cost what its model costs.
- Tasks' `run` and `card` need a model, and they are not in this recipe.
- Prove's run here is the local backend, on this machine.
