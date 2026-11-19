"""TF6-16 to TF6-21: ``--out DIR``, the handover bundle (spec sections 11.2, 11.4, 11.6 and 17.3
item 5, AD11; invariants 1 and 4).

- TF6-16: ``--out DIR`` saves the artifact into the store, as ``--save`` does, and writes a copy
  of its folder into DIR with ``handover.json`` beside it; DIR holds nothing else. The plain output
  gains ``  wrote  DIR`` and then ``  saved  …``; ``--json`` gains ``saved``.
- TF6-17: DIR is created; a DIR that exists is refused before any work unless ``--force``, which
  leaves DIR holding the bundle alone.
- TF6-18: ``handover.json``: section 11.2's keys in its order; every file in DIR but itself, with
  its digest and size, ``artifact.json`` among them; the runs with their names and the store by
  section 11.2's rule.
- TF6-19: the same bundle bytes on every invocation on equal inputs, but for ``written_at``
  (section 11.6).
- TF6-20: a store that cannot be written still gets its bundle in DIR, with the note (SV7).
- TF6-21: nothing is handed over that section 11.4 or 17.3 item 9 says Trace does not hand over:
  no absolute path, no platform string, no user or host name, no key, no row content, no Prove
  content key, no page or renderer, no receipt or chain, nothing sent anywhere.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.trace import CONTENT_KEYS, OBSERVATION_KEYS
from tf0_support import DEEPEVAL, chdir, trace, trace_import
from tf6_support import (
    AFTER, AFTER_ID, BEFORE, BEFORE_ID, HANDOVER_KEYS, UTC, VERBS, argv012, descriptor, files_in,
    keys_in, prove_version, result_of, run_ok, saved_line, sha256_file, store012, strings_in,
    the_artifact, trace_version, tree, without_detail,
)


def _out(tmp_path: Path, verb: str, *extra: str) -> tuple[Path, Path, Any]:
    store = store012(tmp_path)
    bundle = tmp_path / "bundle"
    ran = run_ok(argv012(verb, store, "--out", str(bundle), *extra))
    return store, bundle, ran


# ---------- TF6-16 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_16_out_saves_and_copies_the_artifact(tmp_path: Path, verb: str) -> None:
    store, bundle, ran = _out(tmp_path, verb)
    folder = the_artifact(store, verb)
    assert files_in(bundle) == sorted([*files_in(folder), "handover.json"])
    for name in files_in(folder):
        assert (bundle / name).read_bytes() == (folder / name).read_bytes(), name
    plain = run_ok(argv012(verb, store))
    lines = ran.out.splitlines()
    blank = lines.index("")
    assert lines[blank - 2] == f"  wrote  {bundle}" and lines[blank - 1] == saved_line(verb, folder.name), lines[:blank]
    assert without_detail(ran.out, "wrote", "saved") == plain.out
    doc = run_ok(argv012(verb, store, "--out", str(tmp_path / "again"), "--json")).json()
    assert doc["saved"] == f".poisson/artifacts/{verb}/{folder.name}" and list(doc)[-2:] == ["saved", "next"]


def test_tf6_16_where_writes_svg_and_out_together(tmp_path: Path) -> None:
    store = store012(tmp_path)
    svg, bundle = tmp_path / "c.svg", tmp_path / "b"
    ran = run_ok(argv012("where", store, "--svg", str(svg), "--out", str(bundle)))
    assert (bundle / "charts" / "curve.svg").read_bytes() == svg.read_bytes()
    detail = [line for line in ran.out.splitlines()[1:] if line.startswith("  ")][:3]
    assert detail[0] == f"  wrote  {svg}" and detail[1] == f"  wrote  {bundle}" and detail[2].startswith("  saved  where ")


# ---------- TF6-17 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_17_a_dir_that_exists_is_refused_before_any_work(tmp_path: Path, verb: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from poisson_trace import api

    store = store012(tmp_path)
    bundle = tmp_path / "there"
    bundle.mkdir()
    (bundle / "mine.txt").write_text("keep\n", encoding="utf-8")
    before = tree(tmp_path)
    # the verb's own function, watched: the work is its call
    function = verb.replace("-", "_")
    real = getattr(api, function)
    calls: list[str] = []

    def watched(*args: Any, **kwargs: Any) -> Any:
        calls.append(function)
        return real(*args, **kwargs)

    monkeypatch.setattr(api, function, watched)
    ran = trace(argv012(verb, store, "--out", str(bundle)))
    assert ran.code == 1 and ran.out == "", ran.text
    assert ran.err.startswith("error: ") and str(bundle) in ran.err.splitlines()[0]
    assert "--force" in ran.err
    assert tree(tmp_path) == before
    assert calls == [], "the verb did its work before the folder was looked at"


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_17_force_replaces_it_with_the_bundle(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    bundle = tmp_path / "there"
    bundle.mkdir()
    (bundle / "mine.txt").write_text("gone\n", encoding="utf-8")
    run_ok(argv012(verb, store, "--out", str(bundle), "--force"))
    assert "mine.txt" not in files_in(bundle) and "handover.json" in files_in(bundle)
    assert files_in(bundle) == sorted([*files_in(the_artifact(store, verb)), "handover.json"])


def test_tf6_17_a_file_in_dirs_place_is_refused(tmp_path: Path) -> None:
    store = store012(tmp_path)
    (tmp_path / "f").write_text("x\n", encoding="utf-8")
    ran = trace(argv012("changes", store, "--out", str(tmp_path / "f")))
    assert ran.code == 1 and ran.out == "" and ran.err.startswith("error: "), ran.text


def test_tf6_17_force_without_svg_or_out_is_still_refused(tmp_path: Path) -> None:
    store = store012(tmp_path)
    for verb in VERBS:
        ran = trace(argv012(verb, store, "--force"))
        assert ran.code in (1, 2) and ran.out == "", (verb, ran.text)


# ---------- TF6-18 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_18_handover_json_is_section_11_2s(tmp_path: Path, verb: str) -> None:
    store, bundle, _ = _out(tmp_path, verb)
    doc = json.loads((bundle / "handover.json").read_text(encoding="utf-8"))
    assert list(doc) == HANDOVER_KEYS
    assert doc["schema"] == "poisson-trace.handover/1" and doc["verb"] == verb
    assert [f["name"] for f in doc["files"]] == sorted(n for n in files_in(bundle) if n != "handover.json")
    assert "artifact.json" in [f["name"] for f in doc["files"]]
    for entry in doc["files"]:
        assert list(entry) == ["name", "sha256", "bytes"]
        assert entry["sha256"] == sha256_file(bundle / entry["name"])
        assert entry["bytes"] == (bundle / entry["name"]).stat().st_size
    assert doc["versions"] == {"trace": trace_version(), "prove": prove_version()}
    assert UTC.match(doc["written_at"]), doc["written_at"]
    want = [(AFTER_ID, AFTER)] if verb == "where" else [(BEFORE_ID, BEFORE), (AFTER_ID, AFTER)]
    assert [(r["run_id"], r["run_name"]) for r in doc["runs"]] == want
    assert all(list(r) == ["run_id", "run_name", "store"] for r in doc["runs"])
    # an absolute store path is its last folder's name
    assert {r["store"] for r in doc["runs"]} == {store.name}


def test_tf6_18_a_relative_store_is_written_as_given(tmp_path: Path) -> None:
    (tmp_path / "w").mkdir()
    store012(tmp_path / "w", "runs")
    with chdir(tmp_path / "w"):
        run_ok(argv012("changes", Path("runs"), "--out", "b"))
    doc = json.loads((tmp_path / "w" / "b" / "handover.json").read_text(encoding="utf-8"))
    assert {r["store"] for r in doc["runs"]} == {"runs"}


# ---------- TF6-19 ----------


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_19_the_same_bundle_but_for_written_at(tmp_path: Path, verb: str) -> None:
    store = store012(tmp_path)
    one, two = tmp_path / "one", tmp_path / "two"
    run_ok(argv012(verb, store, "--out", str(one)))
    run_ok(argv012(verb, store, "--out", str(two)))
    assert files_in(one) == files_in(two)
    for name in files_in(one):
        if name != "handover.json":
            assert (one / name).read_bytes() == (two / name).read_bytes(), name
    h1, h2 = (json.loads((d / "handover.json").read_text(encoding="utf-8")) for d in (one, two))
    assert {k: v for k, v in h1.items() if k != "written_at"} == {k: v for k, v in h2.items() if k != "written_at"}


# ---------- TF6-20 ----------


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder is never read-only to root")
def test_tf6_20_a_store_that_cannot_be_written_still_gets_its_bundle(tmp_path: Path) -> None:
    store = store012(tmp_path)
    plain = run_ok(argv012("fix-check", store))
    folders = [p for p in [store, *store.rglob("*")] if p.is_dir()]
    for p in folders:
        p.chmod(0o555)
    try:
        ran = trace(argv012("fix-check", store, "--out", str(tmp_path / "b")))
    finally:
        for p in folders:
            p.chmod(0o755)
    assert ran.code == 0, ran.text
    assert "note: the verdict was not saved: " in ran.err
    assert without_detail(ran.out, "wrote") == plain.out
    assert f"  wrote  {tmp_path / 'b'}" in ran.out.splitlines()
    assert {"artifact.json", "result.json", "report.md", "table.parquet", "handover.json"} <= set(files_in(tmp_path / "b"))
    assert not (store / ".poisson" / "artifacts" / "fix-check").exists()


# ---------- TF6-21 ----------


def _every_text(bundle: Path) -> dict[str, bytes]:
    return {name: (bundle / name).read_bytes() for name in files_in(bundle)}


@pytest.mark.parametrize("verb", VERBS)
def test_tf6_21_nothing_is_handed_over_that_trace_does_not_hand_over(tmp_path: Path, verb: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a bundle is written without the network")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setenv("POISSON_TRACE_UPLOAD_TOKEN", "tok-0123456789abcdef-never-written")
    store, bundle, _ = _out(tmp_path, verb)
    folder = the_artifact(store, verb)
    banned = [str(tmp_path), str(Path.home()), sys.platform + "-", platform.platform(), platform.node(),
              getpass.getuser(), "tok-0123456789abcdef-never-written", sys.version.split()[0] + " ("]
    for where in (bundle, folder):
        for name, data in _every_text(where).items():
            for word in banned:
                if word and len(word) > 2:
                    assert word.encode() not in data, (name, word)
    # no page and no renderer: the bundle holds the artifact and handover.json, and nothing else
    assert not any(n.endswith((".html", ".js", ".css")) for n in files_in(bundle))
    result = result_of(bundle)
    keys = set(keys_in(result)) | set(keys_in(descriptor(bundle)))
    assert not keys & (set(CONTENT_KEYS) | set(OBSERVATION_KEYS)), keys & (set(CONTENT_KEYS) | set(OBSERVATION_KEYS))
    assert not {k for k in keys if any(w in k.lower() for w in ("receipt", "signature", "chain", "viewer", "viewed", "hostname"))}
    assert all(len(s) <= 400 for s in strings_in(result))
    # one verb's verdict: no other verb's schema anywhere in it
    others = {f"poisson-trace.{v}/" for v in VERBS if v != verb}
    assert not any(any(s.startswith(o) for o in others) for s in strings_in(result))


def test_tf6_21_no_rows_text_reaches_the_bundle(tmp_path: Path) -> None:
    """The fast twin of the DeepEval check below: two table runs whose rows carry a column of
    text no reader keeps; the saved verdict over them holds none of it."""
    store = tmp_path / "s"
    secret = "the user's private question number"
    for i, run in enumerate(("t0", "t1")):
        rows = "".join(f"c{j},{'failed' if j % (3 + i) == 0 else 'passed'},{secret} {j},{1.0 + j / 10}\n" for j in range(12))
        csv = tmp_path / f"{run}.csv"
        csv.write_text("case,outcome,prompt_text,wall_time_s\n" + rows, encoding="utf-8")
        made = trace_import(["table", str(csv), "--store", str(store), "--run", run, "--case-column", "case",
                             "--outcome-column", "outcome", "--failed", "failed", "--started", f"2026-11-0{i + 1}T10:00:00Z"])
        assert made.code == 0, made.text
    for verb in ("fix-check", "changes"):
        extra = ["--inputs", "all", "--max-mde", "0.5"] if verb == "fix-check" else []
        run_ok([verb, "t0", "t1", "--store", str(store), "--event", "missed", *extra, "--out", str(tmp_path / verb)])
        for name, data in _every_text(tmp_path / verb).items():
            assert secret.encode() not in data and b"prompt_text" not in data, (verb, name)


@pytest.mark.slow
def test_tf6_21_no_rows_content_reaches_the_bundle(tmp_path: Path) -> None:
    """A DeepEval import keeps the inputs' lengths and nothing of their text (TF21); the saved
    verdict over it holds none of the text either."""
    import gzip

    store = tmp_path / "s"
    for run, which, started in (("da", "a", "2026-09-05T18:54:07Z"), ("db", "b", "2026-09-05T19:50:09Z")):
        made = trace_import(["deepeval", str(DEEPEVAL / f"humaneval-{which}.json.gz"), "--store", str(store),
                             "--run", run, "--metric", "Tests Passed", "--cut", "recorded", "--case", "name",
                             "--started", started])
        assert made.code == 0, made.text
    run_ok(["fix-check", "da", "db", "--store", str(store), "--event", "missed", "--inputs", "all",
            "--max-mde", "0.2", "--out", str(tmp_path / "b")])
    source = json.loads(gzip.decompress((DEEPEVAL / "humaneval-a.json.gz").read_bytes()))
    # each test case's input, where it is not also its name (the name is the case, kept)
    texts = sorted({c["input"] for c in source["testCases"]
                    if isinstance(c.get("input"), str) and len(c["input"]) >= 20 and c["input"] != c.get("name")})[:50]
    assert texts, "the DeepEval file holds text to look for"
    for name, data in _every_text(tmp_path / "b").items():
        if name.endswith((".json", ".md")):
            body = data.decode("utf-8")
            assert not any(t in body for t in texts), name
