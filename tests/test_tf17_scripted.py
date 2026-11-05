"""TF17-44 to TF17-46: the scripted run over the sample repository, and what stays as it is
(spec section 17.4 "How it is tested, with no model"; rule 5 of the session).

- TF17-44: a test plays the written skill's steps in order as a coding agent would, reading the
  step list from the skill and failing if the steps differ from section 17.4's seven: it finds
  the store, the Ragas pair and the JUnit pair, the tools from the dependencies, the failures in
  ``agent.FAILURES`` and the cut in ``evals/score_rag.py``, which file is old and which new;
  writes ``trace.toml`` with a path mistyped, runs the check as the skill shows it (exit 1,
  ``error:`` naming the file, a ``next:``), fixes it, runs the check again (exit 0, the four
  pending files), and stops with nothing but ``trace.toml`` and the skill's own files written,
  no store, no byte code and no connection. The person's command then imports the four runs,
  doctor reads ready, and doctor's ``next:`` is the first fix-check on the named pair.
- TF17-45: nothing is written outside the repository the person named (``HOME`` is untouched by
  ``init --agent``, ``doctor --setup`` and the hand-over).
- TF17-46: no existing verb's output changes: ``init --yes`` on a store, ``runs`` and the
  import print byte for byte what main prints today (their stdout pinned here, apart from the
  lines that name this machine).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tf1_support import shell_words, tau2_copy
from tf2_support import doctor, init_yes, no_network, scratch_home, work  # noqa: F401
from tf17_support import (
    CHECK, COMMAND, CS_FAILURES, FOUR, NEXT_COMMAND, RAGAS, STEP_TITLES, agent, commands,
    config_text, detail, expected_toml, import_lines, ragas_entry, ragas_pair, refusal,
    sample_repo, setup_check, snapshot, split_frontmatter, steps_of, trace_in, write_toml,
)


def test_tf17_44_the_scripted_run_plays_the_seven_steps_and_ends_in_the_check_passing(tmp_path: Path, no_network: list[str]) -> None:  # noqa: F811
    repo = sample_repo(tmp_path, user_files=True)
    home = Path(os.environ["HOME"])
    assert agent(repo).code == 0
    skill = (repo / FOUR[0]).read_text(encoding="utf-8")
    body = split_frontmatter(skill)[1]
    steps = steps_of(body)
    assert [s.title for s in steps] == list(STEP_TITLES), [s.title for s in steps]
    before = snapshot(repo, home)

    # 1: the results on disk, read, nothing run: the store (a folder of run folders, each with a
    # manifest.json), the Ragas tables and the JUnit reports.
    assert "manifest.json" in steps[0].text
    assert sorted(p.name for p in (repo / "store").iterdir() if (p / "manifest.json").is_file()) == ["20260925T234602Z-3ea0", "20260925T235434Z-af48"]
    ragas_files = sorted(p.relative_to(repo).as_posix() for p in (repo / "evals" / "results").glob("*.jsonl"))
    junit_files = sorted(p.relative_to(repo).as_posix() for p in (repo / "reports").glob("*.xml"))
    assert ragas_files == ["evals/results/rag-base.jsonl", "evals/results/rag-raft.jsonl"]
    assert junit_files == ["reports/junit-new.xml", "reports/junit-old.xml"]
    # 2: the tools, from the dependencies
    deps = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert "ragas" in deps and "pytest" in deps and "poisson-prove" in deps
    # 3: the outcomes and the cut, from the code
    code = (repo / "agent" / "__init__.py").read_text(encoding="utf-8")
    failures = re.search(r"^FAILURES = \((.*)\)$", code, re.M)
    assert failures and tuple(w.strip().strip('"') for w in failures.group(1).split(",") if w.strip()) == CS_FAILURES
    scoring = (repo / "evals" / "score_rag.py").read_text(encoding="utf-8")
    assert re.search(r"^FAITHFULNESS_CUT = 0\.5$", scoring, re.M) and ">= FAITHFULNESS_CUT" in scoring
    # 4: old and new, from the names and the README
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "rag-base.jsonl` from" in readme and "before" in readme and "junit-old.xml` before" in readme

    # 5: trace.toml, a path mistyped the first time
    assert "trace.toml" in steps[4].text
    draft = expected_toml().replace('file = "evals/results/rag-raft.jsonl"', 'file = "evals/results/rag-raft.json"')
    assert draft != expected_toml()
    write_toml(repo, draft)

    # 6: the check, as the skill shows it, until it passes; at most three fixes
    (check,) = [c for s, c in commands(body, "bash") if s == "## The check"]
    assert shell_words(check) == shell_words(CHECK)
    results = []
    for _ in range(4):
        r = trace_in(repo, shell_words(check)[1:])
        results.append(r)
        if r.code == 0:
            break
        line, nexts = refusal(r)
        assert "evals/results/rag-raft.json" in line, line
        assert nexts, r.err
        write_toml(repo, expected_toml())
    assert [r.code for r in results] == [1, 0], [(r.code, r.err) for r in results]
    last = results[-1]
    assert last.out.splitlines()[0].startswith("ok  "), last.out
    assert [p["file"] for p in import_lines(last.out)] == ["evals/results/rag-base.jsonl", "evals/results/rag-raft.jsonl", "reports/junit-old.xml", "reports/junit-new.xml"]
    assert last.out.splitlines()[-1] == f"next: {NEXT_COMMAND}"

    # 7: stop and hand over: nothing but trace.toml (and the skill's files) written, no store,
    # no byte code, no connection, no key read
    after = snapshot(repo, home)
    changed = sorted(k for k in before if after.get(k) != before[k])
    assert changed == [], changed
    new = sorted(k for k in after if k not in before)
    assert new == ["repo/trace.toml"], new
    assert not (repo / "trace-store").exists() and not (repo / ".poisson").exists()
    assert not list(repo.rglob("__pycache__"))
    assert no_network == []
    assert all("sk-not-a-real-key" not in r.text for r in results)

    # the person's command (with --yes here, since nothing answers on a terminal)
    (person,) = [c for s, c in commands(body, "text") if s == "## Hand over"]
    assert shell_words(person) == [COMMAND, "init"]
    r = init_yes(repo)
    assert r.code == 0, r.text
    d = doctor(repo)
    assert d.code == 0, d.text
    assert (repo / "trace.toml").read_text(encoding="utf-8") == expected_toml() + '\n[store.imported]\npath = "trace-store"\n'
    words = shell_words(d.out.splitlines()[-1][len("next: "):])
    assert words[:4] == [COMMAND, "fix-check", "rag-base", "rag-raft"] and words[4:6] == ["--store", "imported"], words
    assert no_network == []


def test_tf17_44_doctors_next_after_the_hand_over_is_the_first_fix_check_on_the_named_pair(tmp_path: Path) -> None:
    folder = work(tmp_path)
    base, raft = ragas_pair(folder)
    write_toml(folder, config_text(ragas_entry(base, "old"), ragas_entry(raft, "new"), store=None, events=("missed",)))
    assert init_yes(folder).code == 0
    d = doctor(folder)
    assert d.code == 0, d.text
    words = shell_words(d.out.splitlines()[-1][len("next: "):])
    assert words == [COMMAND, "fix-check", "old", "new"], words
    assert detail(d.out, "config"), d.out


# ---------- TF17-45 ----------


def test_tf17_45_nothing_is_written_outside_the_repository(tmp_path: Path) -> None:
    repo = sample_repo(tmp_path, with_expected=True)
    home = Path(os.environ["HOME"])
    elsewhere = work(tmp_path, "elsewhere")
    before = snapshot(home, elsewhere)
    assert agent(repo).code == 0
    assert setup_check(repo).code == 0
    assert init_yes(repo).code == 0
    assert snapshot(home, elsewhere) == before


# ---------- TF17-46 ----------


def test_tf17_46_init_yes_on_a_store_prints_what_main_prints(tmp_path: Path) -> None:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    r = init_yes(folder, "--store", "proofload-runs", "--event", "unsolved")
    assert r.code == 0, r.text
    assert r.out == (
        "ok  wrote trace.toml: store proofload-runs (3 runs), failures unsolved\n"
        "  names    3 runs, named from their manifests (tau2-airline 2026-09-17 a, tau2-airline "
        '2026-09-15 b, tau2-airline 2026-09-15 a); none named by you yet: poisson-trace name RUN "a name"\n'
        "  prove    poisson-prove is installed at the version Trace reads\n"
        "  the same setup, without questions:\n"
        "    poisson-trace init --yes --store proofload-runs --event unsolved\n"
        "next: poisson-trace runs\n"
    ), r.out
    r = trace_in(folder, ["runs", "--plain"])
    assert r.code == 0, r.text
    assert r.out == (
        "ok  3 runs in proofload-runs (newest first); 0 named by you, 3 named from their manifests\n"
        "\n"
        "  #  name                       rows  failed  traces  started           status\n"
        "  1  tau2-airline 2026-09-17 a    10       3  no      2026-09-17 14:02  complete\n"
        "  2  tau2-airline 2026-09-15 b   200     112  yes     2026-09-15 21:11  complete\n"
        "  3  tau2-airline 2026-09-15 a   200     110  yes     2026-09-15 21:01  complete\n"
        "\n"
        'next: poisson-trace where "tau2-airline 2026-09-15 b"\n'
    ), r.out


def test_tf17_46_the_import_prints_what_main_prints(tmp_path: Path) -> None:
    folder = work(tmp_path)
    (folder / "e").mkdir()
    (folder / "e" / "rag-base.jsonl").write_bytes((RAGAS / "rag-base.jsonl").read_bytes())
    r = trace_in(folder, ["import", "ragas", "e/rag-base.jsonl", "--store", "ts", "--run", "old", "--metric", "faithfulness", "--cut", "0.5", "--below", "--case-column", "case", "--plain", "--started", "2026-10-07T04:00:00Z"])
    assert r.code == 0, r.text
    assert r.out.splitlines()[0] == "ok  wrote run old to ts: 150 rows, 146 cases, 1 to 3 repeats; 95 passed, 52 failed, 3 with no outcome", r.out
    assert "- declared: metric faithfulness · cut 0.5 · side below · case_column case" in r.out, r.out
    assert r.out.splitlines()[-1] == "next: poisson-trace fix-check OLD NEW --store ts --event missed --inputs all --max-mde X  # old is OLD or NEW", r.out
    assert "trace.toml" not in r.out
