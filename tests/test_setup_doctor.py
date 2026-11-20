"""TF2-18 to TF2-20: ``doctor`` says whether this environment is ready, and what to run when it is
not.

Six lines in this order: python, package, prove, config, names, readers. ``ok  …`` and exit 0
when every line holds; ``not ready  …`` and exit 4 when one fails, each failing line ending with
the command that moves the user on, and ``next:`` the first of them (``poisson-trace runs`` when
ready). ``--json`` is ``poisson-trace.doctor/1``: ``schema``, ``verdict``, ``sentence``,
``checks`` (``name``, ``ok``, ``line``, ``next``, in the order printed) and ``next``. The config
line fails with no ``trace.toml``, with one that is not a version 1 config, with a store that is
not there, with no failures set or failures none of the newest runs carry; the names line fails on
a names file every verb would refuse; the prove line fails without Prove or at another version.
The package line names where the package was imported from, and a warning never fails it.
``doctor`` fixes nothing, asks nothing and contacts no host."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import poisson_trace
from look_support import INSTALL_PROVE
from names_support import T_B, shell_words, tau2_copy, write_names
from setup_support import (  # noqa: F401
    CONFIG, DOCTOR_CHECKS, R, ABSENT_READERS, PRESENT_READERS, check, config_of, counts, doc, doctor, doctor_doc, here,
    no_network, run, scratch_home, stamp, store_of, tree, tty, work, write_config,
)

DOCTOR_KEYS = ["schema", "verdict", "sentence", "checks", "next"]


@pytest.fixture
def ready(tmp_path: Path) -> Path:
    folder = work(tmp_path)
    tau2_copy(folder, "proofload-runs")
    write_config(folder, config_of("proofload-runs"))
    return folder


def _failing(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in data["checks"] if not c["ok"]]


def test_tf2_18_a_ready_environment(ready: Path) -> None:
    code, data = doctor_doc(ready)
    assert code == 0
    assert list(data) == DOCTOR_KEYS and data["schema"] == "poisson-trace.doctor/1" and data["verdict"] == "ok"
    assert [c["name"] for c in data["checks"]] == list(DOCTOR_CHECKS)
    assert all(list(c) == ["name", "ok", "line", "next"] and c["ok"] is True and c["next"] is None for c in data["checks"])
    assert data["next"] == "poisson-trace runs"


def test_tf2_18_the_text_is_the_verdict_then_the_six_lines_then_next(ready: Path) -> None:
    _, data = doctor_doc(ready)
    result = doctor(ready)
    assert result.code == 0 and result.err == "", result.text
    lines = result.lines("out")
    assert lines[0].startswith("ok  ") and lines[-1] == "next: poisson-trace runs", result.out
    body = lines[1:-1]
    assert len(body) == 6, result.out
    for line, item in zip(body, data["checks"], strict=True):
        assert line.startswith(f"  {item['name']} ") and item["line"].strip() in line, (line, item)


def test_tf2_18_each_line_says_what_it_found(tmp_path: Path) -> None:
    import poisson_prove

    folder = work(tmp_path)
    store_of(folder / "store", [R("a1", stamp(1, 9)), R("a2", stamp(1, 10)), R("a3", stamp(1, 11)), R("half", stamp(1, 12), status="partial")])
    write_names(folder / "store", {"first": "a1", "second": "a2"})
    write_config(folder, config_of("store", ("fail",)))
    code, data = doctor_doc(folder)
    assert code == 0, data
    python = check(data, "python")["line"]
    assert sys.executable in python and ".".join(str(n) for n in sys.version_info[:3]) in python, python
    package = check(data, "package")["line"]
    folder = Path(poisson_trace.__file__).parent
    assert poisson_trace.__version__ in package and (str(folder) in package or str(folder.resolve()) in package), package
    assert poisson_prove.__version__ in check(data, "prove")["line"]
    line = check(data, "config")["line"]
    assert "store" in line and "fail" in line, line
    found = counts(line)
    assert found[found.index(4):found.index(4) + 3] == [4, 3, 1], line
    assert 2 in counts(check(data, "names")["line"])
    readers = check(data, "readers")["line"]
    assert all(r in readers for r in PRESENT_READERS) and not any(r in readers for r in ABSENT_READERS), readers


@pytest.mark.slow
def test_tf2_18_the_package_line_warns_outside_the_environment_and_stays_ok(ready: Path, tmp_path: Path) -> None:
    """This suite runs the package from outside the interpreter's environment (an editable install,
    or a build on the path). Installed inside a fresh environment, the same package's line is
    the same but for the folder; outside, it carries a warning; ok either way."""
    import os
    import shutil
    import subprocess
    import sysconfig

    inside = tmp_path / "inside-env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(inside)], check=True, capture_output=True, timeout=120)
    lib = Path(subprocess.run([str(inside / "bin" / "python"), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                              check=True, capture_output=True, text=True).stdout.strip())
    package = Path(poisson_trace.__file__).parent
    shutil.copytree(package, lib / "poisson_trace", ignore=shutil.ignore_patterns("__pycache__"))
    (lib / "dependencies.pth").write_text(sysconfig.get_paths()["purelib"] + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run([str(inside / "bin" / "python"), "-c", "import sys; from poisson_trace.cli import main; sys.exit(main(['doctor', '--json']))"],
                          capture_output=True, text=True, cwd=ready, env=env, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    import json

    there = check(json.loads(proc.stdout), "package")
    _, data = doctor_doc(ready)
    here_ = check(data, "package")
    assert there["ok"] is True and here_["ok"] is True
    plain_there = there["line"].replace(str((lib / "poisson_trace").resolve()), "PKG").replace(str(lib / "poisson_trace"), "PKG")
    plain_here = here_["line"].replace(str(package.resolve()), "PKG").replace(str(package), "PKG")
    assert "PKG" in plain_there and "PKG" in plain_here, (there, here_)
    assert plain_here != plain_there, (here_, there)


# ---------- TF2-19: not ready ----------


def _broken(folder: Path, case: str) -> None:
    if case == "no config":
        (folder / CONFIG).unlink()
    elif case == "not a version 1 config":
        write_config(folder, config_of("proofload-runs", extra="\n[check]\nmax_md = 0.2\n"))
    elif case == "a store that is not there":
        write_config(folder, config_of("nowhere"))
    elif case == "no failures set":
        write_config(folder, 'version = 1\n\n[store]\npath = "proofload-runs"\n')
    elif case == "failures no run carries":
        write_config(folder, config_of("proofload-runs", ("bust",)))
    elif case == "a names file every verb refuses":
        write_names(folder / "proofload-runs", {"gone": "20260101T000000Z-dead", "old": T_B})
    elif case == "a named store that is not there":
        write_config(folder, config_of("proofload-runs", extra='\n[store.imported]\npath = "gone"\n'))


NOT_READY = [
    ("no config", "config", ["poisson-trace", "init"]),
    ("not a version 1 config", "config", None),
    ("a store that is not there", "config", None),
    ("no failures set", "config", ["poisson-trace", "init"]),
    ("failures no run carries", "config", None),
    ("a names file every verb refuses", "names", None),
    ("a named store that is not there", "config", None),
]


@pytest.mark.parametrize("case,failing,command", NOT_READY, ids=[c[0] for c in NOT_READY])
def test_tf2_19_a_failing_line_is_not_ready_and_says_what_to_run(ready: Path, case: str, failing: str, command: list[str] | None) -> None:
    before_ok = doctor_doc(ready)
    assert before_ok[0] == 0
    _broken(ready, case)
    code, data = doctor_doc(ready)
    assert code == 4 and data["verdict"] == "not ready", data
    assert [c["name"] for c in _failing(data)] == [failing], data["checks"]
    item = check(data, failing)
    assert item["next"], item
    words = shell_words(item["next"])
    assert words[0] == "poisson-trace", item
    if command is not None:
        assert words == command, item
    if failing == "config":
        assert words[1] == "init", item
    assert data["next"] == item["next"]
    text = doctor(ready)
    assert text.code == 4 and text.lines("out")[0].startswith("not ready  "), text.out
    line = [ln for ln in text.lines("out") if ln.startswith(f"  {failing} ")]
    assert len(line) == 1 and line[0].rstrip().endswith(item["next"]), text.out
    # the command, run as written (on a terminal, Enter for every answer, where it asks), mends it
    if words[1] == "init" and "--yes" not in words:
        mended = tty(words[1:], ["", "", "", ""], cwd=ready)
    else:
        mended = here(ready, words[1:])
    assert mended.code == 0, (words, mended.text)
    code, after = doctor_doc(ready)
    assert code == 0, after["checks"]


def test_tf2_19_the_config_line_names_the_line_of_the_fault(ready: Path) -> None:
    _broken(ready, "not a version 1 config")
    _, data = doctor_doc(ready)
    assert "line 10" in check(data, "config")["line"], data


# a Prove below the floor (0.3.0); one above it, such as 9.9.9, is one Trace reads
@pytest.mark.parametrize("prove", ["absent", "0.3.0"])
def test_tf2_19_the_prove_line_fails_without_the_prove_trace_reads(ready: Path, prove: str) -> None:
    result = run(["doctor", "--json"], cwd=ready, prove=prove)
    assert result.code == 4, result.text
    data = doc(result)
    assert [c["name"] for c in data["checks"]] == list(DOCTOR_CHECKS)
    item = check(data, "prove")
    assert item["ok"] is False and item["next"] == INSTALL_PROVE, item
    if prove != "absent":
        assert prove in item["line"], item
    assert data["next"] == INSTALL_PROVE


def test_tf2_19_doctor_reads_the_config_named_by_flag(ready: Path) -> None:
    (ready / CONFIG).unlink()
    (ready / "conf").mkdir()
    write_config(ready / "conf", config_of("../proofload-runs"), "team.toml")
    assert doctor_doc(ready)[0] == 4
    code, data = doctor_doc(ready, "--config", "conf/team.toml")
    assert code == 0, data["checks"]


# ---------- TF2-20: what doctor never does ----------


@pytest.mark.parametrize("case", ["ready", "no config", "a names file every verb refuses", "not a version 1 config"])
def test_tf2_20_doctor_fixes_nothing(ready: Path, case: str) -> None:
    if case != "ready":
        _broken(ready, case)
    before = tree(ready)
    codes = {doctor(ready).code, doctor(ready, "--json").code}
    assert codes == ({0} if case == "ready" else {4}), codes
    assert tree(ready) == before


def test_tf2_20_doctor_contacts_no_host(ready: Path, no_network: list[str]) -> None:  # noqa: F811
    result = doctor(ready)
    assert result.code == 0, result.text
    assert no_network == []
