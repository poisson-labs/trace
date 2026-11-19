"""TF3-15 to TF3-20: the ``junit`` reader.

- TF3-15: a test case with a ``<failure>`` or an ``<error>`` is ``missed``, one with neither
  ``met``, one ``<skipped>`` a row with no outcome; every test case of the report is a row, under a
  ``<testsuites>`` root, a lone ``<testsuite>`` root, or suites nested in suites.
- TF3-16: the case is the class name and the name (``--case classname-name``, the default), or the
  name alone (``--case name``); test cases sharing a case, within a file or across the files of one
  import, are repeats in the order read; a test case with no name is refused.
- TF3-17: with no ``timestamp`` on any suite the start is the first file's time; ``--started``
  gives it.
- TF3-18: a file that is not a JUnit report is refused naming it, and so is one that declares a
  document type: nothing it names is read, and nothing is written.
- TF3-19: nothing of a failure's or a skip's message or text, nor of a suite's output or
  properties, is kept or printed.
- TF3-20: the summary: ``poisson-trace.import/1``, tool ``junit``, each file's sha256; the store is
  Prove's, ``backend`` ``import:junit``, ``--event missed`` its event.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from poisson_prove.store import Store

from tf0_support import chdir
from tf1_support import runs_json
from tf2_support import scratch_home  # noqa: F401
from tf3_support import (
    Case, by_case, holds, imported, junit_argv, no_outcome_total, read_rows, refusal, report, sha256, suite, usage_error,
    verb, write_report,
)

MIXED = [
    Case("test_a"), Case("test_b", result="failure"), Case("test_c", result="error"), Case("test_d", result="skipped"),
    Case("test_e"),
]


def _import(folder: Path, argv: list[str]) -> dict:
    with chdir(folder):
        return imported(verb([*argv, "--json"]))


def _outcomes(folder: Path, run: str = "r") -> list[str | None]:
    return [o for outs in by_case(read_rows(folder / "st", run)).values() for o in outs]


# ---------- TF3-15: outcomes ----------


def test_tf3_15_failure_and_error_are_missed_skipped_has_no_outcome(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite(MIXED)))
    doc = _import(tmp_path, junit_argv("r.xml", "st", "r", "--case", "name"))
    assert by_case(read_rows(tmp_path / "st", "r")) == {
        "test_a": ["met"], "test_b": ["missed"], "test_c": ["missed"], "test_d": [None], "test_e": ["met"],
    }
    assert doc["rows"] == 5 and doc["outcomes"] == {"met": 2, "missed": 2} and no_outcome_total(doc) == 1


@pytest.mark.parametrize("shape", ["a lone testsuite", "two suites", "a suite inside a suite"])
def test_tf3_15_every_test_case_of_the_report_is_read(tmp_path: Path, shape: str) -> None:
    first, second = MIXED[:3], MIXED[3:]
    if shape == "a lone testsuite":
        text = report(suite(MIXED), root="testsuite")
    elif shape == "two suites":
        text = report(suite(first, name="one"), suite(second, name="two"))
    else:
        inner = suite(second, name="inner")
        text = report(suite(first, name="outer", extra=inner))
    write_report(tmp_path / "r.xml", text)
    _import(tmp_path, junit_argv("r.xml", "st", "r", "--case", "name"))
    assert sorted(by_case(read_rows(tmp_path / "st", "r"))) == ["test_a", "test_b", "test_c", "test_d", "test_e"]


def test_tf3_15_a_passing_test_with_its_own_output_and_properties_is_met(tmp_path: Path) -> None:
    """pytest writes ``<properties>``, ``<system-out>`` and ``<system-err>`` inside a test case
    (``record_property``, ``junit_logging``); none of them is a failure."""
    own = '<properties><property name="k" value="v"/></properties><system-out>out</system-out><system-err>err</system-err>'
    text = report(suite([Case("test_a"), Case("test_b"), Case("test_c", result="failure")]))
    text = text.replace('name="test_a" time="0.010" />', f'name="test_a" time="0.010">{own}</testcase>')
    text = text.replace('name="test_b" time="0.010" />', 'name="test_b" time="0.010"><system-out>only</system-out></testcase>')
    write_report(tmp_path / "r.xml", text)
    doc = _import(tmp_path, junit_argv("r.xml", "st", "r", "--case", "name"))
    assert by_case(read_rows(tmp_path / "st", "r")) == {"test_a": ["met"], "test_b": ["met"], "test_c": ["missed"]}
    assert doc["outcomes"] == {"met": 2, "missed": 1}


def test_tf3_15_a_case_failing_twice_is_one_row(tmp_path: Path) -> None:
    text = report(suite([Case("test_a"), Case("test_b", result="failure")])).replace(
        "</failure></testcase>", '</failure><failure message="again">x</failure></testcase>'
    )
    write_report(tmp_path / "r.xml", text)
    doc = _import(tmp_path, junit_argv("r.xml", "st", "r"))
    assert doc["rows"] == 2 and doc["outcomes"] == {"met": 1, "missed": 1}


# ---------- TF3-16: cases and repeats ----------


def test_tf3_16_the_class_name_and_the_name_make_the_case_unless_asked_for_the_name(tmp_path: Path) -> None:
    cases = [Case("test_x", "tests.test_one"), Case("test_x", "tests.test_two", result="failure"), Case("test_y", "tests.test_one")]
    write_report(tmp_path / "r.xml", report(suite(cases)))
    _import(tmp_path, junit_argv("r.xml", "st", "both"))
    _import(tmp_path, junit_argv("r.xml", "st", "default-again", "--case", "classname-name"))
    _import(tmp_path, junit_argv("r.xml", "st", "named", "--case", "name"))
    both = by_case(read_rows(tmp_path / "st", "both"))
    assert len(both) == 3 and sorted(o for outs in both.values() for o in outs) == ["met", "met", "missed"]
    for case in both:
        assert any(c in case for c in ("tests.test_one", "tests.test_two")) and any(n in case for n in ("test_x", "test_y")), case
    assert by_case(read_rows(tmp_path / "st", "default-again")) == both
    assert by_case(read_rows(tmp_path / "st", "named")) == {"test_x": ["met", "missed"], "test_y": ["met"]}


def test_tf3_16_class_name_and_name_never_run_together(tmp_path: Path) -> None:
    """``tests.a`` with ``bc`` and ``tests.ab`` with ``c`` are two tests: the default case keeps
    the class name and the name apart."""
    write_report(tmp_path / "r.xml", report(suite([Case("bc", "tests.a"), Case("c", "tests.ab", result="failure")])))
    doc = _import(tmp_path, junit_argv("r.xml", "st", "r"))
    assert doc["cases"] == 2 and doc["repeats"] == {"min": 1, "max": 1}


def test_tf3_16_a_case_with_no_class_name_is_its_name(tmp_path: Path) -> None:
    cases = [Case("test_x", None), Case("test_x", None, result="failure"), Case("test_y", "")]
    write_report(tmp_path / "r.xml", report(suite(cases)))
    _import(tmp_path, junit_argv("r.xml", "st", "r"))
    _import(tmp_path, junit_argv("r.xml", "st", "n", "--case", "name"))
    assert by_case(read_rows(tmp_path / "st", "r")) == by_case(read_rows(tmp_path / "st", "n")) == {"test_x": ["met", "missed"], "test_y": ["met"]}


def test_tf3_16_repeats_are_in_the_order_read_across_files(tmp_path: Path) -> None:
    write_report(tmp_path / "one.xml", report(suite([Case("t1", result="failure"), Case("t2"), Case("t1")])))
    write_report(tmp_path / "two.xml", report(suite([Case("t1", result="error"), Case("t2", result="failure")])))
    doc = _import(tmp_path, junit_argv(["two.xml", "one.xml"], "st", "r"))
    got = by_case(read_rows(tmp_path / "st", "r"))
    assert sorted(got.values()) == sorted([["missed", "missed", "met"], ["missed", "met"]]), got
    assert doc["repeats"] == {"min": 2, "max": 3} and doc["cases"] == 2


@pytest.mark.parametrize("missing", ["no name attribute", "an empty name"])
def test_tf3_16_a_test_case_with_no_name_is_refused(tmp_path: Path, missing: str) -> None:
    gone = Case(None) if missing == "no name attribute" else Case("")
    write_report(tmp_path / "r.xml", report(suite([Case("test_a"), gone, Case("test_c")])))
    with chdir(tmp_path):
        line = refusal(verb(junit_argv("r.xml", "st", "r")))
    assert "r.xml" in line, line
    assert not (tmp_path / "st").exists()


def test_tf3_16_a_case_form_it_does_not_know_is_a_wrong_command_line(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite(MIXED)))
    with chdir(tmp_path):
        words = usage_error(verb(junit_argv("r.xml", "st", "r", "--case", "classname")))
    assert words == ["poisson-trace", "import", "junit", "--help"], words


# ---------- TF3-17: the start without a timestamp ----------


def test_tf3_17_with_no_timestamp_the_start_is_the_first_file_s_time(tmp_path: Path) -> None:
    write_report(tmp_path / "one.xml", report(suite(MIXED, timestamp=None)))
    write_report(tmp_path / "two.xml", report(suite(MIXED, timestamp=None)))
    first, second = 1_757_098_447, 1_757_198_447
    os.utime(tmp_path / "one.xml", (first, first))
    os.utime(tmp_path / "two.xml", (second, second))
    doc = _import(tmp_path, junit_argv(["two.xml", "one.xml"], "st", "r"))
    m = Store(tmp_path / "st").manifest("r")
    assert m.created_at == datetime.fromtimestamp(second, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert doc["started"]["from"] == "file time" == m.environment["import"]["started_from"]


def test_tf3_17_started_given_is_the_start(tmp_path: Path) -> None:
    write_report(tmp_path / "r.xml", report(suite(MIXED)))
    doc = _import(tmp_path, junit_argv("r.xml", "st", "r", "--started", "2026-01-02T05:04:05+02:00"))
    assert Store(tmp_path / "st").manifest("r").created_at == "2026-01-02T03:04:05Z" and doc["started"]["from"] == "given"


# ---------- TF3-18: what is not a JUnit report ----------

NOT_REPORTS = {
    "text that is not XML": "this is not XML",
    "XML cut short": report(suite(MIXED))[:-30],
    "another root element": '<?xml version="1.0"?><project><testcase classname="a" name="b"/></project>',
    "a report with no test case": report(suite([])),
    "an empty file": "",
}


@pytest.mark.parametrize("label", list(NOT_REPORTS))
def test_tf3_18_a_file_that_is_not_a_report_is_refused_naming_it(tmp_path: Path, label: str) -> None:
    write_report(tmp_path / "r.xml", NOT_REPORTS[label])
    with chdir(tmp_path):
        line = refusal(verb(junit_argv("r.xml", "st", "r")))
    assert "r.xml" in line, line
    assert not (tmp_path / "st").exists()


def test_tf3_18_a_file_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with chdir(tmp_path):
        refusal(verb(junit_argv("missing.xml", "st", "r")))
        locked = write_report(tmp_path / "locked.xml", report(suite(MIXED)))
        locked.chmod(0o000)
        try:
            if os.geteuid() != 0:
                refusal(verb(junit_argv("locked.xml", "st", "r")))
        finally:
            locked.chmod(0o600)
    assert not (tmp_path / "st").exists()


@pytest.mark.parametrize("kind", ["an external entity", "an internal entity", "nested entities"])
def test_tf3_18_a_declared_document_type_is_refused_and_nothing_it_names_is_read(tmp_path: Path, kind: str) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("SENTINEL-SECRET-4242", encoding="utf-8")
    entities = {
        "an external entity": f'<!ENTITY x SYSTEM "file://{secret}">',
        "an internal entity": '<!ENTITY x "test_from_an_entity">',
        "nested entities": '<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY x "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">',
    }[kind]
    text = f'<?xml version="1.0"?><!DOCTYPE testsuites [{entities}]>' + report(suite([Case("&x;"), Case("test_b")]), head="")
    text = text.replace("&amp;x;", "&x;")
    write_report(tmp_path / "r.xml", text)
    with chdir(tmp_path):
        result = verb(junit_argv("r.xml", "st", "r"))
    refusal(result)
    assert "SENTINEL-SECRET-4242" not in result.text and "test_from_an_entity" not in result.text
    assert not (tmp_path / "st").exists()


# ---------- TF3-19: nothing of a test's text kept ----------


def test_tf3_19_no_message_text_output_or_property_is_kept(tmp_path: Path) -> None:
    said = "SENTINEL-FAILURE-TEXT"
    cases = [
        Case("test_a", result="failure", message=f"{said} message", text=f"{said} traceback"),
        Case("test_b", result="error", message=f"{said} error", text=f"{said} error text"),
        Case("test_c", result="skipped", message=f"{said} skip", text=f"{said} skip text"),
        Case("test_d"),
    ]
    extra = f'<properties><property name="key" value="{said} property"/></properties><system-out>{said} out</system-out><system-err>{said} err</system-err>'
    write_report(tmp_path / "r.xml", report(suite(cases, extra=extra)))
    with chdir(tmp_path):
        result = verb(junit_argv("r.xml", "st", "r"))
        as_json = verb(junit_argv("r.xml", "st", "j", "--json"))
    assert result.code == 0 and as_json.code == 0, result.text
    assert holds(tmp_path / "st", said) == []
    assert said not in result.text and said not in as_json.text


# ---------- TF3-20: the summary and the store ----------


def test_tf3_20_the_summary_and_the_store(tmp_path: Path) -> None:
    write_report(tmp_path / "one.xml", report(suite(MIXED)))
    write_report(tmp_path / "two.xml", report(suite(MIXED[:2])))
    doc = _import(tmp_path, junit_argv(["one.xml", "two.xml"], "st", "r"))
    assert doc["tool"] == "junit" and doc["rows"] == 7
    assert [f["sha256"] for f in doc["files"]] == [sha256(tmp_path / "one.xml"), sha256(tmp_path / "two.xml")]
    assert [f["name"] for f in doc["files"]] == ["one.xml", "two.xml"]
    m = Store(tmp_path / "st").manifest("r")
    assert (m.backend, m.target_id, m.status) == ("import:junit", "import/junit", "complete")
    assert {r["seed"] for r in read_rows(tmp_path / "st", "r")} == {0}
    assert "--event missed" in doc["next"]
    listed = runs_json(tmp_path / "st", "--event", "missed")
    row = [r for r in listed["runs"] if r["run_id"] == "r"][0]
    assert row["traced"] is False and row["backend"] == "import:junit" and row["failed"] == 3
