"""The setup a person's own coding agent follows: ``poisson-trace init --agent`` writes the
skill ``poisson-trace-setup`` (an Agent Skills ``SKILL.md``, in the shared Poisson setup-file
format, version 1) and the prompt that invokes it into the two folders coding agents read
skills from, and nothing else. The skill's text is the template packaged beside this module,
``poisson-trace-setup/SKILL.md``, with the version line filled in; the tool makes no model call
and reads no key, and the agent does the work.

An existing file of the four is refused unless ``--force``, which replaces those four only;
``--print`` prints the skill and writes nothing. Nothing else in the repository is touched: no
``AGENTS.md``, no ``CLAUDE.md``, no rules file of the person's.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import poisson_trace
from poisson_trace import look

SKILL = "poisson-trace-setup"
# where coding agents read skills from: Codex and Cursor read the first, Claude Code and Cursor
# the second
FOLDERS: tuple[str, ...] = (".agents/skills", ".claude/skills")
PROMPT = (
    "Use the poisson-trace-setup skill in this repository: set Poisson Trace up for me to "
    "review, then stop."
)
TEMPLATE = Path(__file__).resolve().parent / SKILL / "SKILL.md"
_VERSION_LINE = re.compile(r"^(  poisson-tool-version:).*$", re.MULTILINE)
NEXT = "give your coding agent the prompt above, then review what it wrote"


class Refused(look.Refused):
    """``init --agent`` refuses: one sentence, exit 1, nothing written."""


def _and(words: Sequence[str]) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


@dataclass(frozen=True)
class Written:
    """What ``init --agent`` did: the files as the person sees them, and the skill's text."""

    wrote: tuple[str, ...]
    skill: str
    sentence: str


def skill_text() -> str:
    """The skill as it is written: the packaged template with the version filled in."""
    text = TEMPLATE.read_text(encoding="utf-8")
    version = poisson_trace.__version__
    filled, n = _VERSION_LINE.subn(lambda m: f'{m.group(1)} "{version}"', text, count=1)
    if n != 1:
        raise look.Failed("the packaged skill has no version line to fill in")
    return filled


def files() -> list[tuple[str, str]]:
    """The four files, relative to the repository, with the text of each."""
    skill = skill_text()
    return [
        (f"{folder}/{SKILL}/{name}", text)
        for folder in FOLDERS
        for name, text in (("SKILL.md", skill), ("prompt.txt", PROMPT + "\n"))
    ]


def _shown(repo: str | None, rel: str) -> str:
    return rel if repo is None else os.path.join(repo, rel)


def write_setup(repo: str | None, *, force: bool, typed: Sequence[str]) -> Written:
    """The four files written into ``repo`` (the current folder when None; no root is looked
    for). Every path is checked before anything is written, so a refusal leaves nothing half
    written. ``typed`` is the command as given, for the refusal's next line."""
    folder = Path("." if repo is None else repo)
    if repo is not None and (repo == "" or not folder.is_dir()):
        why = "is not a folder" if folder.exists() else "does not exist"
        raise Refused(f"--repo {look.word(repo)} {why}; the setup is written into a folder")
    held = files()
    for rel, _ in held:
        parts = Path(rel).parts
        for depth in range(1, len(parts)):
            above = folder.joinpath(*parts[:depth])
            if above.exists() and not above.is_dir():
                raise Refused(
                    f"{_shown(repo, str(Path(*parts[:depth])))} is a file, and the setup needs "
                    "a folder there"
                )
        if (folder / rel).is_dir():
            raise Refused(f"{_shown(repo, rel)} is a folder, and the setup writes a file there")
    existing = [
        _shown(repo, rel)
        for rel, _ in held
        if (folder / rel).exists() or (folder / rel).is_symlink()
    ]
    if existing and not force:
        raise Refused(
            f"{_and(existing)} {'exists' if len(existing) == 1 else 'exist'} already; "
            "init --agent replaces the four files it writes only with --force",
            look.command("poisson-trace", *typed, "--force"),
        )
    for rel, text in held:
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # written beside and moved into place: a link standing there is replaced, never written
        # through to the file it points at
        staged = path.with_name(f".{path.name}.poisson-trace-new")
        try:
            staged.write_text(text, encoding="utf-8", newline="\n")
            os.replace(staged, path)
        except OSError as e:
            staged.unlink(missing_ok=True)
            raise Refused(f"cannot write {_shown(repo, rel)} ({look.why(e)})") from e
    shown = tuple(_shown(repo, rel) for rel, _ in held)
    sentence = f"wrote the setup for your coding agent ({look.count(len(shown))} files)"
    return Written(shown, skill_text(), sentence)
