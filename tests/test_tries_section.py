"""TRIES: the failure breakdown says how many tries had no outcome (FD15, ruled by Taylor on
2026-11-06, ``log/trace-breakdown-b/rulings.md``; this fix's own readings are
``log/trace-tries/rulings.md``).

The section ``## Failures by kind`` counts every try the reader gave, while the verdict counts only
the inputs both runs carry with an outcome (the Ragas page said 150 tries in the section and 141 in
the summary). So whenever a run has tries with no outcome, the section says how many, per run, and
how that squares with the verdict's count; when no try lacks an outcome, nothing changes: no new
line, no new key.

**TRIES-1** The sentence: present, with the right counts, on the committed fixtures that hold tries
with no outcome (the cs_agents replay run: 3 of 24; the Ragas pair: 3 and 8 of 150), and on a
built table store where the two runs differ in what they lack. Where it stands: after the tries
line, before the signals, as a paragraph of its own. Its words, per run (``the old version`` and
``the new version`` on ``fix-check``, ``A`` and ``B`` on ``compare`` and ``changes``).

**TRIES-2** Absent when every try has an outcome: the committed Prove 0.1.3 store prints no
sentence and its diff has no new key; a ``--verdicts`` file that fills the tries with no outcome
leaves none to count, and one that fills some leaves the rest.

**TRIES-3** The counts are an independent read of the store (``poisson_prove``'s own reader, a
try with no outcome one whose outcome is empty; the verdict's tries those of the inputs both runs
carry with an outcome), not the verb's.

**TRIES-4** The same counts on all four surfaces: the plain report, ``--json`` (the diff's
``no_outcome`` and ``verdict_tries``, after ``tries``), the saved verdict (``result.json``'s diff
and ``report.md``'s section) and the Python API (the result's diff, ``to_markdown()``).

**TRIES-5** Runs classified by different rules print digests and no counts (FD4); the sentence is
not there either, for there is no tries line to square.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from breakdown_support import (
    ARMS, HEADING, LABELS, SIGNALS_LINE, TWO_RUNS, argv_of, different_rules_section, of_line, ok, prove_store,
    section, table_store,
)
from conftest import FIXTURES
from tf0_support import chdir, trace_import

CS = FIXTURES / "cs"
CS_A, CS_B = "20260925T234602Z-3ea0", "20260925T235434Z-af48"
CS_EVENTS = ["--event", "app_error", "--event", "forbidden_action", "--event", "max_turns"]
RAGAS = FIXTURES / "ingest" / "ragas"
KEYS = ["taxonomy_sha256", "same_rules", "tries", "no_outcome", "verdict_tries", "kinds", "signals"]
OLD_KEYS = ["taxonomy_sha256", "same_rules", "tries", "kinds", "signals"]


# ---------- the reference: an independent read of the store ----------


def read_counts(store: Path, names: tuple[str, str]) -> dict[str, tuple[int, int]]:
    """Per run: its tries, its tries with no outcome, and the tries the verdict counts (those on
    the inputs both runs carry with an outcome), read with Prove's own reader."""
    from poisson_prove.store import Store

    frames = [Store(store).read(n) for n in names]
    with_outcome = [set(f.loc[f["outcome"].notna(), "config_hash"]) for f in frames]
    both = with_outcome[0] & with_outcome[1]
    tries = tuple(len(f) for f in frames)
    none = tuple(int(f["outcome"].isna().sum()) for f in frames)
    used = tuple(int((f["outcome"].notna() & f["config_hash"].isin(both)).sum()) for f in frames)
    return {"tries": tries, "none": none, "used": used}  # type: ignore[dict-item]


def thousands(n: int) -> str:
    return f"{n:,}"


def whose(verb: str) -> tuple[str, str]:
    """How the sentence names each run's tries (``the old version's``) and each run on its own."""
    if verb == "fix-check":
        return ("the old version", "the new version")
    return LABELS[verb]


def expected_line(verb: str, counts: dict[str, tuple[int, int]]) -> str:
    (na, nb), (ta, tb), (ua, ub) = counts["none"], counts["tries"], counts["used"]
    a, b = whose(verb)
    used = (
        f"{thousands(ua)} tries of each"
        if ua == ub
        else f"{thousands(ua)} tries of {a} and {thousands(ub)} of {b}"
    )
    return (
        f"Tries with no outcome: {thousands(na)} of {a}'s {thousands(ta)} and {thousands(nb)} of {b}'s "
        f"{thousands(tb)}; the counts above include them. The verdict counts only inputs both runs "
        f"carry with an outcome, so it counts {used}."
    )


def of_index(lines: list[str]) -> int:
    return next(i for i, line in enumerate(lines) if line.startswith("of ") and line.endswith("; a try has one kind"))


# ---------- the stores ----------


def cs_store(tmp: Path) -> Path:
    dest = tmp / "cs"
    shutil.copytree(CS, dest)
    return dest


def cs_argv(verb: str, store: Path | str, *extra: str) -> list[str]:
    base = [verb, CS_A, CS_B, "--store", str(store), *CS_EVENTS]
    if verb == "fix-check":
        base += ["--inputs", "all", "--max-mde", "0.10"]
    if verb == "compare":
        base += ["--max-mde-hr", "1.5"]
    return [*base, *extra]


def ragas_store(tmp: Path) -> Path:
    store = tmp / "ragas"
    for name, start in (("rag-base", "2025-03-31T06:56:41Z"), ("rag-raft", "2025-03-31T07:16:07Z")):
        made = trace_import(["ragas", str(RAGAS / f"{name}.jsonl"), "--store", str(store), "--run", name,
                             "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case",
                             "--started", start])
        assert made.code == 0, made.text
    return store


def ragas_argv(verb: str, store: Path | str, *extra: str) -> list[str]:
    base = [verb, "rag-base", "rag-raft", "--store", str(store), "--event", "missed"]
    if verb == "fix-check":
        base += ["--inputs", "all", "--max-mde", "0.5", "--top", "0"]
    return [*base, *extra]


def built_store(tmp: Path) -> Path:
    """Two table imports that lack different things: ``old`` has no outcome on c6 and c7 (8
    tries); ``new`` has none on c7 only, an outcome on c6, and carries c8 alone (9 tries). The
    verdict's inputs are c0 to c5: 6 tries of each."""
    old = {**{f"c{i}": ("failed" if i < 2 else "passed") for i in range(6)}, "c6": "", "c7": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}, "c6": "passed", "c7": "",
           "c8": "failed"}
    return table_store(tmp, {"old": old, "new": new})


def built_argv(verb: str, store: Path | str, *extra: str) -> list[str]:
    base = [verb, "old", "new", "--store", str(store), "--event", "missed"]
    if verb == "fix-check":
        base += ["--inputs", "all", "--max-mde", "0.5"]
    return [*base, *extra]


CASES = [
    ("cs", "fix-check"), ("cs", "compare"), ("cs", "changes"),
    ("ragas", "fix-check"), ("ragas", "changes"),
    ("built", "fix-check"), ("built", "changes"),
]
MAKERS = {"cs": (cs_store, cs_argv, (CS_A, CS_B)),
          "ragas": (ragas_store, ragas_argv, ("rag-base", "rag-raft")),
          "built": (built_store, built_argv, ("old", "new"))}


def made(which: str, verb: str, tmp: Path) -> tuple[Path, list[str], dict[str, tuple[int, int]]]:
    make, argv, names = MAKERS[which]
    store = make(tmp)
    return store, argv(verb, store), read_counts(store, names)


# ---------- TRIES-3: the reference is the fixtures' known counts ----------


def test_tries_3_the_reference_reads_the_known_counts(tmp_path: Path) -> None:
    """Pins the independent read to what the fixtures are known to hold (the cs replay's three
    errored rows; the Ragas pair's 3 and 8 rows with no score), so the tests below mean it."""
    cs = read_counts(CS, (CS_A, CS_B))
    assert cs == {"tries": (24, 24), "none": (0, 3), "used": (21, 21)}
    ragas = read_counts(ragas_store(tmp_path), ("rag-base", "rag-raft"))
    assert ragas == {"tries": (150, 150), "none": (3, 8), "used": (141, 141)}
    (tmp_path / "b").mkdir()
    built = read_counts(built_store(tmp_path / "b"), ("old", "new"))
    assert built == {"tries": (8, 9), "none": (2, 1), "used": (6, 6)}


# ---------- TRIES-1 and TRIES-3: the sentence, with the counts the store holds ----------


@pytest.mark.parametrize(("which", "verb"), CASES)
def test_tries_1_the_sentence_says_how_many(which: str, verb: str, tmp_path: Path) -> None:
    _store, argv, counts = made(which, verb, tmp_path)
    got = section(ok(argv).out)
    at = of_index(got)
    assert got[at + 1] == "" and got[at + 2] == expected_line(verb, counts)
    # a paragraph of its own: the signals' table, where there is one, follows after a blank line
    rest = got[at + 3:]
    # the Prove label kinds pair names, after it, the labels that have no kind (test_pl_section.py, PL-21, holds that)
    if len(rest) >= 2 and rest[0] == "" and rest[1].startswith("Trace has no kind for the label"):
        rest = rest[2:]
    assert rest == [] or (rest[0] == "" and rest[1] == SIGNALS_LINE)
    # the section's tries line is still every try the reader gave, and no other line speaks of it
    assert got[at] == of_line(verb, counts["tries"])
    assert [line for line in got if "no outcome" in line] == [expected_line(verb, counts)]


def test_tries_1_the_ragas_page_no_longer_sits_150_against_141(tmp_path: Path) -> None:
    _store, argv, _counts = made("ragas", "fix-check", tmp_path)
    got = section(ok(argv).out)
    assert "of 150 tries of the old version and 150 of the new; a try has one kind" in got
    line = next(line for line in got if "no outcome" in line)
    assert "3 of the old version's 150 and 8 of the new version's 150" in line
    assert "it counts 141 tries of each" in line


def test_tries_1_unequal_tries_the_verdict_counts_are_named_per_run(tmp_path: Path) -> None:
    """Where the verdict counts a different number of tries on each run (the old run gave each
    of four inputs two tries, the new one try), each is given: 8 of A and 4 of B."""
    rows = {
        "old": [(f"c{i}", "passed") for i in range(4) for _ in range(2)] + [("c4", "")],
        "new": [(f"c{i}", "failed" if i == 0 else "passed") for i in range(4)] + [("c4", "passed")],
    }
    store = tmp_path / "unequal"
    for i, (run, body) in enumerate(rows.items()):
        csv = tmp_path / f"{run}.csv"
        csv.write_text("case,outcome\n" + "".join(f"{c},{o}\n" for c, o in body), encoding="utf-8")
        made = trace_import(["table", str(csv), "--store", str(store), "--run", run, "--case-column", "case",
                             "--outcome-column", "outcome", "--failed", "failed",
                             "--started", f"2026-10-0{i + 1}T00:00:00Z"])
        assert made.code == 0, made.text
    counts = read_counts(store, ("old", "new"))
    assert counts == {"tries": (9, 5), "none": (1, 0), "used": (8, 4)}
    got = section(ok(built_argv("changes", store)).out)
    assert [line for line in got if "no outcome" in line] == [expected_line("changes", counts)]
    assert "so it counts 8 tries of A and 4 of B." in got[of_index(got) + 2]


# ---------- TRIES-2: nothing changes where every try has an outcome ----------


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tries_2_no_sentence_and_no_key_on_the_prove_store(verb: str, tmp_path: Path) -> None:
    store = prove_store(tmp_path)
    out = ok(argv_of(verb, store)).out
    assert "no outcome" not in "\n".join(section(out))
    diff = ok(argv_of(verb, store, "--json")).json()["failure_taxonomy_diff"]
    assert list(diff) == OLD_KEYS


def test_tries_2_a_pair_every_try_of_which_has_an_outcome(tmp_path: Path) -> None:
    old = {f"c{i}": ("failed" if i < 2 else "passed") for i in range(6)}
    new = {f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}
    store = table_store(tmp_path, {"old": old, "new": new})
    for verb in ("fix-check", "changes"):
        ran = ok(built_argv(verb, store))
        assert "no outcome" not in "\n".join(section(ran.out))
        diff = ok(built_argv(verb, store, "--json")).json()["failure_taxonomy_diff"]
        assert list(diff) == OLD_KEYS


def test_tries_2_a_verdicts_file_that_fills_them_leaves_none_to_say(tmp_path: Path) -> None:
    old = {**{f"c{i}": ("failed" if i < 2 else "passed") for i in range(6)}, "c6": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}, "c6": ""}
    store = table_store(tmp_path, {"old": old, "new": new})
    grades = tmp_path / "grades.csv"
    grades.write_text("case,outcome\nc6,fail\n", encoding="utf-8")
    argv = built_argv("changes", store, "--verdicts", str(grades))
    assert "no outcome" not in "\n".join(section(ok(argv).out))
    assert list(ok([*argv, "--json"]).json()["failure_taxonomy_diff"]) == OLD_KEYS


def test_tries_2_a_verdicts_file_that_fills_some_leaves_the_rest(tmp_path: Path) -> None:
    old = {**{f"c{i}": ("failed" if i < 2 else "passed") for i in range(6)}, "c6": "", "c7": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}, "c6": "", "c7": ""}
    store = table_store(tmp_path, {"old": old, "new": new})
    grades = tmp_path / "grades.csv"
    grades.write_text("case,outcome\nc6,fail\n", encoding="utf-8")
    argv = built_argv("changes", store, "--verdicts", str(grades))
    got = section(ok(argv).out)
    # c6 is filled in both runs, c7 stays empty: 1 of 8 each, and the verdict counts c0 to c6
    assert [line for line in got if "no outcome" in line] == [
        expected_line("changes", {"none": (1, 1), "tries": (8, 8), "used": (7, 7)})
    ]


# ---------- TRIES-5: different rules ----------


def test_tries_5_different_rules_print_no_counts_and_no_sentence(tmp_path: Path) -> None:
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    rules = tmp_path / "rules.toml"
    rules.write_text('version = 1\n\n[[taxonomy.rules]]\nfailure_kind = "tool_error"\n'
                     'when_error_matches = "SqlDeadlockError"\n', encoding="utf-8")
    old = {**{f"c{i}": ("failed" if i < 3 else "passed") for i in range(6)}, "c6": ""}
    new = {**{f"c{i}": ("failed" if i < 1 else "passed") for i in range(6)}, "c6": ""}
    store = table_store(tmp_path, {"old": old, "new": new}, configs={"new": rules})
    diff = ok(built_argv("changes", store, "--json")).json()["failure_taxonomy_diff"]
    digests = (diff["taxonomy_sha256"]["a"], diff["taxonomy_sha256"]["b"])
    assert digests[0] == taxonomy_sha256((), None) and digests[1] != digests[0]
    assert section(ok(built_argv("changes", store)).out) == different_rules_section("changes", digests)


# ---------- TRIES-4: the same counts on all four surfaces ----------


def _counts_of(diff: dict[str, Any], verb: str) -> dict[str, tuple[int, int]]:
    a, b = ARMS[verb]
    return {key: (diff[field][a], diff[field][b])
            for key, field in (("tries", "tries"), ("none", "no_outcome"), ("used", "verdict_tries"))}


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tries_4_json_carries_the_counts_after_the_tries(verb: str, tmp_path: Path) -> None:
    store = cs_store(tmp_path)
    counts = read_counts(CS, (CS_A, CS_B))
    diff = ok(cs_argv(verb, store, "--json")).json()["failure_taxonomy_diff"]
    # the Prove label kinds pair adds, last, the labels that have no kind (test_pl_section.py, PL-23, holds that)
    assert [k for k in diff if k != "labels_without_kind"] == KEYS and list(diff)[-1] == "labels_without_kind"
    assert _counts_of(diff, verb) == counts
    assert set(diff["no_outcome"]) == set(diff["verdict_tries"]) == set(ARMS[verb])


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tries_4_the_saved_verdict_holds_the_same(verb: str, tmp_path: Path) -> None:
    store = cs_store(tmp_path)
    counts = read_counts(CS, (CS_A, CS_B))
    printed = ok(cs_argv(verb, store, "--save", "--json")).json()
    folder = store / printed["saved"]
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert result["failure_taxonomy_diff"] == printed["failure_taxonomy_diff"]
    assert _counts_of(result["failure_taxonomy_diff"], verb) == counts
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert expected_line(verb, counts) in report.splitlines()


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tries_4_the_api_carries_the_same(verb: str, tmp_path: Path) -> None:
    from poisson_trace import api

    store = cs_store(tmp_path)
    counts = read_counts(CS, (CS_A, CS_B))
    events = ["app_error", "forbidden_action", "max_turns"]
    with chdir(tmp_path):
        if verb == "fix-check":
            r = api.fix_check("cs", CS_A, CS_B, inputs="all", max_mde=0.10, event=events)
        elif verb == "compare":
            r = api.compare("cs", CS_A, CS_B, max_mde_hr=1.5, event=events)
        else:
            r = api.changes("cs", CS_A, CS_B, event=events)
        plain = ok(cs_argv(verb, "cs"))
        assert r.to_markdown() == plain.out
    assert _counts_of(json.loads(json.dumps(r.failure_taxonomy_diff)), verb) == counts
    assert expected_line(verb, counts) in r.to_markdown().splitlines()
    assert json.loads(r.to_json())["failure_taxonomy_diff"] == json.loads(json.dumps(r.failure_taxonomy_diff))
    del store


@pytest.mark.parametrize("verb", TWO_RUNS)
def test_tries_4_all_four_surfaces_agree(verb: str, tmp_path: Path) -> None:
    """The number in the plain report's sentence is the diff's, the saved verdict's and the
    API's, for each verb."""
    store = cs_store(tmp_path)
    counts = read_counts(CS, (CS_A, CS_B))
    plain = ok(cs_argv(verb, store)).out
    assert expected_line(verb, counts) in section(plain)
    doc = ok(cs_argv(verb, store, "--json")).json()
    assert _counts_of(doc["failure_taxonomy_diff"], verb) == counts
    assert HEADING in plain
