"""TF9, invariant 2: the switch (the look file's rule 16).

Pretty runs only when stdout and stderr are both terminals, ``NO_COLOR`` is unset or empty, ``CI``
is unset, ``TERM`` is not ``dumb``, stdout is UTF-8, and neither ``--json`` nor ``--plain`` was
given. Anything else is plain, byte for byte. ``--plain`` works before or after the verb.

**How pretty is told from plain.** The pretty rendering draws its verdict word in a colour or in
bold, so pretty output holds an SGR escape; the plain rendering holds no escape at all. A case
that falls back to plain on a terminal prints what the same case prints with ``--plain`` added
(plain on a terminal wraps at its width, so the reference is plain on the same terminals); a case
whose stdout is a pipe prints the piped plain rendering. That ``--plain`` itself is plain is
TF9-2c and TF9-7c.

**Two readings, as Prove's own switch reads them:** ``CI`` set to anything, empty included, is
set; ``TERM`` unset is not ``dumb``.

- **TF9-2a** With every condition holding, the rendering is pretty, on stdout and on stderr.
- **TF9-2b** Each condition failing on its own makes the whole output plain, byte for byte.
- **TF9-2c** ``--plain`` before the verb and after it, for the main command and for the import.
- **TF9-2d** ``--plain`` is in the command's help, with help text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tf0_support import trace
from tf9_support import COMPARE_SMALL, Item, Run, shared_base, shared_run


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


ITEM = COMPARE_SMALL  # "too small to tell": a coloured word on stdout, and a short run
REFUSAL = Item("a refusal", "trace", ("where", "no-such-run", "--store", ITEM.argv[4], "--event", "unsolved"), 1)


def _with(item: Item, *extra: str, before: bool = False) -> Item:
    argv = (*extra, *item.argv) if before else (*item.argv, *extra)
    return Item(f"{item.label} {' '.join(extra)}", item.command, argv, item.expect, item.stage)


def _escapes(r: Run) -> bool:
    return "\x1b" in r.out or "\x1b" in r.err


# ---------- TF9-2a ----------


@pytest.mark.parametrize(
    "case, env",
    [
        ("every condition holds", {}),
        ("NO_COLOR set and empty", {"NO_COLOR": ""}),
        ("TERM unset", {"TERM": None}),
    ],
)
def test_tf9_2a_pretty_when_every_condition_holds(base: Path, case: str, env: dict[str, str | None]) -> None:
    r = shared_run(base, ITEM, stdout="pty", stderr="own", env=env)
    assert r.code == 0
    assert "\x1b[" in r.out.split("\n", 1)[0], "the verdict line is not drawn by the pretty rendering"
    e = shared_run(base, REFUSAL, stdout="pty", stderr="own", env=env)
    assert e.code == 1
    assert "\x1b[" in e.err, "the error line is not drawn by the pretty rendering"


# ---------- TF9-2b ----------

#: (case, stdout, stderr, environment): each one condition failing.
FALLS = [
    ("stdout a pipe", "pipe", "own", {}),
    ("stderr a pipe", "pty", "pipe", {}),
    ("NO_COLOR set", "pty", "own", {"NO_COLOR": "1"}),
    ("CI set", "pty", "own", {"CI": "true"}),
    ("CI set and empty", "pty", "own", {"CI": ""}),
    ("TERM dumb", "pty", "own", {"TERM": "dumb"}),
    ("stdout not UTF-8", "pty", "own", {"PYTHONIOENCODING": "latin-1"}),
]


@pytest.mark.parametrize("item", [ITEM, REFUSAL], ids=["a result", "a refusal"])
@pytest.mark.parametrize("case, stdout, stderr, env", FALLS, ids=[f[0] for f in FALLS])
def test_tf9_2b_any_condition_failing_is_plain_byte_for_byte(
    base: Path, item: Item, case: str, stdout: str, stderr: str, env: dict[str, str]
) -> None:
    got = shared_run(base, item, stdout=stdout, stderr=stderr, env=env)
    assert not _escapes(got), f"{case}: an escape sequence in the output"
    if stdout == "pipe":
        want = shared_run(base, item, stdout="pipe", stderr="pipe")
        assert (got.code, got.out) == (want.code, want.out)
        return
    want = shared_run(base, _with(item, "--plain"), stdout=stdout, stderr=stderr, env=env)
    assert (got.code, got.out, got.err) == (want.code, want.out, want.err)


# ---------- TF9-2c ----------


@pytest.mark.parametrize("item", [ITEM, REFUSAL], ids=["a result", "a refusal"])
@pytest.mark.parametrize("before", [False, True], ids=["after the verb", "before the verb"])
def test_tf9_2c_plain_on_terminals_before_or_after_the_verb(base: Path, item: Item, before: bool) -> None:
    got = shared_run(base, _with(item, "--plain", before=before), stdout="pty", stderr="own")
    assert got.code == item.expect
    assert not _escapes(got)
    other = shared_run(base, _with(item, "--plain", before=not before), stdout="pty", stderr="own")
    assert (got.code, got.out, got.err) == (other.code, other.out, other.err)


IMPORT = Item(
    "import", "import",
    ("deepeval", str(Path(__file__).resolve().parent / "fixtures" / "ingest" / "deepeval" / "humaneval-a.json.gz"),
     "--store", "store", "--run", "he-a", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
     "--started", "2026-09-05T18:54:07Z"),
    0,
)


@pytest.mark.parametrize("how", ["poisson-trace import ... --plain", "poisson-trace --plain import ...", "poisson-trace-import --plain ..."])
def test_tf9_2c_plain_on_terminals_for_the_import(base: Path, how: str) -> None:
    if how.startswith("poisson-trace-import"):
        item = _with(IMPORT, "--plain", before=True)
    else:
        trace_form = Item("import", "trace", ("import", *IMPORT.argv), 0)
        item = _with(trace_form, "--plain", before=how.startswith("poisson-trace --plain"))
    got = shared_run(base, item, stdout="pty", stderr="own")
    assert got.code == 0, got.err
    assert not _escapes(got)
    assert got.out.startswith("ok  ")


# ---------- TF9-2d ----------


def test_tf9_2d_plain_is_in_the_help() -> None:
    shown = trace(["--help"])
    assert shown.code == 0
    entry = [line for line in shown.out.splitlines() if line.strip().startswith("--plain")]
    assert entry, "--plain is not in poisson-trace --help"
    assert len(entry[0].split()) > 1 or "plain" in shown.out.split(entry[0], 1)[1].split("\n", 2)[1], "--plain has no help text"
