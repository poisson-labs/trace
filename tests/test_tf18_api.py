"""TF18-17 and TF18-18: the Python API's ``to_html`` and ``build_pages`` (``docs/python.md``),
and ``commands.report``.

**TF18-17** Each counting verb's result (``where``, ``compare``, ``fix_check``, ``changes``) has
``to_html()``: the HTML report's text, the same text ``report DIR`` writes for the bundle the
result's ``to_bundle`` wrote, whether the result was saved or not (the same bytes
for the same bundle). It writes nothing and prints nothing.

**TF18-22** ``docs/python.md`` documents ``build_pages`` as TF13-34 and TF13-35 hold every
function's section (its signature as the code has it, ``api.Refusal``, one example that prints
what the doc shows, run from a fresh TF13 workspace), and names ``to_html()``.

**TF18-18** ``api.build_pages(store, *, config=None)`` is ``poisson-trace ui``: in ``__all__``, it
takes the store as every function does and the config by keyword, builds what ``ui`` builds and
returns a result whose ``to_markdown()`` and ``to_json()`` are ``ui``'s output byte for byte,
with ``verdict``, ``sentence``, ``location``, ``next``, ``exit_code`` and ``notes``; a store it
cannot read is the ``Refusal`` the command prints; it writes nothing outside the stores' pages
(or a folder of its own under the system's temporary folder), prints nothing and reads no
environment variable, as TF13's purity tests watch them. ``poisson_trace.commands.report`` is
``report DIR``: one positional, ``open`` and ``force`` keyword-only and false by default.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tf0_support import chdir
from tf13_support import DOCS, FUNCTIONS, api, cli, commands, doc_sections, fenced, outside, plain_signature, watched, workspace
from tf18_support import build_work, copy_work, read, snapshot, ui, verdict_line

CALLS = {
    "where": lambda a: a.where("store", "agent after", event=["violated", "timeout"]),
    "compare": lambda a: a.compare("store", "agent before", "agent after", event=["violated", "timeout"], max_mde_hr=1.5),
    "fix_check": lambda a: a.fix_check("store", "agent before", "agent after", event=["violated", "timeout"], inputs="all", max_mde=0.1),
    "changes": lambda a: a.changes("store", "agent before", "agent after", event=["violated", "timeout"]),
}


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_work(tmp_path_factory.mktemp("tf18-api"))


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    return copy_work(base, tmp_path)


# ---------- TF18-17 ----------


@pytest.mark.parametrize("verb", list(CALLS))
def test_tf18_17_to_html_is_the_report_of_the_bundle(work: Path, verb: str) -> None:
    with chdir(work):
        r = CALLS[verb](api())
        before = snapshot(work)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            html = r.to_html()
        assert out.getvalue() == err.getvalue() == ""
        assert snapshot(work) == before
        saved = r.to_bundle("bundle")
    ran = cli(work, ["report", "bundle"])
    assert ran.code == 0, ran.text
    written = (work / "bundle" / "report.html").read_text(encoding="utf-8")
    assert html == written
    assert saved.to_html() == written
    assert read(html).h1 == verdict_line(json.loads(r.to_json()))


def test_tf18_17_to_html_is_on_every_counting_result_and_no_other() -> None:
    a = api()
    for name in ("WhereResult", "CompareResult", "FixCheckResult", "ChangesResult"):
        assert callable(getattr(getattr(a, name), "to_html", None)), name
    for name in ("RunsResult", "NameResult", "ImportResult", "BundleCheck", "Bundle"):
        assert not hasattr(getattr(a, name), "to_html"), name


# ---------- TF18-18 ----------


def test_tf18_18_build_pages_is_public() -> None:
    a = api()
    assert "build_pages" in a.__all__
    assert set(a.__all__) - {"build_pages"} >= set(FUNCTIONS)


def test_tf18_18_its_signature() -> None:
    sig = inspect.signature(api().build_pages)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["store", "config"]
    assert params[1].kind is inspect.Parameter.KEYWORD_ONLY and params[1].default is None
    assert params[0].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)


@pytest.mark.parametrize("args,kwargs,argv", [
    (("store",), {}, ["--store", "store"]),
    ((None,), {"config": "conf/trace.toml"}, ["--config", "conf/trace.toml"]),
    (("tables",), {"config": "conf/trace.toml"}, ["--config", "conf/trace.toml", "--store", "tables"]),
])
def test_tf18_18_build_pages_is_ui(work: Path, tmp_path: Path, args: tuple[object, ...], kwargs: dict[str, object], argv: list[str]) -> None:
    other = copy_work(work, tmp_path, name="other")
    with chdir(work):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            r = api().build_pages(*args, **kwargs)
        assert out.getvalue() == err.getvalue() == ""
    plain = ui(other, *argv)
    as_json = ui(other, *argv, "--json")
    # the same address but for the folder each ran in
    assert r.to_markdown() == plain.out.replace(str(other.resolve()), str(work.resolve()))
    assert r.to_json() == as_json.out.replace(str(other.resolve()), str(work.resolve()))
    doc = json.loads(r.to_json())
    assert (r.verdict, r.sentence, r.location, r.next, r.exit_code, tuple(r.notes)) == (
        doc["verdict"], doc["sentence"], doc["location"], doc["next"], 0, ())
    # the class of what a public function returns is public (TF13-1's rule)
    assert type(r).__name__ in api().__all__
    assert {k: v for k, v in snapshot(work).items() if "/.poisson/ui/" not in "/" + k} == {
        k: v for k, v in snapshot(other).items() if "/.poisson/ui/" not in "/" + k}


def test_tf18_18_a_store_it_cannot_read_is_a_refusal(work: Path) -> None:
    want = cli(work, ["ui", "--store", "no-such-store"])
    with chdir(work), pytest.raises(api().Refusal) as caught:
        api().build_pages("no-such-store")
    assert "error: " + caught.value.message == want.err.splitlines()[0]
    assert caught.value.exit_code == want.code


def test_tf18_18_reads_no_environment_variable_and_writes_only_the_pages(work: Path, tmp_path: Path) -> None:
    with chdir(work), watched(tmp_path / "systemp") as watch:
        api().build_pages(None, config="conf/trace.toml")
    assert watch.env == [], watch.env
    # the pages, and a folder of its own beside them it builds them in and renames in last
    pages = [work / s / ".poisson" / "ui" for s in ("store", "tables")]
    assert outside(watch.written, [*pages, tmp_path / "systemp"]) == [], watch.written
    assert watch.written
    for s in ("store", "tables"):
        assert sorted(p.name for p in (work / s / ".poisson" / "ui").iterdir()) == ["trace"]


@pytest.mark.parametrize("verb", list(CALLS))
def test_tf18_17_to_html_reads_no_environment_variable_and_writes_nothing(work: Path, tmp_path: Path, verb: str) -> None:
    with chdir(work):
        r = CALLS[verb](api())
        with watched(tmp_path / "systemp") as watch:
            r.to_html()
    assert watch.env == [] and outside(watch.written, [tmp_path / "systemp"]) == [], (watch.env, watch.written)


def test_tf18_18_commands_report() -> None:
    sig = inspect.signature(commands().report)
    params = list(sig.parameters.values())
    positional = [p for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    keywords = {p.name: p.default for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert len(positional) == 1
    assert keywords == {"open": False, "force": False}


# ---------- TF18-22 ----------


def test_tf18_22_the_doc_has_build_pages_and_to_html(tmp_path: Path) -> None:
    text = DOCS.read_text(encoding="utf-8")
    assert "to_html()" in text
    section = doc_sections(text)["api.build_pages"]
    blocks = fenced(section)
    assert blocks and blocks[0][0] == "python" and blocks[0][1].strip() == plain_signature(api().build_pages)
    assert "api.Refusal" in section
    pythons = [i for i, (lang, _) in enumerate(blocks) if lang == "python"]
    assert len(pythons) == 2 and blocks[pythons[1] + 1][0] == "text"
    code, shown = blocks[pythons[1]][1], blocks[pythons[1] + 1][1]
    assert code.startswith("from poisson_trace import api\n") and shown.strip()
    work = workspace(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("POISSON", "PYTHON"))}
    env["HOME"] = str(tmp_path / "home")
    proc = subprocess.run([sys.executable, "-c", code], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    assert (proc.returncode, proc.stderr, proc.stdout) == (0, "", shown)
