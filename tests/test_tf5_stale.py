"""TF5-30 to TF5-36: nothing stale.

- TF5-30: no page says Trace is at a version it is not. Every version of Trace a page writes
  (``poisson-trace==X``, ``poisson-trace X``, ``poisson_trace-X``, "Trace X") is the version
  the package carries; the placeholder ``0.0.1`` is named only where a sentence calls it a
  placeholder; and no earlier pre-release's number is written outside the CHANGELOG.
- TF5-31: while the package's version is a pre-release the README says so, in a section whose
  title says pre-release and whose install line names that version exactly; once it is not,
  the README says pre-release nowhere and pins no version. The first screen's and the Install
  section's line is ``pip install poisson-trace`` either way.
- TF5-32: no page names ``proofload`` where Prove is meant: the word is in no page, the agent
  skill or the package's own text, but in what a command run on the page printed; the
  examples' store folder is ``prove-runs``.
- TF5-33: no page says a built reader is still to come, and what is said to be coming names
  none of the ten tools.
- TF5-34: no page says an imported run carries no traces, or that ``where`` and ``compare``
  read Prove's runs alone. They read any run that carries traces:
  the three services' API answers and pulls do, their summary and page exports do not.
- TF5-35: that fact, held on the committed captures whatever the pages say: for each of the
  three services, ``where`` places failures on steps and ``compare`` answers on the runs
  imported from its API answers, and on the runs imported from its page or summary export
  ``where`` says the run has no steps and ``compare`` refuses, naming the fix check.
- TF5-36: and shown: a page that runs shows ``where`` reading a run imported from a service's
  API answer, exit 0, and the README says in one passage what ``where`` and ``compare`` need
  (a run that carries traces) with the three services named beside Prove.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from tf5_support import API_TOOLS, CHANGELOG, DOCS, README, RECIPES, REPO, expected_pages, named, parse, passages, prose, read, recipe, rel, trace_commands

SKILL = REPO / "src" / "poisson_trace" / "skills" / "poisson-trace-setup" / "SKILL.md"
PAGES = [*expected_pages(), SKILL]
IDS = [rel(page) for page in PAGES]
VERSION = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
PRE = re.search(r"(a|b|rc)\d+$", VERSION) is not None
_V = r"(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)"
TRACE_VERSION = re.compile(rf"poisson-trace(?:==| ){_V}|poisson_trace-{_V}|\bTrace(?:'s)? `?{_V}`?")
EARLIER = re.compile(r"0\.1\.0rc\d|0\.1\.0b\d")
COMING = re.compile(r"(?i)\b(?:is|are|still) (?:to come|coming)\b|\bcoming (?:soon|later|next)\b|\bnot yet (?:built|read|supported)\b|\bin a later release\b"
                    r"|\bnext slice\b|\bwill (?:read|support|come)\b|^#+ What is coming", re.M)
NO_TRACES = (
    r"(?i)imported runs? (?:carr(?:y|ies)|has|have|holds?) (?:none|no (?:traces?|steps?))",
    r"(?i)traces?, which an imported run",
    r"(?i)`?where`? and `?compare`? (?:read |on |work on |need )?(?:only )?Prove's (?:stored )?runs(?: only| alone)?[,.;]",
    r"(?i)only Prove's (?:stored )?runs carry traces",
    r"(?i)(?:only|alone) (?:on|for) (?:runs )?Prove stored",
)


def _shown(text: str) -> str:
    """What the page's run commands printed, as the page shows it."""
    return "\n".join(block.body for block in parse(text)[0] if block.kind in ("output", "excerpt"))


def _said(text: str) -> str:
    """Everything of a page but what its run commands printed."""
    return prose(text) + "\n" + "\n".join(block.body for block in parse(text)[0] if block.kind not in ("output", "excerpt"))


# ---------- TF5-30 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_30_every_version_of_trace_a_page_writes_is_the_package_s(page: Path) -> None:
    text = read(page)
    for found in TRACE_VERSION.finditer(text):
        version = next(group for group in found.groups() if group)
        if version == "0.0.1":
            continue
        assert version == VERSION or (not PRE and version == VERSION.split("a")[0]), f"{rel(page)}: {found.group(0)}; the package is {VERSION}"
    assert not EARLIER.search(text), f"{rel(page)}: names an earlier pre-release"


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_30_the_placeholder_is_named_only_as_a_placeholder(page: Path) -> None:
    for line, passage in passages(read(page)):
        if re.search(r"(?<![\d.])0\.0\.1(?![\d.])", passage):
            assert "placeholder" in passage, f"{rel(page)}:{line}: 0.0.1"
    for block in parse(read(page))[0]:
        assert not re.search(r"(?<![\d.])0\.0\.1(?![\d.])", block.body), f"{rel(page)}:{block.line}: 0.0.1 in a block"


def test_tf5_30_the_changelog_s_newest_entry_is_not_behind_the_package() -> None:
    entries = re.findall(rf"^## {_V} — ", read(CHANGELOG), re.M)
    assert entries and VERSION in entries, (VERSION, entries)


# ---------- TF5-31 ----------


def test_tf5_31_the_readme_says_pre_release_exactly_while_the_package_is_one() -> None:
    text = read(README)
    titles = [line for line in text.split("\n") if re.match(r"^#{2,3} ", line) and re.search(r"(?i)pre-release", line)]
    pinned = re.findall(r"pip install poisson-trace==(\S+)", text)
    if PRE:
        assert len(titles) == 1, "one section says this is a pre-release"
        assert pinned and set(pinned) == {VERSION}, pinned
        section = text.split(titles[0], 1)[1]
        section = re.split(rf"^#{{1,{titles[0].index(' ')}}} ", section, maxsplit=1, flags=re.M)[0]
        assert f"pip install poisson-trace=={VERSION}" in section and "placeholder" in section, "the line that installs it, and why the plain line does not"
    else:
        assert not titles and not pinned and not re.search(r"(?i)pre-release", prose(text)), "0.1.0 is not a pre-release"


def test_tf5_31_the_plain_install_line_is_the_first_screen_s() -> None:
    text = read(README)
    first = text.split("\n---\n")[0]
    assert re.search(r"^\s*pip install poisson-trace$", first, re.M), "the first screen installs with the one plain line"


# ---------- TF5-32 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_32_no_page_names_proofload(page: Path) -> None:
    said = _said(read(page))
    assert "proofload" not in said.lower(), f"{rel(page)}: names proofload"


def test_tf5_32_the_examples_store_folder_is_the_published_prove_s() -> None:
    for page in PAGES:
        assert "proofload-runs" not in read(page), rel(page)
    assert "prove-runs" in read(README) or "prove-runs" in read(recipe("check-a-fix.md")) or "prove-runs" in read(recipe("first-look.md"))
    for path in sorted((REPO / "src" / "poisson_trace").rglob("*")):
        if path.is_file() and path.suffix in (".py", ".md", ".toml"):
            assert "proofload" not in path.read_text(encoding="utf-8"), path.name


# ---------- TF5-33 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_33_no_built_reader_is_said_to_be_coming(page: Path) -> None:
    text = read(page)
    for line, passage in passages(text):
        if COMING.search(passage):
            assert not named(passage), f"{rel(page)}:{line}: says a reader is to come and names {named(passage)}"
    for title, body in {**_titled(text, 2), **_titled(text, 3)}.items():
        if re.search(r"(?i)coming|not (?:yet )?built|later", title):
            assert not named(prose(body)), f"{rel(page)}: '{title}' names {named(prose(body))}"
    assert not re.search(r"(?i)what trace does not read", text), f"{rel(page)}: the section that said LangSmith was the next slice"


def _titled(text: str, level: int) -> dict[str, str]:
    from tf5_support import sections

    return sections(text, level)


# ---------- TF5-34 ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_tf5_34_no_page_says_only_prove_s_runs_carry_traces(page: Path) -> None:
    said = " ".join(_said(read(page)).split())
    for pattern in NO_TRACES:
        found = re.search(pattern, said)
        assert found is None, f"{rel(page)}: {found.group(0) if found else ''}"


# ---------- TF5-35 ----------

_FLAGS = {
    "langsmith": ["--case-from", "example", "--outcome-from", "feedback:exact", "--cut", "0.5", "--below"],
    "braintrust": ["--case-from", "input", "--outcome-from", "score:exact", "--cut", "0.5", "--below"],
    "weave": ["--case-from", "example", "--outcome-from", "score:exact", "--cut", "0.5", "--below"],
}
#: Per service: its API answers of the two versions (which carry the steps), and its page or
#: summary export of the two (which do not), each with the flags that export needs.
_API = {
    "langsmith": (("langsmith/api/baseline.runs-v2.json", "langsmith/api/baseline.feedback.json"),
                  ("langsmith/api/candidate.runs-v2.json", "langsmith/api/candidate.feedback.json")),
    "braintrust": (("braintrust/api/slice-baseline.fetch.json",), ("braintrust/api/slice-candidate.fetch.json",)),
    "weave": (("weave/api/trace-fixture-slice-baseline.jsonl",), ("weave/api/trace-fixture-slice-candidate.jsonl",)),
}
_PAGE = {
    "langsmith": ((("langsmith/ui/trace-fixture-baseline-bbb64b8e.csv",), ["--case-from", "input", "--outcome-from", "feedback:exact", "--cut", "0.5", "--below"]),
                  (("langsmith/ui/trace-fixture-candidate-7e3f7200.csv",), ["--case-from", "input", "--outcome-from", "feedback:exact", "--cut", "0.5", "--below"])),
    "braintrust": ((("braintrust/ui/slice-baseline.json",), _FLAGS["braintrust"]), (("braintrust/ui/slice-candidate.json",), _FLAGS["braintrust"])),
    "weave": ((("weave/ui/predict-and-score.json",), ["--evaluation", "trace-fixture-slice-baseline", *_FLAGS["weave"]]),
              (("weave/ui/predict-and-score.json",), ["--evaluation", "trace-fixture-slice-candidate", *_FLAGS["weave"]])),
}


def _imported(tmp: Path, tool: str, files: tuple[str, ...], flags: list[str], run: str) -> Path:
    from tf0_support import trace
    from tf21_support import INGEST

    store = tmp / "st"
    ran = trace(["import", tool, *[str(INGEST / f) for f in files], "--store", str(store), "--run", run, *flags])
    assert ran.code == 0, ran.text
    return store


@pytest.mark.parametrize("tool", API_TOOLS)
def test_tf5_35_where_and_compare_read_a_service_s_api_answers(tmp_path: Path, tool: str) -> None:
    from tf0_support import trace

    old, new = _API[tool]
    store = _imported(tmp_path, tool, old, _FLAGS[tool], "old")
    _imported(tmp_path, tool, new, _FLAGS[tool], "new")
    where = trace(["where", "old", "--store", str(store), "--event", "missed"])
    assert where.code == 0 and "## Where they die, by kind of step" in where.out, where.text
    compare = trace(["compare", "old", "new", "--store", str(store), "--event", "missed", "--max-mde-hr", "1.5"])
    assert compare.code == 0 and "\n# Poisson Trace · compare" in compare.out, compare.text


@pytest.mark.parametrize("tool", API_TOOLS)
def test_tf5_35_a_page_or_summary_export_carries_no_steps(tmp_path: Path, tool: str) -> None:
    from tf0_support import trace

    (old, old_flags), (new, new_flags) = _PAGE[tool]
    store = _imported(tmp_path, tool, old, old_flags, "old")
    _imported(tmp_path, tool, new, new_flags, "new")
    where = trace(["where", "old", "--store", str(store), "--event", "missed"])
    assert "## Where they die, by kind of step" not in where.out, where.text
    compare = trace(["compare", "old", "new", "--store", str(store), "--event", "missed", "--max-mde-hr", "1.5"])
    assert compare.code == 1 and "fix-check" in compare.err, compare.text
    check = trace(["fix-check", "old", "new", "--store", str(store), "--event", "missed", "--inputs", "all", "--max-mde", "0.5"])
    assert check.code == 0, check.text


# ---------- TF5-36 ----------


def test_tf5_36_a_page_shows_where_reading_a_service_s_run() -> None:
    shown = []
    for name, source in RECIPES.items():
        if source in API_TOOLS:
            blocks = parse(read(recipe(name)))[0]
            for at, block in enumerate(blocks):
                if block.kind == "command" and any(command[:1] == ["where"] for command in trace_commands("<!-- command -->\n```\n" + block.body + "\n```\n")):
                    following = blocks[at + 1] if at + 1 < len(blocks) else None
                    if following is not None and following.kind in ("output", "excerpt") and following.code == 0:
                        shown.append(source)
    assert set(shown) == set(API_TOOLS), f"where is shown on a run imported from: {sorted(set(shown))}"


def test_tf5_36_the_readme_says_what_where_and_compare_need() -> None:
    found = [passage for _, passage in passages(read(README))
             if "`where`" in passage and "`compare`" in passage and re.search(r"(?i)\btraces?\b|\bsteps\b", passage)
             and re.search(r"\bProve\b", passage) and all(re.search(name, passage) for name in ("LangSmith", "Braintrust", "Weave"))]
    assert found, "no passage of the README says where and compare read any run that carries traces, naming Prove and the three services"
    assert any(re.search(r"(?i)\b(?:page|summary|download|CSV)\b", passage) for passage in found), "and that their page and summary exports carry none"
    assert (DOCS / "commands.md").is_file()
