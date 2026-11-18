"""PF-90 to PF-98: nothing else moves. The pins are main 4bb4b95's, taken by
``fixtures/pf/make_main_pins.py`` from that commit itself (see ``pf_pins``'s opening).

- PF-90: every file of the repository a user is given is main's, but the files the build may
  change (``pf_pins.BUILT``) and the four this pair's own frozen commits change
  (``pf_pins.OURS``, each at the digest it was frozen with); none is gone; and no file is added
  to the package, the docs, the tools, the workflows, the examples or the fixtures but this
  pair's pins and the store the floor made.
- PF-91: ``pyproject.toml`` moves in its Prove requirement and the comment above it, and in
  nothing else: read as TOML it is main's with the one requirement changed.
- PF-92: ``ci.yml`` gains the lane on the newest Prove and what its opening says of it; no line
  of any other job moves (PF-60 holds each job whole).
- PF-93: ``release.yml`` moves only where it named the exact pin.
- PF-94: the README moves in the one sentence that said which Prove ``pip`` brings.
- PF-95: the contributing page moves in the one sentence that said how Prove is declared.
- PF-96: the setup page moves in the one line of ``doctor``'s output that shows Prove, which no
  longer holds one version: it holds on any Prove at or above the floor.
- PF-97: the pins are whole, and none holds a path of the machine that took it.
- PF-98: what main prints is still held: the newest pinned corpus holds every case it held, and
  the earlier pairs' file tests read the files this pair changes as main held them.
"""

from __future__ import annotations

import difflib
import re
import tomllib

import pytest
from pf_pins import BUILT, FLOOR_STORE, MAIN, OURS, PINS, REPO, TEXTS, file_digest, main_text, pinned_paths, pins, tracked
from pin_support import FORMAT_1_0, OR_LATER, RECORDED, REQUIREMENT

PINNED = pins()


def _now(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def _ops(name: str) -> list[tuple[str, list[str], list[str]]]:
    """Each run of lines of ``name`` that is not main's: how it differs, main's lines and the lines now."""
    old, new = main_text(name).split("\n"), _now(name).split("\n")
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    return [(tag, old[i1:i2], new[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


# ---------- PF-90 ----------


def test_pf_90_every_other_file_is_main_s() -> None:
    moved = []
    for name, digest in PINNED["files"].items():
        path = REPO / name
        assert path.is_file(), f"{name} is gone"
        if name in BUILT:
            continue
        # TF9's list of frozen tests moves when a frozen test moves on a ruling (test_tf9_plain.py, TF9-1a, holds each line)
        if name == "tests/fixtures/tf9/frozen-tests.sha256":
            continue
        if file_digest(path) != OURS.get(name, digest):
            moved.append(name)
    assert moved == [], moved


def test_pf_90_what_this_pair_froze_outside_the_tests_is_listed() -> None:
    assert set(OURS) <= set(PINNED["files"]) and not set(OURS) & set(BUILT)
    assert set(BUILT) <= set(PINNED["files"]) and set(TEXTS) <= set(BUILT)
    for name, digest in OURS.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest) and digest != PINNED["files"][name], name


def _on_disk() -> list[str]:
    """Every file of the checkout git tracks or would track: a file added and not yet committed is one too."""
    import subprocess

    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True,
                            check=True).stdout
    return sorted({name for name in listed.split("\0") if name and (REPO / name).is_file()})


def test_pf_90_no_file_is_added_but_the_tests_the_pins_and_the_floors_store() -> None:
    now = _on_disk()
    assert set(tracked()) <= set(now), "a tracked file is missing from the checkout"
    added = sorted(set(pinned_paths(now)) - set(PINNED["files"]))
    sums = (REPO / "tests" / "fixtures" / "prove-stores" / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    store = sorted("tests/fixtures/prove-stores/" + line.partition("  ")[2].removeprefix("./") for line in sums
                   if line.partition("  ")[2].startswith(f"./prove-{RECORDED}/"))
    assert len(store) == 28 and all(name.startswith(FLOOR_STORE) for name in store)
    assert added == store, sorted(set(added) ^ set(store))
    new = sorted(set(now) - set(PINNED["tracked"]))
    assert all(name.startswith("tests/") for name in new), new
    fixtures = [name for name in new if name.startswith("tests/fixtures/")]
    assert sorted(fixtures) == sorted([*store, "tests/fixtures/pf/main-pins.json", "tests/fixtures/pf/make_main_pins.py"]), fixtures
    assert sorted(set(PINNED["tracked"]) - set(now)) == [], "no file main tracks is gone"


# ---------- PF-91 ----------


def test_pf_91_pyproject_moves_in_its_prove_requirement_alone() -> None:
    main, now = tomllib.loads(main_text("pyproject.toml")), tomllib.loads(_now("pyproject.toml"))
    was = main["project"]["dependencies"]
    assert was.count(f"poisson-prove=={FORMAT_1_0}") == 1
    assert now["project"]["dependencies"] == [REQUIREMENT if d == f"poisson-prove=={FORMAT_1_0}" else d for d in was]
    main["project"]["dependencies"] = now["project"]["dependencies"]
    assert now == main, "nothing else of pyproject.toml moves"
    for tag, old, new in _ops("pyproject.toml"):
        assert tag == "replace", (tag, old, new)
        for line in (*old, *new):
            assert line.startswith("#") or line.startswith("dependencies = ["), line
    text = _now("pyproject.toml")
    assert "pinned exactly" not in text and "exact pin" not in text
    assert text.count(RECORDED) == 1, "the floor is written once"


# ---------- PF-92 ----------


def test_pf_92_ci_gains_the_lane_and_loses_nothing() -> None:
    ops = _ops(".github/workflows/ci.yml")
    assert ops, "the lane on the newest Prove"
    head = _now(".github/workflows/ci.yml").split("\n").index("jobs:")
    gone = [line for tag, old, _ in ops for line in old if tag != "insert"]
    # a line of main's that moves is a line of the comment the file opens with, and nothing under jobs:
    assert all(line.startswith("#") for line in gone), gone
    assert all(line in main_text(".github/workflows/ci.yml").split("\n")[:head] for line in gone)
    added = [line for _, _, new in ops for line in new]
    assert any(re.match(r"^  [a-z0-9-]+:$", line) for line in added), "one job is added"
    assert len([line for line in added if re.match(r"^  [a-z0-9-]+:$", line)]) == 1
    for line in added:
        assert "secrets." not in line and "pull_request_target" not in line, line


# ---------- PF-93 ----------


def test_pf_93_the_release_moves_only_where_it_named_the_exact_pin() -> None:
    ops = _ops(".github/workflows/release.yml")
    assert ops and all(tag == "replace" and len(old) == len(new) for tag, old, new in ops), ops
    moved = [(o, n) for _, old, new in ops for o, n in zip(old, new, strict=True)]
    assert len(moved) <= 3, moved
    for was, now in moved:
        assert re.search(r"Prove|poisson-prove", was) and re.search(r"Prove|poisson-prove", now), (was, now)
        assert was.startswith(" " * (len(now) - len(now.lstrip()))), "the line's place in the file is the same"
        assert f"'{FORMAT_1_0}'" not in now and "pinned exactly" not in now and "it pins" not in now, now


# ---------- PF-94, PF-95 ----------


@pytest.mark.parametrize(("name", "said", "gone"), [
    ("README.md", "at the one exact version Trace reads", ("exact version",)),
    ("CONTRIBUTING.md", "pins it to", ("pins it to", "one exact version")),
])
def test_pf_94_95_the_page_moves_in_the_one_sentence_about_which_prove(name: str, said: str, gone: tuple[str, ...]) -> None:
    ops = _ops(name)
    assert len(ops) == 1 and ops[0][0] == "replace", ops
    _, old, new = ops[0]
    assert said in " ".join(old) and 1 <= len(old) <= 3 and 1 <= len(new) <= 4, (old, new)
    text = " ".join(line.strip() for line in new)
    assert RECORDED in text and not any(word in text for word in gone), new
    assert "poisson-prove==" not in _now(name)
    # the lines around the sentence are main's: the paragraph still opens and closes as it did
    assert not any(line.startswith(("#", "```", "<!--")) for line in (*old, *new)), (old, new)


# ---------- PF-96 ----------


def test_pf_96_the_setup_page_shows_doctor_s_prove_line_for_any_prove_at_the_floor_or_above() -> None:
    name = "docs/setup-with-your-agent.md"
    was = f"  prove     poisson-prove {FORMAT_1_0} (the version Trace reads)"
    now = f"  prove     poisson-prove … (Trace reads version {OR_LATER})"
    main, text = main_text(name), _now(name)
    assert main.count(was) == 1 and was not in text and text.count(now) == 1
    lines = text.split("\n")
    at = lines.index(now)
    # the block's mark says the line holds a version written whole, and the checker reads it so
    assert lines[at - 1] == "```" and lines[at - 2] == "<!-- excerpt exit=0 varies -->", lines[at - 2 : at + 1]
    expected = main.replace(was, now).split("\n")
    marks = [i for i, line in enumerate(expected) if line == now]
    expected[marks[0] - 2] = "<!-- excerpt exit=0 varies -->"
    assert lines == expected, "nothing else of the page moves"
    block = lines[at : lines.index("```", at)]
    assert sum("…" in line for line in block) == 1, "the one line that varies"


def test_pf_96_the_checker_holds_that_line_on_any_version() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("docs_check_pf", REPO / "tools" / "docs_check.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["docs_check_pf"] = module
    try:
        spec.loader.exec_module(module)
        shown = f"  prove     poisson-prove … (Trace reads version {OR_LATER})"
        for version in (RECORDED, "0.4.1", "1.0.0", "0.10.2"):
            assert module.line_holds(shown, f"  prove     poisson-prove {version} (Trace reads version {OR_LATER})", True), version
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} (the version Trace reads)", True)
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} is installed, and Trace reads version {OR_LATER}", True)
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} (Trace reads version {OR_LATER})", False)
    finally:
        del sys.modules["docs_check_pf"]


def test_pf_96_no_page_shows_one_prove_as_the_version_trace_reads() -> None:
    pages = [REPO / "README.md", REPO / "CONTRIBUTING.md", *sorted((REPO / "docs").rglob("*.md"))]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "(the version Trace reads)" not in text, page.name
        assert not re.search(r"poisson-prove \d+\.\d+\.\d+ \(Trace reads", text), f"{page.name} holds one Prove's version in doctor's line"
        assert f"poisson-prove=={FORMAT_1_0}" not in text and f"poisson-prove {FORMAT_1_0}" not in text, page.name


# ---------- PF-97 ----------


def test_pf_97_the_pins_are_whole() -> None:
    assert PINNED["main"] == MAIN == "4bb4b95"
    names = set(PINNED["files"])
    assert len(names) >= 1100 and set(BUILT) <= names and set(OURS) <= names
    assert set(PINNED["texts"]) == set(TEXTS)
    assert not any(name.startswith("tests/fixtures/pf/") for name in names)
    assert len(PINNED["tracked"]) >= 1400 and names <= set(PINNED["tracked"])
    for name in TEXTS:
        assert main_text(name)


def test_pf_97_no_pin_holds_a_path_of_the_machine_that_took_it() -> None:
    text = PINS.read_text(encoding="utf-8")
    for word in ("/Users/", "/home/runner", "/private/", "/var/folders/"):
        assert word not in text.replace("/Users/user/", "").replace("/Users/Shared/trace-fixture/", ""), word


def test_pf_97_main_s_files_are_the_ones_the_earlier_pair_pinned_but_what_merged_since() -> None:
    """The Prove label kinds pair pinned main c981832; between it and 4bb4b95 main gained that
    pair's build (#49), the tests' browser guard (#50) and the two test fixes (#51). A file both
    pin differs only if one of those moved it."""
    import json

    from pl_pins import BUILT as LABELS_BUILT, PINS as LABELS_PINS

    earlier = json.loads(LABELS_PINS.read_text(encoding="utf-8"))["files"]
    moved = sorted(name for name, digest in PINNED["files"].items() if name in earlier and earlier[name] != digest)
    assert moved == sorted([*LABELS_BUILT, "tests/fixtures/tf9/frozen-tests.sha256"]), moved


# ---------- PF-98 ----------


def test_pf_98_the_newest_pinned_corpus_holds_every_case_it_held() -> None:
    import json

    from pl_pins import PINS as LABELS_PINS, pin_corpus

    held = json.loads(LABELS_PINS.read_text(encoding="utf-8"))
    assert set(held["piped"]) == set(pin_corpus()) and len(held["piped"]) >= 198
    assert len(held["pages"]) == 23 and len(held["app"]) == 11 and len(held["setup"]) >= 5


def test_pf_98_the_earlier_file_tests_read_these_files_as_main_held_them() -> None:
    """TF20-87 to TF20-90 say what the recipe pair gave five files this pair changes after it;
    each reads the file as main 4bb4b95 held it, so both pairs' changes stay held."""
    import test_tf20_unchanged as earlier

    for name in ("README.md", "CONTRIBUTING.md", "pyproject.toml", ".github/workflows/ci.yml", ".github/workflows/release.yml"):
        assert name in TEXTS and earlier._now(name) == main_text(name), name
    assert earlier._now("CHANGELOG.md") == _now("CHANGELOG.md"), "a file this pair leaves alone is read from the checkout"
