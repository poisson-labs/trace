"""Takes the pins of what main prints, builds and holds, for TF20's unchanged tests
(``tests/test_tf20_unchanged.py``): run on main (the commit ``tf20_pins.MAIN`` names), from the
repository's root, with the package installed and nothing of the three-tools recipe in the
tree or the environment::

    python tests/fixtures/tf20/make_main_pins.py

It writes ``tests/fixtures/tf20/main-pins.json`` (see ``tf20_pins``'s opening for what each
section holds). It refuses to run when the checkout is not main's tree, when the recipe's page
or its fixtures exist, or when Poisson Tasks is installed: the pins are of main as a user of
Trace alone has it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

from tf5_pins import ran_case, ran_every_tool, ran_init, machine, app_pins  # noqa: E402
from tf19_support import make_world, pages_pins  # noqa: E402
from tf20_pins import TEXTS, EVERY_LABEL, INIT, MAIN, PINS, REPO, SETUP, SKILL, digest_text_steps, file_digest, pin_corpus, pinned_paths, tracked  # noqa: E402


def main() -> None:
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    assert head == MAIN, f"take the pins on main {MAIN}, not {head}"
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert dirty == "", "take the pins on main's tree as committed"
    assert not (REPO / "docs" / "recipes" / "with-tasks-and-prove.md").exists() and not (REPO / "examples").exists(), "before the recipe exists"
    assert find_spec("poisson_tasks") is None, "with Poisson Tasks not installed"
    pins: dict[str, object] = {"main": MAIN, "python": sys.version.split()[0], "piped": {}, "init": {}, "setup": {}, "files": {}}
    for label, (place, kind, steps) in pin_corpus().items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["piped"][label] = digest_text_steps(ran_case(Path(tmp), place, kind, steps))  # type: ignore[index]
        print(label, file=sys.stderr)
    for label, (holds, steps) in INIT.items():
        with tempfile.TemporaryDirectory() as tmp:
            pins["init"][label] = digest_text_steps(ran_init(Path(tmp), holds, steps))  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["init"][EVERY_LABEL] = digest_text_steps(ran_every_tool(Path(tmp)))  # type: ignore[index]
    for label, (place, kind, steps) in SETUP.items():
        with tempfile.TemporaryDirectory() as tmp:
            got = [(code, machine(out), machine(err)) for code, out, err in ran_case(Path(tmp), place, kind, steps)]
            pins["setup"][label] = digest_text_steps(got)  # type: ignore[index]
    with tempfile.TemporaryDirectory() as tmp:
        pins["skill"] = digest_text_steps(ran_case(Path(tmp), *SKILL))
    with tempfile.TemporaryDirectory() as tmp:
        pins["app"] = app_pins(make_world(Path(tmp)))
    with tempfile.TemporaryDirectory() as tmp:
        pins["pages"] = pages_pins(make_world(Path(tmp)))
    for name in pinned_paths(tracked()):
        pins["files"][name] = file_digest(REPO / name)  # type: ignore[index]
    pins["texts"] = {name: (REPO / name).read_text(encoding="utf-8") for name in TEXTS}
    pins["tracked"] = tracked()
    PINS.parent.mkdir(parents=True, exist_ok=True)
    PINS.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
