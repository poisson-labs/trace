"""TF26-85: a row whose answer is a reference reads from a pull as it reads from the file.

The default raw copy leaves a row's answer out and keeps its length, and a reference has no
length. Without a stamp of its own such a row would be a row with no answer, and that
decides one reading: a row Weave marks ``descendant_error`` that holds no score is errored when
it holds no answer and is not when it holds one. So the pull stamps ``_poisson_output_ref`` true
on a row whose answer is a reference, and on no other call; the reference itself stays out, as
TF26-35 holds.

Built from the candidate's capture: the case whose step failed and was tried again, which
answered, with its answer made a reference and its scores taken away. Read by whether the case
errored, the answer as a file and the pull of the same answer are the same run, and the case
did not error in either.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from weave_support import (
    RETRIED,
    ROW,
    Transport,
    address,
    by_status,
    case_of,
    columns,
    edited,
    imported,
    op,
    outcomes,
    pulling,
    raw_folder,
    raw_lines,
    recs,
)

VERSION, CASE = RETRIED
REFERENCE = "weave:///example-entity/trace-fixture/object/StockDesk:Zx9/attr/answers/key/c04"
STAMP = "_poisson_output_ref"


def _is_the_row(call: dict[str, Any]) -> bool:
    return op(call) == ROW and case_of(call) == CASE


def _edit(calls: list[dict[str, Any]]) -> None:
    """The retried case answers with a reference and holds no score."""
    for call in calls:
        if _is_the_row(call):
            assert call["summary"]["weave"]["status"] == "descendant_error" and call["output"]["output"] is not None
            call["output"]["output"] = REFERENCE
            call["output"]["scores"] = {}


class _Answers(Transport):
    """The captures' answers, the retried case's row edited the same way in each."""

    def answer(self, method: str, url: str, body: bytes | None) -> bytes:
        calls = [json.loads(line) for line in super().answer(method, url, body).splitlines() if line.strip()]
        _edit(calls)
        return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in calls).encode("utf-8")


def test_tf26_85_a_row_that_answered_with_a_reference_reads_from_a_pull_as_from_the_file(tmp_path: Path) -> None:
    answer = edited(tmp_path / "answer", VERSION, "expanded", _edit)
    files = imported(by_status(answer, tmp_path / "files", "r"))
    with pulling(_Answers()):
        pulled = imported(by_status(address(VERSION), tmp_path / "pulled", "r"))
    assert pulled["pull"]["raw_text_stripped"] is True

    # the raw copy: the row is stamped as answered, with no length and without the reference
    raw = raw_lines(tmp_path / "pulled", "r")
    rows = [c for c in raw if _is_the_row(c)]
    assert len(rows) == 1, rows
    assert rows[0][STAMP] is True and rows[0]["_poisson_output_chars"] is None, rows[0]
    assert rows[0]["output"] == {"scores": {}, "model_latency": rows[0]["output"]["model_latency"]}, rows[0]["output"]
    assert [c["id"] for c in raw if STAMP in c] == [rows[0]["id"]], "no other call is stamped"
    for path in raw_folder(tmp_path / "pulled", "r").iterdir():
        assert REFERENCE.encode() not in path.read_bytes(), path.name

    # the case answered, so it did not error: in the file and in the pull alike
    assert outcomes(tmp_path / "files", "r")[CASE] == outcomes(tmp_path / "pulled", "r")[CASE] == "met"
    assert outcomes(tmp_path / "files", "r") == outcomes(tmp_path / "pulled", "r")
    assert recs(tmp_path / "files", "r") == recs(tmp_path / "pulled", "r")
    left, right = columns(tmp_path / "files", "r"), columns(tmp_path / "pulled", "r")
    for case in left:
        for key in ("outcome", "error", "trace"):
            assert left[case][key] == right[case][key], (case, key)
    for key in ("rows", "cases", "outcomes", "no_outcome", "counts"):
        assert pulled[key] == files[key], key

    # and the saved folder, read again with no key and no request, is that run too
    again = imported(by_status(raw_folder(tmp_path / "pulled", "r"), tmp_path / "pulled", "again"))
    assert again["outcomes"] == files["outcomes"]
    assert outcomes(tmp_path / "pulled", "again")[CASE] == "met"
