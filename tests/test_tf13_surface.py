"""TF13-1 to TF13-7: the API's surface (invariant 1, and what section 11.8 adds; PA1, PA4, PA5,
PA7, PA10, PA16).

TF13-1: ``poisson_trace.api.__all__`` is the public surface: the functions section 11.8 names
for 0.1.0 (R32 as amended, with ``check`` left for TF7 by RF2 and ``build_pages`` for TF18),
the three types, and the class of every result; ``poisson_trace.commands`` holds ``init`` and
``doctor``.

TF13-2: each verb of the main command that reads a store is one function taking what the
command line takes: ``store`` first, the verb's positionals by the parser's names, then every
option as a keyword-only parameter named for its flag, defaulting as the parser does. Read from
the parser as it is when the test runs, so a flag added later must be added to the function too.

TF13-3: ``import_run`` is the import's command line: ``store``, ``tool``, ``files``, the import's
own options as keywords with the parser's defaults, and each reader's flags as keywords.

TF13-4: the functions without a verb of their own: ``name``, ``forget_name``, ``list_names``,
``open_store``, ``load_config``, ``save``, ``load_bundle`` and ``validate_bundle``; and the
result's own methods.

TF13-5: ``commands.init`` and ``commands.doctor`` take every option of their verbs' parsers as
keywords (read live: the setup agent's flags join when TF17 lands).

TF13-6: ``api.Refusal`` is an exception carrying the message, the next commands, the exit code
and the notes, built as ``Refusal(message, *, next=(), exit_code=1, notes=())``.

TF13-7: a value the parser itself would refuse is a ``ValueError``, never a refusal and never
anything else.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from tf13_support import (
    COUNTING, DELIVERY, FUNCTIONS, IMPORT_COMMON, RESULT_TYPES, TYPES, VERB_FUNCTION, api,
    attempt, cli_parsers, commands, expected_keywords, import_parsers, keyword, options_of,
    plain_default, positionals_of, workspace,
)


def _params(fn: Any) -> list[inspect.Parameter]:
    return list(inspect.signature(fn).parameters.values())


# ---------- TF13-1 ----------


def test_tf13_1_the_public_surface_is_all() -> None:
    a = api()
    names = list(a.__all__)
    assert len(names) == len(set(names)), names
    for name in names:
        assert hasattr(a, name), name
    functions = {n for n in names if inspect.isfunction(getattr(a, n))}
    classes = {n for n in names if inspect.isclass(getattr(a, n))}
    # PA5: build_pages came with the pages (TF18), beside the functions TF13 froze
    assert functions == set(FUNCTIONS) | {"build_pages"}, sorted(functions ^ (set(FUNCTIONS) | {"build_pages"}))
    assert set(names) == functions | classes, sorted(set(names) - functions - classes)
    assert set(TYPES) <= classes
    assert set(RESULT_TYPES.values()) <= classes, sorted(set(RESULT_TYPES.values()) - classes)
    # RF2: the check's function comes with the check (TF7)
    assert "check" not in names


def test_tf13_1_a_commands_holds_init_and_doctor_and_is_not_public() -> None:
    c = commands()
    assert inspect.isfunction(c.init) and inspect.isfunction(c.doctor)
    a = api()
    assert "commands" not in a.__all__ and "init" not in a.__all__ and "doctor" not in a.__all__


# ---------- TF13-2 ----------


@pytest.mark.parametrize("verb", list(VERB_FUNCTION))
def test_tf13_2_each_verb_takes_what_its_command_line_takes(verb: str) -> None:
    _top, verbs = cli_parsers()
    parser = verbs[verb]
    fn = getattr(api(), VERB_FUNCTION[verb])
    params = _params(fn)
    want_positional = ["store", *positionals_of(parser)]
    got_positional = [p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD]
    assert got_positional == want_positional, (verb, got_positional)
    for p in params:
        if p.kind is p.POSITIONAL_OR_KEYWORD:
            assert p.default is p.empty, (verb, p.name, "a positional has no default")
    assert not [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.VAR_POSITIONAL)], verb
    want = expected_keywords(parser, DELIVERY[verb] | {"--store"})
    got = {p.name: plain_default(p.default) for p in params if p.kind is p.KEYWORD_ONLY}
    assert set(got) == set(want), (verb, sorted(set(got) ^ set(want)))
    for name, default in want.items():
        assert got[name] == default, (verb, name, got[name], default)
    var_keyword = [p for p in params if p.kind is p.VAR_KEYWORD]
    # the four counting verbs read runs given as folders with the reader's flags (FI8)
    assert bool(var_keyword) == (verb in COUNTING), verb


def test_tf13_2_a_the_naming_rule_on_every_flag_of_the_main_command() -> None:
    """The rule the parity reads, checked on its own: every option's keyword is its longest
    flag, dashes dropped and the inner ones as underscores, but for init's two flags of one
    setting."""
    _top, verbs = cli_parsers()
    for verb, parser in verbs.items():
        for action in options_of(parser):
            name = keyword(action)
            flag = max(action.option_strings, key=len).lstrip("-").replace("-", "_")
            if action.dest == "import_":
                assert name == "import_", (verb, action.option_strings)
            else:
                assert name == flag, (verb, action.option_strings, name)


# ---------- TF13-3 ----------


def test_tf13_3_import_run_takes_what_the_import_takes() -> None:
    fn = api().import_run
    params = _params(fn)
    assert [p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD] == ["store", "tool", "files"]
    _top, subs = import_parsers()
    for tool, parser in subs.items():
        common = [a for a in options_of(parser) if set(a.option_strings) & set(IMPORT_COMMON)]
        assert {max(a.option_strings, key=len) for a in common} == set(IMPORT_COMMON), tool
    want = {keyword(a): plain_default(a.default) for a in common if a.option_strings != ["--store"]}
    got = {p.name: plain_default(p.default) for p in params if p.kind is p.KEYWORD_ONLY}
    assert got == want, (got, want)
    assert [p.kind for p in params if p.kind is p.VAR_KEYWORD], "each reader's flags as keywords"


def test_tf13_3_a_every_readers_flags_are_named_by_the_rule() -> None:
    """What ``**reader_flags`` takes, by reader: each flag a keyword by the same rule, and no two
    of one reader's flags one keyword."""
    _top, subs = import_parsers()
    for tool, parser in subs.items():
        own = [a for a in options_of(parser) if not set(a.option_strings) & set(IMPORT_COMMON)]
        names = [keyword(a) for a in own]
        assert len(names) == len(set(names)), (tool, names)
        assert not set(names) & {"store", "tool", "files", "run", "started", "verdicts", "config"}, tool


# ---------- TF13-4 ----------


def test_tf13_4_the_functions_without_a_verb_of_their_own() -> None:
    a = api()

    def shape(fn: Any) -> tuple[list[str], dict[str, Any]]:
        params = _params(fn)
        return ([p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD],
                {p.name: p.default for p in params if p.kind is p.KEYWORD_ONLY})

    assert shape(a.name) == (["store", "run", "new"], {"config": None})
    assert shape(a.forget_name) == (["store", "run"], {"config": None})
    assert shape(a.list_names) == (["store"], {"config": None})
    assert shape(a.open_store)[0] == ["path"]
    assert shape(a.load_config)[0] == ["path"]
    assert shape(a.save)[0] == ["result"]
    assert shape(a.load_bundle) == (["folder"], {})
    assert shape(a.validate_bundle) == (["folder"], {})


def test_tf13_4_a_each_result_has_its_methods(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    got = attempt(lambda: a.where("store", "agent after", event=["violated", "timeout"]), work)
    assert got.refusal is None
    r = got.result
    for method in ("to_json", "to_markdown", "to_bundle", "to_svg", "write_svg"):
        assert callable(getattr(r, method)), method
    params = _params(r.to_bundle)
    assert [p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD] == ["folder"]
    assert {p.name: p.default for p in params if p.kind is p.KEYWORD_ONLY} == {"force": False}
    params = _params(r.write_svg)
    assert [p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD] == ["path"]
    assert {p.name: p.default for p in params if p.kind is p.KEYWORD_ONLY} == {"force": False}
    for fn, args in (("compare", ("agent before", "agent after")), ("fix_check", ("agent before", "agent after")),
                     ("changes", ("agent before", "agent after"))):
        kw: dict[str, Any] = {"event": ["violated", "timeout"]}
        kw.update({"compare": {"max_mde_hr": 1.5}, "fix_check": {"inputs": "all", "max_mde": 0.2}, "changes": {}}[fn])
        other = attempt(lambda fn=fn, args=args, kw=kw: getattr(a, fn)("store", *args, **kw), work).result
        for method in ("to_json", "to_markdown", "to_bundle"):
            assert callable(getattr(other, method)), (fn, method)


# ---------- TF13-5 ----------


@pytest.mark.parametrize("verb", ["init", "doctor"])
def test_tf13_5_commands_take_what_their_command_lines_take(verb: str) -> None:
    _top, verbs = cli_parsers()
    parser = verbs[verb]
    fn = getattr(commands(), verb)
    params = _params(fn)
    assert all(p.kind is p.KEYWORD_ONLY for p in params), (verb, [(p.name, p.kind) for p in params])
    want = expected_keywords(parser)
    got = {p.name: plain_default(p.default) for p in params}
    assert set(got) == set(want), (verb, sorted(set(got) ^ set(want)))
    for name, default in want.items():
        assert got[name] == default, (verb, name)


# ---------- TF13-6 ----------


def test_tf13_6_a_refusal_carries_what_the_command_line_prints() -> None:
    a = api()
    assert issubclass(a.Refusal, Exception)
    e = a.Refusal("the store at x holds no run", next=("poisson-trace runs --store x",), exit_code=2,
                  notes=("a note",))
    assert str(e) == e.message == "the store at x holds no run"
    assert tuple(e.next) == ("poisson-trace runs --store x",)
    assert e.exit_code == 2 and tuple(e.notes) == ("a note",)
    plain = a.Refusal("one sentence")
    assert tuple(plain.next) == () and plain.exit_code == 1 and tuple(plain.notes) == ()


# ---------- TF13-7 ----------


def _wrong_calls(a: Any) -> dict[str, Any]:
    ev = ["violated", "timeout"]
    return {
        "a by among no choices": lambda: a.where("store", "agent after", event=ev, by="wall"),
        "a bootstrap not a number": lambda: a.where("store", "agent after", event=ev, boot="many"),
        "a step that is text": lambda: a.where("store", "agent after", event=ev, at=["3"]),
        "an event that is not a list": lambda: a.where("store", "agent after", event=5),
        "a run that is not text": lambda: a.where("store", None, event=ev),
        "a store that is a number": lambda: a.where(42, "agent after", event=ev),
        "an alpha that is text": lambda: a.compare("store", "agent before", "agent after", event=ev, max_mde_hr=1.5, alpha="0.05"),
        "a ceiling that is text": lambda: a.fix_check("store", "agent before", "agent after", event=ev, inputs="all", max_mde="0.2"),
        "a max-change that is the flag's text": lambda: a.fix_check("store", "agent before", "agent after", event=ev, inputs="all", max_mde=0.2, max_change=["wall_time_s=10%"]),
        "a top that is a float": lambda: a.changes("store", "agent before", "agent after", event=ev, top=1.5),
        "a reader flag the reader lacks": lambda: a.import_run("new-store", "junit", ["files/humaneval-a.xml"], run="x", bogus=1),
        "a reader flag of the wrong type": lambda: a.import_run("new-store", "ragas", ["files/rag-base.jsonl"], run="x", metric="faithfulness", cut=0.5, below="yes", case_column="case"),
        "a reader's choice it lacks": lambda: a.import_run("new-store", "deepeval", ["files/humaneval-a.json.gz"], run="x", metric="Tests Passed", cut="recorded", case="identifier"),
        "a reader flag on runs from a store": lambda: a.fix_check("store", "agent before", "agent after", event=ev, inputs="all", max_mde=0.2, case_column="case"),
        "all that is not true or false": lambda: a.runs("store", all="yes"),
    }


@pytest.mark.parametrize("label", list(_wrong_calls(type("A", (), {})())))
def test_tf13_7_a_value_the_parser_would_refuse_is_a_value_error(tmp_path: Path, label: str) -> None:
    work = workspace(tmp_path)
    a = api()
    before = sorted(p.relative_to(work).as_posix() for p in work.rglob("*"))
    with pytest.raises(ValueError):
        attempt(_wrong_calls(a)[label], work)
    assert sorted(p.relative_to(work).as_posix() for p in work.rglob("*")) == before, "nothing written"
    assert not issubclass(a.Refusal, ValueError), "a refusal is not a wrong argument"
