"""TF25-66 to TF25-71: nothing else moves (the brief's rule 6), and Prove reads every run written.

**TF25-66** Every invocation of ``tf25_pins.pin_corpus()`` prints, piped, what main 729a678
printed, byte for byte: the exit code, stdout and stderr of each step. That is TF24's corpus
whole (every verb's plain and ``--json`` output on each kind of store, each option, the
refusals, the earlier imports, the names, the saves, ``ui`` and ``report``, the top help and the
bare options, each earlier reader's help under both spellings), the one case TF24 left out
while another session was changing it, and what main gained with the LangSmith reader: its
help, its imports of each kind of export, the verbs over two imported versions and over two
folders of trace files, its refusals, and a pull through its own transport. Pinned by
``fixtures/tf25/make_main_pins.py`` on Python 3.12.13 and checked on 3.11 too.

**TF25-67** The outputs this pair changes, changed exactly so. The import's help is main's
with one row among its tools, ``braintrust``, and one line among its examples, and nothing else.
The refusal of a tool the install lacks is main's sentence with ``braintrust`` after the last
reader it named, in text and under ``--json``. ``braintrust`` itself, which main refused as a
tool the install lacks, is a reader.

**TF25-68** The pages, as main builds them: ``ui`` over TF19's workspace writes every page file
main wrote, byte for byte once the save times are set aside, and no other.

**TF25-69** The terminal app, as main shows it: every screen over that workspace, row for row.

**TF25-70** Prove 0.1.3 reads every run this reader writes, from every export and from a pull:
its manifest, its tally, its rows with their meta, its ``events.jsonl`` in Prove's shape; the
Parquet part has the schema of a run the JUnit reader writes; the run record names the reader
and the files; and Prove's own ``runs`` and ``ui`` list it and build their pages over it, the
rows sharing one horizon though they took different numbers of steps.

**TF25-71** The earlier imports stay as they were: TF21-64 and TF21-65, the run record's pins
and TF24's own unchanged tests stay frozen under their guards.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf19_support import digest, make_world, pages_pins
from tf25_pins import CHANGED, EARLIER, INIT, LANGSMITH, MAIN, PINS, app_pins, pin_corpus, pin_slow, ran_case
from tf25_support import (
    EXPORTS, LOOKUP, SPAN_EXPORTS, VERSIONS, address, bt_argv, by_error, export, imported, pulling,
)

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = pin_slow()


# ---------- TF25-66 ----------


def test_tf25_66_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN == "729a678"
    assert set(PINNED["piped"]) == set(CORPUS)
    assert set(PINNED["changed"]) == set(CHANGED) and not set(CHANGED) & set(CORPUS)
    assert set(PINNED["init"]) == set(INIT)
    assert len(PINNED["piped"]) >= 165 and PINNED["pages"] and PINNED["app"]
    for tool in EARLIER:
        assert f"help: import {tool}" in PINNED["piped"] and f"help: alias {tool}" in PINNED["piped"], tool
    assert set(LANGSMITH) <= set(PINNED["piped"])
    # the case TF24 left out while another session was changing it is settled on main, and held
    assert "refusal: an unknown event" in PINNED["piped"]


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_tf25_66_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    from tf5_pins import as_main_printed

    # the docs pair (TF5) renamed the helps' example store and made the top help's list of tools whole;
    # TF5-3 holds those two changes, and this goes on holding every other byte of each help
    # the docs pair (TF5) also lists the bare command's verbs in the top help's order (ruled 2026-11-13, DOC-33);
    # TF5-3 holds that, and this goes on holding every other byte of the refusal
    # the Prove label kinds pair names, in these five, the labels that have no kind (test_pl_unchanged.py, PL-52, holds
    # that); this goes on holding every other byte of them
    from pl_pins import MOVED_SHARED, unmoved

    found = ran_case(tmp_path, place, kind, steps)
    found = unmoved(found) if label in MOVED_SHARED else found
    got = [[code, digest(as_main_printed(label, out)), digest(as_main_printed(label, err) if not label.startswith("help") else err)]
           for code, out, err in found]
    assert got == PINNED["piped"][label], label


def test_tf25_66_a_fast_case_stands_for_each_slow_one() -> None:
    """The slow cases are the larger fixtures and the DeepEval import (TF18's); each kind of
    invocation among them has a case in the pull-request lane."""
    fast = [label for label in CORPUS if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    assert SLOW & set(CORPUS)
    for label in SLOW & set(CORPUS):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


def test_tf25_66_every_pinned_langsmith_case_runs_as_main_ran_it() -> None:
    """The exit codes main gave the LangSmith cases, written out: the pins hold a reader that
    worked, and each refusal is the one meant."""
    codes = {label: [step[0] for step in PINNED["piped"][label]] for label in LANGSMITH}
    assert codes["langsmith: import"] == [0, 0, 1] and codes["langsmith: import json"] == [0, 0]
    assert codes["langsmith: refusals"] == [1, 2, 2, 1, 1]
    assert codes["langsmith: a pull"] == [0, 0, 1, 0, 0]
    assert all(code == 0 for label in ("langsmith: the verbs", "langsmith: the verbs on folders", "langsmith: import by status",
                                       "langsmith: import the page's csv", "langsmith: import a folder of trace files") for code in codes[label])


# ---------- TF25-67 ----------


def _help_parts(text: str) -> tuple[list[str], dict[str, str], list[str]]:
    """The import's help as: every line before ``tools:``, the tools (name to the words beside or
    under it, whitespace collapsed), and the examples."""
    lines = text.splitlines()
    start, end = lines.index("tools:"), lines.index("examples:")
    tools: dict[str, str] = {}
    current = None
    for line in lines[start + 1:end]:
        if not line.strip():
            continue
        if line.startswith("    ") and not line.startswith("     "):
            name, _, words = line.strip().partition("  ")
            current = name.strip()
            tools[current] = words.strip()
        elif line.strip() == "TOOL":
            continue
        else:
            assert current is not None, line
            tools[current] = (tools[current] + " " + line.strip()).strip()
    return lines[:start], tools, [line for line in lines[end + 1:] if line.strip()]


def test_tf25_67_the_import_s_help_gains_the_reader_and_its_example_and_nothing_else(tmp_path: Path) -> None:
    (code, out, err), = ran_case(tmp_path, *CHANGED["help: import"])
    (main_code, main_out, main_err), = PINNED["changed"]["help: import"]
    assert (code, err) == (main_code, main_err) == (0, "")
    before, tools, examples = _help_parts(out)
    m_before, m_tools, m_examples = _help_parts(main_out)
    assert [line for line in before if not line.startswith(("usage:", " "))] == [line for line in m_before if not line.startswith(("usage:", " "))]
    assert list(m_tools) == list(EARLIER), m_tools
    # this reader after main's; a reader after it is its own pair's to hold (TF26-67)
    assert list(tools)[:len(EARLIER) + 1] == [*EARLIER, "braintrust"], tools
    assert {name: tools[name] for name in EARLIER} == m_tools
    assert "Braintrust" in tools["braintrust"], tools["braintrust"]
    gained = [line for line in examples if line not in m_examples]
    assert [line for line in examples if line in m_examples] == m_examples
    ours = [line for line in gained if line.strip().startswith("poisson-trace import braintrust ")]
    assert len(ours) == 1 and all(line.strip().startswith("poisson-trace import ") for line in gained), gained
    assert len(gained) == len(tools) - len(EARLIER), gained
    usage = " ".join(" ".join(line for line in before if line.startswith(("usage:", " "))).split())
    m_usage = " ".join(" ".join(line for line in m_before if line.startswith(("usage:", " "))).split())
    assert usage == m_usage


def test_tf25_67_the_refusal_of_an_absent_tool_names_one_reader_more(tmp_path: Path) -> None:
    got = ran_case(tmp_path, *CHANGED["import refusal: a tool not in this install"])
    main = PINNED["changed"]["import refusal: a tool not in this install"]
    said = "error: unknown tool otel; this install reads: deepeval, ragas, table, junit, promptfoo, inspect, openai-evals, langsmith"
    following = "  next: poisson-trace import --help\n"
    for (code, out, err), (m_code, m_out, m_err) in zip(got, main, strict=True):
        assert (m_code, m_out, m_err) == (1, "", said + "\n" + following)
        # main's sentence with this reader after the last it named; a reader after it is its
        # own pair's to hold (TF26-67)
        assert (code, out) == (1, "") and err.endswith("\n" + following), err
        named = err[: -len("\n" + following)]
        assert named.startswith(said + ", braintrust") and re.fullmatch(r"(?:, [a-z-]+)*", named[len(said + ", braintrust"):]), err


def test_tf25_67_braintrust_is_no_longer_a_tool_the_install_lacks(tmp_path: Path) -> None:
    (m_code, m_out, m_err), = PINNED["changed"]["import refusal: braintrust"]
    assert (m_code, m_out) == (1, "") and m_err.startswith("error: unknown tool braintrust; this install reads: "), m_err
    (code, out, err), = ran_case(tmp_path, *CHANGED["import refusal: braintrust"])
    # the same words are now a command line for the reader, which asks for its two flags
    assert code == 2 and out == "" and "unknown tool" not in err and "--case-from" in err and "--outcome-from" in err, err


# ---------- TF25-68 ----------


def test_tf25_68_the_pages_as_main_builds_them(tmp_path: Path) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


# ---------- TF25-69 ----------


def test_tf25_69_the_app_as_main_shows_it(tmp_path: Path) -> None:
    got = app_pins(make_world(tmp_path))
    assert sorted(got) == sorted(PINNED["app"])
    for screen, text in PINNED["app"].items():
        assert got[screen] == text, screen


# ---------- TF25-70 ----------


def _prove_reads(root: Path, run: str, rows: int, missed: int, files: list[str], shared: bool) -> None:
    import pyarrow.parquet as pq
    from poisson_prove.store import Store

    from poisson_trace.ingest.writer import RECORD_KEYS
    from tf21_support import do_import

    store = Store(root)
    assert run in store.runs()
    junit = root.parent / f"junit-store-{run}"
    do_import("junit-a", junit, "j")
    want_schema = pq.read_schema(next((junit / "j").rglob("*.parquet")))
    manifest = store.manifest(run)
    assert manifest.status == "complete" and manifest.backend == "import:braintrust"
    assert manifest.target_id == "import/braintrust"
    frame = store.read(run, meta=True, trace="full")
    assert len(frame) == rows
    assert json.dumps(store.tally(run).to_dict(), default=str)
    for meta in frame["meta"]:
        assert set(meta["trace_signals"]) == set(RECORD_KEYS)
        assert meta["trace_signals"]["schema"] == "poisson.trace-signals/1"
    assert sum(1 for o in frame["outcome"] if o == "missed") == missed
    part = next((root / run).rglob("*.parquet"))
    assert pq.read_schema(part).remove_metadata() == want_schema.remove_metadata()
    events = [json.loads(line) for line in (root / run / "events.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in events]
    assert kinds[:2] == ["planned", "started"] and kinds[-1] == "finished"
    assert set(kinds[2:-1]) == {"progress"}
    assert all(set(e) == {"schema", "at", "kind", "detail"} and e["schema"] == "poisson.run-event/1" for e in events)
    block = manifest.to_dict()["environment"]["import"]
    assert block["tool"] == "braintrust" and len(block["taxonomy_sha256"]) == 64
    assert [f["name"] for f in block["files"]] == files, block["files"]
    assert block["declared"]["case_from"] == "input"
    descriptor = json.loads((root / ".poisson" / "store.json").read_text(encoding="utf-8"))
    assert descriptor["format"].startswith("poisson.store/"), descriptor
    # Prove's own command lists the run and builds its pages over it, which it refuses for a run
    # whose rows hold different horizons: the rows share one, the most steps any of them took
    from runrec_support import prove

    code, out, err = prove(root, "runs")
    assert code == 0 and run in out, out + err
    code, out, err = prove(root, "ui")
    assert code == 0, out + err
    assert (root / ".poisson" / "ui" / "runs" / f"{run}.html").is_file()
    scored = frame[frame["outcome"].notna()]
    assert len(set(scored["horizon"])) == 1 and float(scored["horizon"].iloc[0]) == float(scored["t"].max())
    if shared:
        assert len(set(scored["t"])) > 1, "the rows took different numbers of steps"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf25_70_prove_reads_every_run_the_reader_writes(tmp_path: Path, version: str, kind: str) -> None:
    files = export(version, kind)
    imported(by_error(files, tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", 10, 1, [p.name for p in files], kind in SPAN_EXPORTS)


@pytest.mark.parametrize("name", LOOKUP)
@pytest.mark.parametrize("kind", ["fetch", "ui-csv"])
def test_tf25_70_and_a_run_of_two_tries_a_case(tmp_path: Path, name: str, kind: str) -> None:
    files = export(name, kind)
    imported(bt_argv(files, tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", 6, 4 if name == "old" else 0, [p.name for p in files], False)


@pytest.mark.parametrize("version", VERSIONS)
def test_tf25_70_and_every_run_a_pull_writes(tmp_path: Path, version: str) -> None:
    with pulling() as (_, _waits):
        imported(by_error(address(version), tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", 10, 1, ["raw.jsonl"], True)
    from poisson_prove.store import Store

    # the raw copy sits under the store's own folder, which Prove's listing leaves alone
    assert Store(tmp_path / "st").runs() == ["r"]


# ---------- TF25-71 ----------


def test_tf25_71_the_earlier_pins_are_still_held() -> None:
    """TF21-64 and TF21-65, the run record's unchanged tests and TF24's are in the suite under
    their guards: each guard holds the digest of the file as it stands."""
    import hashlib

    tests = Path(__file__).resolve().parent
    held = {
        "test_tf21_unchanged.py": (tests / "test_tf21_frozen.py").read_text(encoding="utf-8"),
        "test_runrec_unchanged.py": (tests / "test_runrec_frozen.py").read_text(encoding="utf-8"),
        "test_tf24_unchanged.py": (tests / "test_tf24_frozen.py").read_text(encoding="utf-8"),
        "fixtures/tf24/main-pins.json": (tests / "test_tf24_frozen.py").read_text(encoding="utf-8"),
    }
    for name, guard in held.items():
        assert hashlib.sha256((tests / name).read_bytes()).hexdigest() in guard, name
