"""What a release must agree with, checked by the release workflow (.github/workflows/release.yml).

    python .github/release/release_check.py tag TAG
    python .github/release/release_check.py dist DIR
    python .github/release/release_check.py index INDEX DIR VERSION

``tag``: the tag ``vVERSION`` (a final ``X.Y.Z`` or a pre-release such as ``0.1.0a1``) names the
version ``pyproject.toml`` and ``poisson_trace.__version__`` carry, and ``CHANGELOG.md`` has an
entry headed ``## VERSION — `` and a date or ``pre-release``.

``dist``: DIR holds one wheel and one sdist of that version, built from this tree. Their
metadata agree; every requirement is one an index can serve (no direct reference, no URL);
Prove is pinned exactly, as ``pyproject.toml`` pins it; the wheel holds the package and its
metadata only (no test, no fixture, no ``.env``); and neither file holds an absolute home or
temporary path or anything shaped like an API key.

``index``: the files INDEX (``pypi`` or ``testpypi``) serves for VERSION are DIR's files, byte
for byte (sha256), no more and no fewer; it waits up to ten minutes for the index to list them.

Prints each problem; exits 1 if there is any.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME, MODULE = "poisson-trace", "poisson_trace"
VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
INDEXES = {"pypi": "https://pypi.org", "testpypi": "https://test.pypi.org"}
# An absolute path on a machine, and the shapes API keys take. Each pattern is joined from parts
# so that this file, which ships in the sdist, does not match itself.
SLASH = rb"/"
PATHS = re.compile(
    SLASH + rb"Users" + SLASH + rb"(?!user\b|Shared/trace-fixture/)[A-Za-z]"
    + rb"|" + SLASH + rb"home" + SLASH + rb"(?:runner|[a-z]+" + SLASH + rb"code)" + SLASH
    + rb"|" + SLASH + rb"private" + SLASH + rb"(?:var" + SLASH + rb"folders|tmp)" + SLASH
)
# The captures' identifiers were replaced with /Users/user/... (scrub_identifiers.py), and the JUnit
# fixtures were made under /Users/Shared/trace-fixture/...: neither is anyone's machine.
KEYS = re.compile(
    rb"s[k]-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}|lsv2_(?:pt|sk)_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    rb"|gh[pousr]_[A-Za-z0-9]{30,}|pyp[i]-[A-Za-z0-9_-]{50,}"
    rb"|(?:OPENAI|LANGSMITH|LANGCHAIN|BRAINTRUST|WANDB)_API_KE[Y]\s*=\s*['\"]?[A-Za-z0-9_-]{8,}"
)
# The tests' fake keys say so in their own text; a match holding one of these is not a key.
FAKES = (b"placeholder", b"sk-not-", b"sk-tf1", b"sk-ant-tf1")


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def check_tag(tag: str) -> list[str]:
    found = re.fullmatch(r"v(.+)", tag)
    if not found or not VERSION.fullmatch(found.group(1)):
        return [f"the tag {tag} is not vX.Y.Z or vX.Y.Z followed by aN, bN or rcN"]
    version, out = found.group(1), []
    declared = pyproject()["project"]["version"]
    if declared != version:
        out.append(f"pyproject.toml says {declared}, the tag {tag}")
    init = (ROOT / "src" / MODULE / "__init__.py").read_text(encoding="utf-8")
    said = re.search(r'^__version__ = "([^"]+)"', init, re.MULTILINE)
    if not said or said.group(1) != version:
        out.append(f"__version__ is {said.group(1) if said else 'missing'}, the tag {tag}")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = re.search(rf"^## {re.escape(version)} — (\S+)$", changelog, re.MULTILINE)
    if not entry:
        out.append(f"CHANGELOG.md has no entry headed '## {version} — '")
    elif entry.group(1) != "pre-release" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.group(1)):
        out.append(f"the CHANGELOG entry for {version} is headed {entry.group(1)}, "
                   "not a date or pre-release")
    return out


def requirement_name(line: str) -> str:
    return re.split(r"[\s;\[<>=!~@(]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")


def check_dist(folder: Path) -> list[str]:
    version = pyproject()["project"]["version"]
    stem = f"{MODULE}-{version}"
    wheels, sdists = sorted(folder.glob("*.whl")), sorted(folder.glob("*.tar.gz"))
    others = [p.name for p in folder.iterdir() if p not in (*wheels, *sdists)]
    out = []
    named = ([p.name for p in wheels], [p.name for p in sdists])
    if named != ([f"{stem}-py3-none-any.whl"], [f"{stem}.tar.gz"]) or others:
        held = sorted(p.name for p in folder.iterdir())
        return [f"{folder} holds {held}, not one wheel and one sdist of {version}"]
    wheel, sdist = wheels[0], sdists[0]
    with zipfile.ZipFile(wheel) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    with tarfile.open(sdist) as tf:
        sd = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}  # type: ignore[union-attr]
    metas = {"wheel": Parser().parsestr(members[f"{stem}.dist-info/METADATA"].decode("utf-8")),
             "sdist": Parser().parsestr(sd[f"{stem}/PKG-INFO"].decode("utf-8"))}
    declared = pyproject()["project"]["dependencies"]
    pinned = [r for r in declared if requirement_name(r) == "poisson-prove"]
    exact = r"poisson-prove==\d+\.\d+\.\d+"
    if len(pinned) != 1 or not re.fullmatch(exact, pinned[0].replace(" ", "")):
        out.append(f"pyproject.toml does not pin poisson-prove exactly: {pinned}")
    for kind, meta in metas.items():
        if meta["Name"] != NAME or meta["Version"] != version:
            out.append(f"the {kind} says {meta['Name']} {meta['Version']}")
        requires = meta.get_all("Requires-Dist") or []
        for line in requires:
            if "@" in line.split(";")[0] or "://" in line or line.lower().startswith("git+"):
                out.append(f"the {kind} requires {line!r}, which no index can serve")
        prove = [r.split(";")[0].replace(" ", "") for r in requires
                 if requirement_name(r) == "poisson-prove"]
        if prove != [p.replace(" ", "") for p in pinned]:
            out.append(f"the {kind} requires Prove as {prove}, pyproject.toml as {pinned}")
    requires_of = {kind: meta.get_all("Requires-Dist") or [] for kind, meta in metas.items()}
    if requires_of["wheel"] != requires_of["sdist"]:
        out.append("the wheel and the sdist do not require the same packages")
    stray = [n for n in members
             if not (n.startswith(f"{MODULE}/") or n.startswith(f"{stem}.dist-info/"))]
    if stray:
        out.append(f"the wheel holds files outside the package: {stray[:10]}")
    for n in members:
        low = n.lower()
        if "/tests/" in f"/{low}" or "fixture" in low or low.endswith(".env") or "/.env" in low:
            out.append(f"the wheel holds {n}")
    for n in sd:
        if n.endswith("/.env") or "/.env." in n:
            out.append(f"the sdist holds {n}")
    for kind, files in (("wheel", members), ("sdist", sd)):
        for n, data in files.items():
            if PATHS.search(data):
                out.append(f"the {kind}'s {n} holds an absolute path")
            if any(not any(f in m.group(0) for f in FAKES) for m in KEYS.finditer(data)):
                out.append(f"the {kind}'s {n} holds something shaped like an API key")
    if not out:
        print(f"{wheel.name} and {sdist.name}: {NAME} {version}, "
              f"requires {', '.join(requires_of['wheel'])}")
        print(f"the wheel holds {len(members)} files, the sdist {len(sd)}; "
              f"Prove pinned as {pinned[0]}")
    return out


def check_index(index: str, folder: Path, version: str) -> list[str]:
    url = f"{INDEXES[index]}/pypi/{NAME}/{version}/json"
    want = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}
    got: dict[str, str] = {}
    for _ in range(40):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                got = {f["filename"]: f["digests"]["sha256"] for f in json.load(r)["urls"]}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            got = {}
        if set(got) >= set(want):
            break
        time.sleep(15)
    if got != want:
        return [f"{url} lists {got}, the files are {want}"]
    for name, digest in want.items():
        print(f"{index}: {name} sha256 {digest}")
    return []


def main(argv: list[str]) -> int:
    if argv[:1] == ["tag"] and len(argv) == 2:
        wrong = check_tag(argv[1])
        ok = f"{argv[1]}: the version and the CHANGELOG entry agree"
    elif argv[:1] == ["dist"] and len(argv) == 2:
        wrong, ok = check_dist(Path(argv[1])), "the files are ready for an index"
    elif argv[:1] == ["index"] and len(argv) == 4 and argv[1] in INDEXES:
        wrong, ok = check_index(argv[1], Path(argv[2]), argv[3]), f"{argv[1]} serves these files"
    else:
        print(__doc__, file=sys.stderr)
        return 2
    print("\n".join(wrong) if wrong else ok)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
