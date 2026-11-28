"""Checks that re-taken pins moved only floats, and only a little.

Run from the repository's root, with the build installed, once the pins are re-taken::

    python tests/fixtures/portable/check_moves.py --base COMMIT NODE [NODE ...] [--pins FILE ...]

``COMMIT`` is the commit the old pins were taken on, and each ``NODE`` is a pytest node id or test
file whose pins were re-taken. For every pin that moved it checks, and prints one line:

1. Only pinned values moved. Every ``tests/fixtures/*/main-pins.json`` that differs from the
   base, every test module among the nodes that differs, and every ``--pins`` file, is read at
   the base and at the head. The two have the same labels in the same order, and only strings
   moved (a test module: the same syntax tree, string literals apart). So no exit code, label or
   other value moved. A string that moved and is not a SHA-256 digest is an output's text, held
   to step 4 directly.
2. The give-back. The nodes run at the base, in a scratch copy of the base commit with its own
   ``src`` first on the path, and the text behind every SHA-256 digest the tests compute is
   recorded. Every old digest that moved is among them: the old output, regenerated at the base,
   gives the old pinned digest.
3. The nodes run at the head the same way, and every new digest is among those recorded.
4. Each old text is held to its new one. A text that is not one JSON document (a plain report,
   stderr) is the same byte for byte. A JSON document has the same keys in the same order, the
   same strings, integers, booleans and nulls, and every float within
   ``max(1e-12 * |old|, 1e-13)`` of the old one. Some pins hash one invocation as
   ``f"{exit code}\n{stdout}\n{stderr}"``; when its stdout is one JSON document, the exit code
   and stderr are the same byte for byte and the document is held as above.
5. One line per moved pin: where it is held, the old digest, the new digest and the largest float
   change. The exit code is 1 if any move is refused, and 0 if every one holds.
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DIGEST = re.compile(r"^[0-9a-f]{64}$")
RELATIVE = 1e-12
ABSOLUTE = 1e-13

# ---------- step 4: one old text against its new one ----------


class Refused(Exception):
    """A move the rules do not allow."""


def _float_bound(old: float) -> float:
    return max(RELATIVE * abs(old), ABSOLUTE)


def _typed(text: str) -> Any:
    """``text`` as one JSON document, with every number tagged by how it is written, and every
    object as its list of pairs so the order of keys is kept."""
    return json.loads(
        text,
        parse_int=lambda s: ("int", int(s)),
        parse_float=lambda s: ("float", float(s)),
        parse_constant=lambda s: ("constant", s),
        object_pairs_hook=lambda pairs: ("object", pairs),
    )


def _walk(old: Any, new: Any, at: str) -> float:
    """The largest float change from ``old`` to ``new``; raises ``Refused`` on any other change."""
    if isinstance(old, tuple) and isinstance(new, tuple) and old[0] == new[0] == "object":
        old_keys, new_keys = [k for k, _ in old[1]], [k for k, _ in new[1]]
        if old_keys != new_keys:
            raise Refused(f"{at or '/'}: the keys moved: {old_keys} -> {new_keys}")
        return max([0.0, *(_walk(o, n, f"{at}/{k}") for (k, o), (_, n) in zip(old[1], new[1], strict=True))])
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            raise Refused(f"{at or '/'}: a list of {len(old)} became one of {len(new)}")
        return max([0.0, *(_walk(o, n, f"{at}/{i}") for i, (o, n) in enumerate(zip(old, new, strict=True)))])
    if isinstance(old, tuple) and isinstance(new, tuple) and old[0] == new[0] == "float":
        change = abs(new[1] - old[1])
        if not change <= _float_bound(old[1]):
            raise Refused(f"{at}: {old[1]!r} -> {new[1]!r}, a change of {change:.3g}, past {_float_bound(old[1]):.3g}")
        return change
    if type(old) is not type(new) or old != new:
        raise Refused(f"{at or '/'}: {_shown(old)} -> {_shown(new)}")
    return 0.0


def _shown(value: Any) -> str:
    if isinstance(value, tuple) and value and value[0] in ("int", "float", "constant"):
        return f"{value[0]} {value[1]!r}"
    if isinstance(value, tuple) and value and value[0] == "object":
        return "an object"
    return repr(value)


def _as_json(text: str) -> Any | None:
    try:
        return _typed(text)
    except ValueError:
        return None


_DECODER = json.JSONDecoder(
    parse_int=lambda s: ("int", int(s)),
    parse_float=lambda s: ("float", float(s)),
    parse_constant=lambda s: ("constant", s),
    object_pairs_hook=lambda pairs: ("object", pairs),
)
_EXIT_LINE = re.compile(r"-?[0-9]+\n")


def _exit_stdout_stderr(text: str) -> tuple[str, Any, str] | None:
    """``text`` as ``(exit code line, stdout as JSON, stderr)`` when it is an invocation written as
    ``f"{exit code}\\n{stdout}\\n{stderr}"`` and its stdout is one JSON document."""
    line = _EXIT_LINE.match(text)
    if line is None or not text.startswith(("{", "["), line.end()):
        return None
    try:
        doc, end = _DECODER.raw_decode(text, line.end())
    except ValueError:
        return None
    if not text.startswith("\n", end):
        return None
    return text[: line.end()], doc, text[end:]


def compare_texts(old: str, new: str) -> float:
    """The largest float change from ``old`` to ``new``, two outputs of one invocation; raises
    ``Refused`` when the move is not one the rules allow."""
    if old == new:
        return 0.0
    old_doc, new_doc = _as_json(old), _as_json(new)
    old_run, new_run = _exit_stdout_stderr(old), _exit_stdout_stderr(new)
    if (old_doc is None or new_doc is None) and old_run is not None and new_run is not None:
        if old_run[0] != new_run[0]:
            raise Refused(f"the exit code moved: {old_run[0].strip()} -> {new_run[0].strip()}")
        if old_run[2] != new_run[2]:
            raise Refused(f"stderr moved: {old_run[2][:200]!r} -> {new_run[2][:200]!r}")
        return _walk(old_run[1], new_run[1], "")
    if old_doc is None or new_doc is None:
        lines_old, lines_new = old.splitlines(), new.splitlines()
        first = next((i for i, (a, b) in enumerate(zip(lines_old, lines_new)) if a != b), min(len(lines_old), len(lines_new)))
        shown_old = lines_old[first] if first < len(lines_old) else "(no line)"
        shown_new = lines_new[first] if first < len(lines_new) else "(no line)"
        raise Refused(f"a text that is not JSON moved at line {first + 1}: {shown_old!r} -> {shown_new!r}")
    return _walk(old_doc, new_doc, "")


# ---------- step 1: the pin storage ----------


def moved_values(old: Any, new: Any, at: str = "") -> Iterator[tuple[str, Any, Any]]:
    """Every leaf that differs between two decoded pin stores, as ``(pointer, old, new)``; raises
    ``Refused`` when their shape differs or a value that is not a string moved."""
    if isinstance(old, dict) and isinstance(new, dict):
        if list(old) != list(new):
            raise Refused(f"{at or '/'}: the labels moved: {sorted(set(old) ^ set(new))[:5]}")
        for key in old:
            yield from moved_values(old[key], new[key], f"{at}/{key}")
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            raise Refused(f"{at or '/'}: a list of {len(old)} became one of {len(new)}")
        for i, (o, n) in enumerate(zip(old, new, strict=True)):
            yield from moved_values(o, n, f"{at}/{i}")
    elif old != new or type(old) is not type(new):
        if not (isinstance(old, str) and isinstance(new, str)):
            raise Refused(f"{at}: a value that is not a text or a digest moved: {old!r} -> {new!r}")
        yield at, old, new


def _module_constants(source: str) -> Any:
    """A test module as data: its syntax tree with every literal string kept, so two versions
    can be compared value by value."""
    tree = ast.parse(source)
    strings: list[str] = []

    class Strip(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, str):
                strings.append(node.value)
                return ast.copy_location(ast.Constant(value=f"<str {len(strings) - 1}>"), node)
            return node

    shape = ast.dump(Strip().visit(tree), include_attributes=False)
    return shape, strings


def storage_moves(name: str, old_text: str, new_text: str) -> list[tuple[str, str, str]]:
    """The values of one pin file that moved, as ``(where, old, new)``."""
    if name.endswith(".json"):
        old, new = json.loads(old_text), json.loads(new_text)
        return [(f"{name}:{at}", o, n) for at, o, n in moved_values(old, new)]
    old_shape, old_strings = _module_constants(old_text)
    new_shape, new_strings = _module_constants(new_text)
    if old_shape != new_shape:
        raise Refused(f"{name}: the module changed beyond the values it pins")
    return [(f"{name}:string {i}", o, n) for i, (o, n) in enumerate(zip(old_strings, new_strings, strict=True)) if o != n]


# ---------- steps 2 and 3: the texts behind the digests ----------

CAPTURE = '''
import base64, hashlib, json, os
_real = hashlib.sha256
_seen = {}


class _Recorded:
    def __init__(self, data=b"", **kwargs):
        self._hash = _real(**kwargs)
        self._data = bytearray()
        self.name, self.digest_size, self.block_size = "sha256", 32, 64
        if data:
            self.update(data)

    def update(self, data):
        data = bytes(data)
        self._data += data
        self._hash.update(data)

    def _keep(self, hexed):
        _seen.setdefault(hexed, bytes(self._data))

    def hexdigest(self):
        hexed = self._hash.hexdigest()
        self._keep(hexed)
        return hexed

    def digest(self):
        raw = self._hash.digest()
        self._keep(raw.hex())
        return raw

    def copy(self):
        twin = _Recorded()
        twin._hash = self._hash.copy()
        twin._data = bytearray(self._data)
        return twin


def _sha256(data=b"", **kwargs):
    return _Recorded(data, **kwargs)


hashlib.sha256 = _sha256


def pytest_sessionfinish(session, exitstatus):
    wanted = set(json.loads(open(os.environ["CHECK_MOVES_WANTED"]).read()))
    held = {d: base64.b64encode(v).decode() for d, v in _seen.items() if d in wanted}
    with open(os.environ["CHECK_MOVES_OUT"], "w") as out:
        json.dump({"exit": int(exitstatus), "texts": held}, out)
'''


def _git(*argv: str) -> bytes:
    return subprocess.run(["git", *argv], cwd=REPO, capture_output=True, check=True).stdout


def _texts(tree: Path, nodes: list[str], wanted: set[str], scratch: Path, side: str) -> tuple[int, dict[str, bytes]]:
    plugin = scratch / "plugin"
    plugin.mkdir(exist_ok=True)
    (plugin / "check_moves_capture.py").write_text(CAPTURE, encoding="utf-8")
    want_file, out_file = scratch / f"{side}-wanted.json", scratch / f"{side}-texts.json"
    want_file.write_text(json.dumps(sorted(wanted)), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "COLUMNS", "PYTHONPATH")}
    env.update(PYTHONPATH=os.pathsep.join([str(plugin), str(tree / "src")]), PYTHONDONTWRITEBYTECODE="1",
               CHECK_MOVES_WANTED=str(want_file), CHECK_MOVES_OUT=str(out_file))
    basetemp = scratch / f"{side}-tmp"
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "check_moves_capture",
                    "--basetemp", str(basetemp), *nodes], cwd=tree, env=env, check=False)
    done = json.loads(out_file.read_text(encoding="utf-8"))
    return done["exit"], {d: base64.b64decode(v) for d, v in done["texts"].items()}


def _base_tree(commit: str, into: Path) -> Path:
    with tarfile.open(fileobj=BytesIO(_git("archive", "--format=tar", commit))) as archive:
        archive.extractall(into, filter="data")
    return into


def _storage(commit: str, nodes: list[str], extra: list[str]) -> list[str]:
    changed = _git("diff", "--name-only", commit, "--", "tests").decode().split()
    names = [n for n in changed if re.fullmatch(r"tests/fixtures/[^/]+/main-pins\.json", n)]
    for node in nodes:
        module = node.split("::", 1)[0]
        if module in changed and module not in names:
            names.append(module)
    return names + [n for n in extra if n not in names]


def _decoded(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check(commit: str, nodes: list[str], extra: list[str]) -> int:
    refused = 0
    moves: list[tuple[str, str, str]] = []
    for name in _storage(commit, nodes, extra):
        old_text = _git("show", f"{commit}:{name}").decode("utf-8")
        new_text = (REPO / name).read_text(encoding="utf-8")
        try:
            moves.extend(storage_moves(name, old_text, new_text))
        except Refused as why:
            print(f"REFUSED {name}: {why}")
            refused += 1
    digests = [(w, o, n) for w, o, n in moves if DIGEST.match(o) and DIGEST.match(n)]
    texts = [(w, o, n) for w, o, n in moves if not (DIGEST.match(o) and DIGEST.match(n))]
    for where, old, new in texts:
        try:
            largest = compare_texts(old, new)
            print(f"held    {where}  text  text  largest float change {largest:.3g}")
        except Refused as why:
            print(f"REFUSED {where}: {why}")
            refused += 1
    if digests:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            base = _base_tree(commit, scratch / "base")
            base_exit, before = _texts(base, nodes, {o for _, o, _ in digests}, scratch, "base")
            head_exit, after = _texts(REPO, nodes, {n for _, _, n in digests}, scratch, "head")
            if base_exit != 0:
                print(f"note: the nodes did not all pass at {commit} (pytest exit {base_exit})")
            if head_exit != 0:
                print(f"note: the nodes did not all pass at the head (pytest exit {head_exit})")
            for where, old, new in digests:
                if old not in before:
                    print(f"REFUSED {where}: the base run did not give the old digest {old[:12]}…")
                    refused += 1
                    continue
                if new not in after:
                    print(f"REFUSED {where}: the head run did not give the new digest {new[:12]}…")
                    refused += 1
                    continue
                old_text, new_text = _decoded(before[old]), _decoded(after[new])
                try:
                    if old_text is None or new_text is None:
                        raise Refused("a binary output moved")
                    largest = compare_texts(old_text, new_text)
                    print(f"held    {where}  {old[:12]}… -> {new[:12]}…  largest float change {largest:.3g}")
                except Refused as why:
                    print(f"REFUSED {where}  {old[:12]}… -> {new[:12]}…: {why}")
                    refused += 1
    print(f"{len(moves)} moved values, {refused} refused")
    return 1 if refused else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True, help="the commit the old pins were taken on")
    parser.add_argument("--pins", action="append", default=[], help="another file that holds pins, from the root")
    parser.add_argument("nodes", nargs="+", help="the pin tests whose pins were re-taken")
    args = parser.parse_args()
    raise SystemExit(check(args.base, args.nodes, args.pins))


if __name__ == "__main__":
    main()
