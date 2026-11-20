"""TF10-1 to TF10-3: the three tools' committed exports (a reader is listed only on a real file
the tool wrote, committed with its provenance and its checksum).

- TF10-1: every data file of ``tests/fixtures/ingest/promptfoo``, ``…/inspect`` and
  ``…/openai-evals`` is listed in ``SHA256SUMS`` with the digest pinned here; ``PROVENANCE.md``
  has a section for each naming the tool's version and its recipe, which is committed beside the
  files.
- TF10-2: the files are what the provenance says: promptfoo's JSON is ``results.version`` 3 by
  promptfoo 0.120.19, two prompts by four tests, and its JSON Lines file the same eight results;
  Inspect's ``.eval`` is a zip whose every member is Zstandard-compressed (compress type 93):
  ``zipfile`` lists the members and ``zstandard`` decompresses each to read its JSON. Its ``.json``
  is ``version`` 2 by inspect_ai 0.3.277, three samples by two epochs, each; OpenAI Evals' two
  records are a ``spec`` line, a ``final_report`` line and three ``match`` events each, all of
  them not correct.
- TF10-3: no fixture names a home folder or the machine's owner, and the one edit the OpenAI
  Evals provenance records is in place: ``/opt/venv`` once in each file, as the opening of the
  ``spec`` line's ``registry_path``, with the digests of the files the tool wrote recorded in
  the provenance. The path that was replaced is not written here: it named the machine.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile

import pytest

from three_tools_support import (
    IN_EVAL, IN_JSON, INSPECT, OE_NEW, OE_OLD, OPENAI, PF_CSV, PROMPTFOO, eval_members,
    match_events, oe_lines, pf_doc, pf_lines,
)
from signals_support import FIXTURES

DATA = {
    "promptfoo": {
        "results.json": "97c14a69b337e987cba953997fea816e7894a88465f8c318604c6e4b85dd07a8",
        "results.jsonl": "0cfce548260e1512d2aa45ab7a07a1bfe354f6149506c1fad4296067fc97f308",
        "results.csv": "b6ac598c8cbe7c1f29d5950a5a15f396e5f770a136953d9979cd395c544fa6a3",
    },
    "inspect": {
        IN_EVAL.name: "4d9922029b8b960f9ff1a5d4cf75df6900fb88921922d0ac2c454aca97ba69b0",
        IN_JSON.name: "f2df35db42157c75254f464a4401695574d3c4a4721ac0e311402d65afff0959",
    },
    "openai-evals": {
        "old.jsonl": "8c25e2fa6ab2e9e988b488b1992664408d51895dfa118495fe26c048867b0794",
        "new.jsonl": "51558948238e77eb51c4821ea66c8ae9e4d3870df3b9a76257af12a94d785f45",
    },
}
RECIPE = {"promptfoo": ("promptfooconfig.yaml",), "inspect": ("fixture_task.py", "run_fixture.py"), "openai-evals": ()}
VERSION = {"promptfoo": "promptfoo 0.120.19", "inspect": "inspect_ai 0.3.277", "openai-evals": "evals 3.0.1.post1"}
HEADING = {"promptfoo": "Added for the promptfoo import", "inspect": "Added for the Inspect import",
           "openai-evals": "Added for the OpenAI Evals import"}
FOLDER = {"promptfoo": PROMPTFOO, "inspect": INSPECT, "openai-evals": OPENAI}
# the two OpenAI Evals records as the tool wrote them, before the one edit
TOOL_WROTE = {"old.jsonl": "661b49d0c386d7afe1d3f8558099c6ee356f5934c167f5d33d2a64275010e1d6",
              "new.jsonl": "087171f6390b76e0612402f30f88b73a15f15ddcd9bd789fdb4d1ddf60f93af2"}
REGISTRY_PATH = "/opt/venv/lib/python3.11/site-packages/evals/registry"


def _sums() -> dict[str, str]:
    out = {}
    for line in (FIXTURES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        out[name.removeprefix("./")] = digest
    return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _section(tool: str) -> str:
    provenance = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    found = [s for s in provenance.split("\n## ") if s.startswith(HEADING[tool])]
    assert len(found) == 1, tool
    return found[0]


# ---------- TF10-1 ----------


@pytest.mark.parametrize("tool", list(DATA))
def test_tf10_1_each_export_is_listed_with_its_digest_and_its_provenance(tool: str) -> None:
    sums = _sums()
    for name, digest in DATA[tool].items():
        key = f"ingest/{tool}/{name}"
        assert sums.get(key) == digest, key
        assert _sha((FOLDER[tool] / name).read_bytes()) == digest, key
    section = _section(tool)
    assert VERSION[tool] in section, tool
    for name in DATA[tool]:
        assert f"ingest/{tool}/{name}" in section, name
    for name in RECIPE[tool]:
        assert (FOLDER[tool] / name).is_file() and name in section, name


# ---------- TF10-2 ----------


def test_tf10_2_the_promptfoo_files_are_what_the_provenance_says() -> None:
    doc = pf_doc()
    assert set(doc) == {"evalId", "results", "config", "shareableUrl", "metadata"}
    assert doc["results"]["version"] == 3 and doc["metadata"]["promptfooVersion"] == "0.120.19"
    results = doc["results"]["results"]
    assert len(results) == 8 and sorted({r["promptIdx"] for r in results}) == [0, 1]
    assert sorted({r["testIdx"] for r in results}) == [0, 1, 2, 3]
    assert sorted((r["promptIdx"], r["testIdx"], r["success"], r["failureReason"]) for r in results) == [
        (0, 0, False, 1), (0, 1, False, 1), (0, 2, True, 0), (0, 3, True, 0),
        (1, 0, True, 0), (1, 1, True, 0), (1, 2, True, 0), (1, 3, True, 0),
    ]
    lines = pf_lines()
    assert len(lines) == 8 and all("evalId" not in r and "timestamp" not in r for r in lines)
    key = lambda r: (r["promptIdx"], r["testIdx"])  # noqa: E731
    assert sorted((key(r), r["success"], r["score"], r["latencyMs"]) for r in lines) == sorted(
        (key(r), r["success"], r["score"], r["latencyMs"]) for r in results)
    header = PF_CSV.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header.count("Status") == 2


def test_tf10_2_the_inspect_eval_is_zstandard_and_its_json_is_version_2() -> None:
    with zipfile.ZipFile(IN_EVAL) as z:
        infos = z.infolist()
        assert infos and all(i.compress_type == 93 for i in infos)
        names = {i.filename for i in infos}
        assert {"header.json", "summaries.json", "reductions.json"} <= names
        assert sorted(n for n in names if n.startswith("samples/")) == sorted(
            f"samples/q{q}_epoch_{e}.json" for q in (1, 2, 3) for e in (1, 2))
        assert any(n.startswith("_journal/") for n in names)
    header = eval_members()["header.json"]
    assert header["status"] == "success" and header["eval"]["model"] == "mockllm/model"
    doc = json.loads(IN_JSON.read_text(encoding="utf-8"))
    assert doc["version"] == 2 and doc["status"] == "success"
    assert {"version", "status", "eval", "plan", "results", "stats", "samples"} <= set(doc)
    assert sorted((s["id"], s["epoch"]) for s in doc["samples"]) == [(f"q{q}", e) for q in (1, 2, 3) for e in (1, 2)]
    assert "inspect_ai 0.3.277" in _section("inspect")


@pytest.mark.parametrize("path", [OE_OLD, OE_NEW], ids=["old", "new"])
def test_tf10_2_each_openai_evals_record_is_a_spec_a_report_and_three_matches(path: object) -> None:
    lines = oe_lines(path)  # type: ignore[arg-type]
    assert "spec" in lines[0] and "final_report" in lines[1]
    matches = match_events(lines)
    assert len(lines) == 5 and len(matches) == 3
    assert all(m["data"]["correct"] is False for m in matches)
    assert sorted(m["sample_id"] for m in matches) == [f"test-match.s1.{i}" for i in range(3)]


# ---------- TF10-3 ----------


def test_tf10_3_no_fixture_names_a_home_folder_or_the_owner() -> None:
    pattern = re.compile(rb"(?i)/Users/|/home/|taylor|kolasinski|claude-501")
    for tool, names in DATA.items():
        for name in names:
            path = FOLDER[tool] / name
            blobs = [path.read_bytes()]
            if path.suffix == ".eval":
                blobs += [json.dumps(v).encode("utf-8") for v in eval_members(path).values()]
            for blob in blobs:
                assert not pattern.search(blob), (tool, name, pattern.search(blob))


@pytest.mark.parametrize("name", ["old.jsonl", "new.jsonl"])
def test_tf10_3_the_one_edit_is_the_scratch_path(name: str) -> None:
    committed = (OPENAI / name).read_text(encoding="utf-8")
    assert committed.count("/opt/venv") == 1
    spec = json.loads(committed.splitlines()[0])["spec"]
    assert spec["run_config"]["eval_spec"]["registry_path"] == REGISTRY_PATH
    assert _sha(committed.encode("utf-8")) != TOOL_WROTE[name]
    section = _section("openai-evals")
    assert TOOL_WROTE[name] in section and "registry_path" in section
