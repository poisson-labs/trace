"""TF5-50 to TF5-54: the CHANGELOG, including the failure breakdown, the tries with no outcome
and the three readers merged after 0.1.0a1's entry was written.

The shape frozen for 0.1.0: one entry for 0.1.0 at the top, written for a reader who saw no
pre-release, holding a line for every build of the release; under it the three pre-release
entries, as they were published, unchanged.

- TF5-50: the file opens ``# Changelog``; every entry is headed ``## VERSION — `` and a date,
  ``pre-release`` or ``unreleased``, the form the release check reads; the entries are 0.1.0,
  0.1.0a1, 0.1.0rc2, 0.1.0rc1, in that order; 0.1.0's reads ``unreleased`` until the package's
  version is 0.1.0, and a date from then.
- TF5-51: the three pre-release entries are byte for byte main's.
- TF5-52: 0.1.0's entry holds a line (one item of a list) for every build: each of ``BUILDS``,
  by the commands, flags, files and names that line must carry, not by its wording.
- TF5-53: it stands alone: it is sorted under headings, lists the readers as every page does
  (all ten, in order), names the eleven sources' pages, and sends no reader to a pre-release's
  entry to learn what 0.1.0 holds.
- TF5-54: it says what moved for someone who used a pre-release: the examples' store folder,
  and nothing else a command prints.
"""

from __future__ import annotations

import hashlib
import re
import tomllib

import pytest

from tf5_support import CHANGELOG, REPO, WORDS, lists_readers, named, passages, read

VERSION = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
HEAD = re.compile(r"^## (\S+) — (\S+)$", re.M)
PRE_RELEASES = "## 0.1.0a1 — pre-release"
PRE_RELEASES_SHA256 = "5baf008c5026052ff31dc661aaed2552df48480379cf9147d4cdb8ad012530f0"

#: Every build of 0.1.0 that must have a line: what it is, and the patterns one list item must
#: all hold. The first seven are the builds that came after 0.1.0a1.
BUILDS: dict[str, tuple[str, ...]] = {
    "the handover": (r"--out\b", r"handover --check"),
    "the setup agent": (r"init --agent", r"doctor --setup"),
    "the run record": (r"(?i)store descriptor|\.poisson/store\.json", r"(?i)event log|events\.jsonl", r"(?i)produced_by|what produced"),
    "compare refuses a run against itself": (r"`compare`", r"(?i)\bitself\b|\bone run\b|\bthe same run\b"),
    "the failures by kind": (r"(?i)failures? by kind|kinds? of failure", r"`fix-check`", r"`compare`", r"`changes`"),
    "the tries with no outcome": (r"(?i)no outcome",),
    "fix-check when no run failed": (r"`fix-check`", r"(?i)no (?:failed )?run(?:s)? failed|holds? no failed|no failures?|none failed"),
    "the LangSmith reader": (r"LangSmith", r"`langsmith:", r"LANGSMITH_API_KEY"),
    "the Braintrust reader": (r"Braintrust", r"`braintrust:", r"BRAINTRUST_API_KEY"),
    "the Weave reader": (r"Weave", r"`weave:", r"WANDB_API_KEY"),
    "the raw copy of a pull": (r"\.poisson/raw/", r"(?i)no (?:prompt|input|output|text)|left out|without (?:its|their|the) text"),
    "the promptfoo, Inspect and OpenAI Evals readers": (r"promptfoo", r"Inspect", r"OpenAI Evals"),
    "a folder in place of files": (r"(?i)\bfolder\b", r"(?i)\bimport\b"),
    "outcomes joined from outside": (r"--verdicts",),
    "saved verdicts": (r"--save\b",),
    "continuous measures": (r"--measures", r"(?i)tokens", r"(?i)cost"),
    "signals and the failure kinds on every import": (r"(?i)signals", r"(?i)thirteen|13", r"trace\.toml"),
    "the pages and the report": (r"poisson-trace ui", r"report"),
    "the terminal app": (r"`poisson-trace`", r"(?i)terminal app"),
    "the Python API": (r"poisson_trace\.api", r"docs/python\.md"),
    "the clean look": (r"--plain", r"NO_COLOR"),
    "the guided setup": (r"`init`|poisson-trace init", r"trace\.toml", r"`doctor`|poisson-trace doctor"),
    "names and runs": (r"`runs`|poisson-trace runs", r"`name`|poisson-trace name", r"latest", r"previous"),
    "where and compare": (r"`where`", r"`compare`", r"(?i)step"),
    "fix-check and changes": (r"`fix-check`", r"`changes`", r"(?i)control"),
    "the docs of this release": (r"docs/recipes/", r"docs/commands\.md", r"docs/config\.md", r"docs/how-it-decides\.md", r"docs/handover\.md"),
    "the examples' store folder": (r"prove-runs",),
    "the Prove it reads": (r"poisson-prove", r"(?i)exact"),
}


def _entries() -> list[tuple[str, str, str]]:
    text = read(CHANGELOG)
    heads = list(HEAD.finditer(text))
    return [(m.group(1), m.group(2), text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]) for i, m in enumerate(heads)]


def _release() -> str:
    entries = _entries()
    assert entries and entries[0][0] == "0.1.0", "the first entry is 0.1.0's"
    return entries[0][2]


def _items(entry: str) -> list[str]:
    """The entry's list items, each with its continuation lines, as one line of text."""
    out: list[str] = []
    for line in entry.split("\n"):
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.startswith("  ") and line.strip() and out:
            out[-1] += " " + line.strip()
        elif not line.strip() or line.startswith("#"):
            out.append("")
    return [item for item in out if item]


# ---------- TF5-50 ----------


def test_tf5_50_the_shape() -> None:
    text = read(CHANGELOG)
    assert text.startswith("# Changelog\n")
    heads = [line for line in text.split("\n") if line.startswith("## ")]
    assert all(HEAD.fullmatch(line) for line in heads), [line for line in heads if not HEAD.fullmatch(line)]
    entries = _entries()
    assert [version for version, _, _ in entries] == ["0.1.0", "0.1.0a1", "0.1.0rc2", "0.1.0rc1"]
    assert [when for _, when, _ in entries[1:]] == ["pre-release"] * 3
    when = entries[0][1]
    if VERSION == "0.1.0":
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", when), "the release dates its entry"
    else:
        assert when == "unreleased", f"the package is {VERSION}: 0.1.0's entry is not dated yet"


# ---------- TF5-51 ----------


def test_tf5_51_the_pre_release_entries_are_main_s() -> None:
    text = read(CHANGELOG)
    assert PRE_RELEASES in text
    tail = text[text.index(PRE_RELEASES):]
    assert hashlib.sha256(tail.encode("utf-8")).hexdigest() == PRE_RELEASES_SHA256


# ---------- TF5-52 ----------


@pytest.mark.parametrize("build", list(BUILDS))
def test_tf5_52_a_line_for_every_build(build: str) -> None:
    items = _items(_release())
    found = [item for item in items if all(re.search(pattern, item) for pattern in BUILDS[build])]
    assert found, f"0.1.0's entry has no line for {build}: an item holding all of {BUILDS[build]}"


# ---------- TF5-53 ----------


def test_tf5_53_the_entry_stands_alone() -> None:
    entry = _release()
    assert len(re.findall(r"^### ", entry, re.M)) >= 5, "sorted under headings"
    assert len(_items(entry)) >= 30
    assert not re.search(r"(?i)\bsee (?:the entry|0\.1\.0(?:a|rc)\d|below)\b|as (?:in|under) 0\.1\.0(?:a|rc)\d|everything (?:under|below)", entry), \
        "0.1.0's entry says what the release holds itself"
    for word in WORDS:
        assert f"docs/integrations/{word}.md" in entry, word
    assert re.search(r"\bProve\b", entry)


def test_tf5_53_the_entry_lists_the_readers_as_every_page_does() -> None:
    entry = _release()
    listed = [(line, passage) for line, passage in passages(entry) if lists_readers(passage)]
    assert listed, "0.1.0's entry lists the readers"
    for line, passage in listed:
        tools = [word for word in named(passage)]
        assert set(tools) == set(WORDS), f"line {line} of the entry lists {tools}"
        kept = [word for word in tools if word != "table"]
        assert kept == [word for word in WORDS if word in kept], kept


# ---------- TF5-54 ----------


def test_tf5_54_what_moved_for_someone_who_used_a_pre_release() -> None:
    items = [item for item in _items(_release()) if "prove-runs" in item]
    assert items and any("proofload-runs" in item and re.search(r"(?i)\bhelp\b|\bexamples?\b", item) for item in items), \
        "the line says the help examples' store folder was proofload-runs and is prove-runs"
