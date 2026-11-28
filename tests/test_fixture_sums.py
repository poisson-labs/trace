"""Every line of ``tests/fixtures/SHA256SUMS`` holds: the file it names is there and has that
digest. This is the check ``CONTRIBUTING.md`` gives (``cd tests/fixtures && shasum -a 256 -c
SHA256SUMS``), so a fixture that moves without its line fails here and not only by hand.
"""

from __future__ import annotations

import hashlib
import re

from conftest import FIXTURES

SUMS = FIXTURES / "SHA256SUMS"
LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


def test_every_line_of_the_fixtures_sha256sums_holds() -> None:
    lines = SUMS.read_text(encoding="utf-8").splitlines()
    assert lines, "SHA256SUMS is empty"
    unread = [line for line in lines if not LINE.match(line)]
    assert not unread, f"lines shasum -c cannot read: {unread[:5]}"
    gone, moved = [], []
    for line in lines:
        found = LINE.match(line)
        assert found
        digest, name = found.groups()
        path = FIXTURES / name
        if not path.is_file():
            gone.append(name)
        else:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != digest:
                moved.append(f"{name}: the line says {digest[:12]}…, the file gives {actual[:12]}…")
    assert not gone, f"named in SHA256SUMS and not there: {gone}"
    assert not moved, "files whose SHA256SUMS line does not hold:\n" + "\n".join(moved)
