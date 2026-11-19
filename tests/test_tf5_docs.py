"""TF5-60 to TF5-69: the docs set.

- TF5-60: ``docs/commands.md`` shows the top help and every verb's help whole, each run, in
  the order the top help lists the verbs; the exit codes, every one, in one table; the
  options every verb shares; and the import's two spellings.
- TF5-61: every flag a tool's import takes is named on that tool's integration page.
- TF5-62: ``docs/config.md`` names every table and every key ``trace.toml`` takes, each under
  its table's heading, the forms a name can take, the keys of an ``[[import]]`` entry and of
  ``trace-names.toml``; it shows a config a command printed and a refusal of a mistyped key.
- TF5-63: ``docs/how-it-decides.md`` names each method the reports rest on, the flags that
  set a size or a seed, and no method the statistics retired; the README keeps none of it.
- TF5-64: ``docs/handover.md``: the bundle file by file, the verbs that write it, the
  check that reads it with its exit codes, what ``result.json`` promises key by key, what is
  never in it, and the HTML page; it shows a bundle written and checked.
- TF5-65: the W&B and MLflow mapping: ``docs/handover.md`` has a
  table whose header names MLflow and W&B, with a row for an imported run's record, its event
  log, and each kind of verdict Trace saves, each row filled in both columns.
- TF5-66: and its test, that every key Trace writes is documented: every key of
  ``handover.json``, ``artifact.json``, the store descriptor, a run's ``produced_by`` and its
  event log, every file of a bundle, every schema Trace stamps, and every key ``PROMISED``
  names of ``result.json``, as Trace writes them today on the four verbs and an import, is
  named in ``docs/handover.md``.
- TF5-67: ``docs/app.md``: the bare command opens the app; every screen, how it is
  reached, and its own keys beside its name, as the key bar writes them; the smallest window; what it never does; and
  what the bare command prints where there is no terminal, run.
- TF5-68: ``CONTRIBUTING.md``: the clone and the dev install, the four lanes by the exact
  marks ``pyproject.toml`` gives them, ``ruff`` and ``mypy``, the two Pythons, the docs
  checker, and that a frozen test file is changed only with its guard's line.
- TF5-69: across the whole set: plain words (the pattern of TF0-21, which holds every page
  under ``docs/`` already, applied to the contributing page's commands alone); no method or
  number the statistics retired; every relative link leads to a file; and every page under
  ``docs/`` but the standards is reached from the README.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf5_support import CONTRIBUTING, DOCS, DOCS_SET, GITHUB, INTEGRATIONS, README, REPO, STANDARDS, VERBS, WORDS, parse, prose, read, rel, sections, trace_commands

COMMANDS, CONFIG, DECIDES, HANDOVER, APP = (DOCS / name for name in ("commands.md", "config.md", "how-it-decides.md", "handover.md", "app.md"))
EXIT_CODES = ("0", "1", "2", "3", "4", "130")
METHODS = ("Cochran–Mantel–Haenszel", "Fisher", "McNemar", "Mantel–Haenszel", "Miettinen–Nurminen", "Benjamini–Hochberg", "log-rank", "bootstrap")
#: TF15-S41's list: the methods and numbers the statistics fixes retired.
RETIRED = ("Sato", "Schoenfeld", "Kaplan", "Greenwood", "could not have detected a rise below", "hazard ratio below 1.457", "--max-mde-hr 1.457",
           "median step:")
PROMISED = ("schema", "verdict", "sentence", "next", "note", "runs", "run", "run_name", "run_id", "cannot_say", "versions")


def _help_shown(text: str) -> dict[tuple[str, ...], str]:
    """Each help the page runs and shows whole: the words after ``poisson-trace`` to the output."""
    blocks = parse(text)[0]
    out = {}
    for at, block in enumerate(blocks):
        following = blocks[at + 1] if at + 1 < len(blocks) else None
        if block.kind == "command" and following is not None and following.kind == "output" and following.code == 0:
            ran = trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n")
            if len(ran) == 1 and ran[0][-1:] == ["--help"]:
                out[tuple(ran[0][:-1])] = following.body
    return out


# ---------- TF5-60 ----------


def test_tf5_60_every_help_is_shown_whole_and_in_order() -> None:
    shown = _help_shown(read(COMMANDS))
    assert () in shown, "the top help"
    order = [key[0] for key in shown if len(key) == 1]
    assert order == list(VERBS), order
    listed = re.findall(r"^    ([a-z-]+)\s", shown[()].split("\nverbs:\n")[1], re.M)
    assert [verb for verb in listed if verb in VERBS] == list(VERBS), "the order is the top help's own"


def test_tf5_60_the_top_help_shown_is_the_one_printed() -> None:
    """The page follows the top help. The page is one of the longer
    ones, run whole in the slow lane (TF5-14); this holds its first block in the fast one."""
    from tf0_support import trace

    ran = trace(["--help"])
    assert ran.code == 0, ran.text
    assert _help_shown(read(COMMANDS))[()].strip("\n") == ran.out.strip("\n")


def test_tf5_60_each_verb_has_its_section() -> None:
    titles = [title for title in sections(read(COMMANDS))]
    at = []
    for verb in VERBS:
        mine = [i for i, title in enumerate(titles) if re.search(rf"`(?:poisson-trace )?{re.escape(verb)}`", title)]
        assert len(mine) == 1, f"one section headed with `{verb}`"
        at.append(mine[0])
    assert at == sorted(at)


def test_tf5_60_the_exit_codes_in_one_table() -> None:
    text = read(COMMANDS)
    tables = [[row for row in passage.split("\n") if row.startswith("|")] for passage in re.split(r"\n\s*\n", prose(text))]
    found = [rows for rows in tables if rows and {cell.strip(" `|") for cell in (row.split("|")[1] for row in rows)} >= set(EXIT_CODES)]
    assert len(found) == 1, "one table with a row for each of 0, 1, 2, 3, 4 and 130"
    for row in found[0][2:]:
        assert len([cell for cell in row.strip("|").split("|") if cell.strip()]) >= 2, row


def test_tf5_60_what_every_verb_shares() -> None:
    said = prose(read(COMMANDS))
    for word in ("`--json`", "`--plain`", "`--debug`", "`--version`", "`--config`", "`--store`", "`--event`", "`NO_COLOR`", "`trace.toml`",
                 "`poisson-trace-import`", "latest", "previous", "`#1`"):
        assert word in said, word
    assert f"`{'`, `'.join(WORDS[:2])}`" in said or all(f"integrations/{word}.md" in read(COMMANDS) for word in WORDS)


# ---------- TF5-61 ----------


@pytest.mark.parametrize("page", INTEGRATIONS, ids=[page.stem for page in INTEGRATIONS])
def test_tf5_61_every_flag_of_a_tool_s_import_is_on_its_page(page: Path) -> None:
    from tf0_support import trace

    ran = trace(["import", page.stem, "--help"])
    assert ran.code == 0, ran.text
    flags = sorted(set(re.findall(r"(?<![\w-])--[a-z][a-z-]+(?![\w-])", ran.out)) - {"--help", "--version", "--plain", "--json", "--debug", "--config"})
    text = read(page)
    missing = [flag for flag in flags if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text)]
    assert missing == [], f"{page.name} never names {missing}"


# ---------- TF5-62 ----------


def test_tf5_62_every_table_and_key_of_the_config() -> None:
    from poisson_trace import config

    text = read(CONFIG)
    by_title = {**sections(text, 2), **sections(text, 3)}
    for table, keys in config._SETTINGS.items():
        mine = [body for title, body in by_title.items() if f"[{table}]" in title]
        assert mine, f"no section headed with `[{table}]`"
        for key in keys:
            assert f"`{key}`" in mine[0], f"[{table}] {key}"
    entry = [body for title, body in by_title.items() if "[[import]]" in title]
    assert entry and all(f"`{key}`" in entry[0] for key in config._ENTRY)
    for word in ("`version`", "[signals.budgets]", "[[taxonomy.rules]]", "`trace-names.toml`", "`poisson-trace name`", "`poisson-trace doctor`",
                 *[f"`{form}`" for form in config.FORMS]):
        assert word in text, word
    for budget in ("max_total_tokens",):
        assert f"`{budget}`" in text, budget


def test_tf5_62_the_config_page_shows_a_config_and_a_refusal() -> None:
    blocks = parse(read(CONFIG))[0]
    shown = [block for block in blocks if block.kind in ("output", "excerpt")]
    assert any(block.code == 0 and "[store]" in block.body and "[events]" in block.body for block in shown), "a trace.toml a command printed"
    assert any(block.code == 1 and block.body.startswith("error: ") and "did you mean" in block.body for block in shown), "a mistyped key, refused"


# ---------- TF5-63 ----------


def test_tf5_63_how_it_decides_names_the_methods() -> None:
    text = " ".join(read(DECIDES).split())
    for method in METHODS:
        assert method in text, method
    for flag in ("--max-mde", "--max-mde-hr", "--alpha", "--boot", "--seed", "--inputs", "--failing-from"):
        assert flag in text, flag
    for verb in ("where", "compare", "fix-check", "changes"):
        assert f"`{verb}`" in text, verb
    for verdict in ("*different*", "*no significant difference*", "*too small to tell*"):
        assert verdict in text, verdict


# ---------- TF5-64 ----------


def test_tf5_64_the_handover_page_names_the_bundle() -> None:
    text = read(HANDOVER)
    for word in ("`result.json`", "`report.md`", "`table.parquet`", "`artifact.json`", "`handover.json`", "`charts/curve.svg`", "`report.html`",
                 "`--out`", "`--force`", "`--save`", "poisson-trace handover --check", "`poisson-trace report`", "`poisson-trace ui`",
                 "`where`", "`compare`", "`fix-check`", "`changes`", "sha256", "400"):
        assert word in text, word
    said = prose(text)
    assert any(re.search(r"(?i)\bprompt\b", passage) and re.search(r"(?i)\bkey\b", passage) and re.search(r"(?i)absolute path", passage)
               and re.search(r"(?i)\bnothing\b|\bno\b|\bnever\b", passage) for passage in re.split(r"\n\s*\n", said)), "what is never in a bundle"
    assert re.search(r"(?i)breaking change", said) and "CHANGELOG" in said, "how the promise is kept"
    for code in ("0", "1", "4"):
        assert re.search(rf"(?i)exit(?:s| code)? `?{code}`?\b", said), f"the check's exit {code}"


def test_tf5_64_the_handover_page_shows_a_bundle_written_and_checked() -> None:
    text = read(HANDOVER)
    ran = trace_commands(text)
    assert any("--out" in command for command in ran), "a verb writing a bundle"
    assert any(command[:2] == ["handover", "--check"] for command in ran), "the check reading it"
    blocks = parse(text)[0]
    assert any(block.kind in ("output", "excerpt") and block.code == 0 and "handover.json" in block.body and "result.json" in block.body
               for block in blocks), "the bundle's files, listed by a command"


# ---------- TF5-65 ----------


def test_tf5_65_the_mapping_to_mlflow_and_wandb() -> None:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in read(HANDOVER).splitlines() if line.strip().startswith("|")]
    headers = [i for i, row in enumerate(rows) if "MLflow" in row and "W&B" in row]
    assert headers, "no table names MLflow and W&B"
    header = rows[headers[0]]
    body = [row for row in rows[headers[0] + 2:] if len(row) == len(header)]
    m, w = header.index("MLflow"), header.index("W&B")
    for kind in ("run record", "events.jsonl", "where", "compare", "fix-check", "changes", "chart"):
        found = [row for row in body if kind in row[0]]
        assert found and len(found[0][m]) > 10 and len(found[0][w]) > 10, (kind, body)
    assert re.search(r"(?i)no exporter is built|Trace exports? nothing|builds? no exporter", prose(read(HANDOVER))), "the mapping is a mapping, not a feature"


# ---------- TF5-66 ----------


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for inner in value.values() for key in _keys(inner)}
    if isinstance(value, list):
        return {key for inner in value for key in _keys(inner)}
    return set()


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """Everything Trace writes beside a result, on the four verbs and an import, by where."""
    import shutil

    from tf0_support import trace
    from tf21_support import INGEST

    tmp = tmp_path_factory.mktemp("tf5-keys")
    tau, cs, he = tmp / "tau2", tmp / "cs", tmp / "he"
    shutil.copytree(REPO / "tests" / "fixtures" / "tau2", tau)
    shutil.copytree(REPO / "tests" / "fixtures" / "cs", cs)
    a, b = "tau2-airline 2026-09-15 a", "tau2-airline 2026-09-15 b"
    verbs = {
        "where": ["where", "cs_agents 2026-09-25 a", "--store", str(cs), "--event", "unresolved"],
        "compare": ["compare", a, b, "--store", str(tau), "--event", "unsolved", "--max-mde-hr", "1.5"],
        "fix-check": ["fix-check", a, b, "--store", str(tau), "--event", "unsolved", "--inputs", "all", "--max-mde", "0.1"],
        "changes": ["changes", a, b, "--store", str(tau), "--event", "unsolved"],
    }
    out: dict[str, set[str]] = {"files": set(), "schemas": set(), "handover.json": set(), "artifact.json": set(), "result.json": set()}
    for verb, argv in verbs.items():
        bundle = tmp / f"bundle-{verb}"
        ran = trace([*argv, "--out", str(bundle)])
        assert ran.code == 0, ran.text
        out["files"] |= {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
        handover = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
        artifact = json.loads((bundle / "artifact.json").read_text(encoding="utf-8"))
        result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
        out["handover.json"] |= _keys(handover)
        out["artifact.json"] |= set(artifact) | _keys(artifact["files"]) | _keys(artifact["summary"]) | _keys(artifact["inputs"])
        out["result.json"] |= {key for key in PROMISED if key in result or key in _keys(result.get("runs", result.get("run", {})))}
        out["schemas"] |= {handover["schema"], result["schema"], artifact["format"], *[f["schema"] for f in artifact["files"] if f.get("schema")]}
        assert trace(["handover", "--check", str(bundle)]).code == 0
    ran = trace(["import", "junit", str(INGEST / "junit" / "humaneval-a.xml"), "--store", str(he), "--run", "old", "--case", "name"])
    assert ran.code == 0, ran.text
    descriptor = json.loads((he / ".poisson" / "store.json").read_text(encoding="utf-8"))
    manifest = json.loads((he / "old" / "manifest.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (he / "old" / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    out["store.json"] = _keys(descriptor)
    out["produced_by"] = {"produced_by"} | (_keys(manifest["produced_by"]) - set(manifest["produced_by"].get("options", {})))
    out["event kinds"] = {event["kind"] for event in events}
    out["event keys"] = {key for event in events for key in _keys(event)}
    out["schemas"] |= {descriptor["format"], *{event["schema"] for event in events}}
    out["files"] |= {".poisson/store.json", "events.jsonl", "manifest.json"}
    return out


def test_tf5_66_what_trace_writes_is_what_the_test_reads(written: dict[str, set[str]]) -> None:
    assert {"handover.json", "artifact.json", "result.json", "report.md", "table.parquet", "charts/curve.svg", "charts/curve.json"} <= written["files"]
    assert written["handover.json"] == {"schema", "verb", "files", "name", "sha256", "bytes", "versions", "trace", "prove", "written_at", "runs",
                                        "run_id", "run_name", "store"}
    assert {"tool", "version", "reader", "from", "name", "sha256", "options"} <= written["produced_by"]
    assert written["event kinds"] == {"planned", "started", "progress", "finished"}
    assert {"files", "reader", "rows", "run_id"} <= written["event keys"], "the planned event's detail (RR2)"
    assert {"poisson-trace.handover/1", "poisson.artifact/1", "poisson.store/1", "poisson.run-event/1"} <= written["schemas"] | {"poisson.artifact/1"}
    assert set(PROMISED) - {"run"} <= written["result.json"] | {"run"}


#: Where each thing Trace writes is documented: the word that must stand in the same row of a
#: table, or the same paragraph, as the keys.
ANCHORS = {"handover.json": "`handover.json`", "artifact.json": "`artifact.json`", "store.json": "store.json`", "produced_by": "`produced_by`",
           "event kinds": "`events.jsonl`", "event keys": "`events.jsonl`"}


def _units(text: str) -> list[str]:
    """The page's units outside its blocks: each row of a table, and each paragraph."""
    out: list[str] = []
    for passage in re.split(r"\n\s*\n", prose(text)):
        rows = [line for line in passage.split("\n") if line.startswith("|")]
        out.extend(rows if rows else [passage])
    return out


def _named_in(unit: str) -> set[str]:
    named = set(re.findall(r"`([^`\n]+)`", unit))
    return named | {part for word in named for part in re.split(r"[.\s/]", word)}


def test_tf5_66_every_key_trace_writes_is_documented(written: dict[str, set[str]]) -> None:
    """Each key beside the name of the file or the record it belongs to: in that row of the
    files' table, or in that paragraph. A key named somewhere else on the page documents
    another file's key of the same name."""
    text = read(HANDOVER)
    units = _units(text)
    missing: dict[str, list[str]] = {}
    for where, keys in written.items():
        if where in ANCHORS:
            mine = [unit for unit in units if ANCHORS[where] in unit]
            assert mine, f"nothing on the page names {ANCHORS[where]}"
            named = set().union(*[_named_in(unit) for unit in mine])
        else:
            named = _named_in(prose(text))
        missing[where] = sorted(key for key in keys if key not in named)
    assert not any(missing.values()), {where: keys for where, keys in missing.items() if keys}


# ---------- TF5-67 ----------


def test_tf5_67_the_app_page() -> None:
    from tf19_support import NAV_KEYS, OWN, SHARED

    text = read(APP)
    said = prose(text)
    assert "`poisson-trace`" in said and re.search(r"(?i)terminal", said)
    # each number with its unit (the unit rule, TF5-38): "80 × 24" names neither
    assert re.search(r"\b80 columns\b[^.]*\b24 (?:rows|lines)\b", " ".join(said.split())), "the smallest window"
    for key in SHARED:
        assert f"`{key}`" in said, f"the key {key}"
    units = _units(text)
    for screen, keys in OWN.items():
        words = screen.split()
        mine = [unit for unit in units if all(re.search(rf"(?i)(?<![\w-]){re.escape(word)}(?![\w-])", unit) for word in words)
                and all(f"`{key}`" in unit for key in keys)]
        assert mine, f"no row or paragraph names the screen {screen!r} with its keys {keys}"
    for screen in NAV_KEYS:
        assert re.search(rf"(?i)\b{re.escape(screen.split()[-1] if screen.startswith('verdict') else screen)}\b", said), screen
    for word in ("`NO_COLOR`", "`--plain`", "`--config`", "`--store`", "Ctrl-C"):
        assert word in said, word
    assert re.search(r"(?i)runs nothing|makes no model call|calls no model", said) and re.search(r"(?i)every (?:fact|number)", said), \
        "what it never does, and that a screen holds the plain command's facts"


def test_tf5_67_the_app_page_shows_the_bare_command_with_no_terminal() -> None:
    blocks = parse(read(APP))[0]
    for at, block in enumerate(blocks):
        if block.kind == "command" and trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n") == [[]]:
            following = blocks[at + 1] if at + 1 < len(blocks) else None
            assert following is not None and following.kind in ("output", "excerpt") and following.code == 2
            assert "no verb was given" in following.body
            return
    raise AssertionError("docs/app.md never runs the bare command where there is no terminal")


# ---------- TF5-68 ----------


def test_tf5_68_the_contributing_page() -> None:
    text = read(CONTRIBUTING)
    for word in ("git clone https://github.com/poisson-labs/trace", "pip install -e '.[dev]'", '-m "not math and not lane_j and not slow"', "-m math",
                 "-m slow", "-m lane_j", "ruff check src tests", "mypy --strict", "3.11", "3.12", "tools/docs_check.py", "tests/fixtures/SHA256SUMS",
                 "PROVENANCE.md", "docs/cli-look.md", "docs/repo-hygiene.md"):
        assert word in text, word
    assert re.search(r"(?i)frozen", text) and re.search(r"_frozen\.py", text), "a frozen test file moves only with its guard's line"
    assert re.search(r"(?i)no (?:paid|network)|never (?:calls|reaches)", text), "the suite calls no service"
    blocks = parse(text)[0]
    assert blocks and all(block.kind in ("skip", "data") for block in blocks), "its commands are a contributor's: shown, not run by the docs check"


# ---------- TF5-69 ----------


def _all_pages() -> list[Path]:
    return [README, CONTRIBUTING, *sorted(p for p in DOCS.rglob("*.md") if p.name not in STANDARDS)]


@pytest.mark.parametrize("page", [DOCS / name for name in DOCS_SET] + [CONTRIBUTING], ids=[*DOCS_SET, "CONTRIBUTING.md"])
def test_tf5_69_no_page_shows_a_retired_method_or_number(page: Path) -> None:
    text = read(page)
    for word in RETIRED:
        assert word not in text, f"{rel(page)}: {word}"


def test_tf5_69_every_relative_link_leads_to_a_file() -> None:
    for page in _all_pages():
        if page == README:
            continue
        for link in re.findall(r"\]\(([^)\s]+)\)", prose(read(page))):
            if link.startswith(("https://", "http://", "mailto:", "#")):
                if link.startswith(GITHUB):
                    assert (REPO / link[len(GITHUB):].split("#")[0]).exists(), f"{rel(page)}: {link}"
                continue
            target = (page.parent / link.split("#")[0]).resolve()
            assert target.exists(), f"{rel(page)}: {link} leads nowhere"


def test_tf5_69_every_page_is_reached_from_the_readme() -> None:
    text = read(README)
    for page in _all_pages():
        if page != README:
            assert f"{GITHUB}{rel(page)}" in text, f"the README never links {rel(page)}"


@pytest.mark.parametrize("word", ["run", "store", "case", "input", "event"])
def test_tf5_69_each_of_the_five_words_is_explained(word: str) -> None:
    """The five words "run", "store", "case", "input" and "event" are each explained where first
    used. Held as one sentence of the README that says what the word is ("A run is ...")."""
    said = " ".join(prose(read(README)).split())
    article = "an" if word[0] in "aei" else "a"
    assert re.search(rf"(?i)\b{article} {word}(?:, [^.]*,)? is\b", said), f"the README never says what {article} {word} is"


def test_tf5_69_the_two_standards_are_as_main_has_them() -> None:
    import hashlib

    got = {name: hashlib.sha256((DOCS / name).read_bytes()).hexdigest() for name in STANDARDS}
    assert got == {"cli-look.md": "92e71488c2824c056252be9a7b340e7fc138d15359fbcb7431bcfc6fa267d85f", "repo-hygiene.md": "802d0ff86e6a1b269c37281de749e57b9c5b069cd425aa91eed04edeba604131"}
