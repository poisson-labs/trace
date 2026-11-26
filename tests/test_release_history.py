"""The release's history check, ``.github/release/history.py``: who every commit is by, and
that none names an assistant.

A release is cut only from a history in which every commit is authored and committed under the
one work identity, ``TaylorKolasinski <taylor@poissonlabs.ai>``, so the check holds the name and
the address of the author and of the committer of every commit reachable from ``HEAD``, beside
the assistant attribution it already refuses.

- the check passes a history made under the work identity alone, and says how many commits it
  read;
- it fails, exit 1, on a commit whose author or committer has another address or another name,
  and its line names the commit, the role and what it found: an address on another domain,
  another address on the work domain, the address GitHub commits a merge made on its site with,
  and the work address under another spelling of the name;
- it still fails on a message that names an assistant, and says both faults of one commit on
  one line;
- one faulty commit anywhere in the history fails it, not the newest alone;
- the release workflow runs it over the whole history, in the job every other job waits for.
- CI runs it too, on every event, over the whole history: on a pull request over the pull
  request's own commits, so a commit under another identity shows before it reaches main.

Each history is made here, in a repository of its own under the test's folder, with the
identities given on the command line, so the test reads nothing of the checkout's own history
and passes in a shallow clone and on a merge commit a runner made.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from docs_support import jobs

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / ".github" / "release" / "history.py"
RELEASE = REPO / ".github" / "workflows" / "release.yml"

NAME = "TaylorKolasinski"
ADDRESS = "taylor@poissonlabs.ai"
WORK = (NAME, ADDRESS)


def _git(repo: Path, *argv: str, env: dict[str, str] | None = None) -> str:
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *argv],
                          cwd=repo, capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _history(repo: Path, commits: list[tuple[tuple[str, str], tuple[str, str], str]]) -> list[str]:
    """A repository holding one commit for each (author, committer, message), oldest first;
    the commits' full hashes, in that order."""
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    made = []
    for n, (author, committer, message) in enumerate(commits):
        env = {**os.environ, "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
               "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1],
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        _git(repo, "commit", "--quiet", "--allow-empty", "-m", message or f"change {n}", env=env)
        made.append(_git(repo, "rev-parse", "HEAD"))
    return made


def _check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECK)], cwd=repo, capture_output=True, text=True, timeout=120)


def test_a_history_under_the_work_identity_passes(tmp_path: Path) -> None:
    _history(tmp_path / "repo", [(WORK, WORK, "first"), (WORK, WORK, "second"), (WORK, WORK, "third")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.strip() == "every commit is clean (3 checked)"


OTHERS = [
    ("an address on another domain", ("TaylorKolasinski", "someone@example.com")),
    ("another address on the work domain", ("TaylorKolasinski", "work@poissonlabs.ai")),
    ("the address GitHub commits with", ("GitHub", "noreply@github.com")),
    ("a GitHub account's hidden address", ("TaylorKolasinski", "1234567+TaylorKolasinski@users.noreply.github.com")),
    ("the work address under another spelling of the name", ("taylor kolasinski", "taylor@poissonlabs.ai")),
    ("the work address under another name", ("Someone Else", "taylor@poissonlabs.ai")),
]


@pytest.mark.parametrize("role", ["author", "committer"])
@pytest.mark.parametrize(("what", "other"), OTHERS, ids=[what for what, _ in OTHERS])
def test_another_identity_fails_and_is_named(tmp_path: Path, role: str, what: str, other: tuple[str, str]) -> None:
    author, committer = (other, WORK) if role == "author" else (WORK, other)
    (sha,) = _history(tmp_path / "repo", [(author, committer, "a change")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 1, (what, ran.stdout + ran.stderr)
    assert ran.stdout.splitlines() == [f"{sha[:12]}: {role} {other[0]} <{other[1]}>"], ran.stdout


def test_both_roles_of_one_commit_are_named_on_its_line(tmp_path: Path) -> None:
    author, committer = ("Someone Else", "someone@example.com"), ("GitHub", "noreply@github.com")
    (sha,) = _history(tmp_path / "repo", [(author, committer, "a change")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 1
    assert ran.stdout.splitlines() == [
        f"{sha[:12]}: author Someone Else <someone@example.com>; committer GitHub <noreply@github.com>"]


@pytest.mark.parametrize("message", [
    "a change\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
    "a change\n\nco-authored-by: GitHub Copilot <copilot@github.com>",
    "a change\n\nGenerated with Claude Code",
    "a change\n\nGenerated by AI",
])
def test_a_message_that_names_an_assistant_still_fails(tmp_path: Path, message: str) -> None:
    (sha,) = _history(tmp_path / "repo", [(WORK, WORK, message)])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 1, ran.stdout + ran.stderr
    assert ran.stdout.splitlines() == [f"{sha[:12]}: an assistant named in the message"]


def test_a_co_author_who_is_a_person_passes(tmp_path: Path) -> None:
    _history(tmp_path / "repo", [(WORK, WORK, "a change\n\nCo-authored-by: Ada Lovelace <ada@example.com>")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_both_faults_of_one_commit_are_on_one_line(tmp_path: Path) -> None:
    other = ("Someone Else", "someone@example.com")
    (sha,) = _history(tmp_path / "repo", [(other, WORK, "a change\n\nCo-Authored-By: Claude <noreply@anthropic.com>")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 1
    assert ran.stdout.splitlines() == [f"{sha[:12]}: author Someone Else <someone@example.com>; an assistant named in the message"]


def test_one_faulty_commit_deep_in_the_history_fails_it(tmp_path: Path) -> None:
    other = ("TaylorKolasinski", "someone@example.com")
    made = _history(tmp_path / "repo", [(WORK, WORK, "first"), (WORK, other, "second"), (WORK, WORK, "third"), (WORK, WORK, "fourth")])
    ran = _check(tmp_path / "repo")
    assert ran.returncode == 1
    assert ran.stdout.splitlines() == [f"{made[1][:12]}: committer TaylorKolasinski <someone@example.com>"]


def test_no_commit_is_let_through_by_its_hash() -> None:
    assert not re.search(r"\b[0-9a-f]{40}\b", CHECK.read_text(encoding="utf-8")), "no commit is excepted by its hash"


def test_the_release_runs_it_over_the_whole_history() -> None:
    held = jobs(RELEASE.read_text(encoding="utf-8"))
    job = held["check"]
    assert re.search(r"(?m)^        run: python \.github/release/history\.py$", job), "the check job runs the history check"
    assert re.search(r"(?m)^          fetch-depth: 0$", job), "on the whole history"
    (name,) = re.findall(r"(?m)^      - name: (.+)\n        run: python \.github/release/history\.py$", job)
    assert re.search(r"(?i)work identity", name) and re.search(r"(?i)assistant", name), name
    # every other job waits for it, itself or through the jobs it needs
    needs = {job: re.findall(r"[a-z][a-z-]*", found.group(1)) if (found := re.search(r"(?m)^    needs: (.+)$", body)) else []
             for job, body in held.items()}

    def reaches(job: str) -> bool:
        return "check" in needs[job] or any(reaches(needed) for needed in needs[job])

    assert [job for job in held if job != "check" and not reaches(job)] == []


def test_ci_runs_it_on_every_pull_request_and_push() -> None:
    found = {name: body for name, body in jobs().items() if re.search(r"python \.github/release/history\.py", body)}
    assert len(found) == 1, sorted(found)
    (job,) = found.values()
    assert not re.search(r"(?m)^    if:", job), "no event skips it"
    assert re.search(r"(?m)^    timeout-minutes: \d+$", job)
    assert re.search(r"(?m)^          fetch-depth: 0$", job), "on the whole history"
    # A pull request is checked out as a merge commit the runner makes, committed as GitHub.
    # The check reads the pull request's own newest commit; the expression is empty on any
    # other event, which then checks out the commit the event is for.
    assert re.search(r"(?m)^          ref: \$\{\{ github\.event\.pull_request\.head\.sha \}\}$", job), "the pull request's own commits"
