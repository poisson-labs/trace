# Where the tasks came from

`tasks/depth-d1.jsonl` and `tasks/depth-d3.jsonl` were written by Poisson Tasks 0.4.2 (the
`poisson-tasks` package, from PyPI), with no model and no network, by this command, run in this
folder:

```text
poisson-tasks generate --knob depth --levels 1,3 --tasks-per-level 10 --out tasks/
```

Nothing in either file was edited afterwards. Tasks writes the same bytes on every run of that
command, so running it again and comparing is the check that these are its own. Their SHA-256:

```text
126024569ffddca64a0c2fa480346e6f301330392611f3dcca282514e1cdb7f5  tasks/depth-d1.jsonl
7601a961568e79c20a20ca7e00900d3c979ac90d62f6942c65618e7c4e2c3793  tasks/depth-d3.jsonl
```

Each file holds 10 tasks, one a line. The two levels use the same 10 seeds, so a task at depth 3
is its depth 1 twin with two more steps.
