"""The Python API: the one core every face of Trace calls (spec section 11.8, as amended on
2026-10-28; R32, R33).

One function per verb of the command line, taking what the command line takes: the store
first (a path, a name the config names, a ``Store``, or None for the config's own store or
runs given as folders), the verb's positionals, then every option as a keyword named for its
flag with the dashes as underscores and the parser's default. Each returns a frozen dataclass
carrying every key of the verb's ``--json`` as an attribute, and what a save writes
(``summary``, ``before_you_act``, ``note``, ``versions``, the failure-type diff and the
continuous measures on a verb of two runs, ``settings``); ``to_json()`` is the ``--json``
output byte for byte, ``to_markdown()`` the plain output, ``exit_code`` the command's, and
``notes`` the sentences the command prints as ``note:`` lines. ``--save``, ``--out`` and
``--svg`` are ``save(result)``, ``result.to_bundle(folder)`` and ``result.write_svg(path)``.

Every refusal is a ``Refusal``: the sentence the command line prints after ``error:``, the
commands under it, the exit code and the notes before it. A value the parser would refuse (a
wrong type, a choice it lacks, a flag the verb or the reader does not take) is a
``ValueError``, raised before anything is read.

The API prints nothing, reads no environment variable, reads no file and lists no folder it
was not given a path to, and writes only in ``import_run``, ``name``, ``forget_name``,
``save``, ``to_bundle``, ``write_svg`` and ``build_pages``, each only where it is pointed.
``__all__`` is the public surface; ``init``, ``doctor`` and ``report``, which touch the
environment rather than a store, are ``poisson_trace.commands``, not public. The names here
that open with an underscore are the command lines' own helpers and promise nothing.
"""

from __future__ import annotations

import argparse
import contextlib
import contextvars
import dataclasses
import functools
import os
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from poisson_trace import core, look

__all__ = [
    "Bundle",
    "BundleCheck",
    "ChangesResult",
    "CompareResult",
    "Config",
    "FixCheckResult",
    "ImportResult",
    "NameResult",
    "PagesResult",
    "Refusal",
    "RunsResult",
    "Store",
    "WhereResult",
    "build_pages",
    "changes",
    "compare",
    "fix_check",
    "forget_name",
    "import_run",
    "list_names",
    "load_bundle",
    "load_config",
    "name",
    "open_store",
    "runs",
    "save",
    "validate_bundle",
    "where",
]

P = ParamSpec("P")
R = TypeVar("R")


# ---------- the refusal, the store and the config ----------


class Refusal(Exception):
    """What a command refuses, as it prints it: ``message`` is the sentence after ``error:``,
    ``next`` the commands under it, ``exit_code`` the command's (1; 2 for a setting a verb
    needs that nothing gives; 3 for a failure after work started), ``notes`` the sentences
    printed as ``note:`` lines before it."""

    def __init__(
        self,
        message: str,
        *,
        next: Sequence[str] = (),  # noqa: A002
        exit_code: int = 1,
        notes: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.next = tuple(next)
        self.exit_code = exit_code
        self.notes = tuple(notes)


class Unordered(Refusal):
    """``latest`` or ``previous`` refused because the start times cannot order the runs: the
    command line rebuilds the first next command from its own words (PA19)."""

    def __init__(
        self, held: Any, message: str, *, next: Sequence[str], notes: Sequence[str]
    ) -> None:  # noqa: A002
        super().__init__(message, next=next, exit_code=1, notes=notes)
        self.held = held


@dataclass(frozen=True)
class Store:
    """A store Prove wrote, opened: ``path`` as it was given."""

    path: str


@dataclass(frozen=True)
class Config:
    """A config file, read: ``path`` as it was given."""

    path: str
    _held: Any = field(repr=False, compare=False)

    def store(self, name: str | None = None) -> str:
        """The path of the store the config names under ``[store.NAME]``, or its unnamed
        ``[store]`` for None."""
        held = self._held
        if name is None:
            if held.store is None:
                raise Refusal(f"{held.shown} names no store")
            return str(held.store)
        if name not in held.named:
            listed = ", ".join(sorted(held.named)) or "none"
            raise Refusal(f'{held.shown} names no store "{name}"; it names: {listed}')
        return str(held.named[name])


# ---------- a keyword passed is a flag given (PA16) ----------

_GIVEN: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("given", default=())


def _keywords_given(fn: Callable[P, R]) -> Callable[P, R]:
    """The function with the names of the keywords each call passes kept for it, so that a
    keyword passed at its default value still counts as the flag given (SV5)."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        token = _GIVEN.set(tuple(kwargs))
        try:
            return fn(*args, **kwargs)
        finally:
            _GIVEN.reset(token)

    return wrapper


# ---------- the values, as the parser would take them (PA7) ----------


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} takes text, not {type(value).__name__}")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    return None if value is None else _text(name, value)


def _bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} is a flag: it takes True or False, not {type(value).__name__}")
    return value


def _int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} takes a whole number, not {type(value).__name__}")
    return value


def _whole(values: Mapping[str, Any]) -> dict[str, int]:
    """Each value a whole number, by its keyword's name."""
    return {k: _int(k, v) for k, v in values.items()}


def _optional_int(name: str, value: Any) -> int | None:
    return None if value is None else _int(name, value)


def _float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} takes a number, not {type(value).__name__}")
    return float(value)


def _optional_float(name: str, value: Any) -> float | None:
    return None if value is None else _float(name, value)


def _items(name: str, value: Any) -> list[Any]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ValueError(f"{name} is repeatable: it takes a list, not {type(value).__name__}")
    return list(value)


def _texts(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    return [_text(name, v) for v in _items(name, value)]


def _ints(name: str, value: Any) -> list[int]:
    return [_int(name, v) for v in _items(name, value)]


def _choice(name: str, value: Any, choices: Sequence[str]) -> str:
    text = _text(name, value)
    if text not in choices:
        raise ValueError(f"{name} takes {' or '.join(choices)}, not {text!r}")
    return text


def _max_change(value: Any) -> list[tuple[str, float]]:
    out = []
    for item in _items("max_change", value):
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or isinstance(item[1], bool)
            or not isinstance(item[1], int | float)
        ):
            raise ValueError(
                "max_change takes (measure, share) pairs, as the flag's MEASURE=N% is read, "
                f"not {item!r}"
            )
        out.append((item[0], float(item[1])))
    return out


def _store_word(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Store):
        return value.path
    return _text("store", value)


def _config_word(value: Any) -> Any:
    if value is None or isinstance(value, Config):
        return None if value is None else value._held
    return _text("config", value)


# ---------- what the core raises, as the API raises it ----------


def _refusal_of(e: BaseException, notes: Sequence[str]) -> Refusal:
    from poisson_trace.ingest.rows import Refusal as ReaderRefusal

    if isinstance(e, look.Usage):
        return Refusal(str(e), next=e.nexts, exit_code=look.USAGE, notes=notes)
    if isinstance(e, look.Refused | ReaderRefusal):
        return Refusal(str(e), next=e.nexts, exit_code=look.REFUSED, notes=notes)
    return Refusal(str(e), exit_code=look.FAILED, notes=notes)


@contextlib.contextmanager
def _calling(ns: argparse.Namespace | None = None) -> Iterator[None]:
    """The core's refusals as the API's, with the notes collected so far."""
    from poisson_trace import names
    from poisson_trace.ingest.rows import Refusal as ReaderRefusal

    notes: Sequence[str] = ns.notes if ns is not None else ()
    try:
        yield
    except Refusal:
        raise
    except names.Unordered as e:
        if ns is None:
            raise _refusal_of(e, notes) from None
        sentence, nexts = core.unordered(e, ns.verb, ns.call_words, ns.call_valued)
        raise Unordered(e, sentence, next=nexts, notes=notes) from None
    except (look.Usage, look.Refused, look.Failed, ReaderRefusal) as e:
        raise _refusal_of(e, notes) from None


# ---------- the call as the core takes it ----------


def _flag_of(keyword: str) -> str:
    return "--" + keyword.replace("_", "-")


def _words_of(keyword: str, value: Any) -> list[str]:
    """A keyword and its value as the command line's words (for a next command and PA19's
    rebuilt line)."""
    flag = _flag_of(keyword)
    if isinstance(value, bool):
        return [flag] if value else []
    if value is None:
        return []
    if isinstance(value, Config):
        return [look.option("--config", str(value.path))]
    if isinstance(value, Store):
        return [look.option(flag, value.path)]
    if isinstance(value, list | tuple):
        out: list[str] = []
        for item in value:
            if isinstance(item, tuple) and len(item) == 2:
                out.append(look.option(flag, f"{item[0]}={100.0 * float(item[1]):g}%"))
            else:
                out.append(look.option(flag, str(item)))
        return out
    return [look.option(flag, str(value))]


def _namespace(
    verb: str,
    store: Any,
    positionals: Mapping[str, Any],
    keywords: Mapping[str, Any],
    reader_flags: Mapping[str, Any],
) -> argparse.Namespace:
    """The verb's settings as its command line's parser would give them, with what the core
    adds: the flags given, the notes, and the call's words for a next command."""
    given = _GIVEN.get()
    ns = argparse.Namespace(verb=verb, store=_store_word(store), json=False, debug=False)
    for key, value in positionals.items():
        setattr(ns, key, value)
    for key, value in keywords.items():
        setattr(ns, key, value)
    ns.config = _config_word(keywords.get("config"))
    ns.typed_flags = {_flag_of(k) for k in given}
    ns.notes = []
    words = [verb, *[str(v) for v in positionals.values()]]
    if ns.store is not None:
        words += [look.option("--store", ns.store)]
    valued = {"--store"}
    for key in given:
        value = reader_flags[key] if key in reader_flags else keywords.get(key)
        if value is None:
            continue
        if not isinstance(value, bool):
            valued.add(_flag_of(key))
        words += _words_of(key, value)
    ns.call_words = words
    ns.call_valued = valued
    ns.reader_flags = [w for k in given if k in reader_flags for w in _words_of(k, reader_flags[k])]
    return ns


def _reader_namespace(tool: str, verb: str, flags: Mapping[str, Any]) -> argparse.Namespace:
    """A reader's flags as its parser gives them: each keyword the reader's own, of its kind
    (a flag True or False, a repeatable flag a list, a choice among its choices), else a
    ``ValueError``; the defaults the parser gives for the rest."""
    from poisson_trace.ingest import importing

    actions = {_keyword(a): a for a in importing.reader_actions(tool)}
    unknown = sorted(set(flags) - set(actions))
    if unknown:
        raise ValueError(
            f"{verb} takes no {', '.join(unknown)}: the {tool} reader's flags are "
            f"{', '.join(actions) or 'none'}"
        )
    values = {a.dest: a.default for a in importing.reader_parser(tool)._actions}
    for key, value in flags.items():
        action = actions[key]
        values[action.dest] = _reader_value(key, action, value)
    return argparse.Namespace(**values)


def _keyword(action: argparse.Action) -> str:
    return max(action.option_strings, key=len).lstrip("-").replace("-", "_")


def _reader_value(key: str, action: argparse.Action, value: Any) -> Any:
    if action.nargs == 0:
        return _bool(key, value)
    if isinstance(action, argparse._AppendAction):
        return [_reader_item(key, action, v) for v in _items(key, value)]
    return _reader_item(key, action, value)


def _reader_item(key: str, action: argparse.Action, value: Any) -> Any:
    text = _text(key, value)
    if action.choices is not None and text not in action.choices:
        raise ValueError(f"{key} takes {' or '.join(str(c) for c in action.choices)}, not {text!r}")
    return text


_FUNCTIONS = {
    "where": "where",
    "compare": "compare",
    "fix-check": "fix_check",
    "changes": "changes",
}


def _counting(
    verb: str,
    store: Any,
    positionals: Mapping[str, Any],
    keywords: Mapping[str, Any],
    reader_flags: Mapping[str, Any],
) -> Any:
    """A counting verb: prepared and checked as the command line does it, its run words sorted
    into stored runs and folders, the reader's flags read for a tool's folders, then its
    work; the result built from the outcome."""
    ns = _namespace(verb, store, positionals, keywords, reader_flags)
    with _calling(ns):
        core.prepare(ns)
        plan = core.plan_folders(ns)
        flags = None
        if plan.kind == "tool":
            assert plan.tool is not None
            flags = _reader_namespace(plan.tool, verb, reader_flags)
        elif reader_flags:
            raise ValueError(
                f"{verb} takes a reader's flags only for runs given as folders of that tool's "
                f"results, not for {'a Prove folder' if plan.kind == 'prove' else 'stored runs'}: "
                f"{', '.join(reader_flags)}"
            )
        counted = core.run_verb(ns, core.VERBS[verb], plan, flags)
    return _result(counted, core.Delivered())


# ---------- the results ----------


@dataclass(frozen=True)
class _Counting:
    """What every counting verb's result carries beside its JSON's keys: the summary's lines
    and the caveats the report prints, the versions, the artifact's settings (SV5), the notes,
    the exit code, and where the verdict was saved (None until it is)."""

    schema: str
    verdict: str
    sentence: str
    prove: dict[str, Any]
    events: list[str]
    cannot_say: list[str]
    saved: str | None
    next: str
    summary: list[list[str]]
    before_you_act: list[str]
    versions: dict[str, str]
    settings: dict[str, Any]
    notes: tuple[str, ...]
    exit_code: int
    _counted: Any = field(repr=False, compare=False)
    _delivered: Any = field(repr=False, compare=False)

    @property
    def note(self) -> list[str]:
        """Section 11.3's list: the sentence a report of a run with no traces carries, and the
        note that the two runs' failure types were decided by different rules."""
        return list(self._counted.result_document()["note"])

    def to_json(self) -> str:
        """The ``--json`` output, byte for byte, its final newline included."""
        from poisson_trace import report

        return report.json_text(core.document(self._counted, self._delivered))

    def to_markdown(self) -> str:
        """The plain output, byte for byte: the verdict line, the detail lines, the report and
        the ``next:`` line."""
        return core.text(self._counted, self._delivered)

    def to_html(self) -> str:
        """The HTML report of this verdict (spec section 11.7): the text ``poisson-trace report
        DIR`` writes for the bundle ``to_bundle`` writes, saved or not. Nothing is written."""
        with _calling(self._counted.ns):
            return str(core.to_html(self._counted))

    def to_bundle(self, folder: str, *, force: bool = False) -> Any:
        """``--out DIR``: the verdict saved into the runs' store and handed over as a bundle
        into ``folder``, which is made; one that is there is refused without ``force``. The
        result as the command prints it with ``--out``."""
        _text("folder", folder)
        with _calling(self._counted.ns):
            delivered = core.save(self._counted, self._delivered, folder, _bool("force", force))
        return _result(self._counted, delivered)


@dataclass(frozen=True)
class WhereResult(_Counting):
    """``poisson-trace where``: where in the workflow one run's episodes died."""

    run: dict[str, Any]
    clock: dict[str, Any]
    curve: list[dict[str, Any]]
    median_step: int | None
    at: list[dict[str, Any]]
    causes: list[dict[str, Any]]
    bootstrap: dict[str, Any]
    declared: dict[str, Any] | None

    def to_svg(self) -> str:
        """The curve as SVG text; refused where the run has no traces."""
        with _calling(self._counted.ns):
            return str(self._counted.svg())

    def write_svg(self, path: str, *, force: bool = False) -> WhereResult:
        """``--svg FILE``: the curve written to ``path``; a file that is there is refused
        without ``force``. The result as the command prints it with ``--svg``."""
        _text("path", path)
        with _calling(self._counted.ns):
            delivered = core.write_svg(self._counted, self._delivered, path, _bool("force", force))
        result: WhereResult = _result(self._counted, delivered)
        return result


@dataclass(frozen=True)
class _TwoRuns(_Counting):
    """A verb of two runs: TF6's failure-type diff (TF21's kinds and signals counted in each
    run) and TF23's continuous measures, saved with every verdict of two runs, worked out when
    the call read the signals or when first read."""

    runs: dict[str, Any]
    verdicts: dict[str, Any] | None

    @property
    def failure_taxonomy_diff(self) -> dict[str, Any]:
        self._counted.two_run_parts()
        return dict(self._counted.diff[0])

    @property
    def continuous_measures(self) -> dict[str, Any]:
        self._counted.two_run_parts()
        return dict(self._counted.measures.to_dict())


@dataclass(frozen=True)
class CompareResult(_TwoRuns):
    """``poisson-trace compare``: a before (A) and an after (B), compared."""

    clock: dict[str, Any]
    at: list[dict[str, Any]]
    comparison: dict[str, Any]
    per_cause: list[dict[str, Any]]


@dataclass(frozen=True)
class FixCheckResult(_TwoRuns):
    """``poisson-trace fix-check``: an old and a new version re-run on the same inputs."""

    gap_seconds: float
    inputs: dict[str, Any]
    rows: dict[str, Any]
    control: dict[str, Any]
    test: dict[str, Any]
    difference: dict[str, Any]
    by_input: dict[str, Any]
    consistency: dict[str, Any]
    limits: dict[str, Any]
    direction: str
    guidance: dict[str, Any] | None
    changes: dict[str, Any]


@dataclass(frozen=True)
class ChangesResult(_TwoRuns):
    """``poisson-trace changes``: the inputs whose failure share moved between two runs."""

    tested: int
    flagged: int
    alpha: float
    lone_threshold: float
    smallest_attainable_p: float
    together: int | None
    lone_flip_repeats: int
    rows: list[dict[str, Any]]


_RESULTS: dict[str, type[_Counting]] = {
    "where": WhereResult,
    "compare": CompareResult,
    "fix-check": FixCheckResult,
    "changes": ChangesResult,
}
_OWN = frozenset(
    {
        "summary",
        "before_you_act",
        "versions",
        "settings",
        "notes",
        "exit_code",
        "_counted",
        "_delivered",
    }
)


def _result(c: Any, d: Any) -> Any:
    from poisson_trace import saved

    cls = _RESULTS[c.kind]
    doc = core.document(c, d)
    values: dict[str, Any] = {
        f.name: doc.get(f.name) for f in dataclasses.fields(cls) if f.name not in _OWN
    }
    values.update(
        summary=[[label, line] for label, line in c.data.get("_summary") or ()],
        before_you_act=list(c.data.get("_before_you_act") or ()),
        versions={"trace": saved.trace_version(), "prove": saved.prove_version()},
        settings=c.settings,
        notes=(*c.ns.notes, *d.notes),
        exit_code=look.DONE,
        _counted=c,
        _delivered=d,
    )
    return cls(**values)


@dataclass(frozen=True)
class RunsResult:
    """``poisson-trace runs``: the runs of a store, newest first."""

    schema: str
    verdict: str
    sentence: str
    store: str
    runs: list[dict[str, Any]]
    next: str
    notes: tuple[str, ...]
    exit_code: int
    _text: str = field(repr=False, compare=False)

    def to_json(self) -> str:
        from poisson_trace import report

        return report.json_text(
            {
                "schema": self.schema,
                "verdict": self.verdict,
                "sentence": self.sentence,
                "store": self.store,
                "runs": self.runs,
                "next": self.next,
            }
        )

    def to_markdown(self) -> str:
        return self._text


@dataclass(frozen=True)
class NameResult:
    """``poisson-trace name`` in its three forms: a name given, taken back, or the names
    listed. The command prints no JSON, so there is ``to_markdown()`` alone (PB1)."""

    verdict: str
    sentence: str
    next: str
    notes: tuple[str, ...]
    exit_code: int
    _text: str = field(repr=False, compare=False)

    def to_markdown(self) -> str:
        return self._text


@dataclass(frozen=True)
class ImportResult:
    """``poisson-trace import``: one run written from another tool's result files."""

    schema: str
    verdict: str
    sentence: str
    run: str
    store: str
    tool: str
    files: list[dict[str, Any]]
    verdicts: dict[str, Any] | None
    declared: dict[str, Any]
    started: dict[str, Any]
    rows: int
    cases: int
    repeats: dict[str, int]
    outcomes: dict[str, int]
    no_outcome: dict[str, int]
    counts: dict[str, int]
    next: str
    notes: tuple[str, ...]
    exit_code: int
    _data: dict[str, Any] = field(repr=False, compare=False)
    _text: str = field(repr=False, compare=False)

    def to_json(self) -> str:
        from poisson_trace import report

        return report.json_text(self._data)

    def to_markdown(self) -> str:
        return self._text


@dataclass(frozen=True)
class BundleCheck:
    """``poisson-trace handover --check DIR``: ``ok`` and exit 0, or ``not valid`` with the
    first failing line and exit 4. The command prints no JSON (PB1). ``next`` is the command
    a bundle that holds what it promises gets: its HTML report (SB5)."""

    verdict: str
    sentence: str
    exit_code: int
    notes: tuple[str, ...] = ()
    next: str | None = None

    def to_markdown(self) -> str:
        tail = f"\nnext: {self.next}\n" if self.next else ""
        return f"{self.verdict}  {self.sentence}\n{tail}"


@dataclass(frozen=True)
class PagesResult:
    """``poisson-trace ui``: the pages built over a store's runs and saved verdicts, and where
    their index is (``location``, a ``file:`` address). ``next`` is None: the address is the
    next thing."""

    schema: str
    verdict: str
    sentence: str
    location: str
    next: None
    notes: tuple[str, ...]
    exit_code: int

    def to_json(self) -> str:
        from poisson_trace import report

        return report.json_text(
            {
                "schema": self.schema,
                "verdict": self.verdict,
                "sentence": self.sentence,
                "location": self.location,
                "next": self.next,
            }
        )

    def to_markdown(self) -> str:
        return f"{self.verdict}  {self.sentence}\n"


@dataclass(frozen=True)
class Bundle:
    """A handover bundle read back: the verb, ``result.json``, ``handover.json`` and
    ``artifact.json`` as JSON reads them, and ``report.md`` as text."""

    verb: str
    result: dict[str, Any]
    handover: dict[str, Any]
    artifact: dict[str, Any]
    report: str


# ---------- the functions ----------


def open_store(path: str) -> Store:
    """A store Prove wrote, at ``path``; refused when no folder under it holds a run."""
    _text("path", path)
    with _calling():
        core.prove_present()
        core._open(path)
    return Store(path)


def load_config(path: str) -> Config:
    """The config file at ``path``, read and checked against version 1."""
    from poisson_trace import config

    _text("path", path)
    with _calling():
        held = config.load(path)
    return Config(path, held)


@_keywords_given
def where(
    store: Any,
    run: str,
    *,
    event: Sequence[str] | None = None,
    config: Any = None,
    by: str = "kind",
    at: Sequence[int] = (),
    boot: int = 1000,
    seed: int = 0,
    **reader_flags: Any,
) -> WhereResult:
    """Where in the workflow the episodes of one stored run died."""
    keywords = {
        "event": _texts("event", event),
        "config": config,
        "by": _choice("by", by, ("kind", "step")),
        "at": _ints("at", at),
        **_whole({"boot": boot, "seed": seed}),
    }
    result: WhereResult = _counting(
        "where", store, {"run": _text("run", run)}, keywords, reader_flags
    )
    return result


@_keywords_given
def compare(
    store: Any,
    a: str,
    b: str,
    *,
    event: Sequence[str] | None = None,
    config: Any = None,
    by: str = "kind",
    at: Sequence[int] = (),
    max_mde_hr: float | None = None,
    alpha: float = 0.05,
    verdicts: str | None = None,
    **reader_flags: Any,
) -> CompareResult:
    """A before (A) and an after (B), compared."""
    keywords = {
        "event": _texts("event", event),
        "config": config,
        "by": _choice("by", by, ("kind", "step")),
        "at": _ints("at", at),
        "max_mde_hr": _optional_float("max_mde_hr", max_mde_hr),
        "alpha": _float("alpha", alpha),
        "verdicts": _optional_text("verdicts", verdicts),
    }
    result: CompareResult = _counting(
        "compare", store, {"a": _text("a", a), "b": _text("b", b)}, keywords, reader_flags
    )
    return result


@_keywords_given
def fix_check(
    store: Any,
    old: str,
    new: str,
    *,
    event: Sequence[str] | None = None,
    config: Any = None,
    alpha: float = 0.05,
    top: int = 10,
    failing_from: str | None = None,
    min_failures: int | None = None,
    inputs: str | None = None,
    max_mde: float | None = None,
    seed: int = 0,
    measures: bool = False,
    max_change: Sequence[tuple[str, float]] = (),
    verdicts: str | None = None,
    **reader_flags: Any,
) -> FixCheckResult:
    """An old and a new version re-run on the same inputs, compared."""
    keywords = {
        "event": _texts("event", event),
        "config": config,
        "alpha": _float("alpha", alpha),
        "top": _int("top", top),
        "failing_from": _optional_text("failing_from", failing_from),
        "min_failures": _optional_int("min_failures", min_failures),
        "inputs": _optional_text("inputs", inputs),
        "max_mde": _optional_float("max_mde", max_mde),
        **_whole({"seed": seed}),
        "measures": _bool("measures", measures),
        "max_change": _max_change(max_change),
        "verdicts": _optional_text("verdicts", verdicts),
    }
    result: FixCheckResult = _counting(
        "fix-check",
        store,
        {"old": _text("old", old), "new": _text("new", new)},
        keywords,
        reader_flags,
    )
    return result


@_keywords_given
def changes(
    store: Any,
    a: str,
    b: str,
    *,
    event: Sequence[str] | None = None,
    config: Any = None,
    alpha: float = 0.05,
    top: int = 10,
    verdicts: str | None = None,
    **reader_flags: Any,
) -> ChangesResult:
    """The inputs whose failure share moved between two runs."""
    keywords = {
        "event": _texts("event", event),
        "config": config,
        "alpha": _float("alpha", alpha),
        "top": _int("top", top),
        "verdicts": _optional_text("verdicts", verdicts),
    }
    result: ChangesResult = _counting(
        "changes", store, {"a": _text("a", a), "b": _text("b", b)}, keywords, reader_flags
    )
    return result


@_keywords_given
def runs(
    store: Any,
    *,
    event: Sequence[str] | None = None,
    config: Any = None,
    all: bool = False,  # noqa: A002
) -> RunsResult:
    """The runs of a store, newest first, with their names and numbers."""
    keywords = {"event": _texts("event", event), "config": config, "all": _bool("all", all)}
    ns = _namespace("runs", store, {}, keywords, {})
    with _calling(ns):
        core.prepare(ns)
        listed = core.runs(ns)
    assert listed.data is not None
    return RunsResult(
        schema=listed.data["schema"],
        verdict=listed.data["verdict"],
        sentence=listed.data["sentence"],
        store=listed.data["store"],
        runs=listed.data["runs"],
        next=listed.data["next"],
        notes=tuple(ns.notes),
        exit_code=look.DONE,
        _text=listed.text,
    )


def _naming(store: Any, keywords: Mapping[str, Any], **form: Any) -> NameResult:
    ns = _namespace("name", store, {}, {**keywords, **form}, {})
    with _calling(ns):
        core.prepare(ns)
        listed = core.name(ns)
    return NameResult(
        verdict="ok",
        sentence=listed.sentence,
        next=listed.following,
        notes=tuple(ns.notes),
        exit_code=look.DONE,
        _text=listed.text,
    )


@_keywords_given
def name(store: Any, run: str, new: str, *, config: Any = None) -> NameResult:
    """``name RUN NEW``: give a stored run a name of yours."""
    return _naming(
        store,
        {"config": config},
        run=_text("run", run),
        new=_text("new", new),
        forget=False,
        list=False,
    )


@_keywords_given
def forget_name(store: Any, run: str, *, config: Any = None) -> NameResult:
    """``name RUN --forget``: take back the name of yours that RUN has."""
    return _naming(
        store, {"config": config}, run=_text("run", run), new=None, forget=True, list=False
    )


@_keywords_given
def list_names(store: Any, *, config: Any = None) -> NameResult:
    """``name --list``: the names of yours in the store."""
    return _naming(store, {"config": config}, run=None, new=None, forget=False, list=True)


@_keywords_given
def import_run(
    store: Any,
    tool: str | None,
    files: Sequence[str],
    *,
    config: Any = None,
    run: str | None = None,
    started: str | None = None,
    verdicts: str | None = None,
    **reader_flags: Any,
) -> ImportResult:
    """``poisson-trace import TOOL FILE [FILE ...]``: the files read with the tool's reader,
    written as one new run of the store. ``tool`` may be None when ``files`` is one folder,
    whose files say which tool wrote them."""
    from poisson_trace.ingest import importing

    held_files = [_text("files", f) for f in _items("files", files)]
    ns = argparse.Namespace(
        tool=_optional_text("tool", tool),
        files=held_files,
        store=_store_word(store),
        config=_config_word(config),
        run=_optional_text("run", run),
        started=_optional_text("started", started),
        verdicts=_optional_text("verdicts", verdicts),
        json=False,
        debug=False,
    )
    ns.notes = []
    ns.verb = "import"
    with _calling(ns):
        settings = _settings_of(ns.config)
        present = importing.present()
        if ns.tool is not None and ns.tool not in present and core.is_folder(ns.tool):
            # a folder in the tool's place, as the command line takes it: the tool is the one
            # whose files it holds
            held_files = [ns.tool, *held_files]
            ns.files, ns.tool = held_files, None
        folders = [f for f in held_files if core.is_folder(f)]
        if ns.tool is None:
            if len(held_files) != 1 or not folders:
                raise ValueError("tool is None, and files is not one folder of a tool's results")
            ns.tool = _import_folder_tool(held_files[0])
        if ns.tool not in present:
            raise look.Refused(
                f"unknown tool {look.shown(ns.tool)}; this install reads: "
                f"{', '.join(present) or 'nothing'}",
                f"{importing.PROG} --help",
            )
        help_line = f"{importing.PROG} {ns.tool} --help"
        flags = _reader_namespace(ns.tool, "import", reader_flags)
        given = set(reader_flags)
        if settings is not None and settings.signals:
            filled = importing.filled_stand_ins(ns.tool, settings.signals, given, reader_flags)
            for dest, value in filled.items():
                setattr(flags, dest, value)
                given.add(dest)
        for dest, value in vars(flags).items():
            setattr(ns, dest, value)
        missing = [
            max(a.option_strings, key=len)
            for a in importing.reader_actions(ns.tool)
            if a.required and a.dest not in given
        ]
        if missing:
            raise look.Usage(
                f"the following arguments are required: {', '.join(missing)}", help_line
            )
        if not folders and ns.run is None:
            raise look.Usage("the following arguments are required: --run", help_line)
        if len(folders) > 1 or (folders and len(held_files) > 1):
            raise look.Usage(
                "a folder is given alone, in place of the files: give one folder, or files",
                help_line,
            )
        said = importing.usage_fault(ns)
        if said is not None:
            raise look.Usage(look.quoted(said), help_line)
        imported = importing.import_run(ns, settings, folders)
    data = imported.data
    return ImportResult(
        schema=data["schema"],
        verdict=data["verdict"],
        sentence=data["sentence"],
        run=data["run"],
        store=data["store"],
        tool=data["tool"],
        files=data["files"],
        verdicts=data.get("verdicts"),
        declared=data["declared"],
        started=data["started"],
        rows=data["rows"],
        cases=data["cases"],
        repeats=data["repeats"],
        outcomes=data["outcomes"],
        no_outcome=data["no_outcome"],
        counts=data["counts"],
        next=data["next"],
        notes=tuple(ns.notes),
        exit_code=look.DONE,
        _data=data,
        _text=imported.text,
    )


def _settings_of(given: Any) -> Any:
    """The config a call named: read when a path, as it is when read already, None for None."""
    from poisson_trace import config

    if given is None or isinstance(given, config.Config):
        return given
    return config.load(given)


def save(result: Any) -> Any:
    """``--save``: the verdict saved as an artifact in the runs' store, under
    ``.poisson/artifacts``. The result as the command prints it with ``--save``; a store that
    cannot be written to is a note, and the result goes on."""
    if not isinstance(result, _Counting):
        raise ValueError(
            "save takes the result of where, compare, fix_check or changes, not "
            f"{type(result).__name__}"
        )
    with _calling(result._counted.ns):
        delivered = core.save(result._counted, result._delivered, None, False)
    return _result(result._counted, delivered)


def load_bundle(folder: str) -> Bundle:
    """A handover bundle ``to_bundle`` wrote, read back; refused when ``folder`` is not a
    bundle or does not hold what it promises."""
    _text("folder", folder)
    with _calling():
        read = core.load_bundle(folder)
    return Bundle(read.verb, read.result, read.handover, read.artifact, read.report)


def validate_bundle(folder: str) -> BundleCheck:
    """``poisson-trace handover --check DIR``: whether the bundle holds what it promises."""
    _text("folder", folder)
    with _calling():
        checked = core.validate_bundle(folder)
    return BundleCheck(checked.verdict, checked.sentence, checked.exit_code, (), checked.following)


# ---------- the static pages (section 17.3 item 7) ----------


def _as_ui(e: Refusal) -> Refusal:
    """A refusal ``runs`` gives, as ``ui`` gives it: the commands under it name ``ui``."""
    swap = ("poisson-trace runs", "poisson-trace ui")
    return Refusal(
        e.message.replace(*swap),
        next=tuple(n.replace(*swap) for n in e.next),
        exit_code=e.exit_code,
        notes=e.notes,
    )


def _ui_listing(store: Any, config: Any) -> RunsResult:
    """The runs of a store for its pages, as ``runs`` lists them under the config's failures;
    a store that does not carry them (the config's other store, DM9) is listed with the failed
    column uncounted; a store ``runs`` cannot read is the refusal ``runs`` gives (A5)."""
    try:
        return runs(store, config=config)
    except Refusal as e:
        first = e
    if config is None:
        raise _as_ui(first)
    try:
        cfg = config if isinstance(config, Config) else load_config(config)
        named = store is None or (isinstance(store, str) and store in cfg._held.named)
        path = cfg.store(store) if named else _store_word(store)
        assert path is not None
        return runs(path)
    except Refusal:
        raise _as_ui(first) from None


def _stores_of(store: Any, config: Any) -> list[tuple[str | None, str]]:
    """The stores ``ui`` builds, each as its config name (None for the unnamed store, or a
    store given by its path) and its path: the store read first, then every other store the
    config names (DM10)."""
    word = _store_word(store)
    if config is None:
        assert word is not None
        return [(None, word)]
    cfg = config if isinstance(config, Config) else load_config(config)
    held = cfg._held
    if word is None:
        root, name = cfg.store(None), None
    elif word in held.named:
        root, name = cfg.store(word), word
    else:
        root, name = word, None
    out: list[tuple[str | None, str]] = [(name, root)]
    everyone: list[tuple[str | None, str]] = []
    if held.store is not None:
        everyone.append((None, str(held.store)))
    everyone += [(n, str(p)) for n, p in held.named.items()]
    for other_name, path in everyone:
        if os.path.realpath(path) != os.path.realpath(root):
            out.append((other_name, path))
    return out


def build_pages(store: Any, *, config: Any = None) -> PagesResult:
    """``poisson-trace ui``: Trace's pages over a store's runs and saved verdicts, built into
    its ``.poisson/ui/trace/``, and, when a config is read, over every other store it names,
    so that the pages link one another (DM10). Prove's own pages beside them are never
    touched. Refused as ``runs`` refuses a store it cannot read, and where the pages cannot be
    written."""
    if config is not None and not isinstance(config, Config):
        _text("config", config)
    listing = _ui_listing(store, config)
    stores = _stores_of(store, config)
    cfg = None if config is None else config if isinstance(config, Config) else load_config(config)
    events = list(cfg._held.events) if cfg is not None and cfg._held.events else None
    index_of = {
        path: Path(path) / ".poisson" / "ui" / core.PAGES / "index.html" for _, path in stores
    }
    try:
        for i, (name, path) in enumerate(stores):
            listed = listing if i == 0 else _ui_listing(name, cfg)
            counted = (
                events if events and all(r["failed"] is not None for r in listed.runs) else None
            )
            links = [
                (Path(other).name, _relative(index_of[path], index_of[other]))
                for _other_name, other in stores
                if other != path
            ]
            doc = {
                "verdict": listed.verdict,
                "sentence": listed.sentence,
                "store": listed.store,
                "runs": listed.runs,
            }
            core.build_store_pages(Path(path), doc, counted, links)
    except look.Refused as e:
        raise Refusal(str(e), next=e.nexts) from None
    except OSError as e:
        raise Refusal(f"cannot write the pages into {listing.store}: {look.why(e)}") from None
    location = index_of[stores[0][1]].resolve().as_uri()
    return PagesResult(
        schema="poisson-trace.ui/1",
        verdict="ok",
        sentence=f"pages at {location}",
        location=location,
        next=None,
        notes=(),
        exit_code=look.DONE,
    )


def _relative(here: Path, there: Path) -> str:
    """``there`` as a link on the page at ``here``: a relative path, never an absolute one
    (section 17.3 item 9)."""
    return os.path.relpath(
        os.path.abspath(there), start=os.path.dirname(os.path.abspath(here))
    ).replace(os.sep, "/")


# ---------- for the command lines: not public, and promising nothing ----------


def _config_here() -> Config | None:
    """The current folder's ``trace.toml``, read, or None when there is none: what the
    command line passes in when ``--config`` is not given."""
    from poisson_trace import config

    with _calling():
        held = config.load(None)
    return None if held is None else Config(config.CONFIG, held)


def _is_folder(word: str) -> bool:
    return core.is_folder(word)


def _folder_reader(
    verb: str, store: Any, positionals: Mapping[str, str], keywords: Mapping[str, Any]
) -> str | None:
    """The reader whose flags the command line's leftover words are: the tool whose result
    files the verb's folder words hold, or None when no run word is such a folder. Prepared
    and planned as the verb is, so that what the verb refuses first is refused here first."""
    import inspect

    function = globals()[_FUNCTIONS[verb]]
    defaults = {
        p.name: p.default
        for p in inspect.signature(function).parameters.values()
        if p.kind is p.KEYWORD_ONLY
    }
    token = _GIVEN.set(tuple(keywords))
    try:
        ns = _namespace(verb, store, positionals, {**defaults, **keywords}, {})
    finally:
        _GIVEN.reset(token)
    with _calling(ns):
        core.prepare(ns)
        plan = core.plan_folders(ns)
    return plan.tool


def _unordered_line(
    e: Unordered, argv: Sequence[str], valued: Collection[str]
) -> tuple[str, tuple[str, ...]]:
    """PA19: the refusal's sentence and next commands from the command line's own words."""
    return core.unordered(e.held, str(argv[0]), argv, valued)


def _reader(tool: str) -> Any:
    from poisson_trace.ingest import importing

    return importing.reader(tool)


def _present() -> tuple[str, ...]:
    from poisson_trace.ingest import importing

    return importing.present()


def _module_name(tool: str) -> str:
    from poisson_trace.ingest import importing

    return importing.module_name(tool)


def _readers() -> tuple[str, ...]:
    from poisson_trace.ingest import importing

    return importing.READERS


def _stand_ins(tool: str, cfg: Config, words: Sequence[str] = ()) -> dict[str, Any]:
    """What ``[signals]`` stands in for among the reader's flags, for the import's command
    line to fill into its words before it parses them (SA8). ``words`` is the command line,
    for a reader whose stand-ins depend on what the line itself says: a cut stands in for the
    LangSmith reader only where the line or the config reads a score."""
    from poisson_trace.ingest import importing

    return importing.stand_ins(tool, cfg._held.signals, _typed(words))


def _typed(words: Sequence[str]) -> dict[str, Any]:
    """The long options on a command line, by dest: each with the word after it, or True for
    one given alone. Read before the line is parsed, so a value is the next word as written."""
    out: dict[str, Any] = {}
    line = list(words)
    for i, word in enumerate(line):
        if not word.startswith("--") or word == "--":
            continue
        name, equals, value = word[2:].partition("=")
        if equals:
            out[name.replace("-", "_")] = value
        elif i + 1 < len(line) and not line[i + 1].startswith("--"):
            out[name.replace("-", "_")] = line[i + 1]
        else:
            out[name.replace("-", "_")] = True
    return out


def _import_folder_tool(path: str) -> str:
    """The tool whose files a folder given in the tool's place holds."""
    from poisson_trace.ingest import importing

    with _calling():
        importing._prove_present()
        found = importing._resolved(path, None)
    assert found.tool is not None
    return str(found.tool)


def _import_usage(ns: argparse.Namespace) -> str | None:
    """Why an import command line its parser takes is still wrong, in the reader's words."""
    from poisson_trace.ingest import importing

    return importing.usage_fault(ns)


def _form_word(text: str) -> str:
    """``--names from=FORM`` read: the form, or a ``ValueError`` with the parser's words."""
    from poisson_trace.config import FORMS

    key, _, form = text.partition("=")
    if key != "from" or form not in FORMS:
        raise ValueError(f'takes from=target, from=date or from=target-date, not "{text}"')
    return form


def _fail_on_word(text: str) -> tuple[str, ...]:
    """``--fail-on`` read: the check's results that fail its job, comma-separated."""
    from poisson_trace.config import FAIL_ON

    picked = [p.strip() for p in text.split(",")] if text.strip() else []
    if any(p not in FAIL_ON for p in picked):
        raise ValueError(f'takes failed-more, too-small or both, comma-separated, not "{text}"')
    return tuple(dict.fromkeys(picked))


def _max_change_word(text: str) -> tuple[str, float]:
    """``--max-change MEASURE=N%`` read: the measure and its ceiling as a share (CS10)."""
    from poisson_trace.stats.continuous import parse_max_change

    return parse_max_change(text)
