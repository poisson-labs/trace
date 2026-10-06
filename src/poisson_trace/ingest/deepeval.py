"""DeepEval's saved test runs, as DeepEval 4.2.6 writes them.

One import reads one metric. The files are DeepEval's own: the results-folder file
``test_run_<YYYYMMDD_HHMMSS>.json``, ``.latest_run_full.json``, or the wrapped
``.latest_test_run.json``, as ``.json`` or ``.json.gz``. Nothing here imports DeepEval, and
no text of a test case is kept: not its input, its outputs or a metric's reason.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import zlib
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace.ingest.cut import MET, MISSED, Cut
from poisson_trace.ingest.rows import Refusal, Row, Run, case_id, digest_id

ENVELOPES: tuple[str, ...] = ("test run", "wrapped test run")

TOOL = "deepeval"
NO_SCORE = "no score"
WITHOUT_METRIC = "without this metric"
_CASES = ("name", "input", "position")
_LISTS = ("testCases", "conversationalTestCases")  # single-turn, then conversational
# the name DeepEval gives a test case whose name the user did not set
_POSITIONAL = re.compile(r"(?:conversational_)?test_case_\d+")
# the results-folder file, named on DeepEval's local clock, with its collision suffix or not
_NAMED = re.compile(r"test_run_(\d{8}_\d{6})(?:_\d+)?\.json(?:\.gz)?")
_GZIP = b"\x1f\x8b"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metric", required=True, metavar="NAME", help="the metric's name, as the file has it"
    )
    parser.add_argument(
        "--cut",
        required=True,
        metavar="recorded|X",
        help="recorded: DeepEval's own decision for the metric; or a number, with its side",
    )
    parser.add_argument("--below", action="store_true", help="a score under the cut missed it")
    parser.add_argument("--above", action="store_true", help="a score over the cut missed it")
    parser.add_argument(
        "--case",
        required=True,
        choices=_CASES,
        metavar="name|input|position",
        help="what identifies a test case across the two versions",
    )


def _cut(ns: argparse.Namespace) -> Cut | None:
    """The declared cut, or None for DeepEval's recorded decision."""
    if ns.cut == "recorded":
        if ns.below or ns.above:
            raise Refusal(
                "--cut recorded takes DeepEval's own decision and no side; drop --below and "
                "--above, or give the cut as a number"
            )
        return None
    try:
        value = float(ns.cut)
    except ValueError:
        value = math.nan
    if math.isnan(value):
        raise Refusal(f"--cut takes recorded or a number, not {ns.cut}")
    if ns.below == ns.above:
        raise Refusal(
            f"--cut {ns.cut} needs exactly one side: --below if a score under it missed, "
            "--above if a score over it missed"
        )
    return Cut(value, "below" if ns.below else "above")


def _load(path: Path) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refusal(f"{path} could not be read: {e.strerror or e}") from e
    body = raw
    if raw.startswith(_GZIP):
        try:
            body = gzip.decompress(raw)
        except (OSError, EOFError, zlib.error):
            # a stream that cannot be inflated, a checksum that does not match, a file cut short
            raise Refusal(
                f"{path} is a gzip file that cannot be read: it is damaged or cut short"
            ) from None
    try:
        return raw, json.loads(body.decode("utf-8"))
    except ValueError:
        raise Refusal(f"{path} is not a DeepEval test run: it is not JSON") from None


def _test_run(path: Path, doc: Any) -> tuple[str, Mapping[str, Any]]:
    """The envelope's name and the test run inside it."""
    if isinstance(doc, Mapping):
        inner = doc.get("testRunData")
        if isinstance(inner, Mapping) and isinstance(inner.get("testCases"), list):
            return ENVELOPES[1], inner
        if isinstance(doc.get("testCases"), list):
            return ENVELOPES[0], doc
        if "testRunLink" in doc:
            raise Refusal(
                f"{path} holds a link to Confident AI and no results: DeepEval wrote it while "
                "logged in; import the file in DEEPEVAL_RESULTS_FOLDER or "
                ".deepeval/.latest_run_full.json"
            )
    raise Refusal(f"{path} is not a DeepEval test run: it has no testCases and no testRunData")


def _entries(path: Path, test_run: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Every test case of the file as ``(list, test case)``, single-turn then conversational,
    each list in file order."""
    out = []
    for key in _LISTS:
        held = test_run.get(key, [])
        if not isinstance(held, list) or not all(isinstance(tc, Mapping) for tc in held):
            raise Refusal(f"{path} is not a DeepEval test run: {key} is not a list of test cases")
        out += [(key, tc) for tc in held]
    return out


def _metrics(path: Path, test_case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    held = test_case.get("metricsData", [])
    if not isinstance(held, list) or not all(isinstance(m, Mapping) for m in held):
        raise Refusal(f"{path} is not a DeepEval test run: metricsData is not a list of metrics")
    return held


def _case(path: Path, rule: str, held_in: str, test_case: Mapping[str, Any]) -> str:
    if rule == "position":
        order = test_case.get("order")
        if isinstance(order, bool) or not isinstance(order, int):
            raise Refusal(
                f"{path} holds a test case with no order, so --case position cannot read it"
            )
        return f"position:{order}"
    if rule == "input" and held_in != _LISTS[0]:
        raise Refusal(
            f"{path} holds a conversational test case, which has no input; identify the "
            "cases with --case name or --case position"
        )
    text = test_case.get(rule)
    if not isinstance(text, str) or text == "":
        raise Refusal(
            f"{path} holds a test case with no {rule}, so --case {rule} cannot identify it"
        )
    return digest_id(text) if rule == "input" else case_id(text)


def _row(path: Path, m: Mapping[str, Any], case: str, cut: Cut | None) -> Row:
    score = m.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or math.isnan(score):
        score = None
    success = m.get("success")
    detail = {
        "metric": m.get("name"),
        "threshold": m.get("threshold"),
        "cut": "recorded" if cut is None else cut.cut,
        "side": None if cut is None else cut.side,
        "deepeval_success": success if isinstance(success, bool) else None,
    }
    if score is None or m.get("error") is not None:
        return Row(case, None, NO_SCORE, None, None, detail)
    if cut is not None:
        outcome = cut.outcome(float(score))
    elif isinstance(success, bool):
        outcome = MET if success else MISSED
    else:
        raise Refusal(
            f"{path} holds a scored metric with no success recorded, so --cut recorded cannot "
            "read it; give the cut as a number with its side"
        )
    return Row(case, outcome, None, float(score), None, detail)


def _utc(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _started(first: Path) -> tuple[str, str]:
    """The time in the first file's name, which DeepEval takes from its local clock when it
    saves the file, read in this machine's zone; else the file's modification time."""
    named = _NAMED.fullmatch(first.name)
    if named is not None:
        try:
            local = datetime.strptime(named.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            pass
        else:
            return _utc(local.astimezone()), "file name"
    return _utc(datetime.fromtimestamp(first.stat().st_mtime, UTC)), "file time"


def read(ns: argparse.Namespace) -> Run:
    cut = _cut(ns)
    paths = [Path(f) for f in ns.files]
    files, read_in = [], []
    for path in paths:
        raw, doc = _load(path)
        _, test_run = _test_run(path, doc)
        files.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        read_in.append((path, _entries(path, test_run)))
    rows: list[Row] = []
    without = 0
    carried: set[str] = set()
    thresholds: Counter[str] = Counter()
    for path, entries in read_in:
        found = []
        for held_in, test_case in entries:
            metrics = _metrics(path, test_case)
            carried.update(str(m.get("name")) for m in metrics)
            mine = [m for m in metrics if m.get("name") == ns.metric]
            if len(mine) > 1:
                raise Refusal(
                    f"{path} holds a test case that carries the metric {ns.metric} "
                    f"{len(mine)} times, so which score is meant cannot be told"
                )
            if mine:
                found.append((held_in, test_case, mine[0]))
            else:
                without += 1
        names = [test_case.get("name") for _, test_case, _ in found]
        if (
            ns.case == "name"
            and names
            and all(isinstance(name, str) and _POSITIONAL.fullmatch(name) for name in names)
        ):
            raise Refusal(
                f"every test case in {path} has the name DeepEval gives by position, so "
                "--case name cannot identify them; --case position reads them, and assumes "
                "both files list the cases in the same order"
            )
        for held_in, test_case, m in found:
            rows.append(_row(path, m, _case(path, ns.case, held_in, test_case), cut))
            threshold = m.get("threshold")
            thresholds[
                "no recorded threshold"
                if threshold is None
                else f"recorded threshold {json.dumps(threshold)}"
            ] += 1
    if not rows and carried:
        raise Refusal(
            f"no test case carries the metric {ns.metric}; the files carry: "
            f"{', '.join(sorted(carried))}"
        )
    if not rows:
        raise Refusal(f"no test case carries the metric {ns.metric}; the files carry no metric")
    declared: dict[str, Any] = {"metric": ns.metric, "cut": "recorded" if cut is None else cut.cut}
    if cut is not None:
        declared["side"] = cut.side
    declared["case"] = ns.case
    counts = {WITHOUT_METRIC: without}
    if cut is None:
        counts.update(thresholds)
    started, started_from = _started(paths[0])
    return Run(
        name=ns.run,
        tool=TOOL,
        rows=tuple(rows),
        started=started,
        started_from=started_from,
        declared=declared,
        files=tuple(files),
        counts=counts,
    )
