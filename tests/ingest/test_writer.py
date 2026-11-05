"""IC3 to IC8 at the writer: one new run, read back through Prove, the manifest of section 2.5,
repeats by order within the case, no content, and the import boundary."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import Store, config_hash
from poisson_prove.trace import CONTENT_KEYS, OBSERVATION_KEYS, from_otel
from support import HUMANEVAL, INGEST, holds, read_rows, tree

import poisson_trace
from poisson_trace.ingest.rows import Row, Run
from poisson_trace.ingest.writer import Written, write

STARTED = "2026-09-05T18:54:07Z"


def make_run(rows: list[Row], name: str = "run", **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "name": name, "tool": "deepeval", "rows": tuple(rows), "started": STARTED,
        "started_from": "given",
        "declared": {"metric": "Score", "cut": 0.5, "side": "below", "case": "name"},
        "files": ({"name": "results.json", "sha256": "ab" * 32},),
    }
    fields.update(kw)
    return Run(**fields)


ROWS = [
    Row("c1", "met", None, 0.9),
    Row("c2", "missed", None, 0.1),
    Row("c1", "missed", None, 0.2),
    Row("c3", None, "no score"),
    Row("c1", "met", None, 0.95),
    Row("c2", "met", None, 0.7),
]


# ---------- IC3 ----------


def test_ic3_write_creates_exactly_one_run_and_changes_no_byte_of_another(tmp_path: Path) -> None:
    root = tmp_path / "store"
    shutil.copytree(HUMANEVAL, root)
    before = tree(root)
    written = write(make_run(ROWS, name="imported"), root)
    after = tree(root)
    assert isinstance(written, Written) and written.run == "imported"
    # a format 0 store also gains the store descriptor on Trace's first write (run record, SV1)
    assert {k: v for k, v in after.items()
            if k != "imported" and not k.startswith("imported/") and k != ".poisson"
            and k != ".poisson/store.json"} == before
    assert ".poisson/store.json" in after
    assert sorted(Store(root).runs()) == sorted([*Store(HUMANEVAL).runs(), "imported"])
    write(make_run(ROWS, name="second"), root)
    assert {k: v for k, v in tree(root).items() if k != "second" and not k.startswith("second/")} == after


def test_ic3_a_name_in_use_is_refused_with_nothing_written(tmp_path: Path) -> None:
    """Sole catch at the writer for an importer that appends to, or overwrites, a run."""
    root = tmp_path / "store"
    write(make_run(ROWS, name="old"), root)
    before = tree(root)
    with pytest.raises(Exception) as caught:
        write(make_run([Row("c9", "met", None, 1.0)], name="old"), root)
    assert not isinstance(caught.value, NotImplementedError)
    assert tree(root) == before
    assert len(read_rows(root, "old")) == len(ROWS)


# ---------- IC4 ----------


def test_ic4_one_row_per_row_config_repeat_seed_and_one_of_outcome_or_error(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write(make_run(ROWS), root)
    frame = Store(root).read("run", meta=False, trace="none")
    assert len(frame) == len(ROWS)
    got = sorted(
        (cfg["case"], int(ri), o, e, int(seed))
        for cfg, ri, o, e, seed in zip(
            frame["config"], frame["replicate_index"], frame["outcome"], frame["error"],
            frame["seed"], strict=True)
    )
    assert got == [
        ("c1", 0, "met", None, 0), ("c1", 1, "missed", None, 0), ("c1", 2, "met", None, 0),
        ("c2", 0, "missed", None, 0), ("c2", 1, "met", None, 0), ("c3", 0, None, "no score", 0),
    ]
    assert all(dict(cfg) == {"case": cfg["case"]} for cfg in frame["config"])
    assert all(h == config_hash({"case": cfg["case"]}) for h, cfg in zip(frame["config_hash"], frame["config"], strict=True))
    assert all((o is None) != (e is None) for o, e in zip(frame["outcome"], frame["error"], strict=True))
    tally = Store(root).tally("run")
    assert (tally.rows, tally.no_outcome, tally.with_outcome) == (6, 1, 5)


def test_ic4_the_repeat_is_the_rows_order_within_its_case(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write(make_run(ROWS), root)
    scores = {(r["case"], r["repeat"]): r["import"]["score"] for r in read_rows(root, "run")}
    assert scores == {
        ("c1", 0): 0.9, ("c1", 1): 0.2, ("c1", 2): 0.95, ("c2", 0): 0.1, ("c2", 1): 0.7,
        ("c3", 0): None,
    }


def test_ic4_t_and_horizon_and_meta_import_are_as_section_2_5_says(tmp_path: Path) -> None:
    root = tmp_path / "store"
    detail = {"metric": "Score", "threshold": 0.5, "deepeval_success": True}
    rows = [Row("c1", "met", None, 0.75, None, detail), Row("c2", None, "no score", None, None, detail)]
    write(make_run(rows), root)
    got = {r["case"]: r for r in read_rows(root, "run")}
    # one step with no spans, so Prove 0.1.3's pages build over the store (RR5)
    assert (got["c1"]["t"], got["c1"]["horizon"]) == (1.0, 1.0)
    assert got["c2"]["t"] is None and got["c2"]["horizon"] is None
    assert got["c1"]["import"] == {"score": 0.75, **detail}
    assert got["c2"]["import"] == {"score": None, **detail}
    assert all("trace" not in r["meta"] for r in got.values())
    full = Store(root).read("run", meta=True, trace="full")
    assert all("trace" not in m for m in full["meta"])


# ---------- IC5 ----------


def test_ic5_the_manifest_carries_the_fields_of_section_2_5(tmp_path: Path) -> None:
    root = tmp_path / "store"
    declared = {"metric": "Answer Relevancy", "cut": 0.7, "side": "below", "case": "name"}
    files = ({"name": "a.json", "sha256": "ab" * 32}, {"name": "b.json.gz", "sha256": "cd" * 32})
    write(make_run(ROWS, name="v1", started="2026-01-02T03:04:05Z", started_from="file name",
                   declared=declared, files=files), root)
    m = Store(root).manifest("v1")
    assert (m.run_id, m.target_id, m.backend) == ("v1", "import/deepeval", "import:deepeval")
    assert (m.t_unit, m.run_salt, dict(m.axis_types)) == ("steps", "import", {"case": "categorical"})
    assert m.created_at == "2026-01-02T03:04:05Z"
    assert m.status == "complete"
    imported = m.environment["import"]
    # spec section 9.6 item 2 (ruled 2026-10-20, item 5): a start read from a file's name records
    # the zone it was read in
    # TF21 (SA5, ruled 2026-11-03): the taxonomy's digest is recorded beside declared
    assert set(imported) == {"tool", "started_from", "declared", "taxonomy_sha256", "files",
                             "poisson_trace", "zone"}
    assert set(imported["zone"]) == {"name", "offset"}
    assert imported["tool"] == "deepeval"
    assert imported["started_from"] == "file name"
    assert imported["declared"] == declared
    assert [dict(f) for f in imported["files"]] == [dict(f) for f in files]
    assert imported["poisson_trace"] == poisson_trace.__version__


# ---------- IC6 ----------


def _case_rows(root: Path, run: str, case: str) -> list[tuple[Any, ...]]:
    return [(r["repeat"], r["outcome"], r["error"], r["import"]["score"], r["config_hash"])
            for r in read_rows(root, run) if r["case"] == case]


def test_ic6_permuting_other_cases_rows_changes_no_row_of_a_case(tmp_path: Path) -> None:
    mine = [Row("x", "missed", None, 0.1), Row("x", "met", None, 0.8), Row("x", "met", None, 0.6)]
    others = [Row("y", "met", None, 0.9), Row("z", "missed", None, 0.2), Row("y", "missed", None, 0.3),
              Row("z", None, "no score"), Row("w", "met", None, 0.55)]
    orders = [
        [mine[0], others[0], others[1], mine[1], others[2], others[3], mine[2], others[4]],
        [others[4], others[3], mine[0], mine[1], others[2], others[1], others[0], mine[2]],
        [mine[0], mine[1], mine[2], *reversed(others)],
    ]
    seen = []
    for i, rows in enumerate(orders):
        root = tmp_path / f"s{i}"
        write(make_run(rows), root)
        seen.append(_case_rows(root, "run", "x"))
    assert seen[0] == seen[1] == seen[2]
    assert [s for _, _, _, s, _ in seen[0]] == [0.1, 0.8, 0.6]


# ---------- IC7 at the writer ----------


SENTINEL = "Q7f3a9c2e41b8d065KX"
KEEP = "W4d1e8b73c09a2f56JM"


def _attr(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


def _span(span_id: str, parent: str | None, start: int, attrs: dict[str, str], name: str = "step") -> dict[str, Any]:
    out: dict[str, Any] = {
        "spanId": span_id, "name": name, "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + 1000), "status": {"code": 1},
        "attributes": [_attr(k, v) for k, v in attrs.items()],
    }
    if parent is not None:
        out["parentSpanId"] = parent
    return out


CONTENT = [
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.prompt", "gen_ai.completion",
    "gen_ai.prompt.0.content", "gen_ai.completion.0.content", "traceloop.entity.input",
    "traceloop.entity.output", "llm.input_messages.0.message.content",
    "llm.output_messages.0.message.content", "input.value", "output.value",
    "gen_ai.tool.call.arguments", "gen_ai.tool.call.result", "poisson_prove.logprobs",
]


def _spans(content: bool) -> tuple[dict[str, Any], ...]:
    def attrs(extra: dict[str, str]) -> dict[str, str]:
        base = {k: f"{SENTINEL}-{i}" for i, k in enumerate(CONTENT)} if content else {}
        return {**base, **extra}
    return (
        _span("00000000000000a1", None, 1_000_000, attrs({"app.stage": KEEP}), "agent"),
        _span("00000000000000b1", "00000000000000a1", 2_000_000, attrs({"gen_ai.operation.name": "chat", "gen_ai.request.model": "model-x"}), "call"),
        _span("00000000000000b2", "00000000000000a1", 3_000_000, attrs({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "lookup"}), "tool"),
        _span("00000000000000c1", "00000000000000b1", 4_000_000, attrs({"gen_ai.operation.name": "chat"}), "inner"),
    )


def test_ic7_the_writer_drops_every_content_attribute_before_a_span_is_stored(tmp_path: Path) -> None:
    assert all(k in CONTENT_KEYS or k in OBSERVATION_KEYS for k in CONTENT)
    root = tmp_path / "store"
    write(make_run([Row("c1", "met", None, 1.0, _spans(True)), Row("c2", None, "no score", None, _spans(True))]), root)
    assert holds(root, SENTINEL) == []
    assert holds(root, KEEP) != []


def test_ic7_the_stored_trace_is_from_otel_of_the_spans_without_their_content(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write(make_run([Row("c1", "met", None, 1.0, _spans(True))]), root)
    frame = Store(root).read("run", meta=True, trace="full")
    (meta,) = list(frame["meta"])
    assert meta["trace"] == from_otel(list(_spans(False))).to_dict()


def test_ic4_t_and_horizon_are_the_number_of_leaf_spans(tmp_path: Path) -> None:
    root = tmp_path / "store"
    write(make_run([Row("c1", "met", None, 1.0, _spans(False)), Row("c2", "missed", None, 0.0, _spans(False)[:1])]), root)
    got = {r["case"]: (r["t"], r["horizon"]) for r in read_rows(root, "run")}
    # a1 holds b1 and b2; b1 holds c1: the leaves are b2 and c1
    assert got == {"c1": (2.0, 2.0), "c2": (1.0, 1.0)}


# ---------- IC8 ----------


def _imports(path: Path) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append(node.module)
    return out


def _prove(modules: list[str]) -> list[str]:
    return [m for m in modules if m == "poisson_prove" or m.startswith("poisson_prove.")]


def test_ic8_the_writer_is_the_only_module_that_imports_poisson_prove() -> None:
    modules = sorted(INGEST.glob("*.py"))
    assert "writer.py" in [p.name for p in modules]
    for path in modules:
        prove = _prove(_imports(path))
        if path.name == "writer.py":
            assert "poisson_prove.store" in prove, "the writer writes through poisson_prove.store"
            assert set(prove) <= {"poisson_prove.store", "poisson_prove.trace"}, prove
        else:
            assert prove == [], (path.name, prove)


OTHER_TOOLS = ("deepeval", "ragas", "langsmith", "langfuse", "phoenix", "opentelemetry", "uselemma_tracing", "uselemma")


def test_ic8_no_module_imports_another_tool() -> None:
    """Green by construction on the skeleton: a static rule over the package."""
    for path in sorted(INGEST.glob("*.py")):
        tree_ = ast.parse(path.read_text())
        for module in _imports(path):
            assert module.split(".")[0] not in OTHER_TOOLS, (path.name, module)
        for node in ast.walk(tree_):
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if name in ("import_module", "__import__") and isinstance(node.args[0].value, str):
                    assert node.args[0].value.split(".")[0] not in OTHER_TOOLS, (path.name, node.args[0].value)
