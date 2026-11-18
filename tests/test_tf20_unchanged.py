"""TF20-80 to TF20-91: nothing else moves (the brief's rule 8). The pins are main 901e845's,
taken by ``fixtures/tf20/make_main_pins.py`` before anything of TF20 was written, on Python
3.12.13, twice, the two takes the same byte for byte, and once on 3.11.15, the same but for the
Python's version (see ``tf20_pins``'s opening for what each section holds).

- TF20-80: the pins are whole: every case of the corpus, every ``init`` case, ``doctor``,
  ``init`` on a store and the skill, the 23 page files and the 11 screens, and every file of
  the repository a user is given; and none holds a path of the machine that took it.
- TF20-81: every invocation of the corpus prints, piped, what main printed, byte for byte: every
  verb's plain and ``--json`` output, every help, every import, every refusal. The larger cases
  are slow; each kind among them has a fast case in the pull-request lane.
- TF20-82: ``init`` on the files it finds, and on a folder of every tool, as main prints it.
- TF20-83: ``doctor`` and ``init`` on a store (the machine's own words written out), and the
  setup skill, as main prints them.
- TF20-84: the pages ``ui`` writes, as main writes them; TF20-85: the terminal app's screens, as
  main shows them.
- TF20-86: every file of the repository a user is given is main's, byte for byte, but the six
  this pair changes (TF20-87 to TF20-90, TF20-92) and the docs checker (``test_tf20_ci.py``); none is
  gone.
- TF20-87: the README gains one passage, which links the recipe by its absolute address, and
  loses nothing.
- TF20-88: the CHANGELOG's count of recipes says sixteen where main's says fifteen, and nothing
  else moves.
- TF20-89: ``pyproject.toml`` gains Tasks' pin in the development extra, and nothing else moves.
- TF20-90: ``ci.yml`` and ``release.yml`` gain lines and lose none: in the clean-install job,
  Tasks at its pin and its tokenizer file; in a job that runs the pull-request or the slow lane,
  a step that fetches the tokenizer file, and nothing else (TF20-75 holds that each such job
  has one). The lanes now run the recipe, whose first command needs that file.
- TF20-92: ``CONTRIBUTING.md`` gains one passage, which says to fetch the tokenizer file once
  after the development install, and loses nothing.
- TF20-91: no file is added to the package, the docs, the tools, the workflows or the fixtures
  but the recipe's page; the recipe's files are under ``examples/three-tools/``.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tf5_pins import machine, ran_case, ran_every_tool, ran_init
from tf19_support import make_world, pages_pins
from tf20_pins import TEXTS, EVERY_LABEL, INIT, MAIN, PINS, REPO, SETUP, SKILL, digest_text_steps, file_digest, pin_corpus, pin_slow, pinned_paths
from tf20_support import EXAMPLE, PAGE, TASKS_PIN

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = pin_slow()
RECIPE_LINK = "https://github.com/poisson-labs/trace/blob/main/docs/recipes/with-tasks-and-prove.md"
#: The files this pair changes, each held by its own test; and the one Session B may write as it
#: needs, held by what it does.
CHANGED = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "pyproject.toml", ".github/workflows/ci.yml", ".github/workflows/release.yml")
#: A line a job other than clean-install may gain: a step that fetches Tasks' tokenizer file.
TOKENIZER_STEP = re.compile(r"^      - name: [^\n]*(?i:tokenizer)[^\n]*$|^        run: \|?$"
                            r"|^        (?:run: )?(?:  )?\.venv/bin/(?:poisson-tasks doctor --fix --yes(?: --offline)?|python -m poisson_tasks\.fetch_encoding)$")
FREE = ("tools/docs_check.py",)


def _main(name: str) -> str:
    """A file this pair changes, as main holds it (pinned as text, and checked against its
    digest)."""
    text = PINNED["texts"][name]
    from hashlib import sha256

    assert sha256(text.encode("utf-8")).hexdigest() == PINNED["files"][name], f"the pinned text of {name} is not main's file"
    return str(text)


def _now(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def _ops(name: str) -> list[tuple[str, list[str], list[str]]]:
    old, new = _main(name).split("\n"), _now(name).split("\n")
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    return [(tag, old[i1:i2], new[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


# ---------- TF20-80 ----------


def test_tf20_80_the_pins_are_whole() -> None:
    assert PINNED["main"] == MAIN == "901e845" and PINNED["python"] == "3.12.13"
    assert set(PINNED["piped"]) == set(CORPUS) and len(CORPUS) >= 194
    assert set(PINNED["init"]) == {*INIT, EVERY_LABEL} and set(PINNED["setup"]) == set(SETUP) and len(PINNED["skill"]) == 1
    assert len(PINNED["pages"]) == 23 and len(PINNED["app"]) == 11
    assert set(PINNED["texts"]) == set(TEXTS) == set(CHANGED) and len(PINNED["tracked"]) >= len(PINNED["files"])
    names = set(PINNED["files"])
    assert len(names) >= 1000 and {"README.md", "CHANGELOG.md", "pyproject.toml", "tools/docs_check.py", ".github/workflows/ci.yml"} <= names
    assert any(n.startswith("src/poisson_trace/") for n in names) and any(n.startswith("docs/recipes/") for n in names)
    assert "docs/recipes/with-tasks-and-prove.md" not in names and not any(n.startswith("examples/") for n in names)


def test_tf20_80_no_pin_holds_a_path_of_the_machine_that_took_it() -> None:
    text = PINS.read_text(encoding="utf-8")
    for word in ("/Users/", "/home/", "/private/", "/var/folders/"):
        assert word not in text, word


# ---------- TF20-81 ----------


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_tf20_81_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    # the Prove label kinds pair names, in these five, the labels that have no kind (test_pl_unchanged.py, PL-52, holds
    # that); this goes on holding every other byte of them
    from pl_pins import MOVED_SHARED, unmoved

    ran = ran_case(tmp_path, place, kind, steps)
    assert digest_text_steps(unmoved(ran) if label in MOVED_SHARED else ran) == PINNED["piped"][label], label


def test_tf20_81_a_fast_case_stands_for_each_slow_one() -> None:
    fast = [label for label in CORPUS if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    assert SLOW & set(CORPUS)
    for label in SLOW & set(CORPUS):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


# ---------- TF20-82 ----------


@pytest.mark.parametrize("label", list(INIT))
def test_tf20_82_init_on_the_files_it_finds(tmp_path: Path, label: str) -> None:
    holds, steps = INIT[label]
    assert digest_text_steps(ran_init(tmp_path, holds, steps)) == PINNED["init"][label]


def test_tf20_82_init_on_a_file_of_every_tool(tmp_path: Path) -> None:
    assert digest_text_steps(ran_every_tool(tmp_path)) == PINNED["init"][EVERY_LABEL]


# ---------- TF20-83 ----------


@pytest.mark.parametrize("label", list(SETUP))
def test_tf20_83_doctor_and_init_on_a_store(tmp_path: Path, label: str) -> None:
    got = [(code, machine(out), machine(err)) for code, out, err in ran_case(tmp_path, *SETUP[label])]
    assert digest_text_steps(got) == PINNED["setup"][label], label


def test_tf20_83_the_setup_skill(tmp_path: Path) -> None:
    assert digest_text_steps(ran_case(tmp_path, *SKILL)) == PINNED["skill"]


# ---------- TF20-84, TF20-85 ----------


def test_tf20_84_the_pages(tmp_path: Path) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


def test_tf20_85_the_app(tmp_path: Path) -> None:
    from tf5_pins import app_pins

    assert app_pins(make_world(tmp_path)) == PINNED["app"]


# ---------- TF20-86 ----------


def test_tf20_86_every_other_file_is_main_s() -> None:
    moved = []
    for name, digest in PINNED["files"].items():
        path = REPO / name
        assert path.is_file(), f"{name} is gone"
        if name in CHANGED or name in FREE:
            continue
        # the Prove label kinds pair builds its rule in these (test_pl_unchanged.py, PL-56, holds every other file)
        from pl_pins import BUILT

        if name in BUILT:
            continue
        # TF9's list of frozen tests moves when a frozen test moves on a ruling (test_tf9_plain.py, TF9-1a, holds
        # each line of it): tests/conftest.py for trace#50, ruled 2026-11-17 (PV-1)
        if name == "tests/fixtures/tf9/frozen-tests.sha256":
            continue
        if file_digest(path) != digest:
            moved.append(name)
    assert moved == [], moved


# ---------- TF20-87 ----------


def test_tf20_87_the_readme_gains_one_passage_that_links_the_recipe() -> None:
    ops = _ops("README.md")
    assert ops and all(tag == "insert" for tag, _, _ in ops), ops
    assert len(ops) == 1, "one passage"
    (_, _, added), = ops
    text = "\n".join(added)
    assert RECIPE_LINK in text and len([line for line in added if line.strip()]) <= 5, added
    assert _now("README.md").count(RECIPE_LINK) == 1


# ---------- TF20-88 ----------


def test_tf20_88_the_changelog_counts_sixteen_recipes() -> None:
    main = _main("CHANGELOG.md")
    assert main.count("Fifteen recipes under `docs/recipes/`") == 1
    assert _now("CHANGELOG.md") == main.replace("Fifteen recipes under `docs/recipes/`", "Sixteen recipes under `docs/recipes/`")


# ---------- TF20-89 ----------


def test_tf20_89_pyproject_gains_tasks_pin_in_the_development_extra() -> None:
    import tomllib

    main, now = tomllib.loads(_main("pyproject.toml")), tomllib.loads(_now("pyproject.toml"))
    dev_main, dev_now = main["project"]["optional-dependencies"]["dev"], now["project"]["optional-dependencies"]["dev"]
    assert dev_now == [*dev_main, TASKS_PIN], dev_now
    main["project"]["optional-dependencies"]["dev"] = dev_now
    assert now == main, "nothing else of pyproject.toml moves"
    ops = _ops("pyproject.toml")
    assert len(ops) == 1 and ops[0][0] == "replace" and len(ops[0][1]) == len(ops[0][2]) == 1, ops
    assert _now("pyproject.toml").count("poisson-tasks") == 1


# ---------- TF20-90 ----------


@pytest.mark.parametrize("name", [".github/workflows/ci.yml", ".github/workflows/release.yml"])
def test_tf20_90_the_workflows_gain_the_tokenizer_and_lose_nothing(name: str) -> None:
    old, lines = _main(name).split("\n"), _now(name).split("\n")
    matcher = difflib.SequenceMatcher(a=old, b=lines, autojunk=False)
    ops = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    assert all(tag == "insert" for tag, *_ in ops), [(tag, old[i1:i2], lines[j1:j2]) for tag, i1, i2, j1, j2 in ops]
    clean = (lines.index("  clean-install:"), None) if "  clean-install:" in lines else (None, None)
    end = None
    if clean[0] is not None:
        end = next((i for i in range(clean[0] + 1, len(lines)) if re.match(r"^  \S", lines[i])), len(lines))
    for _, _, _, j1, j2 in ops:
        if clean[0] is not None and end is not None and clean[0] < j1 and j2 <= end:
            continue
        for line in lines[j1:j2]:
            assert TOKENIZER_STEP.match(line) or not line.strip(), f"{name}: a line added outside clean-install that does not fetch the tokenizer: {line}"
    if name.endswith("release.yml"):
        assert ops, "the release's lanes run the recipe too"


# ---------- TF20-92 ----------


def test_tf20_92_contributing_says_to_fetch_the_tokenizer_once() -> None:
    ops = _ops("CONTRIBUTING.md")
    assert len(ops) == 1 and ops[0][0] == "insert", ops
    added = "\n".join(ops[0][2])
    assert re.search(r"poisson-tasks doctor --fix --yes|poisson_tasks\.fetch_encoding", added), added
    assert len([line for line in ops[0][2] if line.strip()]) <= 8, ops[0][2]


# ---------- TF20-91 ----------


def _files_on_disk() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True,
                            check=True).stdout
    return sorted({name for name in listed.split("\0") if name and (REPO / name).is_file()})


def test_tf20_91_no_other_file_is_added() -> None:
    pinned = set(PINNED["files"])
    added = [name for name in pinned_paths(_files_on_disk()) if name not in pinned]
    # the Prove label kinds pair's own pins (test_pl_unchanged.py, PL-56, holds that it adds nothing else)
    added = [name for name in added if not name.startswith("tests/fixtures/pl/")]
    assert added == [PAGE.relative_to(REPO).as_posix()], added
    top = {name.split("/")[0] for name in _files_on_disk()} - {name.split("/")[0] for name in tracked_at_main()}
    assert top <= {"examples"}, top
    examples = [name for name in _files_on_disk() if name.startswith("examples/")]
    assert examples and all(name.startswith(EXAMPLE.relative_to(REPO).as_posix() + "/") for name in examples), examples


def tracked_at_main() -> list[str]:
    return list(PINNED["tracked"])


