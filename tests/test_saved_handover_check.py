"""TF6-22 to TF6-24: ``poisson-trace handover --check DIR``, the contract test both sides share
(``docs/handover.md``).

- TF6-22: exit 0 on every bundle each verb writes; the verdict line is ``ok``.
- TF6-23: exit 4 with the first failing line, each break made alone (the bundle resealed so that
  only the rule broken fails): a listed file missing, its digest wrong, its size wrong;
  ``artifact.json``'s own digests wrong; ``result.json`` not JSON, its schema not one of the
  verbs', a promised key missing or of the wrong type, its verdict outside the verb's closed set;
  ``report.md``'s first line not ``<verdict>␣␣<sentence>``; a Prove content or observation key
  anywhere in ``result.json``; a string in it longer than 400 characters. The verdict word is
  ``not valid`` and the sentence names the file at fault.
- TF6-24: exit 1, a refusal: DIR missing, not a folder, or holding no ``handover.json``.
"""

from __future__ import annotations

import atexit
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from look_support import trace
from saved_support import VERBS, argv012, reseal, reseal_descriptor, run_ok, store012


_WRITTEN: dict[str, Path] = {}


def _bundle(tmp_path: Path, verb: str = "fix-check") -> Path:
    """A copy, the test's own to break, of the bundle the verb writes: each verb's is written
    once in each process, in a folder no test is given, and nothing in a bundle names its place."""
    if verb not in _WRITTEN:
        root = Path(tempfile.mkdtemp(prefix="tf6-bundle-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        run_ok(argv012(verb, store012(root), "--out", str(root / "bundle")))
        _WRITTEN[verb] = root / "bundle"
    bundle = tmp_path / "bundle"
    shutil.copytree(_WRITTEN[verb], bundle)
    return bundle


def _check(bundle: Path) -> Any:
    return trace(["handover", "--check", str(bundle)])


def _invalid(bundle: Path, *named: str) -> str:
    ran = _check(bundle)
    assert ran.code == 4, ran.text
    first = ran.out.splitlines()[0]
    assert first.startswith("not valid  "), first
    assert all(n in first for n in named), (first, named)
    return first


def _edit_result(bundle: Path, change: Any) -> None:
    doc = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    change(doc)
    (bundle / "result.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reseal_descriptor(bundle)


# ---------- TF6-22 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_22_every_bundle_trace_writes_checks_out(tmp_path: Path, verb: str) -> None:
    ran = _check(_bundle(tmp_path, verb))
    assert ran.code == 0, ran.text
    assert ran.out.splitlines()[0].startswith("ok  ") and ran.err == ""


def test_tf6_22_the_check_writes_nothing(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    before = {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert _check(bundle).code == 0
    assert {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()} == before


# ---------- TF6-23: the handover's own list ----------


def test_tf6_23_a_listed_file_missing(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "table.parquet").unlink()
    _invalid(bundle, "table.parquet")


def test_tf6_23_a_listed_files_digest(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with (bundle / "report.md").open("a", encoding="utf-8") as f:
        f.write("one more line\n")
    _invalid(bundle, "report.md")


def test_tf6_23_a_listed_files_size(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    doc = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    entry = next(f for f in doc["files"] if f["name"] == "table.parquet")
    entry["bytes"] += 1
    (bundle / "handover.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    _invalid(bundle, "table.parquet")


def test_tf6_23_the_descriptors_digests(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    desc = json.loads((bundle / "artifact.json").read_text(encoding="utf-8"))
    next(f for f in desc["files"] if f["path"] == "report.md")["sha256"] = "0" * 64
    (bundle / "artifact.json").write_text(json.dumps(desc, indent=2) + "\n", encoding="utf-8")
    reseal(bundle)
    _invalid(bundle, "report.md")


# ---------- TF6-23: result.json ----------


def test_tf6_23_result_json_not_json(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "result.json").write_text("{ not json\n", encoding="utf-8")
    reseal_descriptor(bundle)
    _invalid(bundle, "result.json")


def test_tf6_23_a_schema_not_one_of_the_verbs(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d.update(schema="poisson-trace.fix-check/9"))
    _invalid(bundle, "result.json", "schema")


PROMISED = ["schema", "verdict", "sentence", "next", "note", "cannot_say", "versions", "runs"]


@pytest.mark.parametrize("key", PROMISED)
def test_tf6_23_a_promised_key_missing(tmp_path: Path, key: str) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d.pop(key))
    _invalid(bundle, "result.json", key)


WRONG_TYPE = {
    "verdict": 3, "sentence": ["a"], "next": 5, "note": "one sentence", "cannot_say": "x",
    "versions": {"trace": 1}, "runs": [],
}


@pytest.mark.parametrize("key", list(WRONG_TYPE))
def test_tf6_23_a_promised_key_of_the_wrong_type(tmp_path: Path, key: str) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d.update({key: WRONG_TYPE[key]}))
    _invalid(bundle, "result.json", key)


def test_tf6_23_a_run_without_its_name(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d["runs"]["new"].pop("run_name"))
    _invalid(bundle, "result.json", "run_name")


@pytest.mark.parametrize("verb,word", [("fix-check", "ok"), ("where", "different"), ("changes", "unsure")])
def test_tf6_23_a_verdict_outside_the_verbs_set(tmp_path: Path, verb: str, word: str) -> None:
    bundle = _bundle(tmp_path, verb)

    def change(d: dict[str, Any]) -> None:
        d["verdict"] = word

    _edit_result(bundle, change)
    report = (bundle / "report.md").read_text(encoding="utf-8").split("\n", 1)
    sentence = json.loads((bundle / "result.json").read_text(encoding="utf-8"))["sentence"]
    (bundle / "report.md").write_text(f"{word}  {sentence}\n" + report[1], encoding="utf-8")
    reseal_descriptor(bundle)
    _invalid(bundle, "result.json", "verdict")


def test_tf6_23_a_null_where_a_number_is_fine(tmp_path: Path) -> None:
    """``next`` may be null; the check passes it."""
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d.update(next=None))
    assert _check(bundle).code == 0


# ---------- TF6-23: report.md, content, length ----------


def test_tf6_23_reports_first_line(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    text = (bundle / "report.md").read_text(encoding="utf-8")
    first, rest = text.split("\n", 1)
    (bundle / "report.md").write_text(first.replace("  ", " ", 1) + "\n" + rest, encoding="utf-8")
    reseal_descriptor(bundle)
    _invalid(bundle, "report.md")


@pytest.mark.parametrize("key", ["gen_ai.prompt", "input.value", "llm.input_messages", "poisson_prove.logprobs"])
def test_tf6_23_a_content_key_anywhere(tmp_path: Path, key: str) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d["runs"]["old"].update({"extra": [{key: "x"}]}))
    _invalid(bundle, "result.json", key)


def test_tf6_23_a_string_over_400_characters(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _edit_result(bundle, lambda d: d["cannot_say"].append("x" * 401))
    _invalid(bundle, "result.json", "400")
    bundle2 = _bundle(tmp_path / "two")
    _edit_result(bundle2, lambda d: d["cannot_say"].append("x" * 400))
    assert _check(bundle2).code == 0


def test_tf6_23_only_the_first_failing_line(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "table.parquet").unlink()
    (bundle / "report.md").write_text("broken\n", encoding="utf-8")
    ran = _check(bundle)
    assert ran.code == 4 and len([x for x in ran.out.splitlines() if x.startswith("not valid  ")]) == 1


# ---------- TF6-24 ----------


@pytest.mark.parametrize("case", ["missing", "a file", "no handover.json"])
def test_tf6_24_what_is_not_a_bundle_is_refused(tmp_path: Path, case: str) -> None:
    target = tmp_path / "x"
    if case == "a file":
        target.write_text("x\n", encoding="utf-8")
    elif case == "no handover.json":
        target.mkdir()
        (target / "result.json").write_text("{}\n", encoding="utf-8")
    ran = _check(target)
    assert ran.code == 1 and ran.out == "", ran.text
    assert ran.err.startswith("error: ") and str(target) in ran.err.splitlines()[0]
