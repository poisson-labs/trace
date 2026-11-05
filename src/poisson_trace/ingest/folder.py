"""The folder resolver: what a folder of results holds, read without reading a row (spec
section 18.3.1, SG8 and SG17, as FI1 to FI7 rule it).

``resolve(path, tool=None)`` says what the folder at ``path`` is, in this order:

1. a Prove run folder (``manifest.json`` beside ``episodes/``): the run, read where it is;
2. a folder Prove reads as a store (FI4): the one run it holds, or refused naming every run's
   folder when it holds several (FI2, FI5);
3. a saved pull folder (``pull.json``, ``poisson.raw-pull/1``, section 18.3.2): its tool's
   reader on the files it lists, in its order, each there, inside the folder and of the digest
   listed; refused when any of that is not so or the tool is not in this install;
4. an unpacked Inspect log (``header.json`` beside ``samples/``): one Inspect run, the folder
   itself the one "file" the Inspect reader reads (FI3, TF10's RD7); refused, saying so, in an
   install without that reader, and when another tool is named;
5. otherwise one tool's result files: the regular files directly in it, in the order of their
   names, each claimed by the reader whose ``looks_like`` claims it (the readers' own detectors
   are the signature table, FI1). Hidden files, names starting with ``_`` or ``README``, files
   no reader claims and subfolders are left out (FI7). Files of two tools are refused unless a
   tool is named, which reads its files alone.

Whether several files of one tool are one run or several (FI6) needs their cases, so the import
decides it after reading them (``ingest/cli.py``). Resolving writes nothing, and Prove is asked
through the writer, the one module under ``ingest/`` that imports it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from poisson_trace.ingest.rows import Refusal

#: What a folder can be: a Prove run folder, a store of one run, a saved pull, one tool's files.
KINDS: tuple[str, ...] = ("run", "store", "pull", "files")
#: The schema a saved pull's ``pull.json`` names (section 18.3.2).
PULL_SCHEMA = "poisson.raw-pull/1"
PULL = "pull.json"
# the names a folder of results holds that are never results (section 18.3.1 step 3)
_LEFT_OUT = (".", "_", "README")


@dataclass(frozen=True)
class Resolved:
    """What a folder holds. ``name`` is the folder's own name, the run's name by default;
    ``tool`` and ``files`` (absolute when ``path`` is) are a pull's or a tool folder's;
    ``store`` and ``run_id`` are a Prove folder's: the store the run is read from and its id."""

    kind: str
    path: Path
    name: str
    tool: str | None = None
    files: tuple[Path, ...] = ()
    store: Path | None = None
    run_id: str | None = None


def _is_dir(path: Path) -> bool:
    """Whether ``path`` is a folder; a path the system cannot look up (a name too long for it)
    is not one."""
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def is_folder(word: str) -> bool:
    """Whether the word a command line gave names a folder, never raising."""
    return _is_dir(Path(word))


def resolve(path: Path | str, tool: str | None = None) -> Resolved:
    """What the folder at ``path`` holds, or a ``Refusal`` naming it; ``tool`` names the tool
    whose files are wanted, as ``import TOOL DIR`` gives it."""
    folder = Path(path)
    if not _is_dir(folder):
        if _is_file(folder):
            raise Refusal(f"{folder} is a file, not a folder of results")
        raise Refusal(f"there is no folder at {folder}")
    name = folder.name or folder.resolve().name
    if _is_dir(folder / "episodes") and _is_file(folder / "manifest.json"):
        return Resolved("run", folder, name, store=folder.parent, run_id=name)
    from poisson_trace.ingest.writer import runs_in

    held = runs_in(folder)
    if len(held) == 1:
        return Resolved("store", folder, name, store=folder, run_id=held[0])
    if held:
        each = [str(folder / run_id) for run_id in held]
        raise Refusal(
            f"{folder} is a store of {len(held)} runs, not one run: give the folder of the run "
            f"you mean, one of {', '.join(each)}",
            *(f"poisson-trace runs --store {_quoted(str(folder))}",),
        )
    if _is_file(folder / PULL):
        return _pull(folder, name, tool)
    if _is_file(folder / "header.json") and _is_dir(folder / "samples"):
        return _inspect(folder, name, tool)
    return _files(folder, name, tool)


def _inspect(folder: Path, name: str, tool: str | None) -> Resolved:
    """An unpacked Inspect log: one run, read by the Inspect reader from the folder itself."""
    from poisson_trace.ingest.cli import present

    if "inspect" not in present():
        raise Refusal(
            f"{folder} is an unpacked Inspect log (header.json beside samples/), and this install "
            "has no Inspect reader to read it"
        )
    if tool is not None and tool != "inspect":
        raise Refusal(
            f"{folder} is an unpacked Inspect log (header.json beside samples/), not the {tool} "
            "reader's files"
        )
    return Resolved("files", folder, name, tool="inspect", files=(folder,))


def _quoted(text: str) -> str:
    from poisson_trace.look import word

    return word(text)


# ---------- a saved pull ----------


def _pull(folder: Path, name: str, tool: str | None) -> Resolved:
    from poisson_trace.ingest.cli import present

    said = folder / PULL
    try:
        doc = json.loads(said.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        raise Refusal(f"{said} is not a pull record: it cannot be read as JSON") from None
    if not isinstance(doc, Mapping):
        raise Refusal(f"{said} is not a pull record: it is not a JSON object")
    if doc.get("schema") != PULL_SCHEMA:
        raise Refusal(
            f"{said} names the schema {json.dumps(doc.get('schema'))}; this install reads "
            f"{PULL_SCHEMA}"
        )
    pulled = doc.get("tool")
    if not isinstance(pulled, str) or not pulled:
        raise Refusal(f"{said} names no tool")
    if pulled not in present():
        raise Refusal(
            f"{said} is a pull of {pulled}, which this install cannot read; it reads: "
            f"{', '.join(present()) or 'nothing'}"
        )
    if tool is not None and tool != pulled:
        raise Refusal(f"{said} is a pull of {pulled}, not of {tool}")
    listed = doc.get("files")
    if not isinstance(listed, Sequence) or isinstance(listed, str) or not listed:
        raise Refusal(f"{said} lists no file, so there is nothing to read")
    files: list[Path] = []
    inside = folder.resolve()
    for entry in listed:
        files.append(_listed(folder, inside, said, entry))
    if len(set(files)) != len(files):
        raise Refusal(f"{said} lists one file twice")
    return Resolved("pull", folder, name, tool=pulled, files=tuple(files))


def _listed(folder: Path, inside: Path, said: Path, entry: Any) -> Path:
    """One file ``pull.json`` lists: there, inside the folder, and of the digest listed."""
    if not isinstance(entry, Mapping):
        raise Refusal(f"{said} lists a file that is not an object with a path and a sha256")
    given, digest = entry.get("path"), entry.get("sha256")
    if not isinstance(given, str) or not given or not isinstance(digest, str):
        raise Refusal(f"{said} lists a file without a path or a sha256")
    relative = PurePosixPath(given)
    path = folder.joinpath(*relative.parts)
    try:
        within = not relative.is_absolute() and path.resolve().is_relative_to(inside)
    except (OSError, ValueError):
        within = False
    if not within:
        raise Refusal(f"{said} lists {given}, which is outside the folder")
    try:
        raw = path.read_bytes()
    except (OSError, ValueError):
        raise Refusal(f"{said} lists {given}, which is not in the folder") from None
    if hashlib.sha256(raw).hexdigest() != digest.lower():
        raise Refusal(
            f"{given} is not the file {said} lists: its sha256 differs, so it changed after the "
            "pull"
        )
    return path


# ---------- one tool's files ----------


def _detectors() -> dict[str, Any]:
    """Each reader in the install that has a detector, in the order the import names them."""
    from poisson_trace.ingest.cli import present, reader

    out = {}
    for tool in present():
        module = reader(tool)
        if hasattr(module, "looks_like"):
            out[tool] = module.looks_like
    return out


def claims(folder: Path) -> list[tuple[Path, str]]:
    """Each file directly in ``folder`` some reader claims, with that reader, in the order of
    the files' names (by code point); hidden, journal and README files left out."""
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name)
    except OSError as e:
        from poisson_trace.look import why

        raise Refusal(f"the folder {folder} could not be read ({why(e)})") from e
    detectors = _detectors()
    found: list[tuple[Path, str]] = []
    for entry in entries:
        if entry.name.startswith(_LEFT_OUT) or not _is_file(entry):
            continue
        for tool, looks_like in detectors.items():
            if looks_like(entry) is not None:
                found.append((entry, tool))
                break
    return found


def _files(folder: Path, name: str, tool: str | None) -> Resolved:
    found = claims(folder)
    if tool is not None:
        mine = tuple(path for path, owner in found if owner == tool)
        if not mine:
            held = f"; it holds {_held(found)}" if found else ""
            raise Refusal(f"{folder} holds no file the {tool} reader reads{held}")
        return Resolved("files", folder, name, tool=tool, files=mine)
    if not found:
        raise Refusal(
            f"{folder} holds no result file this install reads (hidden files, names starting "
            "with _ or README, and subfolders are left out)"
        )
    tools = list(dict.fromkeys(owner for _, owner in found))
    if len(tools) > 1:
        raise Refusal(
            f"{folder} holds the files of {len(tools)} tools, {_held(found)}; one import reads "
            "one tool's: name the tool before the folder",
            *(f"poisson-trace import {t} {_quoted(str(folder))}" for t in tools),
        )
    return Resolved("files", folder, name, tool=tools[0], files=tuple(p for p, _ in found))


def _held(found: Sequence[tuple[Path, str]]) -> str:
    return ", ".join(f"{path.name} ({owner})" for path, owner in found)
