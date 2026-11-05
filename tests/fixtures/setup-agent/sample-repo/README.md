# Support agent

A small customer-support agent and the evaluations the team runs on it. Nothing here calls a
model: the agent in `agent/` is a stand-in that answers from a table, so the repository can be
checked out and its tests run with no key.

What is where:

- `agent/`: the agent. `agent.FAILURES` names the ways a case can end that the team counts as
  failures; `agent.run_case` runs one case.
- `store/`: the runs Poisson Prove recorded of the agent, before and after the replay change
  (two runs, each a folder holding `manifest.json`).
- `evals/`: the retrieval evaluation. `evals/score_rag.py` scores a Ragas table and names the
  cut a row must reach; `evals/results/` holds the two scored tables, `rag-base.jsonl` from
  before the retriever change and `rag-raft.jsonl` from after it.
- `tests/`: the agent's own tests (`agent_checks.py`). `pytest --junitxml` writes their reports into `reports/`:
  `reports/junit-old.xml` before the fix of the parser, `reports/junit-new.xml` after it.
