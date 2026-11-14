# From Ragas

You scored two versions of a retrieval pipeline with Ragas, and one has the better mean score.
This recipe checks whether fewer answers miss the cut on the new version than on the old. It
starts from the score tables you saved and runs no metric and no model.

## 1. The files

Save each version's scores as a table, with a column that says which question a row is:
`result.to_pandas().to_json("base.jsonl", orient="records", lines=True)` writes one. CSV, JSON
and Parquet are read too.

Here the files are `rag-base.jsonl` and `rag-raft.jsonl` in `tests/fixtures/ingest/ragas/` in
a clone of the repository: a base model and the same model fine-tuned, each scored on 150 rows
of 146 questions. The commands run from the clone's root.

## 2. Import each table as a version

One import is one version and one score column. A Ragas table records no threshold, so you
say where the cut is and which side of it is a miss: `--cut 0.5 --below` counts a score under
0.5 as missed. `--case-column` names the column that pairs rows across the two tables.

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-base.jsonl \
  --store ./store --run base --metric faithfulness --cut 0.5 --below --case-column case
```

<!-- excerpt exit=0 -->
```
ok  wrote run base to ./store: 150 rows, 146 cases, 1 to 3 repeats; 95 passed, 52 failed, 3 with no outcome
```

<!-- command -->
```
poisson-trace import ragas tests/fixtures/ingest/ragas/rag-raft.jsonl \
  --store ./store --run tuned --metric faithfulness --cut 0.5 --below --case-column case
```

<!-- excerpt exit=0 -->
```
ok  wrote run tuned to ./store: 150 rows, 146 cases, 1 to 3 repeats; 95 passed, 47 failed, 8 with no outcome
```

A row Ragas could not score has no outcome. The summary counts those rows, and the comparison
leaves them out and says so.

## 3. Check the fix

<!-- command -->
```
poisson-trace fix-check base tuned --store ./store --event missed \
  --inputs all --max-mde 0.10
```

<!-- excerpt exit=0 -->
```
too small to tell  too few tries to see a 10-point drop
```

<!-- excerpt exit=0 -->
```
| version | runs | failed | failure share | did not fail |
|---|---|---|---|---|
| old | 141 | 51 | 36.2% | 63.8% |
| new | 141 | 46 | 32.6% | 67.4% |
```

The fine-tuned model missed the cut a little less often, and these rows are too few to tell
that from chance at the size asked for. The report's Guidance section says how many repeats of
each question, or how many more questions, would settle it. The
[Ragas page](../integrations/ragas.md) reads the same two tables on their other two scores and
has every flag.

## What this does not do

- It does not run Ragas, a metric or a model; it reads the table you saved.
- It does not compare mean scores. It compares how often a score falls on the wrong side of
  the cut you name.
- It does not choose the cut. Write it down before you look at a result.
- It keeps no question and no answer text, only the value of the case column you name.
