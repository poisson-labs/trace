"""TF15-H1 to TF15-H14: the hands-on fixes of 2026-10-20 (spec sections 4.4, 5.2 and 12 as amended;
Taylor's rulings of that day, items 2, 3 and 6, and S3 and S4).

- A folder of several tools' result files leads somewhere: one import line per file init does not
  import, every answer init can read filled in and each it cannot a word in capitals; the
  several-tools refusal carries the lines; --no-import lists them and drops the private Prove
  link, which stays only where init found nothing at all (S4); a store found beside other tools'
  files says what it left out.
- The listing names a store by what wrote it, and "Prove store" leaves init's output.
- doctor notices a store beside a config that names none.
- latest and previous refuse in a form that cannot be copied backwards: the runs listed by name,
  OLDER and NEWER in place of the words (S3).

The sentences are pinned as section 4.4, 5.2 and 12 write them, and the import lines as the
spec's own example (log/trace-report-summary-spec/evidence/mockups-setup.md, S1) prints them.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
from pathlib import Path

from conftest import FIXTURES, TAU2
from tf2_support import doctor, here, import_here, init_yes, scratch_home, tty, work  # noqa: F401
from tf3_support import JUNIT, TABLE_A, TABLE_B, refusal

DEEPEVAL = FIXTURES / "ingest" / "deepeval"
RAGAS = FIXTURES / "ingest" / "ragas"
COLUMNS = ["--case-column", "case", "--outcome-column", "outcome", "--failed", "failed_assertion", "--failed", "crashed"]

LINES = [
    'poisson-trace import deepeval results/test_run_20260905_185407.json --store trace-store --run test_run_20260905_185407 --metric "Tests Passed" --cut recorded --case name',
    'poisson-trace import deepeval results/test_run_20260905_195009.json --store trace-store --run test_run_20260905_195009 --metric "Tests Passed" --cut recorded --case name',
    "poisson-trace import table humaneval-a.csv --store trace-store --run humaneval-a-table --case-column case --outcome-column outcome --failed failed_assertion --failed crashed",
    "poisson-trace import table humaneval-b.csv --store trace-store --run humaneval-b-table --case-column case --outcome-column outcome --failed failed_assertion --failed crashed",
    "poisson-trace import junit humaneval-a.xml --store trace-store --run humaneval-a-junit",
    "poisson-trace import junit humaneval-b.xml --store trace-store --run humaneval-b-junit",
    "poisson-trace import ragas rag-base.jsonl --store trace-store --run rag-base --metric METRIC --cut CUT --below --case-column case",
    "poisson-trace import ragas rag-raft.jsonl --store trace-store --run rag-raft --metric METRIC --cut CUT --below --case-column case",
]
PRIVATE = ("proofload sweep", "github.com/poisson-labs/prove")
# "a Prove store" as a noun; "runs Prove stored" is another phrase
PROVE_STORE = re.compile(r"\bProve stores?\b")


def _four_tools(folder: Path) -> Path:
    """The partner files' first results laid out together, as at the 2026-10-19 hands-on: two
    DeepEval saved test runs in results/, the two tables, the two JUnit reports and the two Ragas
    tables."""
    (folder / "results").mkdir(parents=True)
    for which, name in (("a", "test_run_20260905_185407.json"), ("b", "test_run_20260905_195009.json")):
        (folder / "results" / name).write_bytes(gzip.decompress((DEEPEVAL / f"humaneval-{which}.json.gz").read_bytes()))
    shutil.copy(TABLE_A, folder / "humaneval-a.csv")
    shutil.copy(TABLE_B, folder / "humaneval-b.csv")
    shutil.copy(JUNIT / "humaneval-a.xml", folder / "humaneval-a.xml")
    shutil.copy(JUNIT / "humaneval-b.xml", folder / "humaneval-b.xml")
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "rag-base.jsonl")
    shutil.copy(RAGAS / "rag-raft.jsonl", folder / "rag-raft.jsonl")
    return folder


def _error_line(err: str) -> str:
    """The error line, after init's listing on stderr; every line after it a next: line."""
    lines = err.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("error: "))
    assert all(line.startswith("  next: ") for line in lines[at + 1:]), lines[at:]
    return lines[at]


def _next_lines(err: str) -> list[str]:
    return [line[len("  next: "):] for line in err.splitlines() if line.startswith("  next: ")]


# ---------- the several-tools refusal (4.4) ----------


def test_tf15_h1_several_tools_and_no_store_refuse_with_a_line_per_file(tmp_path: Path) -> None:
    folder = _four_tools(work(tmp_path))
    result = init_yes(folder)
    assert result.code == 1 and result.out == "", result.text
    line = _error_line(result.err)
    assert line == (
        "error: the 8 result files here were written by 4 tools (deepeval, table, junit and ragas), and init can "
        "import one tool's files at a time, so it imported none; pick the two files you want to compare, the old "
        "version's and the new one's, import each with its line below (a word in capitals is yours to fill in), "
        "then run poisson-trace init --force --store trace-store; or give --no-import to write trace.toml with no "
        "store first"
    ), line
    assert _next_lines(result.err) == [*LINES, "poisson-trace import --help"]
    assert not (folder / "trace.toml").exists() and not (folder / "trace-store").exists()


def test_tf15_h2_every_line_imports_when_its_capitals_are_filled_in(tmp_path: Path) -> None:
    """The lines are commands that run: each DeepEval, table and JUnit line as printed, the Ragas
    lines with METRIC and CUT filled in; then the finishing command sets Trace up."""
    folder = _four_tools(work(tmp_path))
    lines = _next_lines(init_yes(folder).err)[:-1]
    for line in lines:
        filled = line.replace("METRIC", "faithfulness").replace("CUT", "0.5")
        words = [w.strip('"') for w in re.findall(r'"[^"]*"|\S+', filled)][2:]
        result = import_here(folder, words)
        assert result.code == 0, (line, result.text)
    finished = here(folder, ["init", "--yes", "--force", "--store", "trace-store"])
    assert finished.code == 0, finished.text


def test_tf15_h3_at_most_twelve_lines(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for k in range(14):
        shutil.copy(TABLE_A, folder / f"t{k:02d}.csv")
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "rag-base.jsonl")
    result = init_yes(folder)
    lines = _next_lines(result.err)
    assert sum(1 for line in lines if line.startswith("poisson-trace import ")) - sum(
        1 for line in lines if line == "poisson-trace import --help") == 12, lines
    assert "and 3 more files: poisson-trace import --help" in result.err, result.err


# ---------- --no-import (4.4, S4) ----------


def test_tf15_h4_no_import_lists_the_lines_and_drops_the_private_link(tmp_path: Path) -> None:
    folder = _four_tools(work(tmp_path))
    result = init_yes(folder, "--no-import")
    assert result.code == 0, result.text
    out = result.out.splitlines()
    assert out[0] == "ok  wrote trace.toml with no store yet; 8 result files of 4 tools not imported", out[0]
    block = out.index(
        "  left out 8 result files, not imported; the lines below import them. To compare two, run the pair's "
        "lines (a word in capitals is yours to fill in), then run poisson-trace init --force --store trace-store:"
    )
    assert out[block + 1:block + 9] == [f"    {line}" for line in LINES]
    assert out[block - 1].startswith("  prove "), out[block - 1]
    assert out[-1] == "next: poisson-trace import --help"
    assert not any(word in result.text for word in PRIVATE), result.text


def test_tf15_h5_the_private_link_stays_where_nothing_was_found(tmp_path: Path) -> None:
    result = init_yes(work(tmp_path), "--no-import")
    assert result.code == 0, result.text
    assert "proofload sweep" in result.out.splitlines()[-1]
    assert "found no store and no result file a reader of this install reads" in result.err
    assert not PROVE_STORE.search(result.text)


# ---------- a store found beside other tools' files (4.4) ----------


def test_tf15_h6_a_store_beside_other_tools_files_says_what_it_left_out(tmp_path: Path) -> None:
    folder = _four_tools(work(tmp_path))
    shutil.copytree(TAU2, folder / "proofload-runs")
    result = init_yes(folder)
    assert result.code == 0, result.text
    out = result.out.splitlines()
    assert out[0] == (
        "ok  wrote trace.toml: store proofload-runs (3 runs), failures unsolved; 8 result files of 4 tools not imported"
    ), out[0]
    block = out.index(
        "  left out 8 result files, not imported; the lines below import them. To compare two, run the pair's "
        "lines (a word in capitals is yours to fill in), then run poisson-trace init --add-store trace-store to add "
        "their store beside this one:"
    )
    assert out[block + 1:block + 9] == [f"    {line}" for line in LINES]
    assert out[-1] == "next: poisson-trace runs"
    assert "found 1 store:" in result.err and not PROVE_STORE.search(result.text)


def test_tf15_h7_files_beside_trace_store_join_it(tmp_path: Path) -> None:
    """The Ragas pair imported into trace-store, the tables beside it: init sets up trace-store, and
    the tables' lines import into the store trace.toml reads."""
    folder = work(tmp_path)
    for name, started in (("rag-base", "2025-03-31T06:56:41Z"), ("rag-raft", "2025-03-31T07:16:07Z")):
        argv = ["ragas", str(RAGAS / f"{name}.jsonl"), "--store", "trace-store", "--run", name, "--metric",
                "faithfulness", "--cut", "0.5", "--below", "--case-column", "case", "--started", started]
        assert import_here(folder, argv).code == 0
    shutil.copy(TABLE_A, folder / "humaneval-a.csv")
    shutil.copy(TABLE_B, folder / "humaneval-b.csv")
    result = init_yes(folder)
    assert result.code == 0, result.text
    out = result.out.splitlines()
    assert out[0].endswith("; 2 result files of 1 tool not imported"), out[0]
    assert any(line.endswith("they join trace-store, which trace.toml reads:") for line in out), out
    assert re.search(r"\d+\) trace-store +2 runs · imported from ragas · newest 2025-03-31", result.err), result.err
    assert "found 1 store:" in result.err and not PROVE_STORE.search(result.text)


# ---------- the import question names no Prove store (4.4, item 6) ----------


def test_tf15_h8_the_import_question(tmp_path: Path) -> None:
    folder = work(tmp_path)
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "rag-base.jsonl")
    shutil.copy(RAGAS / "rag-raft.jsonl", folder / "rag-raft.jsonl")
    result = tty(["init"], ["n"], cwd=folder)
    assert (
        "No store here, but these look like results another tool wrote. Import them as runs Trace can read? [Y/n]"
    ) in result.err, result.err
    assert not PROVE_STORE.search(result.text)


# ---------- doctor with a store beside the config (12) ----------


def test_tf15_h9_doctor_sees_trace_store_beside_a_config_that_names_none(tmp_path: Path) -> None:
    folder = work(tmp_path)
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "rag-base.jsonl")
    shutil.copy(RAGAS / "rag-raft.jsonl", folder / "rag-raft.jsonl")
    assert init_yes(folder, "--no-import").code == 0
    for name, started in (("rag-base", "2025-03-31T06:56:41Z"), ("rag-raft", "2025-03-31T07:16:07Z")):
        argv = ["ragas", f"{name}.jsonl", "--store", "trace-store", "--run", name, "--metric", "faithfulness",
                "--cut", "0.5", "--below", "--case-column", "case", "--started", started]
        assert import_here(folder, argv).code == 0
    result = doctor(folder)
    assert result.code == 4, result.text
    said = (
        "trace.toml names no store yet, and trace-store beside it holds 2 runs imported from ragas (rag-base, "
        "rag-raft): run the command below to set Trace up with it"
    )
    assert result.out.splitlines()[0] == f"not ready  config fails: {said}", result.out
    assert any(line.strip().startswith("config") and said in line for line in result.out.splitlines()), result.out
    assert result.out.splitlines()[-1] == "next: poisson-trace init --force --store trace-store"
    js = doctor(folder, "--json")
    assert js.json()["next"] == "poisson-trace init --force --store trace-store"


def test_tf15_h10_doctor_names_at_most_three_runs(tmp_path: Path) -> None:
    folder = work(tmp_path)
    assert init_yes(folder, "--no-import").code == 0
    for k, started in enumerate(("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z", "2026-01-05T00:00:00Z")):
        argv = ["table", str(TABLE_A), "--store", "trace-store", "--run", f"t{k}", *COLUMNS, "--started", started]
        assert import_here(folder, argv).code == 0
    first = doctor(folder).out.splitlines()[0]
    assert "holds 5 runs imported from table (" in first and "and 2 more)" in first, first


# ---------- latest and previous, refused so they cannot be copied backwards (5.2, S3) ----------


def test_tf15_h11_the_tie_is_listed_by_name_with_placeholders(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table in (("zz-old", TABLE_A), ("aa-new", TABLE_B)):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", "2026-09-05T18:54:07Z"]
        assert import_here(folder, argv).code == 0
    result = here(folder, ["fix-check", "previous", "latest", "--store", "st", "--event", "missed", "--inputs", "all", "--max-mde", "0.02"])
    line = refusal(result)
    assert line == (
        'error: previous goes by when each run started, and "aa-new" and "zz-old" (listed by name; Trace doesn\'t '
        "know which is older) started at the same moment, so Trace cannot tell which is the older version; you can: "
        "give the two by name, the older version first"
    ), line
    nexts = _next_lines(result.err)
    assert nexts[0] == (
        'poisson-trace fix-check OLDER NEWER --store st --event missed --inputs all --max-mde 0.02  # OLDER and '
        'NEWER are "aa-new" and "zz-old", in the order you know'
    ), nexts
    assert nexts[-1].startswith("poisson-trace runs"), nexts
    assert "the older first" not in result.err


def test_tf15_h12_file_times_name_the_cause_and_offer_started(tmp_path: Path) -> None:
    folder = work(tmp_path)
    # by file time "before" is the older, by name "after" comes first: the listing goes by name
    shutil.copy(TABLE_B, folder / "after.csv")
    shutil.copy(TABLE_A, folder / "before.csv")
    os.utime(folder / "before.csv", (1_700_000_000, 1_700_000_000))
    os.utime(folder / "after.csv", (1_700_000_600, 1_700_000_600))
    assert init_yes(folder, *COLUMNS).code == 0
    result = here(folder, ["fix-check", "previous", "latest", "--inputs", "all", "--max-mde", "0.02"])
    line = refusal(result)
    assert line.startswith(
        'error: previous goes by when each run started, and the starts of "after" and "before" (listed by name; '
        "Trace doesn't know which is older) are their files' modification times, which say when a file was written "
        "or copied, not when the run ran, so Trace cannot tell which is the older version;"), line
    assert line.endswith(
        "or import them again with --started (for example --started 2026-01-31T09:00:00Z, the time that run really "
        "started)"), line
    assert _next_lines(result.err)[0] == (
        'poisson-trace fix-check OLDER NEWER --inputs all --max-mde 0.02  # OLDER and NEWER are "after" and '
        '"before", in the order you know'
    )


def test_tf15_h13_only_the_reserved_word_is_replaced(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table in (("zz-old", TABLE_A), ("aa-new", TABLE_B)):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", "2026-09-05T18:54:07Z"]
        assert import_here(folder, argv).code == 0
    result = here(folder, ["fix-check", "zz-old", "latest", "--store", "st", "--event", "missed", "--inputs", "all", "--max-mde", "0.02"])
    assert result.code == 1, result.text
    assert _next_lines(result.err)[0].startswith("poisson-trace fix-check zz-old NEWER --store st"), result.err


def test_tf15_h14_a_verb_of_one_run(tmp_path: Path) -> None:
    folder = work(tmp_path)
    for name, table in (("zz-old", TABLE_A), ("aa-new", TABLE_B)):
        argv = ["table", str(table), "--store", "st", "--run", name, *COLUMNS, "--started", "2026-09-05T18:54:07Z"]
        assert import_here(folder, argv).code == 0
    result = here(folder, ["where", "latest", "--store", "st", "--event", "missed"])
    line = refusal(result)
    assert line.endswith("give the run you mean by name"), line
    nexts = _next_lines(result.err)
    assert len(nexts) == 1 and nexts[0].startswith("poisson-trace runs"), nexts


def test_tf15_h12_file_times_that_tie_name_the_file_time_cause(tmp_path: Path) -> None:
    """Where both causes hold (two files init imported together, copied in one second), the
    file-time sentence is the one printed, since it names the cause (5.2)."""
    folder = work(tmp_path)
    shutil.copy(TABLE_A, folder / "before.csv")
    shutil.copy(TABLE_B, folder / "after.csv")
    for name in ("before.csv", "after.csv"):
        os.utime(folder / name, (1_700_000_000, 1_700_000_000))
    assert init_yes(folder, *COLUMNS).code == 0
    line = refusal(here(folder, ["fix-check", "previous", "latest", "--inputs", "all", "--max-mde", "0.02"]))
    assert "are their files' modification times" in line and "started at the same moment" not in line, line


def test_tf15_h15_a_word_init_cannot_read_is_left_in_capitals(tmp_path: Path) -> None:
    """A table with no column named case, id, case_id, question_id or sample_id gets CASE."""
    import csv

    folder = work(tmp_path)
    with open(TABLE_A, newline="") as src:
        rows = list(csv.DictReader(src))
    for name in ("x.csv", "y.csv"):
        with open(folder / name, "w", newline="") as out:
            w = csv.DictWriter(out, fieldnames=["task", "outcome"])
            w.writeheader()
            for r in rows[:50]:
                w.writerow({"task": r["case"], "outcome": r["outcome"]})
    shutil.copy(RAGAS / "rag-base.jsonl", folder / "rag-base.jsonl")
    lines = _next_lines(init_yes(folder).err)
    tables = [line for line in lines if line.startswith("poisson-trace import table ")]
    assert len(tables) == 2 and all("--case-column CASE" in line for line in tables), lines
