"""TF24-66 to TF24-71: nothing else moves (the brief's rule 6), and Prove reads every run written.

**TF24-66** Every invocation of ``tf24_support.pin_corpus()`` prints, piped, what main a4bc065
printed, byte for byte: the exit code, stdout and stderr of each step. That is TF19's corpus whole
(every verb's plain and ``--json`` output on each kind of store, each option, the refusals, the
earlier imports, the names, the saves, ``ui`` and ``report``), the top help and the bare options,
``report``'s help and ``report`` on a page already there, and each earlier reader's help under
both spellings. Pinned by ``fixtures/tf24/make_main_pins.py`` on Python 3.12.13 and checked on
3.11 too. One case of main's is left out, because another session is changing it while these
tests are written: a verb asked for an event no run carries.

**TF24-67** The two outputs this pair changes, changed exactly so. The import's help is main's
with one row among its tools, ``langsmith``, and one line among its examples, and nothing else.
The refusal of a tool the install lacks is main's sentence with ``langsmith`` after the last
reader it named, in text and under ``--json``.

**TF24-68** The pages, as main builds them: ``ui`` over TF19's workspace writes every page file
main wrote, byte for byte once the save times are set aside, and no other.

**TF24-69** The terminal app, as main shows it: every screen over that workspace, row for row.

**TF24-70** Prove 0.1.3 reads every run this reader writes, from every export and from a pull:
its manifest, its tally, its rows with their meta, its ``events.jsonl`` in Prove's shape; the
Parquet part has the schema of a run the JUnit reader writes; the run record names the reader
and the files; and Prove's own ``runs`` and ``ui`` list it and build their pages over it, which
needs the rows to share one horizon though they took different numbers of steps.

**TF24-71** The earlier imports stay as they were: TF21-64 and TF21-65 (everything a verb reads
of the eleven earlier imports, and their ``--json``) and the run record's pins stay frozen and
unedited, and the same eleven imports' summaries are main's here too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf19_support import digest, make_world, pages_pins
from tf24_support import (
    CHANGED, EARLIER, ELSEWHERE, EXPORTS, MAIN, PINS, VERSIONS, address, app_pins, by_status, export, imported, ls_argv,
    pin_corpus, pin_slow, pulling, ran_case,
)

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = pin_slow()
HELD = [label for label in CORPUS if label not in PINNED["left_out"]]


# ---------- TF24-66 ----------


def test_tf24_66_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN
    assert set(PINNED["piped"]) | set(PINNED["left_out"]) == set(CORPUS)
    assert not set(PINNED["piped"]) & set(PINNED["left_out"])
    assert PINNED["left_out"] == ["refusal: an unknown event"], PINNED["left_out"]
    assert set(PINNED["changed"]) == set(CHANGED) and not set(CHANGED) & set(CORPUS)
    assert len(PINNED["piped"]) >= 150 and PINNED["pages"] and PINNED["app"]
    for tool in EARLIER:
        assert f"help: import {tool}" in PINNED["piped"] and f"help: alias {tool}" in PINNED["piped"], tool
    assert ELSEWHERE == "unknown event"


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in HELD])
def test_tf24_66_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    got = [[code, digest(out), digest(err)] for code, out, err in ran_case(tmp_path, place, kind, steps)]
    assert got == PINNED["piped"][label], label


def test_tf24_66_a_fast_case_stands_for_each_slow_one() -> None:
    """The slow cases are the larger fixtures and the DeepEval import (TF18's); each kind of
    invocation among them has a case in the pull-request lane."""
    fast = [label for label in HELD if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    for label in SLOW & set(HELD):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


# ---------- TF24-67 ----------


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


def test_tf24_67_the_import_s_help_gains_the_reader_and_its_example_and_nothing_else(tmp_path: Path) -> None:
    (code, out, err), = ran_case(tmp_path, *CHANGED["help: import"])
    (main_code, main_out, main_err), = PINNED["changed"]["help: import"]
    assert (code, err) == (main_code, main_err) == (0, "")
    before, tools, examples = _help_parts(out)
    m_before, m_tools, m_examples = _help_parts(main_out)
    assert [line for line in before if not line.startswith(("usage:", " "))] == [line for line in m_before if not line.startswith(("usage:", " "))]
    assert list(m_tools) == list(EARLIER), m_tools
    # this reader after main's; a reader after it is its own pair's to hold (TF25-67)
    assert list(tools)[:len(EARLIER) + 1] == [*EARLIER, "langsmith"], tools
    assert {name: tools[name] for name in EARLIER} == m_tools
    assert "LangSmith" in tools["langsmith"], tools["langsmith"]
    gained = [line for line in examples if line not in m_examples]
    assert [line for line in examples if line in m_examples] == m_examples
    ours = [line for line in gained if line.strip().startswith("poisson-trace import langsmith ")]
    assert len(ours) == 1 and all(line.strip().startswith("poisson-trace import ") for line in gained), gained
    assert len(gained) == len(tools) - len(EARLIER), gained
    usage = " ".join(" ".join(line for line in before if line.startswith(("usage:", " "))).split())
    m_usage = " ".join(" ".join(line for line in m_before if line.startswith(("usage:", " "))).split())
    assert usage == m_usage


def test_tf24_67_the_refusal_of_an_absent_tool_names_one_reader_more(tmp_path: Path) -> None:
    got = ran_case(tmp_path, *CHANGED["import refusal: a tool not in this install"])
    main = PINNED["changed"]["import refusal: a tool not in this install"]
    said = "error: unknown tool otel; this install reads: deepeval, ragas, table, junit, promptfoo, inspect, openai-evals"
    following = "  next: poisson-trace import --help\n"
    for (code, out, err), (m_code, m_out, m_err) in zip(got, main, strict=True):
        assert (m_code, m_out, m_err) == (1, "", said + "\n" + following)
        # main's sentence with this reader after the last it named; a reader after it is its
        # own pair's to hold (TF25-67)
        assert (code, out) == (1, "") and err.endswith("\n" + following), err
        named = err[: -len("\n" + following)]
        assert named.startswith(said + ", langsmith") and re.fullmatch(r"(?:, [a-z-]+)*", named[len(said + ", langsmith"):]), err


# ---------- TF24-68 ----------


def test_tf24_68_the_pages_as_main_builds_them(tmp_path: Path) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


# ---------- TF24-69 ----------


def test_tf24_69_the_app_as_main_shows_it(tmp_path: Path) -> None:
    got = app_pins(make_world(tmp_path))
    assert sorted(got) == sorted(PINNED["app"])
    for screen, text in PINNED["app"].items():
        assert got[screen] == text, screen


# ---------- TF24-70 ----------


def _prove_reads(root: Path, run: str, missed: int, files: list[str]) -> None:
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
    assert manifest.status == "complete" and manifest.backend == "import:langsmith"
    assert manifest.target_id == "import/langsmith"
    frame = store.read(run, meta=True, trace="full")
    assert len(frame) == 10
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
    assert block["tool"] == "langsmith" and len(block["taxonomy_sha256"]) == 64
    assert [f["name"] for f in block["files"]] == files, block["files"]
    assert block["declared"]["case_from"] == "metadata:ls_example_case"
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


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", EXPORTS)
def test_tf24_70_prove_reads_every_run_the_reader_writes(tmp_path: Path, version: str, kind: str) -> None:
    files = export(version, kind)
    imported(by_status(files, tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", 1, [p.name for p in files])


@pytest.mark.parametrize("version", VERSIONS)
def test_tf24_70_and_every_run_a_pull_writes(tmp_path: Path, version: str) -> None:
    with pulling() as (_, _waits):
        imported(ls_argv(address(version), tmp_path / "st", "r"))
    _prove_reads(tmp_path / "st", "r", {"baseline": 4, "candidate": 2}[version], ["raw.jsonl"])
    from poisson_prove.store import Store

    # the raw copy sits under the store's own folder, which Prove's listing leaves alone
    assert Store(tmp_path / "st").runs() == ["r"]


# ---------- TF24-71 ----------


def test_tf24_71_the_earlier_pins_are_still_held() -> None:
    """TF21-64 and TF21-65 and the run record's unchanged tests are in the suite, unedited: their
    guards hold their digests, and this pair moved neither."""
    import hashlib

    tests = Path(__file__).resolve().parent
    held = {
        "test_tf21_unchanged.py": (tests / "test_tf21_frozen.py").read_text(encoding="utf-8"),
        "test_runrec_unchanged.py": (tests / "test_runrec_frozen.py").read_text(encoding="utf-8"),
    }
    for name, guard in held.items():
        assert hashlib.sha256((tests / name).read_bytes()).hexdigest() in guard, name
