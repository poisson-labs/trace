"""No commit reachable from HEAD names an AI assistant in its message.

    python .github/release/history.py

Prove's release check (poisson-labs/prove, .github/lanes/history.py) also holds every author
and committer address to the work domain. That half is left out here until Trace's history
rewrite before 0.1.0: some merge commits on main carry another address. Prints each commit
that fails; exits 1 if any does. Needs the whole history (``fetch-depth: 0``).
"""

from __future__ import annotations

import re
import subprocess
import sys

#: An attribution line an assistant leaves, matched case-insensitively (Prove's rule).
ATTRIBUTION = re.compile(
    r"^co-authored-by:.*\b(claude|anthropic|openai|chatgpt|gpt|copilot|gemini|cursor|codex)\b"
    r"|generated (with|by) .*\b(claude|chatgpt|copilot|gemini|cursor|codex|ai)\b",
    re.IGNORECASE | re.MULTILINE,
)


def main() -> int:
    raw = subprocess.run(["git", "log", "--format=%H%x00%B%x1e"], capture_output=True, text=True,
                         check=True).stdout
    records = [r.strip("\n").split("\x00", 1) for r in raw.split("\x1e") if r.strip()]
    found = [f"{sha[:12]}: an assistant named in the message" for sha, message in records
             if ATTRIBUTION.search(message)]
    print("\n".join(found) if found else f"every commit is clean ({len(records)} checked)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
