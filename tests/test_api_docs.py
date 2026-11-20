"""TF13-34 to TF13-36: ``docs/python.md``, with examples that run in CI and print what the doc
shows.

TF13-34: the doc has a section ``## api.<name>`` for every public function and none for anything
else; each section holds the function's signature as the code has it (in a ``python`` block of
its own, the first in the section), names what it refuses with (``api.Refusal``), and holds one
example (the section's second ``python`` block) with what it prints under it (a ``text`` block).
The results' methods and attributes are named in it too.

TF13-35: each example, run in a fresh interpreter from inside a fresh workspace (the folder the
doc's opening describes, ``api_support.workspace``), exits 0, writes nothing to stderr and prints
exactly the ``text`` block under it.

TF13-36: the doc says the API is for users and Trace's own command line, not a promise to
Poisson's products, in the sentence ``PRODUCTS`` gives; it is in plain words;
its examples import nothing of the package but ``poisson_trace.api``; and it documents nothing of
``poisson_trace.commands``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from look_support import INTERNAL
from api_support import DOCS, FUNCTIONS, api, doc_sections, fenced, plain_signature, workspace

PRODUCTS = "Poisson's products reach Trace through its command line, not through this API."
WORKSPACE_NAMES = ("`store`", "`tables`", "`jstore`", "`grades.csv`", "`files/`", "`conf/trace.toml`")
RESULT_WORDS = ("to_json()", "to_markdown()", "to_bundle(", "to_svg()", "write_svg(", "exit_code", "notes")


def _text() -> str:
    assert DOCS.is_file(), "docs/python.md"
    return DOCS.read_text(encoding="utf-8")


def _example(name: str) -> tuple[str, str]:
    section = doc_sections(_text())[f"api.{name}"]
    blocks = fenced(section)
    pythons = [i for i, (lang, _) in enumerate(blocks) if lang == "python"]
    assert len(pythons) == 2, (name, "a signature block and one example")
    at = pythons[1]
    assert at + 1 < len(blocks) and blocks[at + 1][0] == "text", (name, "what the example prints, under it")
    return blocks[at][1], blocks[at + 1][1]


# ---------- TF13-34 ----------


def test_tf13_34_a_section_for_every_function_and_nothing_else() -> None:
    sections = doc_sections(_text())
    # build_pages came with the pages (TF18), whose own tests hold its section (TF18-22)
    names = {f"api.{name}" for name in (*FUNCTIONS, "build_pages")}
    assert set(sections) == names, sorted(set(sections) ^ names)


@pytest.mark.parametrize("name", FUNCTIONS)
def test_tf13_34_a_each_section_has_its_signature_its_refusals_and_one_example(name: str) -> None:
    section = doc_sections(_text())[f"api.{name}"]
    blocks = fenced(section)
    assert blocks and blocks[0][0] == "python", name
    assert blocks[0][1].strip() == plain_signature(getattr(api(), name)), (name, blocks[0][1])
    assert "api.Refusal" in section, name
    code, shown = _example(name)
    assert code.startswith("from poisson_trace import api\n"), name
    assert shown.strip(), name


def test_tf13_34_b_the_results_and_the_workspace_are_described() -> None:
    text = _text()
    head = text.split("\n## ", 1)[0]
    for word in WORKSPACE_NAMES:
        assert word in head, word
    for word in RESULT_WORDS:
        assert word in text, word


# ---------- TF13-35 ----------


@pytest.mark.parametrize("name", FUNCTIONS)
def test_tf13_35_each_example_prints_what_the_doc_shows(tmp_path: Path, name: str) -> None:
    code, shown = _example(name)
    work = workspace(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("POISSON", "PYTHON"))}
    env["HOME"] = str(tmp_path / "home")
    proc = subprocess.run([sys.executable, "-c", code], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (name, proc.stderr)
    assert proc.stderr == "", (name, proc.stderr)
    assert proc.stdout == shown, (name, proc.stdout)


# ---------- TF13-36 ----------


def test_tf13_36_the_doc_says_what_the_api_is_for_and_is_in_plain_words() -> None:
    text = _text()
    assert PRODUCTS in " ".join(text.split()), "the API is not a promise to the products"
    found = INTERNAL.findall(text)
    assert not found, found
    assert "poisson_trace.commands" not in text and not re.search(r"\bcommands\.\w", text)
    for name in FUNCTIONS:
        code, _ = _example(name)
        for line in code.splitlines():
            m = re.match(r"\s*(?:from|import)\s+(poisson_trace[\w.]*)", line)
            if m:
                assert m.group(1) == "poisson_trace", (name, line)
                assert re.fullmatch(r"\s*from poisson_trace import api\s*", line), (name, line)
