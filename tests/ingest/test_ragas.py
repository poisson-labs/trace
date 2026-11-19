"""IR1 to IR6: Ragas's score tables, as a team saves ``to_pandas()``, built in the test.

The reader takes a table, not a Ragas format: CSV, JSON Lines, JSON (a list of objects) or
Parquet, by the file's extension, ``.gz`` on the first three. It reads two columns, the score
and the case, and applies the declared cut. Refusals are checked by their exit code, one line
on stderr and nothing under the store, each beside a control that differs only in the clause
and is accepted; no message words are matched.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from poisson_prove.store import Store
from support import IMPORT_MAIN, holds, read_rows, refused, run_import, run_python, scalars, tree

STARTED = ["--started", "2026-09-30T09:00:00Z"]


def ragas_argv(
    files: Path | list[Path],
    store: Path,
    run: str = "v1",
    *,
    metric: tuple[str, ...] = ("--metric", "score"),
    cut: tuple[str, ...] = ("--cut", "0.5", "--below"),
    case_column: tuple[str, ...] = ("--case-column", "case"),
    extra: tuple[str, ...] = (),
) -> list[str]:
    paths = [files] if isinstance(files, Path) else files
    return [
        "ragas",
        *[str(p) for p in paths],
        "--store",
        str(store),
        "--run",
        run,
        *metric,
        *cut,
        *case_column,
        *extra,
    ]


def _ok(argv: list[str]) -> Any:
    r = run_import(argv)
    assert r.code == 0, r.text
    return r


def _nothing_under(root: Path) -> None:
    assert not root.exists() or not any(root.iterdir()), tree(root)


def _said(r: Any, tmp_path: Path) -> str:
    """The refusal line with the test's own directory taken out, so that nothing in a path
    can stand in for what the line must name."""
    return r.err.replace(str(tmp_path.resolve()), "").replace(str(tmp_path), "")


def _frame(root: Path, run: str = "v1") -> pd.DataFrame:
    return Store(root).read(run, meta=True, trace="none").drop(columns=["run_id"])


def save_table(path: Path, rows: list[dict[str, Any]]) -> Path:
    """The table as a team saves ``to_pandas()``: pandas's own writer for the file's extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    name = path.name
    if name.endswith((".csv", ".csv.gz")):
        frame.to_csv(path, index=False)
    elif name.endswith((".jsonl", ".jsonl.gz")):
        frame.to_json(path, orient="records", lines=True)
    elif name.endswith((".json", ".json.gz")):
        frame.to_json(path, orient="records")
    elif name.endswith(".parquet"):
        frame.to_parquet(path, index=False)
    else:
        raise AssertionError(name)
    return path


def jsonl(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines))
    return path


def _scored(
    root: Path, run: str = "v1"
) -> dict[str, list[tuple[str | None, str | None, float | None]]]:
    """Case -> (outcome, error, the score kept in ``meta["import"]``), in repeat order."""
    out: dict[str, list[tuple[str | None, str | None, float | None]]] = {}
    for r in read_rows(root, run):  # sorted by case, then repeat
        out.setdefault(r["case"], []).append((r["outcome"], r["error"], r["import"]["score"]))
    return out


# ---------- IR1: four formats, and the extension decides ----------

TEXT = 'What is "alpha", and why?\nA second line.'
TABLE = [
    {
        "case": "q-alpha",
        "user_input": TEXT,
        "retrieved_contexts": ["one, two", "three"],
        "faithfulness": 0.9,
        "answer_relevancy": 0.11,
    },
    {
        "case": "q-beta",
        "user_input": "beta?",
        "retrieved_contexts": [],
        "faithfulness": 0.1,
        "answer_relevancy": 0.12,
    },
    {
        "case": "q-alpha",
        "user_input": TEXT,
        "retrieved_contexts": ["four"],
        "faithfulness": math.nan,
        "answer_relevancy": 0.13,
    },
    {
        "case": "q-gamma",
        "user_input": "gamma?",
        "retrieved_contexts": ["five"],
        "faithfulness": 0.5,
        "answer_relevancy": 0.14,
    },
    {
        "case": "q-alpha",
        "user_input": TEXT,
        "retrieved_contexts": ["six"],
        "faithfulness": 0.35,
        "answer_relevancy": 0.15,
    },
    {
        "case": "q-delta",
        "user_input": "delta?",
        "retrieved_contexts": ["seven"],
        "faithfulness": 1.0,
        "answer_relevancy": 0.16,
    },
]
TABLE_ROWS = {
    "q-alpha": [("met", None, 0.9), (None, "no score", None), ("missed", None, 0.35)],
    "q-beta": [("missed", None, 0.1)],
    "q-gamma": [("met", None, 0.5)],
    "q-delta": [("met", None, 1.0)],
}
SHAPES = ("t.csv", "t.csv.gz", "t.jsonl", "t.jsonl.gz", "t.json", "t.json.gz", "t.parquet")
FAITHFULNESS = ("--metric", "faithfulness")


def test_ir1_the_four_formats_and_their_gzips_give_equal_rows(tmp_path: Path) -> None:
    frames = {}
    for name in SHAPES:
        f = save_table(tmp_path / name.replace("t.", "scores.", 1), TABLE)
        root = tmp_path / f"store-{name}"
        _ok(ragas_argv(f, root, metric=FAITHFULNESS, extra=tuple(STARTED)))
        assert _scored(root) == TABLE_ROWS, name
        frames[name] = _frame(root)
    for name in SHAPES[1:]:
        pd.testing.assert_frame_equal(frames[SHAPES[0]], frames[name], check_exact=True, obj=name)


def test_ir1_a_csvs_text_cells_are_read_as_numbers_where_they_parse(tmp_path: Path) -> None:
    """Ragas's own CSV backend writes every value as text."""
    f = tmp_path / "scores.csv"
    f.write_text("case,score\na,0.25\nb,1e-1\nc,-0.5\nd,1.5\ne,0.50\nf,1\ng,0\n")
    root = tmp_path / "store"
    _ok(ragas_argv(f, root))
    assert _scored(root) == {
        "a": [("missed", None, 0.25)],
        "b": [("missed", None, 0.1)],
        "c": [("missed", None, -0.5)],
        "d": [("met", None, 1.5)],
        "e": [("met", None, 0.5)],
        "f": [("met", None, 1.0)],
        "g": [("missed", None, 0.0)],
    }


def _as_jsonl(tmp_path: Path) -> bytes:
    return save_table(
        tmp_path / "source.jsonl", [{"case": "a", "score": 0.9}, {"case": "b", "score": 0.1}]
    ).read_bytes()


def _as_csv(tmp_path: Path) -> bytes:
    return save_table(
        tmp_path / "source.csv", [{"case": "a", "score": 0.9}, {"case": "b", "score": 0.1}]
    ).read_bytes()


def _as_json(tmp_path: Path) -> bytes:
    return save_table(
        tmp_path / "source.json", [{"case": "a", "score": 0.9}, {"case": "b", "score": 0.1}]
    ).read_bytes()


def _as_parquet(tmp_path: Path) -> bytes:
    return save_table(
        tmp_path / "source.parquet", [{"case": "a", "score": 0.9}, {"case": "b", "score": 0.1}]
    ).read_bytes()


BODIES = {"jsonl": _as_jsonl, "csv": _as_csv, "json": _as_json, "parquet": _as_parquet}


@pytest.mark.parametrize(
    "body,wrong",
    [
        ("jsonl", "json"),
        ("jsonl", "csv"),
        ("csv", "jsonl"),
        ("csv", "json"),
        ("json", "jsonl"),
        ("parquet", "csv"),
    ],
)
def test_ir1_the_format_is_decided_by_the_extension(tmp_path: Path, body: str, wrong: str) -> None:
    data = BODIES[body](tmp_path)
    root = tmp_path / "store"
    misnamed = tmp_path / f"scores.{wrong}"
    misnamed.write_bytes(data)
    refused(run_import(ragas_argv(misnamed, root)))
    _nothing_under(root)
    named = tmp_path / f"scores.{body}"
    named.write_bytes(data)
    _ok(ragas_argv(named, root))
    assert _scored(root) == {"a": [("met", None, 0.9)], "b": [("missed", None, 0.1)]}


@pytest.mark.parametrize(
    "name",
    ["scores.tsv", "scores.txt", "scores.xlsx", "scores", "scores.jsonl.zip", "scores.parquet.gz"],
)
def test_ir1_an_extension_not_read_is_refused(tmp_path: Path, name: str) -> None:
    if name.startswith("scores.parquet"):
        data, good = gzip.compress(_as_parquet(tmp_path)), "scores.parquet"
    else:
        data, good = _as_jsonl(tmp_path), "scores.jsonl"
    root = tmp_path / "store"
    (tmp_path / name).write_bytes(data)
    refused(run_import(ragas_argv(tmp_path / name, root)))
    _nothing_under(root)
    (tmp_path / good).write_bytes(gzip.decompress(data) if name.endswith(".gz") else data)
    _ok(ragas_argv(tmp_path / good, root))


# ---------- IC10 through this reader: not a table, no file, no row, no outcome ----------

NOT_A_TABLE = {
    "a JSON object, not a list": ("scores.json", b'{"case": "a", "score": 0.9}'),
    "a JSON list of numbers": ("scores.json", b"[0.9, 0.1]"),
    "a JSON Lines line that is a list": (
        "scores.jsonl",
        b'{"case": "a", "score": 0.9}\n["b", 0.1]\n',
    ),
    "a JSON Lines line cut short": (
        "scores.jsonl",
        b'{"case": "a", "score": 0.9}\n{"case": "b", "sco\n',
    ),
    "bytes that are not text": ("scores.csv", b"\xff\xfe\x00\x81case,score\n"),
    "text that is not Parquet": ("scores.parquet", b"case,score\na,0.9\n"),
    "a .gz that is not gzip": ("scores.csv.gz", b"case,score\na,0.9\n"),
}


@pytest.mark.parametrize("what", list(NOT_A_TABLE))
def test_ic10_a_file_that_is_not_a_table_of_its_format_is_refused(
    tmp_path: Path, what: str
) -> None:
    name, data = NOT_A_TABLE[what]
    f = tmp_path / name
    f.write_bytes(data)
    root = tmp_path / "store"
    refused(run_import(ragas_argv(f, root)))
    _nothing_under(root)
    save_table(f, [{"case": "a", "score": 0.9}, {"case": "b", "score": 0.1}])
    _ok(ragas_argv(f, root))


def test_ic10_a_missing_file_is_refused(tmp_path: Path) -> None:
    good = save_table(tmp_path / "scores.jsonl", [{"case": "a", "score": 0.9}])
    root = tmp_path / "store"
    refused(run_import(ragas_argv(tmp_path / "absent.jsonl", root)))
    refused(run_import(ragas_argv([good, tmp_path / "absent.csv"], root)))
    _nothing_under(root)
    _ok(ragas_argv(good, root))


def _empty(fmt: str, path: Path) -> None:
    if fmt == "csv":
        path.write_text("case,score\n")
    elif fmt == "jsonl":
        path.write_text("")
    elif fmt == "json":
        path.write_text("[]")
    else:
        pq.write_table(
            pa.table({"case": pa.array([], pa.string()), "score": pa.array([], pa.float64())}), path
        )


@pytest.mark.parametrize("fmt", ["csv", "jsonl", "json", "parquet"])
def test_ic10_a_table_with_no_row_is_refused(tmp_path: Path, fmt: str) -> None:
    f = tmp_path / f"scores.{fmt}"
    _empty(fmt, f)
    root = tmp_path / "store"
    refused(run_import(ragas_argv(f, root)))
    _nothing_under(root)
    save_table(f, [{"case": "a", "score": 0.9}])
    _ok(ragas_argv(f, root))


def test_ic10_a_table_whose_every_score_is_missing_is_refused(tmp_path: Path) -> None:
    """A judge that failed on every row (a model metric run without its key leaves every cell
    empty) gives a run with nothing to compare: refused, not written."""
    f = jsonl(
        tmp_path / "scores.jsonl",
        [
            '{"case": "a", "score": null}',
            '{"case": "b", "score": NaN}',
            '{"case": "a", "score": ""}',
        ],
    )
    root = tmp_path / "store"
    refused(run_import(ragas_argv(f, root)))
    _nothing_under(root)
    jsonl(
        f,
        [
            '{"case": "a", "score": null}',
            '{"case": "b", "score": 0.4}',
            '{"case": "a", "score": ""}',
        ],
    )
    _ok(ragas_argv(f, root))


# ---------- IR2: one row per table row, in order; the cut on its side; the score kept ----------


def test_ir2_one_row_per_table_row_in_file_order_then_the_order_the_files_were_given(
    tmp_path: Path,
) -> None:
    """The files are named so that their names sort the other way from the order given."""
    first = save_table(
        tmp_path / "z-first.jsonl",
        [
            {"case": "a", "score": 0.9},
            {"case": "b", "score": 0.1},
            {"case": "a", "score": 0.2},
            {"case": "c", "score": 0.7},
            {"case": "a", "score": 0.6},
        ],
    )
    second = save_table(
        tmp_path / "a-second.csv", [{"case": "a", "score": 0.3}, {"case": "b", "score": 0.8}]
    )
    root = tmp_path / "store"
    _ok(ragas_argv([first, second], root, "given"))
    _ok(ragas_argv([second, first], root, "reversed"))
    scores = {
        run: {case: [s for _, _, s in rows] for case, rows in _scored(root, run).items()}
        for run in ("given", "reversed")
    }
    assert scores["given"] == {"a": [0.9, 0.2, 0.6, 0.3], "b": [0.1, 0.8], "c": [0.7]}
    assert scores["reversed"] == {"a": [0.3, 0.9, 0.2, 0.6], "b": [0.8, 0.1], "c": [0.7]}
    assert len(read_rows(root, "given")) == 7 and Store(root).tally("given").rows == 7


@pytest.mark.parametrize(
    "cut,side,scores,want",
    [
        ("0.5", "--below", [0.49, 0.5, 0.51, -0.2, 1.7], ["missed", "met", "met", "missed", "met"]),
        ("0.5", "--above", [0.49, 0.5, 0.51, -0.2, 1.7], ["met", "met", "missed", "met", "missed"]),
        ("1.0", "--below", [1.0, 0.9999999, 1.0000001], ["met", "missed", "met"]),
    ],
)
def test_ir2_the_outcome_is_the_cut_on_its_side_and_a_score_equal_to_the_cut_met_it(
    tmp_path: Path, cut: str, side: str, scores: list[float], want: list[str]
) -> None:
    f = save_table(
        tmp_path / "scores.jsonl", [{"case": f"c{i}", "score": s} for i, s in enumerate(scores)]
    )
    root = tmp_path / "store"
    _ok(ragas_argv(f, root, cut=("--cut", cut, side)))
    got = _scored(root)
    assert [got[f"c{i}"][0][0] for i in range(len(scores))] == want
    assert [got[f"c{i}"][0][2] for i in range(len(scores))] == scores


@pytest.mark.parametrize("side", ["below", "above"])
def test_ir2_the_score_the_metric_the_cut_and_the_side_are_kept_on_every_row(
    tmp_path: Path, side: str
) -> None:
    """The named column's score, exactly, and not another score column's."""
    f = save_table(
        tmp_path / "scores.parquet",
        [
            {"case": "a", "faithfulness": 2 / 3, "answer_relevancy": 0.05},
            {"case": "b", "faithfulness": 0.1 + 0.2, "answer_relevancy": 0.95},
            {"case": "c", "faithfulness": None, "answer_relevancy": 0.5},
        ],
    )
    root = tmp_path / "store"
    _ok(ragas_argv(f, root, metric=FAITHFULNESS, cut=("--cut", "0.6", f"--{side}")))
    kept = {r["case"]: r["import"] for r in read_rows(root, "v1")}
    assert [kept[c]["score"] for c in "abc"] == [2 / 3, 0.1 + 0.2, None]
    for c in "abc":
        assert (kept[c]["metric"], kept[c]["cut"], kept[c]["side"]) == ("faithfulness", 0.6, side)


# ---------- IR3: a cell with no number has no score ----------


def _missing_csv(path: Path) -> tuple[Path, int]:
    path.write_text("case,score\nm1,0.9\nx1,\nx2,nan\nx3,NaN\nx4,null\nx5,n/a\nm2,0.2\n")
    return path, 5


def _missing_jsonl(path: Path) -> tuple[Path, int]:
    return jsonl(
        path,
        [
            '{"case": "m1", "score": 0.9}',
            '{"case": "x1", "score": null}',
            '{"case": "x2", "score": NaN}',
            '{"case": "x3", "score": ""}',
            '{"case": "x4", "score": "high"}',
            '{"case": "x5"}',
            '{"case": "m2", "score": 0.2}',
        ],
    ), 5


def _missing_json(path: Path) -> tuple[Path, int]:
    path.write_text(
        json.dumps(
            [
                {"case": "m1", "score": 0.9},
                {"case": "x1", "score": None},
                {"case": "x2", "score": ""},
                {"case": "x3", "score": "not a number"},
                {"case": "x4"},
                {"case": "m2", "score": 0.2},
            ]
        )
    )
    return path, 4


def _missing_parquet(path: Path) -> tuple[Path, int]:
    table = pa.table(
        {
            "case": pa.array(["m1", "x1", "x2", "m2"]),
            "score": pa.array([0.9, None, math.nan, 0.2], pa.float64(), from_pandas=False),
        }
    )
    pq.write_table(table, path)
    return path, 2


MISSING = {
    "csv": _missing_csv,
    "jsonl": _missing_jsonl,
    "json": _missing_json,
    "parquet": _missing_parquet,
}


@pytest.mark.parametrize("fmt", list(MISSING))
def test_ir3_an_empty_nan_null_or_non_numeric_cell_has_no_score(tmp_path: Path, fmt: str) -> None:
    """A reader that reads a missing score as 0 fails here: at a cut of 0.5 below, 0 would be
    missed. The rows keep no score, and the summary counts them."""
    f, n = MISSING[fmt](tmp_path / f"scores.{fmt}")
    root = tmp_path / "store"
    r = _ok(ragas_argv(f, root, extra=("--json",)))
    got = _scored(root)
    assert got.pop("m1") == [("met", None, 0.9)] and got.pop("m2") == [("missed", None, 0.2)]
    assert got == {f"x{i}": [(None, "no score", None)] for i in range(1, n + 1)}
    assert r.json()["no_outcome"] == {"no score": n}
    assert Store(root).tally("v1").no_outcome == n


# ---------- IR4: rows that share a case are its repeats ----------


# case -> (the case after whose row its second row comes, the second row's score); q050's second
# row is an exact copy of its first, as repeats of a 0-or-1 metric often are
TWICE = {
    "q003": ("q040", 0.25),
    "q050": ("q090", 0.05),
    "q099": ("q120", 0.35),
    "q145": ("q145", 0.65),
}


def test_ir4_rows_sharing_a_case_value_are_repeats_numbered_in_order(tmp_path: Path) -> None:
    """146 distinct values in 150 rows, four of them twice, each second row later in the file;
    a row that copies an earlier one exactly is a repeat like any other."""
    rows: list[dict[str, Any]] = []
    for i in range(146):
        rows.append({"case": f"q{i:03d}", "score": i / 1000})
        rows += [
            {"case": case, "score": score}
            for case, (after, score) in TWICE.items()
            if after == f"q{i:03d}"
        ]
    assert len(rows) == 150 and len({r["case"] for r in rows}) == 146
    f = save_table(tmp_path / "scores.jsonl", rows)
    root = tmp_path / "store"
    r = _ok(ragas_argv(f, root, extra=("--json",)))
    got = _scored(root)
    assert len(got) == 146
    assert {case for case, reps in got.items() if len(reps) > 1} == set(TWICE)
    for case, (_, later) in TWICE.items():
        assert [s for _, _, s in got[case]] == [int(case[1:]) / 1000, later], case
    d = r.json()
    assert (d["rows"], d["cases"], d["repeats"]) == (150, 146, {"min": 1, "max": 2})


def test_ir4_a_case_is_the_value_as_the_file_holds_it(tmp_path: Path) -> None:
    """A CSV's case cells are text: 007 and 7 are two cases, and so are 1.0 and 1."""
    f = tmp_path / "scores.csv"
    f.write_text("case,score\n007,0.9\n7,0.1\n1.0,0.8\n1,0.2\n007,0.3\n")
    root = tmp_path / "store"
    _ok(ragas_argv(f, root))
    got = _scored(root)
    assert set(got) == {"007", "7", "1.0", "1"}
    assert [s for _, _, s in got["007"]] == [0.9, 0.3]
    assert [len(got[c]) for c in ("7", "1.0", "1")] == [1, 1, 1]


# ---------- IR5: the rules are declared, and a table that cannot be read by them is refused ----------


def _base(tmp_path: Path) -> Path:
    return save_table(
        tmp_path / "scores.jsonl",
        [
            {"case": "a", "user_input": "a?", "score": 0.9, "faithfulness": 0.4},
            {"case": "b", "user_input": "b?", "score": 0.2, "faithfulness": 0.7},
        ],
    )


MALFORMED = {
    "no --metric": {"metric": ()},
    "no --cut": {"cut": ()},
    "no --case-column": {"case_column": ()},
    "a number with no side": {"cut": ("--cut", "0.5")},
    "a number with both sides": {"cut": ("--cut", "0.5", "--below", "--above")},
    "a side with no number": {"cut": ("--below",)},
    "recorded, which a Ragas table does not hold": {"cut": ("--cut", "recorded")},
    "recorded with a side": {"cut": ("--cut", "recorded", "--below")},
    "a cut that is not a number": {"cut": ("--cut", "high", "--below")},
    "a nan cut": {"cut": ("--cut", "nan", "--below")},
    "the score column named as the case column": {"metric": ("--metric", "case")},
    "the case column named as the score column": {"case_column": ("--case-column", "score")},
}


# a flag missing, or a value outside its choices, is a wrong command line: exit 2, one line,
# nothing on stdout and nothing written
WRONG_COMMAND_LINE = {"no --metric", "no --cut", "no --case-column", "a side with no number"}


def _wrong_command_line(r) -> None:  # type: ignore[no-untyped-def]
    assert r.code == 2, r.text
    assert r.out.strip() == "", r.out
    lines = [line for line in r.err.splitlines() if line.strip()]
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), r.err


@pytest.mark.parametrize("what", list(MALFORMED))
def test_ir5_a_missing_or_malformed_rule_is_refused(tmp_path: Path, what: str) -> None:
    f = _base(tmp_path)
    root = tmp_path / "store"
    (_wrong_command_line if what in WRONG_COMMAND_LINE else refused)(run_import(ragas_argv(f, root, **MALFORMED[what])))
    _nothing_under(root)
    _ok(ragas_argv(f, root))


COLUMNS = ("question_key", "user_input", "retrieved_contexts", "faithfulness", "answer_relevancy")
LACKING = {
    "the score column": (("--metric", "answer_correctness"), ("--case-column", "question_key")),
    "the case column": (("--metric", "faithfulness"), ("--case-column", "question_id")),
}


@pytest.mark.parametrize("what", list(LACKING))
def test_ir5_a_named_column_the_file_lacks_is_refused_naming_its_columns(
    tmp_path: Path, what: str
) -> None:
    """Every column of the file that the command does not name is in the line."""
    f = save_table(
        tmp_path / "scores.csv",
        [
            {
                "question_key": "a",
                "user_input": "a?",
                "retrieved_contexts": ["c"],
                "faithfulness": 0.4,
                "answer_relevancy": 0.8,
            }
        ],
    )
    root = tmp_path / "store"
    metric, case_column = LACKING[what]
    argv = ragas_argv(f, root, metric=metric, case_column=case_column)
    r = run_import(argv)
    refused(r)
    for column in (c for c in COLUMNS if c not in argv):
        assert re.search(rf"(?<![\w-]){column}(?![\w-])", _said(r, tmp_path)), (column, r.err)
    _nothing_under(root)
    _ok(ragas_argv(f, root, metric=FAITHFULNESS, case_column=("--case-column", "question_key")))


def test_ir5_a_column_the_second_file_lacks_is_refused_naming_that_files_columns(
    tmp_path: Path,
) -> None:
    first = save_table(tmp_path / "one.jsonl", [{"case": "a", "faithfulness": 0.4}])
    second = save_table(
        tmp_path / "two.jsonl", [{"case": "a", "context_recall": 0.8, "noise_sensitivity": 0.1}]
    )
    root = tmp_path / "store"
    r = run_import(ragas_argv([first, second], root, metric=FAITHFULNESS))
    refused(r)
    said = _said(r, tmp_path)
    assert "context_recall" in said and "noise_sensitivity" in said, r.err
    _nothing_under(root)
    save_table(second, [{"case": "a", "faithfulness": 0.8}])
    _ok(ragas_argv([first, second], root, metric=FAITHFULNESS))


def _empty_case_at(fmt: str, path: Path, at: int, empty: Any) -> None:
    """``at`` rows, the case of row ``at`` (counting from 1) empty."""
    cases = [f"c{i}" for i in range(1, at + 1)]
    cases[at - 1] = empty
    if fmt == "parquet":
        pq.write_table(
            pa.table({"case": pa.array(cases, pa.string()), "score": pa.array([0.5] * at)}), path
        )
    elif fmt == "csv":
        path.write_text("case,score\n" + "".join(f"{'' if c is None else c},0.5\n" for c in cases))
    else:
        jsonl(path, [json.dumps({"case": c, "score": 0.5}) for c in cases])


@pytest.mark.parametrize(
    "fmt,empty", [("csv", ""), ("jsonl", ""), ("jsonl", None), ("parquet", None)]
)
def test_ir5_an_empty_case_value_is_refused_naming_the_row(
    tmp_path: Path, fmt: str, empty: Any
) -> None:
    """Row 57 of the table: the line names it as row 57, or as line 58 of a file with a header."""
    f = tmp_path / f"scores.{fmt}"
    _empty_case_at(fmt, f, 57, empty)
    root = tmp_path / "store"
    r = run_import(ragas_argv(f, root))
    refused(r)
    assert set(re.findall(r"(?<![\d.])\d+(?![\d.])", _said(r, tmp_path))) & {"57", "58"}, r.err
    _nothing_under(root)
    _empty_case_at(fmt, f, 57, "c57")
    _ok(ragas_argv(f, root))


# ---------- IR6: only the two named columns are read ----------

SENTINEL = "Rq7Kx2Vb9Lm4Tz8W"
NUMBER = "0.8642097531"


def _content_table() -> list[dict[str, Any]]:
    """Every column but the two named holds the sentinel, or a number found nowhere else; one
    column's name is the sentinel."""
    return [
        {
            "case": f"q{i}",
            "score": s,
            "user_input": f"{SENTINEL} question {i}",
            "response": f"{SENTINEL} answer {i}",
            "retrieved_contexts": [f"{SENTINEL} context {i}", f"{SENTINEL} context {i}b"],
            "reference": f"{SENTINEL} reference {i}",
            "answer_relevancy": float(NUMBER),
            f"{SENTINEL}_column": "x",
        }
        for i, s in enumerate([0.9, 0.2, None, 0.6])
    ]


@pytest.mark.parametrize("name", ["scores.jsonl", "scores.csv", "scores.json.gz", "scores.parquet"])
def test_ir6_no_other_column_reaches_the_store_or_the_summary(tmp_path: Path, name: str) -> None:
    f = save_table(tmp_path / name, _content_table())
    root = tmp_path / "store"
    md = _ok(ragas_argv(f, root, "v1"))
    js = _ok(ragas_argv(f, root, "v2", extra=("--json",)))
    assert len(read_rows(root, "v1")) == 4
    assert holds(root, SENTINEL) == []
    # TF21: every numeric column but the case column is a score in the
    # signals record, so the number reaches the store there, as the answer_relevancy score
    from poisson_prove.store import Store

    for meta in Store(root).read("v1", meta=True, trace="none")["meta"]:
        assert meta["trace_signals"]["scores"]["answer_relevancy"] == float(NUMBER)
    for r in (md, js):
        assert SENTINEL not in r.out and NUMBER not in r.out


def test_ir6_a_case_value_longer_than_80_characters_is_stored_as_its_digest(tmp_path: Path) -> None:
    """The case column is the question itself: a long question, and one with a line break."""
    long_q = f"{SENTINEL} " + "why does the long question go on " * 3
    broken_q = f"{SENTINEL} first line\nsecond line"
    f = save_table(
        tmp_path / "scores.csv",
        [
            {"user_input": long_q, "score": 0.9},
            {"user_input": broken_q, "score": 0.2},
            {"user_input": long_q, "score": 0.1},
        ],
    )
    root = tmp_path / "store"
    _ok(ragas_argv(f, root, case_column=("--case-column", "user_input")))
    ids = {
        q: "sha256:" + hashlib.sha256(q.encode("utf-8")).hexdigest()[:16]
        for q in (long_q, broken_q)
    }
    got = _scored(root)
    assert got == {
        ids[long_q]: [("met", None, 0.9), ("missed", None, 0.1)],
        ids[broken_q]: [("missed", None, 0.2)],
    }
    assert holds(root, SENTINEL) == []
    assert holds(root, ids[long_q]) != []


# ---------- IC5 and IC12 through this reader ----------


def test_ic5_the_manifest_records_the_tool_each_file_and_the_four_rules(tmp_path: Path) -> None:
    first = save_table(tmp_path / "z-first.csv", [{"question_id": "a", "faithfulness": 0.9}])
    second = save_table(tmp_path / "a-second.jsonl.gz", [{"question_id": "a", "faithfulness": 0.2}])
    root = tmp_path / "store"
    _ok(
        ragas_argv(
            [first, second],
            root,
            metric=FAITHFULNESS,
            cut=("--cut", "0.7", "--above"),
            case_column=("--case-column", "question_id"),
            extra=tuple(STARTED),
        )
    )
    m = Store(root).manifest("v1")
    assert (m.target_id, m.backend) == ("import/ragas", "import:ragas")
    env = m.environment["import"]
    assert env["tool"] == "ragas"
    assert [dict(f) for f in env["files"]] == [
        {"name": "z-first.csv", "sha256": hashlib.sha256(first.read_bytes()).hexdigest()},
        {"name": "a-second.jsonl.gz", "sha256": hashlib.sha256(second.read_bytes()).hexdigest()},
    ]
    declared = scalars(env["declared"])
    assert {"faithfulness", "above", "question_id"} <= set(declared)
    assert 0.7 in declared or "0.7" in declared, env["declared"]


NEW_YORK = "America/New_York"


def test_ic12_without_started_the_start_is_the_first_files_modification_time(
    tmp_path: Path,
) -> None:
    """Run in a process at New York's time, so that the file's time read on the local clock
    cannot pass for UTC, as it would on a machine whose own zone is UTC."""
    first = save_table(tmp_path / "z-first.jsonl", [{"case": "a", "score": 0.9}])
    second = save_table(tmp_path / "a-second.jsonl", [{"case": "a", "score": 0.1}])
    os.utime(first, (1_757_098_447, 1_757_098_447))  # 2025-09-05T18:54:07Z, 14:54:07 in New York
    os.utime(second, (1_800_000_000, 1_800_000_000))
    root = tmp_path / "store"
    r = run_python(
        IMPORT_MAIN,
        ragas_argv([first, second], root),
        env=dict(os.environ, TZ=NEW_YORK),
        cwd=tmp_path,
    )
    assert r.code == 0, r.text
    m = Store(root).manifest("v1")
    assert m.environment["import"]["started_from"] == "file time"
    assert m.created_at.endswith("Z") and pd.Timestamp(m.created_at) == pd.Timestamp(
        "2025-09-05T18:54:07Z"
    )
    assert "file time" in r.out
    _ok(ragas_argv([first, second], root, "v2", extra=tuple(STARTED)))
    m = Store(root).manifest("v2")
    assert (m.created_at, m.environment["import"]["started_from"]) == (
        "2026-09-30T09:00:00Z",
        "given",
    )
