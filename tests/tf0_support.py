"""Shared helpers for the tests of the look and the errors (TF0-1 to TF0-21): the exit-code table,
the patterns a user must never read, runners for both commands in-process and in a subprocess
(with Prove present, absent, or at another version), and the corpus of invocations the
conformance and plain-words tests run.

Not a test module and not collected. The corpus is the spec's: every verb's help and the
version, the README's worked examples on the committed fixtures, every refusal the front-door
transcript's mistakes section made, and the new refusals this pair adds.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conftest import CS, CS_EVENTS, CS_RECORD, FIXTURES, TAU2, TAU2_A, TAU2_B, CliResult, events_args
from pin_support import INSTALL

REPO = Path(__file__).resolve().parent.parent
CLI_LOOK = REPO / "docs" / "cli-look.md"
HUMANEVAL = FIXTURES / "humaneval"
HE_A, HE_B = "20260905T185407Z-0313", "20260905T195009Z-18ac"
HE_EVENTS = ("failed_assertion", "crashed")
PILOT = "20260917T140219Z-2b2d"
DEEPEVAL = FIXTURES / "ingest" / "deepeval"
RAGAS = FIXTURES / "ingest" / "ragas"
VERBS = ("where", "compare", "fix-check", "changes")
TOOLS = ("deepeval", "ragas")

# spec section 3.3, the Tasks table kept to the letter
EXIT_CODES = frozenset({0, 1, 2, 3, 4, 130})
INSTALL_PROVE = INSTALL  # the one command that installs the Prove Trace reads (pin_support.py)
PLACEHOLDER_INSTALL = "/path/to/prove"
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{4}")
VERDICT_LINE = re.compile(r"^[a-z][a-z ]*  \S")

# What an error never holds (the shared look's rule 4): a traceback, a library's own exception
# text as Python prints it, or a Python representation of a value. A quoted value is a quote
# that opens after neither a letter nor a quote, so "Prove's" and "runs'" are prose.
REPR = re.compile(
    r"Traceback \(most recent call last\)"
    r"|\[Errno \d+\]"
    r"|(?<![\w'])'[^'\n]*'(?![\w'])"
    r"|\(\s*'|\['|\{'"
    r"|<[\w.]+ object at 0x[0-9a-fA-F]+>"
    r"|\b\w+(?:Error|Exception|Interrupt|Exit):"
)

# Plain words (spec section 7.2): the Tasks pattern, copied, with Trace's own identifiers: spec,
# invariant and test-group numbers, decision numbers, session names and the words that only mean
# something inside the lab.
INTERNAL = re.compile(
    r"\b(?:TR|IT|IL|IC|ID|IR|FD|LST|TF|CAL|MP|R|[XNGAE])\d+\b"
    r"|\b2\.\d defines\b|§|\bTG-(?:ADR|M)\d*"
    r"|\b[Vv]ault\b|\bTaylor\b|\b[Rr]uling\b|\bhandoff\b|\b[Ff]rozen\b|\b[Oo]racle\b"
    r"|\bSession [AB]\b"
)


# ---------- the exit-code table, as docs/cli-look.md writes it ----------


def doc_exit_codes(text: str) -> list[int]:
    """The codes of every markdown table whose first header cell is ``code``, in order."""
    codes: list[int] = []
    in_table = False
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if not cells:
            in_table = False
            continue
        if cells[0].lower() == "code":
            in_table = True
            continue
        if in_table and cells[0].isdigit():
            codes.append(int(cells[0]))
    return codes


# ---------- running the two commands ----------


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err

    def lines(self, stream: str = "err") -> list[str]:
        return [line for line in getattr(self, stream).splitlines() if line.strip()]

    def json(self) -> Any:
        return json.loads(self.out, parse_constant=_no_constant)


def _no_constant(name: str) -> Any:
    raise ValueError(f"JSON constant {name} is not a number")


# What a run reads as when anything but SystemExit leaves ``main``: the console script would
# print a traceback and exit 1, or die of Ctrl-C. Caught here, so a Ctrl-C a command lets out
# fails its test instead of stopping the whole session.
ESCAPED = -1


def _call(module: str, argv: Sequence[Any]) -> Ran:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = _main(module)([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        except BaseException:  # noqa: BLE001
            traceback.print_exc()
            code = ESCAPED
    return Ran(int(code), out.getvalue(), err.getvalue())


def trace(argv: Sequence[Any]) -> Ran:
    """``poisson-trace`` in-process."""
    return _call("poisson_trace.cli", argv)


def trace_import(argv: Sequence[Any]) -> Ran:
    """``poisson-trace-import`` in-process."""
    return _call("poisson_trace.ingest.cli", argv)


def _main(module: str) -> Callable[[list[str]], int]:
    import importlib

    main: Callable[[list[str]], int] = importlib.import_module(module).main
    return main


COMMANDS = {"trace": "poisson_trace.cli", "import": "poisson_trace.ingest.cli"}


def script(command: str, *, prove: str = "present") -> str:
    """The console script's body for ``python -c``: ``prove`` is ``present``, ``absent`` (the
    import fails) or a version string (a fake ``poisson_prove`` at that version is put first)."""
    head = "import sys\n"
    if prove == "absent":
        head += "sys.modules['poisson_prove'] = None\n"
    elif prove != "present":
        head += (
            "import types\nfake = types.ModuleType('poisson_prove')\n"
            f"fake.__version__ = {prove!r}\nsys.modules['poisson_prove'] = fake\n"
        )
    return head + f"from {COMMANDS[command]} import main\nsys.exit(main(sys.argv[1:]))\n"


def run_sub(
    command: str,
    argv: Sequence[Any],
    *,
    prove: str = "present",
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    stdout: Any = subprocess.PIPE,
    timeout: int = 300,
) -> Ran:
    """The command in a fresh interpreter; the streams decoded as UTF-8 with replacement, so a
    stream in another encoding still reads."""
    proc = subprocess.run(
        [sys.executable, "-c", script(command, prove=prove), *[str(a) for a in argv]],
        stdout=stdout, stderr=subprocess.PIPE, env=dict(os.environ if env is None else env),
        cwd=cwd, timeout=timeout,
    )
    out = proc.stdout.decode("utf-8", "replace") if isinstance(proc.stdout, bytes) else ""
    return Ran(proc.returncode, out, proc.stderr.decode("utf-8", "replace"))


def run_module(argv: Sequence[Any], *, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> Ran:
    """``python -m poisson_trace``."""
    proc = subprocess.run(
        [sys.executable, "-m", "poisson_trace", *[str(a) for a in argv]], capture_output=True,
        env=dict(os.environ if env is None else env), cwd=cwd, timeout=300,
    )
    return Ran(proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace"))


def as_ran(result: CliResult) -> Ran:
    return Ran(result.code, result.out, result.err)


# ---------- invocations on the committed fixtures ----------


def where_cs(*extra: str) -> list[str]:
    return ["where", CS_RECORD, "--store", str(CS), *events_args(CS_EVENTS), *extra]


def compare_tau2(ceiling: str, *extra: str) -> list[str]:
    return ["compare", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved", "--max-mde-hr", ceiling, *extra]


def fix_check_tau2(*extra: str) -> list[str]:
    return ["fix-check", TAU2_B, PILOT, "--store", str(TAU2), "--event", "unsolved", "--failing-from", TAU2_A, "--max-mde", "0.20", *extra]


def fix_check_tau2_all(ceiling: str, *extra: str) -> list[str]:
    return ["fix-check", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved", "--inputs", "all", "--max-mde", ceiling, *extra]


def fix_check_he(*extra: str) -> list[str]:
    return ["fix-check", HE_A, HE_B, "--store", str(HUMANEVAL), *events_args(HE_EVENTS), "--inputs", "all", "--max-mde", "0.05", *extra]


def changes_he(*extra: str) -> list[str]:
    return ["changes", HE_A, HE_B, "--store", str(HUMANEVAL), *events_args(HE_EVENTS), "--top", "2", *extra]


def deepeval_import(store: Path | str, run: str, which: str = "a", *extra: str) -> list[str]:
    return [
        "deepeval", str(DEEPEVAL / f"humaneval-{which}.json.gz"), "--store", str(store), "--run", run,
        "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
        "--started", "2026-09-05T18:54:07Z" if which == "a" else "2026-09-05T19:50:09Z", *extra,
    ]


def ragas_import(store: Path | str, run: str, *extra: str) -> list[str]:
    return [
        "ragas", str(RAGAS / "rag-base.jsonl"), "--store", str(store), "--run", run, "--metric", "faithfulness",
        "--cut", "0.5", "--below", "--case-column", "case", "--started", "2025-03-31T06:56:41Z", *extra,
    ]


# ---------- help ----------


def help_blocks(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def help_entries(text: str) -> list[tuple[str, str]]:
    """``(invocation, help text)`` for every entry under ``positional arguments:`` and
    ``options:``: an entry opens on a line indented two spaces, and lines indented deeper
    continue its help."""
    entries: list[tuple[str, str]] = []
    section = False
    for line in text.splitlines():
        if re.match(r"^\S.*:$", line):
            section = line.rstrip(":").strip() in ("positional arguments", "options", "optional arguments")
            continue
        if not section or not line.strip():
            continue
        if re.match(r"^  \S", line):
            m = re.match(r"^  (\S.*?)(?:\s{2,}(\S.*))?$", line)
            assert m is not None
            entries.append((m.group(1), m.group(2) or ""))
        elif entries:
            invocation, words = entries[-1]
            entries[-1] = (invocation, (words + " " + line.strip()).strip())
    return entries


def examples(text: str, starts: Sequence[str]) -> list[str]:
    """Every command in the help that begins with one of ``starts``, a line ending in a
    backslash joined to the next."""
    joined = re.sub(r"\\\n\s*", " ", text)
    found = []
    for line in joined.splitlines():
        stripped = line.strip().removeprefix("$ ")
        if any(stripped.startswith(s + " ") for s in starts):
            found.append(stripped)
    return found


def example_argv(command: str) -> tuple[str, list[str]]:
    """``("trace" | "import", argv)`` for an example command, in either of the import's two
    written forms."""
    words = shlex.split(command)
    if words[0] == "poisson-trace-import":
        return "import", words[1:]
    if words[:2] == ["poisson-trace", "import"]:
        return "import", words[2:]
    assert words[0] == "poisson-trace", command
    return "trace", words[1:]


def usage_line(text: str) -> str:
    """The usage block as one line."""
    block = help_blocks(text)[0]
    assert block.startswith("usage:"), text
    return " ".join(block.split())


def depth_at(usage: str, index: int) -> int:
    """How many brackets are open at ``index`` of a usage line."""
    depth = 0
    for ch in usage[:index]:
        depth += ch == "["
        depth -= ch == "]"
    return depth


@contextlib.contextmanager
def chdir(path: Path):  # type: ignore[no-untyped-def]
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def stderr_shape(lines: Sequence[str]) -> list[str]:
    """The stderr lines that are none of ``error:``, ``note:`` or a two-space continuation of
    one of them."""
    bad = []
    opened = False
    for line in lines:
        if line.startswith(("error: ", "note: ")):
            opened = True
        elif line.startswith("  ") and line.strip() and opened:
            continue
        else:
            bad.append(line)
    return bad


def plain(text: str) -> list[str]:
    return [line for line in text.splitlines() if INTERNAL.search(line)]


# ---------- the corpus ----------


@dataclass(frozen=True)
class Item:
    label: str
    command: str  # "trace" or "import"
    argv: tuple[str, ...]
    expect: int
    kind: str  # "report", "help", "version", "refusal" or "usage"


def prepare(work: Path) -> Path:
    """The folder the corpus runs in: an empty folder, a plain file and an existing SVG to name
    as stores and targets, and a store already holding a run named ``in-use``."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "empty-store").mkdir()
    (work / "a-file").write_text("not a store\n")
    (work / "exists.svg").write_text("<svg/>\n")
    with chdir(work):
        made = trace_import(deepeval_import("in-use-store", "in-use"))
    assert made.code == 0, made.text
    return work


def corpus() -> list[Item]:
    """Every invocation the look is held to, run in a folder ``prepare`` made, in this order."""
    items: list[Item] = []

    def add(label: str, command: str, argv: Sequence[Any], expect: int, kind: str) -> None:
        items.append(Item(label, command, tuple(str(a) for a in argv), expect, kind))

    # results: the README's worked examples on the fixtures, and two imports and their fix check
    add("import deepeval", "import", deepeval_import("imported", "he-a"), 0, "report")
    add("import deepeval, the other version", "import", deepeval_import("imported", "he-b", "b"), 0, "report")
    add("import ragas as JSON", "import", ragas_import("imported", "rag-base", "--json"), 0, "report")
    add("fix-check on the imports", "trace", ["fix-check", "he-a", "he-b", "--store", "imported", "--event", "missed", "--inputs", "all", "--max-mde", "0.02", "--top", "3"], 0, "report")
    add("where", "trace", where_cs("--at", "20", "--at", "40"), 0, "report")
    add("where as JSON", "trace", ["where", TAU2_A, "--store", str(TAU2), "--event", "unsolved", "--json"], 0, "report")
    add("compare, too small to tell", "trace", compare_tau2("1.3", "--at", "10", "--at", "20"), 0, "report")
    add("compare, no significant difference", "trace", compare_tau2("1.457"), 0, "report")
    add("compare as JSON", "trace", compare_tau2("1.3", "--json"), 0, "report")
    add("fix-check with a selecting run", "trace", fix_check_tau2(), 0, "report")
    add("fix-check on every input", "trace", fix_check_he(), 0, "report")
    add("fix-check as JSON", "trace", fix_check_tau2("--json"), 0, "report")
    add("changes", "trace", changes_he(), 0, "report")
    add("changes as JSON", "trace", changes_he("--json"), 0, "report")
    # help and the version
    add("help", "trace", ["--help"], 0, "help")
    for verb in VERBS:
        add(f"{verb} help", "trace", [verb, "--help"], 0, "help")
    add("import help", "import", ["--help"], 0, "help")
    for tool in TOOLS:
        add(f"import {tool} help", "import", [tool, "--help"], 0, "help")
    add("version", "trace", ["--version"], 0, "version")
    add("import version", "import", ["--version"], 0, "version")
    # refusals: the transcript's mistakes, and the paths that ended in a traceback
    fix = ["fix-check", TAU2_B, PILOT, "--store", str(TAU2), "--event", "unsolved"]
    add("an unknown run", "trace", ["where", "no-such-run", "--store", str(CS), "--event", "unresolved"], 1, "refusal")
    add("an unknown event", "trace", ["where", CS_RECORD, "--store", str(CS), "--event", "unresolvd"], 1, "refusal")
    add("a store that is not there", "trace", ["where", CS_RECORD, "--store", "no-such-store", "--event", "unresolved"], 1, "refusal")
    add("a store that is an empty folder", "trace", ["where", CS_RECORD, "--store", "empty-store", "--event", "unresolved"], 1, "refusal")
    add("a store that is a file", "trace", ["where", CS_RECORD, "--store", "a-file", "--event", "unresolved"], 1, "refusal")
    add("a ceiling out of range", "trace", [*fix, "--failing-from", TAU2_A, "--max-mde", "20"], 1, "refusal")
    add("no ceiling", "trace", [*fix, "--failing-from", TAU2_A], 1, "refusal")
    add("no hazard-ratio ceiling", "trace", ["compare", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved"], 1, "refusal")
    add("inputs other than all", "trace", [*fix, "--inputs", "some", "--max-mde", "0.2"], 1, "refusal")
    add("the same run twice", "trace", ["changes", HE_A, HE_A, "--store", str(HUMANEVAL), "--event", "crashed"], 1, "refusal")
    add("no common cell", "trace", ["compare", TAU2_A, PILOT, "--store", str(TAU2), "--event", "unsolved", "--max-mde-hr", "1.5"], 1, "refusal")
    add("a bootstrap of none", "trace", where_cs("--boot", "0"), 1, "refusal")
    add("an SVG into a folder that is not there", "trace", where_cs("--svg", "no-such-dir/curve.svg"), 1, "refusal")
    add("an SVG over a file", "trace", where_cs("--svg", "exists.svg"), 1, "refusal")
    add("an SVG onto a folder", "trace", where_cs("--svg", "empty-store"), 1, "refusal")
    add("the selecting run as an arm", "trace", [*fix, "--failing-from", TAU2_B, "--max-mde", "0.2"], 1, "refusal")
    add("a file that is not there", "import", ["deepeval", "no-such-file.json", "--store", "store2", "--run", "x", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name"], 1, "refusal")
    add("a metric no case carries", "import", ["deepeval", str(DEEPEVAL / "humaneval-a.json.gz"), "--store", "store2", "--run", "x", "--metric", "Tests Pased", "--cut", "recorded", "--case", "name"], 1, "refusal")
    add("a column the table lacks", "import", ["ragas", str(RAGAS / "rag-base.jsonl"), "--store", "store2", "--run", "x", "--metric", "faithfulnes", "--cut", "0.5", "--below", "--case-column", "case"], 1, "refusal")
    add("a tool not in this install", "import", ["otel", "x.json", "--store", "store2", "--run", "x"], 1, "refusal")
    add("a start with no zone", "import", ragas_import("store2", "x")[:-2] + ["--started", "2025-03-31T06:56:41"], 1, "refusal")
    add("a start that is not a time", "import", ragas_import("store2", "x")[:-2] + ["--started", "yesterday"], 1, "refusal")
    add("a cut with no side", "import", [w for w in ragas_import("store2", "x") if w != "--below"], 1, "refusal")
    add("a run name in use", "import", deepeval_import("in-use-store", "in-use"), 1, "refusal")
    # a refusal stays on stderr in text when --json was asked for
    add("an unknown run, as JSON", "trace", ["where", "no-such-run", "--store", str(CS), "--event", "unresolved", "--json"], 1, "refusal")
    add("a store that is not there, as JSON", "trace", [*fix, "--inputs", "all", "--max-mde", "0.2", "--json"][:3] + ["--store", "no-such-store", "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2", "--json"], 1, "refusal")
    add("a metric no case carries, as JSON", "import", ["deepeval", str(DEEPEVAL / "humaneval-a.json.gz"), "--store", "store2", "--run", "x", "--metric", "Tests Pased", "--cut", "recorded", "--case", "name", "--json"], 1, "refusal")
    # the command line is wrong
    add("no verb", "trace", [], 2, "usage")
    add("an unknown verb", "trace", ["bogus", CS_RECORD, "--store", str(CS), "--event", "unresolved"], 2, "usage")
    add("an unknown option", "trace", where_cs("--bogus"), 2, "usage")
    add("a value not among the choices", "trace", where_cs("--by", "wall"), 2, "usage")
    add("a value that is not an integer", "trace", where_cs("--boot", "many"), 2, "usage")
    add("an abbreviated option", "trace", ["where", CS_RECORD, "--store", str(CS), "--ev", "unresolved"], 2, "usage")
    add("a run missing", "trace", ["compare", TAU2_A, "--store", str(TAU2), "--event", "unsolved", "--max-mde-hr", "1.5"], 2, "usage")
    add("no tool", "import", [], 2, "usage")
    add("an import flag missing", "import", deepeval_import("store2", "x")[:-2][: -2] + ["--started", "2026-09-05T18:54:07Z"], 2, "usage")
    add("an import value not among the choices", "import", [*deepeval_import("store2", "x")[:-4], "--case", "identifier"], 2, "usage")
    add("an abbreviated import option", "import", ["deepeval", str(DEEPEVAL / "humaneval-a.json.gz"), "--sto", "store2", "--run", "x", "--metric", "Tests Passed", "--cut", "recorded", "--case", "name"], 2, "usage")
    return items


def run_item(item: Item) -> Ran:
    return (trace if item.command == "trace" else trace_import)(item.argv)
