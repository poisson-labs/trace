"""Every commit reachable from HEAD is by the work identity, and none names an AI assistant.

    python .github/release/history.py

A commit passes when its author and its committer are both the work identity, name and
address, and its message carries no assistant's attribution line. No commit is excepted, and
neither is one GitHub made: a merge made on the site is committed as GitHub, so a pull request
is merged from a checkout, where the merge is committed and signed under the work identity.
Prints one line for each commit that fails, saying what it found; exits 1 if any does. Needs
the whole history (``fetch-depth: 0``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable

#: The one identity a commit is authored and committed under.
WORK_NAME = "TaylorKolasinski"
WORK_ADDRESS = "taylor@poissonlabs.ai"
#: An attribution line an assistant leaves, matched case-insensitively (Prove's rule).
ATTRIBUTION = re.compile(
    r"^co-authored-by:.*\b(claude|anthropic|openai|chatgpt|gpt|copilot|gemini|cursor|codex)\b"
    r"|generated (with|by) .*\b(claude|chatgpt|copilot|gemini|cursor|codex|ai)\b",
    re.IGNORECASE | re.MULTILINE,
)
#: What ``git log`` is asked for, one record a commit: the hash, the author's name and address,
#: the committer's, then the message.
FORMAT = "%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x1e"


def problems(commits: Iterable[tuple[str, str, str, str, str, str]]) -> list[str]:
    """``(hash, author name, author address, committer name, committer address, message)`` for
    each commit -> one line for each commit that fails."""
    out = []
    for sha, author, author_address, committer, committer_address, message in commits:
        why = [f"{role} {name} <{address}>"
               for role, name, address in (("author", author, author_address),
                                           ("committer", committer, committer_address))
               if (name, address) != (WORK_NAME, WORK_ADDRESS)]
        if ATTRIBUTION.search(message):
            why.append("an assistant named in the message")
        if why:
            out.append(f"{sha[:12]}: " + "; ".join(why))
    return out


def commits() -> list[tuple[str, str, str, str, str, str]]:
    raw = subprocess.run(["git", "log", f"--format={FORMAT}"], capture_output=True, text=True,
                         check=True).stdout
    records = [r.strip("\n").split("\x00", 5) for r in raw.split("\x1e") if r.strip()]
    return [(sha, an, ae, cn, ce, message) for sha, an, ae, cn, ce, message in records]


def main() -> int:
    read = commits()
    found = problems(read)
    print("\n".join(found) if found else f"every commit is clean ({len(read)} checked)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
