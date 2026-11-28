"""The one core behind every face of Trace: the verbs' work, from the words the command line or
``poisson_trace.api`` hands it to an outcome that holds everything the command prints and saves.

Nothing here prints. What the command line prints as ``note:`` lines is collected on
``ns.notes``; every refusal is raised (``look.Refused`` with its next commands, ``look.Usage``
for a setting a verb needs that nothing gives, ``look.Failed`` after work started); the text
and the JSON come back on the outcome. ``cli.py`` parses the command line, calls ``api`` and
prints; ``api.py`` types the surface and turns what is raised here into ``api.Refusal``.

The settings reach a verb as an ``argparse.Namespace`` built by the command line's parser or
by ``api`` from its keywords, each attribute the verb's flag; ``ns.typed_flags`` names the
flags given (a keyword passed is a flag given), ``ns.config`` is the config's path, the
config read already, or None, when no config is read at all.
"""

from __future__ import annotations

import argparse
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poisson_trace import look
from poisson_trace.look import count
from poisson_trace.stats import portable

# The by-input reading's seeded sign assignments, when there are too many to enumerate.
_DRAWS = 100_000
# The most bootstrap resamples where takes: a thousand times the default.
_MOST_BOOT = 1_000_000
DOES = "Poisson Trace reads stored runs"
# the verbs that count failures, and so need them from a flag or the config
_COUNTING = ("where", "compare", "fix-check", "changes")
# the complete runs the listing shows, newest first, before it says how many more there are
_LISTED = 50
#: The most steps and parent spans ``timings`` lists for one run when it lists the whole run.
MOST_STEPS = 20_000


class _Refusal(look.Refused):
    """One sentence, exit 1, and the commands to run next under it, if any."""


# the verbs that read two runs, the older version's first
_TWO_RUNS = ("compare", "fix-check", "changes")
PLACEHOLDERS = ("OLDER", "NEWER")


def unordered(
    e: Any, verb: str, argv: Sequence[str], valued: Collection[str]
) -> tuple[str, tuple[str, ...]]:
    """latest or previous refused because the start times cannot order the runs: the sentence
    and the next commands. For a verb of two runs, the command as it was given with OLDER and
    NEWER in place of each reserved word, so that it cannot be run the wrong way round as it
    stands; ``argv`` is the verb and its words as typed (the command line's) or as rebuilt
    from the call (the API's), ``valued`` the options that take a value."""
    words: list[str] = []
    replaced: list[str] = []
    place = -1  # -1 until the verb is passed; then the place of each run given
    i = 0
    while i < len(argv):
        word = argv[i]
        if word.startswith("-") and word != "-":
            words.append(typed_option(word))
            if "=" not in word and word in valued and i + 1 < len(argv):
                words.append(look.word(argv[i + 1]))
                i += 1
        elif place < 0:
            words.append(look.word(word))
            place = 0
        else:
            if verb in _TWO_RUNS and place < 2 and by_start(word):
                words.append(PLACEHOLDERS[place])
                replaced.append(PLACEHOLDERS[place])
            else:
                words.append(look.word(word))
            place += 1
        i += 1
    if not replaced:
        return str(e.sentence(two=False)), (str(e.listing),)
    runs = " and ".join(f'"{r}"' for r in e.runs)
    if len(replaced) == 2:
        said = f"OLDER and NEWER are {runs}, in the order you know"
    else:
        said = f"{replaced[0]} is one of {runs}, as you know them"
    line = look.command("poisson-trace", *words) + f"  # {said}"
    return str(e.sentence(two=True)), (line, str(e.listing))


def typed_option(word: str) -> str:
    """An option as typed, its value after ``=`` quoted for a shell."""
    flag, joined, value = word.partition("=")
    return f"{flag}={look.word(value)}" if joined else word


def by_start(word: str) -> bool:
    """Whether a run is given by a word that goes by when runs started: latest or previous."""
    text = word.strip()
    return text in ("latest", "previous") or text.startswith(("latest:", "previous:"))


def _from_config(ns: argparse.Namespace, *, folders: bool = False) -> None:
    """The store, the failures and the ceilings a verb takes from the config when no flag gives
    them; a store name the config holds is that store. What neither gives is a wrong command
    line, as it is with no config, but for a store when every run is given as a folder."""
    from poisson_trace import config

    ns.folder_words = {}
    ns.reader_flags = list(getattr(ns, "reader_flags", ()))
    ns.from_folders = False
    ns.notes = list(getattr(ns, "notes", ()))
    # the config: read when the command line names a file (or found trace.toml here and
    # passed it in), never looked for by the core itself
    if isinstance(ns.config, config.Config):
        held: config.Config | None = ns.config
    elif ns.config is None:
        held = None
    else:
        held = config.load(ns.config)
    ns.form = held.names_from if held is not None else "target"
    ns.typed_store = ns.store
    ns.typed_events = list(getattr(ns, "event", None) or ())
    ns.config_flags = held.flags() if held is not None else ()
    ns.settings = held
    if ns.store is not None and held is not None and ns.store in held.named:
        ns.store = held.named[ns.store]
    elif ns.store is None and held is not None:
        ns.store = held.store
    if hasattr(ns, "event") and ns.event is None and held is not None and held.events is not None:
        ns.event = list(held.events)
    flags = []
    if ns.store is None and not folders:
        flags.append("--store")
    if ns.verb in _COUNTING and not ns.event:
        flags.append("--event")
    if flags:
        said = {"--store": "a store", "--event": "the failures"}
        if held is None:
            why = "no trace.toml here gives " + " or ".join(said[f] for f in flags)
        else:
            why = f"{held.shown} gives no " + " and no ".join(
                said[f].removeprefix("a ").removeprefix("the ") for f in flags
            )
        raise look.Usage(
            f"{' and '.join(flags)} {'is' if len(flags) == 1 else 'are'} required: {why}",
            f"poisson-trace {ns.verb} --help",
        )
    if held is not None:
        if ns.verb == "compare" and ns.max_mde_hr is None:
            ns.max_mde_hr = held.max_mde_hr
        if ns.verb == "fix-check" and ns.max_mde is None:
            ns.max_mde = held.max_mde
    # the continuous measures' ceilings: the config's, a flag winning for its measure;
    # every verb of two runs saves the measures with them, fix-check prints them
    ns.ceilings = _ceilings(held, getattr(ns, "max_change", None) or [])
    ns.joined = None  # the --verdicts join, once made
    ns.temp_store = False  # the runs were read from tool folders into a store that does not last
    ns.verdicts = getattr(ns, "verdicts", None)
    ns.measures = getattr(ns, "measures", False)


def _ceilings(held: Any, flags: Sequence[tuple[str, float]]) -> dict[str, float]:
    from poisson_trace.stats.continuous import MEASURES

    merged: dict[str, float] = dict(held.max_change) if held is not None else {}
    for measure, fraction in flags:
        merged[measure] = fraction
    return {m: merged[m] for m in MEASURES if m in merged}


def prepare(ns: argparse.Namespace) -> None:
    """What every verb that reads a store does before any work, in the command's order: the
    config's store, failures and ceilings (what nothing gives is a wrong command line), Prove
    present at a version this package reads, and the settings checked."""
    words = run_words(ns)
    folders = [w for _, w in words if is_folder(w)]
    _from_config(ns, folders=bool(words) and len(folders) == len(words))
    refusal = look.prove_refusal(DOES)
    if refusal is not None:
        raise _Refusal(refusal, *look.prove_nexts())
    _validate(ns)


def prove_present(does: str = DOES) -> None:
    refusal = look.prove_refusal(does)
    if refusal is not None:
        raise _Refusal(refusal, *look.prove_nexts())


def _validate(ns: argparse.Namespace) -> None:
    """The settings a verb refuses after the command line is read (the command line's own
    checks of ``--svg``, ``--out`` and ``--force`` stay with it)."""
    if ns.verb == "where":
        if not 1 <= ns.boot <= _MOST_BOOT:
            raise _Refusal(f"--boot takes 1 to {count(_MOST_BOOT)} resamples, not {ns.boot}")
    if ns.verb in _COUNTING and ns.verdicts == "":
        raise _Refusal("--verdicts takes the name of the file to read")
    if ns.verb in ("where", "fix-check") and ns.seed < 0:
        raise _Refusal(f"--seed takes 0 or more, not {ns.seed}")
    if ns.verb == "compare":
        if ns.max_mde_hr is None:
            raise _Refusal(
                "--max-mde-hr is required: the largest minimum detectable hazard ratio you "
                "accept, such as 1.5; it has no default"
            )
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if not ns.max_mde_hr > 0.0:
            raise _Refusal("--max-mde-hr must be a positive hazard ratio")
    if ns.verb in ("fix-check", "changes"):
        if not 0.0 < ns.alpha < 1.0:
            raise _Refusal("--alpha must be strictly between 0 and 1")
        if ns.top < 0:
            raise _Refusal("--top must be 0 or more")
    if ns.verb in ("compare", "changes") and ns.a == ns.b:
        raise _Refusal(f"A and B are both {ns.a}; the two runs compared must differ")
    if ns.verb == "fix-check":
        _validate_fix_check(ns)


def _validate_fix_check(ns: argparse.Namespace) -> None:
    if (ns.failing_from is None) == (ns.inputs is None):
        raise _Refusal(
            "exactly one of --failing-from RUN and --inputs all is required; which inputs are "
            "compared has no default"
        )
    if ns.inputs is not None and ns.inputs != "all":
        raise _Refusal(f"--inputs takes only the value all, not {ns.inputs}")
    if ns.min_failures is not None:
        if ns.failing_from is None:
            raise _Refusal("--min-failures applies to --failing-from and was given without it")
        if ns.min_failures < 1:
            raise _Refusal("--min-failures must be at least 1")
    if ns.max_mde is None:
        raise _Refusal(
            "--max-mde is required, as a fraction of failure share (0.20 is twenty points); "
            "it has no default"
        )
    if not 0.0 < ns.max_mde < 1.0:
        raise _Refusal("--max-mde must be strictly between 0 and 1 (0.20 is twenty points)")
    if ns.old == ns.new:
        raise _Refusal(f"OLD and NEW are both {ns.old}; the two runs compared must differ")
    for arm, run in (("old", ns.old), ("new", ns.new)):
        if ns.failing_from == run:
            raise _Refusal(
                f"the selecting run {run} is also the {arm} arm; both arms must be fresh "
                "re-runs, because the selecting run's failures on these inputs are there by "
                "selection"
            )


# ---------- runs given as folders ----------

# each verb's run words, by the attribute its parser gives them
_RUN_WORDS: dict[str, tuple[str, ...]] = {
    "where": ("run",),
    "compare": ("a", "b"),
    "fix-check": ("old", "new", "failing_from"),
    "changes": ("a", "b"),
}


def run_words(ns: argparse.Namespace) -> list[tuple[str, str]]:
    """``(attribute, word)`` for each run the command line gives the verb."""
    given = [(attr, getattr(ns, attr, None)) for attr in _RUN_WORDS.get(ns.verb, ())]
    return [(attr, word) for attr, word in given if isinstance(word, str)]


def is_folder(word: str) -> bool:
    from poisson_trace.ingest import folder

    return folder.is_folder(word)


def _reached(ns: argparse.Namespace, words: Sequence[str]) -> list[str]:
    """The words that reach a stored run of the verb's store; none when there is no store or
    it cannot be read, since a word that reaches nothing may still name a folder."""
    if ns.store is None:
        return []
    try:
        _, index = _named(ns)
    except Exception:
        return []
    out = []
    for word in words:
        try:
            index.resolve(word)
        except Exception:
            continue
        out.append(word)
    return out


@dataclass
class Plan:
    """Which of a verb's run words are folders to read, once the words
    that reach stored runs are taken out: ``kind`` is ``none``, ``prove`` (Prove's folders,
    read where they are) or ``tool`` (one tool's result files, read with its reader's flags
    into a store that does not outlive the call); ``found`` is each folder resolved."""

    given: list[tuple[str, str]] = field(default_factory=list)
    found: list[tuple[str, str, Any]] = field(default_factory=list)
    kind: str = "none"
    tool: str | None = None


def plan_folders(ns: argparse.Namespace) -> Plan:
    """The verb's run words sorted into stored runs and folders, with the refusals the command
    line gives in its order: a word that reaches a stored run is that run; a word
    that reaches none and names a folder is the folder; runs from two places on one report are
    refused, so are folders of two tools and two folders of one name."""
    from poisson_trace.ingest.folder import resolve
    from poisson_trace.ingest.rows import Refusal

    words = run_words(ns)
    stored = set(_reached(ns, [w for _, w in words if is_folder(w)]))
    given = [(attr, w) for attr, w in words if is_folder(w) and w not in stored]
    if not given:
        return Plan()
    others = [w for attr, w in words if (attr, w) not in given]
    if others:
        # each must reach a stored run, and is refused where it does not
        _, index = _named(ns)
        for word in others:
            index.resolve(word)
        folders = _listed([w for _, w in given])
        raise _Refusal(
            f"{folders} {'is a folder' if len(given) == 1 else 'are folders'} and "
            f"{_listed(others)} a stored run; a report reads its runs from one place, so import "
            "the folder into the store and give its run by name",
            *(
                look.command("poisson-trace", "import", look.word(w), *_reach(ns), *ns.reader_flags)
                for _, w in given
            ),
        )
    try:
        found = [(attr, word, resolve(Path(word))) for attr, word in given]
    except Refusal as e:
        raise _Refusal(str(e), *e.nexts) from None
    prove = [(a, w, r) for a, w, r in found if r.kind in ("run", "store")]
    tools = [(a, w, r) for a, w, r in found if r.kind not in ("run", "store")]
    if prove and tools:
        raise _Refusal(
            f"{_listed([w for _, w, _ in prove])} {'is' if len(prove) == 1 else 'are'} Prove's "
            f"and {_listed([w for _, w, _ in tools])} another tool's results; a report reads its "
            "runs from one place, so import the results into that store and give the runs by "
            "name"
        )
    if prove:
        return Plan(given, prove, "prove", None)
    names = list(dict.fromkeys(str(r.tool) for _, _, r in tools))
    if len(names) > 1:
        each = ", ".join(f"{w} ({r.tool})" for _, w, r in tools)
        raise _Refusal(
            f"the folders hold the results of {len(names)} tools, {each}; a report compares "
            "runs of one tool's, read with its reader's flags"
        )
    return Plan(given, tools, "tool", names[0])


def run_verb(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], Any],
    plan: Plan,
    flags: argparse.Namespace | None,
) -> Any:
    """The verb on its stored runs, or on the folders the plan found: Prove's where they are,
    a tool's through its reader with ``flags``, the reader's flags as its parser gives them."""
    from poisson_trace.ingest.rows import Refusal

    if plan.kind == "none":
        return verb(ns)
    try:
        if plan.kind == "prove":
            return _read_prove_folders(ns, verb, plan.found)
        assert flags is not None
        return _read_tool_folders(ns, verb, flags, plan.found)
    except Refusal as e:
        raise _Refusal(str(e), *e.nexts) from None


def _listed(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _read_prove_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], Any],
    found: Sequence[tuple[str, str, Any]],
) -> Any:
    """Prove folders, read where they are: their one store, each run by its id."""
    stores = {Path(r.store).resolve() for _, _, r in found}
    if len(stores) > 1:
        raise _Refusal(
            f"{_listed([w for _, w, _ in found])} are runs of {len(stores)} different stores; "
            "a report reads its runs from one store"
        )
    _, first, resolved = found[0]
    ns.store = str(resolved.store)
    words: dict[str, str] = {}
    if resolved.kind == "run":
        # every run of the store is a folder beside the one typed, and named so
        from poisson_trace.ingest.writer import runs_in

        for run_id in runs_in(Path(ns.store)):
            words[run_id] = str(Path(first).parent / run_id)
    for attr, word, r in found:
        setattr(ns, attr, r.run_id)
        words[r.run_id] = word
    ns.typed_store = None
    ns.folder_words = words
    ns.from_folders = True
    return verb(ns)


def _read_tool_folders(
    ns: argparse.Namespace,
    verb: Callable[[argparse.Namespace], Any],
    flags: argparse.Namespace,
    found: Sequence[tuple[str, str, Any]],
) -> Any:
    """Tool folders, read by their reader with its flags into a store that does not outlive the
    call, each run under its folder's name."""
    import shutil
    import tempfile

    from poisson_trace.ingest import importing as importer
    from poisson_trace.names import import_name_refusal

    named: dict[str, str] = {}
    for _, word, r in found:
        if r.name in named:
            raise _Refusal(
                f"{named[r.name]} and {word} are both named {r.name}, and a run read from a "
                f"folder takes its folder's name; import them under two names and give the runs "
                "by name"
            )
        named[r.name] = word
        hole = import_name_refusal(r.name)
        if hole is not None:
            raise _Refusal(f"a run read from a folder takes its folder's name, and {hole}")
    tool = str(found[0][2].tool)
    module = importer.reader(tool)
    wrong = getattr(module, "usage", None)
    said = wrong(flags) if wrong is not None else None
    if said is not None:
        raise look.Usage(look.quoted(said), f"poisson-trace {ns.verb} --help")
    from poisson_trace.ingest.writer import write

    settings = ns.settings
    held = tempfile.mkdtemp(prefix="poisson-trace-")
    try:
        read: list[tuple[str, Any, Any]] = []
        for attr, _, r in found:
            read_ns = argparse.Namespace(
                **vars(flags),
                files=[str(f) for f in r.files],
                run=r.name,
                store=held,
                signals=dict(settings.signals) if settings is not None else {},
            )
            run = module.read(read_ns)
            importer.one_run(tool, read_ns, r, run, ())
            read.append((attr, r, run))
        if ns.verdicts is not None:
            # the join as the folders are read, so a verdict joins by the input key the reader
            # computed as well as by case; over both runs' rows at once
            read = _join_read(ns, read)
        for attr, r, run in read:
            importer.checked(run)
            write(
                run,
                Path(held),
                ns.form,
                rules=settings.rules if settings is not None else (),
                budgets=settings.budgets if settings is not None else None,
            )
            setattr(ns, attr, r.name)
        ns.store = held
        ns.temp_store = True
        ns.typed_store = None
        ns.folder_words = {r.name: word for _, word, r in found}
        ns.from_folders = True
        return verb(ns)
    finally:
        shutil.rmtree(held, ignore_errors=True)


def _join_read(
    ns: argparse.Namespace, read: Sequence[tuple[str, Any, Any]]
) -> list[tuple[str, Any, Any]]:
    """The verdicts file joined onto the runs read from folders that the verb compares (the
    two arms, not a selecting run), by case then by input key, in memory."""
    from dataclasses import replace

    from poisson_trace.ingest import verdicts

    arms = [(attr, r, run) for attr, r, run in read if attr in _ARMS]
    rows: list[Any] = []
    inputs: dict[str, str] = {}
    for _, _, run in arms:
        rows.extend(run.rows)
        for case, key in run.inputs.items():
            inputs.setdefault(case, key)
    joined = verdicts.join(rows, Path(ns.verdicts), inputs or None)
    ns.joined = verdicts.block(Path(ns.verdicts), joined)
    out: list[tuple[str, Any, Any]] = []
    at = 0
    for attr, r, run in read:
        if attr in _ARMS:
            run = replace(run, rows=joined.rows[at : at + len(run.rows)])
            at += len(run.rows)
        out.append((attr, r, run))
    return out


# the attributes that hold a verb's two compared runs, which --verdicts joins onto
_ARMS = ("a", "b", "old", "new")


def _open(path: str) -> tuple[Any, list[str]]:
    """The store and the runs it holds, or a refusal when no folder under the path holds a run
    Prove stored: a path that is not there, an empty folder and a plain file alike. A store
    whose descriptor says it is in a newer format than Trace knows, or whose descriptor file is
    not a descriptor, is refused before anything of it is read: every verb opens its store
    here, so none reads or writes into one. The broken file is refused in the words --save
    refuses it in."""
    from poisson_prove.store import Store

    from poisson_trace import saved

    newer = saved.newer_format(Path(path))
    if newer is not None:
        raise _Refusal(saved.newer_said(f"the store at {look.shown(path)}", newer))
    broken = saved.broken_said(Path(path))
    if broken is not None:
        raise _Refusal(f"{broken}; nothing was written")
    store = Store(path)
    try:
        held = store.runs()
    except OSError as e:
        raise _Refusal(f"cannot read the store at {look.shown(path)} ({look.why(e)})") from e
    if not held:
        raise _Refusal(
            f"no store at {look.shown(path)} (no folder under it holds a run Prove stored)"
        )
    return store, held


def _named(ns: argparse.Namespace, *, lenient: bool = False) -> tuple[Any, Any]:
    """The store and its runs, each with its name: a store that is not there, a names file
    that is not one and an entry for a run the store lacks are refused."""
    from poisson_trace import names

    store, held = _open(ns.store)
    # where the store is, for what a result reads later, wherever the process is then
    ns.store_root = os.path.abspath(ns.store)
    if ns.from_folders:
        # the runs were read from folders: a command names each by its folder and carries no
        # store, and one that names no run carries nothing
        index = names.index(store, held, ns.store, lenient=lenient, form=ns.form, carried=())
        index.given = dict(ns.folder_words)
        index.notes = ns.notes
        return store, index
    index = names.index(
        store, held, ns.store, lenient=lenient, form=ns.form, carried=tuple(_reach(ns))
    )
    index.notes = ns.notes
    return store, index


def _load(store: Any, run: Any, *, trace: str = "envelope") -> tuple[Any, Any, Any]:
    """``(manifest, frame, tally)`` for a run the words given reached."""
    try:
        return (
            store.manifest(run.run_id),
            store.read(run.run_id, meta=False, trace=trace),
            store.tally(run.run_id),
        )
    except Exception as e:
        raise _Refusal(f"Prove could not read the run {run.shown()} ({look.why(e)})") from e


def _store_shown(ns: argparse.Namespace) -> Any:
    """The store a verb's JSON names: none when the runs were read from folders, since no
    store the user has holds them."""
    return None if ns.from_folders else ns.store


def _two(index: Any, first: str, second: str, labels: tuple[str, str]) -> tuple[Any, Any]:
    """The two runs two words reach, refused when they are one run."""
    a, b = index.resolve(first), index.resolve(second)
    if a.run_id == b.run_id:
        raise _Refusal(
            f"{labels[0]} and {labels[1]} are both {a.shown()}; the two runs compared must differ"
        )
    return a, b


def _reach(ns: argparse.Namespace) -> list[str]:
    """What a next command carries to read the same store: ``--store`` as it was typed, and
    the config file when it was named by flag; nothing for a store the config gave."""
    words = [] if ns.typed_store is None else [look.option("--store", ns.typed_store)]
    return [*words, *ns.config_flags, *ns.reader_flags]


def _flags(ns: argparse.Namespace) -> list[str]:
    """What a next command carries: the store and each ``--event`` as they were typed, and the
    config file when it was named by flag; what the config gave is left out, since the command
    reads the same config."""
    words = [] if ns.typed_store is None else [look.option("--store", ns.typed_store)]
    for event in dict.fromkeys(ns.typed_events):
        words.append(look.option("--event", event))
    return [*words, *ns.config_flags, *ns.reader_flags]


def _next(index: Any, verb: str, runs: Sequence[Any], ns: argparse.Namespace, *extra: str) -> str:
    """A next command: the runs by the words that reach them, the store and the events given."""
    words = (look.word(index.word_for(r)) for r in runs)
    return look.command("poisson-trace", verb, *words, *_flags(ns), *extra)


def _enveloped(
    data: Mapping[str, Any], verdict: str, sentence: str, following: str | None
) -> dict[str, Any]:
    """The verb's JSON in its order: the schema, the verdict and its sentence, every key the
    verb had, and the next command last."""
    head = {"schema": data["schema"], "verdict": verdict, "sentence": sentence}
    rest = {k: v for k, v in data.items() if k != "schema"}
    # a run's header holds what the markdown alone reads, in keys that open with an underscore
    if isinstance(rest.get("run"), Mapping):
        rest["run"] = _public(rest["run"])
    if isinstance(rest.get("runs"), Mapping):
        rest["runs"] = {k: _public(v) for k, v in rest["runs"].items()}
    return {**head, **rest, "next": following}


def _public(header: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in header.items() if not k.startswith("_")}


def _start_of(manifest: Any) -> dict[str, Any] | None:
    """Where an imported run's start came from, as its import recorded it: the import's word
    for the source (``file time``, ``given``, ``file name``, ``file``, ``earliest span``), the
    tool, and for a time read from a file's name the zone it was read in (None when the run
    was imported before the zone was recorded). None for a run Prove stored."""
    environment = getattr(manifest, "environment", None)
    recorded = environment.get("import") if isinstance(environment, Mapping) else None
    if not isinstance(recorded, Mapping):
        return None
    zone = recorded.get("zone")
    return {
        "from": recorded.get("started_from"),
        "tool": recorded.get("tool"),
        "zone": dict(zone) if isinstance(zone, Mapping) else None,
    }


def _said(verdict: str, sentence: str, report: str, following: str, *details: str) -> str:
    """The text: the verdict line, each detail line under it (what was joined, what was
    written, what was saved), a blank line, the report and the next command."""
    head = f"{verdict}  {sentence}\n" + "".join(f"{line}\n" for line in details)
    return f"{head}\n{report}\nnext: {following}\n"


def _run_before(index: Any, run: Any) -> Any | None:
    """The complete run of the same target that started just before ``run``."""
    order = list(reversed(index.runs))
    at = next((i for i, r in enumerate(order) if r.run_id == run.run_id), None)
    if at is None:
        # a run whose start Prove's record does not give has no place in the order
        return None
    return next((r for r in reversed(order[:at]) if r.complete and r.target == run.target), None)


def _outcomes(frame: Any) -> set[str]:
    return {o for o in frame["outcome"] if o is not None}


def _traced(frame: Any) -> bool:
    """Whether any row of the run carries a trace."""
    return bool(frame["trace"].notna().any()) if len(frame) else False


def _from(run: Any) -> str:
    """Where an untraced run came from, for the sentence that says why it has no traces."""
    return f" (it was imported from {run.backend[len('import:') :]})" if run.imported else ""


def _no_traces(run: Any) -> str:
    """The line every report of a run with no traces carries in place of its curve."""
    return (
        f"This run has no traces{_from(run)}, so there is no step to place it on; fix-check and "
        "changes read it."
    )


def _header(run: Any, manifest: Any, placement: Any) -> dict[str, Any]:
    from poisson_trace.clock import REASONS

    counts = {r: portable.isum(1 for p in placement.rows if p.reason == r) for r in REASONS}
    return {
        "run_id": run.run_id,
        "run_name": run.name,
        "target_id": manifest.target_id,
        "t_unit": manifest.t_unit,
        "status": manifest.status,
        "cap": placement.cap,
        "tally": placement.tally.to_dict(),
        "placement": {
            "placed": len(placement.rows),
            **counts,
            "excluded": dict(placement.excluded),
        },
        "_imported": run.imported,
        "_start": _start_of(manifest),
        # what sweep --note recorded for the run, as Prove reads it; None where there is none
        "_note": getattr(manifest, "note", None),
    }


def _ordered(causes: set[str]) -> list[str]:
    from poisson_prove.trace import KINDS

    return [k for k in KINDS if k in causes] + sorted(c for c in causes if c not in KINDS)


def _tries(placement: Any) -> list[tuple[str, int, str, str]]:
    """Each placed try as the competing-ends estimator reads it: its input, its step, how it
    ended, and the kind of step it failed at."""
    return [(p.config_hash, int(p.index), p.reason, p.cause) for p in placement.rows]


def _arrays(placement: Any) -> tuple[Any, Any, Any]:
    import numpy as np

    index = np.array([p.index for p in placement.rows], dtype=np.int64)
    died = np.array([p.died for p in placement.rows], dtype=bool)
    cause = np.array([p.cause for p in placement.rows], dtype=object)
    return index, died, cause


# ---------- the saved verdict, the handover bundle and the measures ----------


def _check_out(path: str, force: bool) -> None:
    """Refuse, before any work, a bundle folder that is there already without --force, a file
    in its place, or a parent that cannot be written to."""
    target = Path(path)
    try:
        there = target.exists() or target.is_symlink()
        if there and (not target.is_dir() or target.is_symlink()):
            raise _Refusal(f"cannot write {path}: it is a file, not a folder for a bundle")
        if there and not force:
            raise _Refusal(f"{path} exists; add --force to replace it with the bundle")
        parent = target.parent
        if parent.exists() and not parent.is_dir():
            raise _Refusal(f"cannot write {path}: {parent} is not a folder")
        if parent.is_dir() and not os.access(parent, os.W_OK):
            raise _Refusal(f"cannot write {path}: the folder {parent} cannot be written to")
    except OSError as e:
        raise _Refusal(f"cannot write {path} ({look.why(e)})") from e


def _signals(
    ns: argparse.Namespace, arms: Sequence[tuple[str, Any]], events: frozenset[str]
) -> tuple[dict[str, tuple[Any, ...]], dict[str, tuple[Any, ...]]]:
    """Each arm's rows as the reader classifies them, before and after the ``--verdicts``
    join (the same rows when there is no file). A run Prove swept is classified by the config's
    own taxonomy (``_team``). On stored runs the join is made here, over both runs' rows at
    once, by case, and a failure the file filled in is given its kind after it; on
    tool folders it was made as they were read."""
    from poisson_trace.ingest.prove import read_rows

    root = Path(ns.store_root)
    labels, rules, budgets = _team(ns)
    before = {
        arm: read_rows(root, run.run_id, sorted(events), labels, rules, budgets)
        for arm, run in arms
    }
    after = dict(before)
    if ns.verdicts is not None and ns.joined is None:
        from poisson_trace.ingest import verdicts
        from poisson_trace.ingest.rows import Refusal

        rows = [row for arm, _ in arms for row in before[arm]]
        try:
            joined = verdicts.join(rows, Path(ns.verdicts), None)
        except Refusal as e:
            raise _Refusal(str(e), *e.nexts) from None
        ns.joined = verdicts.block(Path(ns.verdicts), joined)
        at = 0
        for arm, _ in arms:
            n = len(before[arm])
            after[arm] = tuple(_kinds_filled(joined.rows[at : at + n]))
            at += n
    return before, after


def _kinds_filled(rows: Sequence[Any]) -> list[Any]:
    """The rows after a ``--verdicts`` join, a failure the file filled in given its kind by the
    built-in rules, so that the failure-type diff counts it under a kind; a kind the file
    gave stays, and a try the source graded was classified as it was read."""
    from poisson_trace.ingest.taxonomy import classify

    return [
        classify(r) if r.result in ("fail", "censored") and r.failure_kind is None else r
        for r in rows
    ]


_MISALIGNED = "the run's rows and its signals do not line up; the report was not printed"


def _filled(frame: Any, before: Sequence[Any], after: Sequence[Any], events: frozenset[str]) -> Any:
    """The run's frame with the outcomes a verdict filled: a filled ``fail`` counts as failed
    whatever the run's failure words, a filled success as not; a try with a
    recorded outcome is as it was, since a verdict that differed was refused."""
    changed = [
        (i, a)
        for i, (b, a) in enumerate(zip(before, after, strict=True))
        if (a.outcome, a.error) != (b.outcome, b.error)
    ]
    if not changed:
        return frame
    if len(frame) != len(before):
        raise look.Failed(_MISALIGNED)
    frame = frame.copy()
    for column in ("outcome", "error"):
        frame[column] = frame[column].astype(object)
    words = sorted(events)
    at_outcome, at_error = frame.columns.get_loc("outcome"), frame.columns.get_loc("error")
    for i, row in changed:
        config = frame["config"].iloc[i]
        same = frame["config_hash"].iloc[i] == row.case or (
            isinstance(config, Mapping) and config.get("case") == row.case
        )
        if not same:
            raise look.Failed(_MISALIGNED)
        outcome = row.outcome
        if row.result == "fail" and outcome not in events:
            outcome = words[0]
        frame.iat[i, at_outcome] = outcome
        frame.iat[i, at_error] = None
    return frame


def _verdicts_line(block: Mapping[str, Any]) -> str:
    return (
        f"  verdicts  {block['name']} · rows {count(block['rows'])} · joined by case "
        f"{count(block['by_case'])} · by input {count(block['by_input'])} · matched no case "
        f"{count(block['unmatched'])}"
    )


def _absolute(ns: argparse.Namespace) -> dict[str, str]:
    """Each absolute path the command carried, and the name it is written as in what is saved:
    its last folder's or file's name."""
    paths: list[str] = []
    for word in (ns.store, ns.typed_store, ns.config):
        if isinstance(word, str) and word:
            paths.append(word)
    held = ns.settings
    if held is not None and held.given:
        paths.append(str(held.path))
    paths.extend(w for w in ns.folder_words.values() if isinstance(w, str))
    out: dict[str, str] = {}
    for path in paths:
        if os.path.isabs(path):
            name = Path(path).name or Path(path).resolve().name
            out[path] = name
    return out


def _came(ns: argparse.Namespace, flag: str, in_config: bool = False) -> str:
    """Where a setting came from: the flag, trace.toml or the default."""
    if flag in ns.typed_flags:
        return "flag"
    return "trace.toml" if in_config else "default"


def _file_digest(path: str) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(ns: argparse.Namespace, verb: str, selecting: Any = None) -> dict[str, Any]:
    """The result-changing settings of a verb, in their order, then where each came from
    and the config's names of the stores read."""
    held = ns.settings
    events = sorted(ns.event)
    verdicts = None if ns.verdicts is None else _file_digest(ns.verdicts)
    settings: dict[str, Any] = {"events": events}
    came: dict[str, str] = {
        "events": _came(ns, "--event", held is not None and held.events is not None)
    }
    if verb in ("where", "compare"):
        settings["by"], came["by"] = ns.by, _came(ns, "--by")
        settings["at"], came["at"] = list(ns.at), _came(ns, "--at")
    if verb == "where":
        settings.update({"boot": ns.boot, "seed": ns.seed})
        came.update({"boot": _came(ns, "--boot"), "seed": _came(ns, "--seed")})
    if verb == "compare":
        settings["max_mde_hr"] = ns.max_mde_hr
        in_config = held is not None and held.max_mde_hr is not None
        came["max_mde_hr"] = _came(ns, "--max-mde-hr", in_config)
    if verb == "fix-check":
        settings["inputs"], came["inputs"] = ns.inputs, _came(ns, "--inputs")
        settings["failing_from"] = None if selecting is None else selecting.run_id
        came["failing_from"] = _came(ns, "--failing-from")
        settings["min_failures"] = (
            None if selecting is None else (1 if ns.min_failures is None else ns.min_failures)
        )
        came["min_failures"] = _came(ns, "--min-failures")
        settings["max_mde"] = ns.max_mde
        came["max_mde"] = _came(ns, "--max-mde", held is not None and held.max_mde is not None)
    if verb in _TWO_RUNS:
        settings["alpha"], came["alpha"] = ns.alpha, _came(ns, "--alpha")
    if verb == "fix-check":
        settings.update({"seed": ns.seed, "max_change": dict(ns.ceilings)})
        came.update({"seed": _came(ns, "--seed")})
        came["max_change"] = _came(ns, "--max-change", held is not None and bool(held.max_change))
    if verb in _TWO_RUNS:
        settings["verdicts"], came["verdicts"] = verdicts, _came(ns, "--verdicts")
    if verb in ("where", "compare") and (ns.timings or ns.timings_of):
        # asked for by --timings or by --timings-of, which implies it: either way it was asked
        # on the command, so the two ways of asking for the same conversations are one result
        settings["timings"], came["timings"] = True, "flag"
        named = _timings_named(ns)
        if named is not None:
            settings["timings_of"] = [[config_hash, replicate] for config_hash, replicate in named]
            came["timings_of"] = "flag"
    settings["from"] = came
    settings["stores"] = (
        [ns.typed_store] if held is not None and ns.typed_store in held.named else []
    )
    return settings


def _timings_named(ns: argparse.Namespace) -> list[tuple[str, int]] | None:
    """The conversations ``--timings-of`` names, each once and in ``(config_hash,
    replicate_index)`` order whatever order they were given in; None when the whole run is
    asked for or ``timings`` is not."""
    if not ns.timings_of:
        return None
    return sorted({(str(config_hash), int(replicate)) for config_hash, replicate in ns.timings_of})


def _refuse_unheld(
    named: Sequence[tuple[str, int]], holds: Collection[tuple[str, int]], of: str, following: str
) -> None:
    """Refuse a ``--timings-of`` name that is a conversation of no run read: a mistyped name
    is told at once, where a conversation the run holds and did not place is a result."""
    from poisson_trace import steps

    words = [steps.name_word(name) for name in steps.missing(named, holds)]
    if not words:
        return
    if len(words) == 1:
        raise _Refusal(
            f"--timings-of names {words[0]}, which is not a conversation {of}", following
        )
    raise _Refusal(
        f"--timings-of names {', '.join(words[:-1])} and {words[-1]}, "
        f"which are not conversations {of}",
        following,
    )


def _timings(
    ns: argparse.Namespace, rows: Sequence[Any], side: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """One run's ``timings`` and the line to print with it, if any: that the ceiling cut the
    whole-run list short, or that some of the conversations named are not listed. ``side`` says
    which run of two the line is about."""
    from poisson_trace import steps

    named = _timings_named(ns)
    made = steps.timings_of(rows, named, MOST_STEPS)
    document = made.document
    lines: list[str] = []
    if made.cut:
        lines.append(
            f"timings lists {count(document['listed'])} of {count(document['conversations'])} "
            f"conversations{side}: listing more would pass {count(MOST_STEPS)} steps and parent "
            "spans"
        )
    elif document["not_listed"]:
        lines.append(steps.not_listed_line(document, side))
    return document, lines


def _team(ns: argparse.Namespace) -> tuple[Mapping[str, str], tuple[Any, ...], Any]:
    """The config's own taxonomy, which a run Prove swept is classified by as it is read: its
    ``[taxonomy.labels]``, its ``[[taxonomy.rules]]`` and its ``[signals.budgets]``; none of
    them without a config."""
    held = getattr(ns, "settings", None)
    if held is None:
        return {}, (), None
    return held.labels, held.rules, held.budgets


def _imports_digest(manifest: Any) -> str | None:
    """The digest a run's import recorded; None for a run Prove swept."""
    environment = getattr(manifest, "environment", None)
    recorded = environment.get("import") if isinstance(environment, Mapping) else None
    digest = recorded.get("taxonomy_sha256") if isinstance(recorded, Mapping) else None
    return digest if isinstance(digest, str) else None


def _digest_of(
    manifest: Any,
    labels: Mapping[str, str] | None = None,
    rules: Sequence[Any] = (),
    budgets: Any = None,
) -> str:
    """The digest of the rules a run's failure types were decided by: the one its import
    recorded, or, for a run Prove swept, that of the taxonomy it was read under:
    the built-in rules' when the config has no rules, no budgets and no labels table."""
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    digest = _imports_digest(manifest)
    return digest if digest is not None else taxonomy_sha256(tuple(rules), budgets, labels)


#: The outcome words that say only that a try failed: never named as a label with no kind.
PLAIN_WORDS: frozenset[str] = frozenset({"fail", "failed", "failure", "missed"})


def _labels_without_kind(
    arms: Sequence[str],
    rows: Mapping[str, Sequence[Any]],
    manifests: Mapping[str, Any],
    labels: Mapping[str, str],
    rules: Sequence[Any],
) -> list[dict[str, Any]]:
    """The outcome labels Trace has no kind for, sorted, each with its count in each run: the
    failed tries of a run Prove swept that count as ``unclassified_error`` because their label
    is in neither the team's table nor the defaults and no rule of the team's matched them. A
    plain word for a failure is not a label, and an imported run counts none."""
    from poisson_trace.ingest.taxonomy import LABEL_KINDS

    counts: dict[str, Counter[str]] = {}
    for arm in arms:
        found: Counter[str] = Counter()
        if _imports_digest(manifests[arm]) is None:
            for r in rows[arm]:
                if (
                    r.result == "fail"
                    and r.failure_kind == "unclassified_error"
                    and r.outcome is not None
                    and r.outcome not in PLAIN_WORDS
                    and r.outcome not in labels
                    and r.outcome not in LABEL_KINDS
                    and not any(rule.matches(r) for rule in rules)
                ):
                    found[r.outcome] += 1
        counts[arm] = found
    named = sorted({label for found in counts.values() for label in found})
    return [{"label": label, **{arm: counts[arm][label] for arm in arms}} for label in named]


DIFFERENT_RULES = (
    "The failure types of the two runs were decided by different rules, so their counts are "
    "not set side by side; the digest of each run's rules is given."
)


def _taxonomy_diff(
    arms: Sequence[str],
    rows: Mapping[str, Sequence[Any]],
    manifests: Mapping[str, Any],
    verdict_tries: Mapping[str, int] | None = None,
    labels: Mapping[str, str] | None = None,
    rules: Sequence[Any] = (),
    budgets: Any = None,
) -> tuple[dict[str, Any], str | None]:
    """The saved verdict's failure-type diff: each run's taxonomy digest,
    whether the rules are the same, the tries, and each kind's and signal's count in each run
    in the kinds' precedence order; no counts, and a note, when the rules differ. Where a run
    has tries with no outcome, each run's number of them and the tries the verdict counts follow
    the tries; where none has, those two are left out. ``labels``, ``rules`` and
    ``budgets`` are the config's own taxonomy, which the runs Prove swept were read under;
    where the rules are the same and such a run has failed tries whose label has no kind, the
    labels and their counts come last (``labels_without_kind``)."""
    from poisson_trace.ingest.rows import FAILURE_KINDS, SIGNALS

    digests = {arm: _digest_of(manifests[arm], labels, rules, budgets) for arm in arms}
    same = len(set(digests.values())) == 1
    kinds = signals = None
    if same:
        kinds = [
            {
                "failure_kind": k,
                **{arm: portable.isum(1 for r in rows[arm] if r.failure_kind == k) for arm in arms},
            }
            for k in FAILURE_KINDS
            if any(r.failure_kind == k for arm in arms for r in rows[arm])
        ]
        signals = [
            {
                "signal": s,
                **{arm: portable.isum(1 for r in rows[arm] if s in r.signals) for arm in arms},
            }
            for s in SIGNALS
            if any(s in r.signals for arm in arms for r in rows[arm])
        ]
    tries = {arm: len(rows[arm]) for arm in arms}
    diff: dict[str, Any] = {"taxonomy_sha256": digests, "same_rules": same, "tries": tries}
    none = {arm: portable.isum(1 for r in rows[arm] if r.outcome is None) for arm in arms}
    if verdict_tries is not None and any(none.values()):
        diff["no_outcome"] = none
        diff["verdict_tries"] = {arm: verdict_tries[arm] for arm in arms}
    diff["kinds"] = kinds
    diff["signals"] = signals
    if same:
        without = _labels_without_kind(arms, rows, manifests, labels or {}, rules)
        if without:
            diff["labels_without_kind"] = without
    return diff, None if same else DIFFERENT_RULES


def _measures(
    ns: argparse.Namespace,
    rows: Mapping[str, Sequence[Any]],
    arms: Sequence[tuple[str, Any]],
    labels: tuple[str, str],
) -> Any:
    """The comparison of the two runs' time, length, tokens and cost over every case both
    hold, at the verb's level, the ceilings the config and the flags set."""
    from poisson_trace.ingest.tries import version_of
    from poisson_trace.stats.continuous import compare

    (arm_a, run_a), (arm_b, run_b) = arms
    return compare(
        version_of(rows[arm_a], run_a.run_id, labels[0]),
        version_of(rows[arm_b], run_b.run_id, labels[1]),
        ceilings=ns.ceilings or None,
        alpha=ns.alpha,
    )


MEASURES_HEADING = "## Time, length, tokens and cost"
NOTHING_MEASURED = "No try in either run recorded a time, a length, tokens or a cost."


def _measures_section(comparison: Any) -> list[str]:
    """The report's section: the heading, the table, and each measure shown with its lines."""
    from poisson_trace.stats.continuous import table

    header, rows = table(comparison)
    if not rows:
        return [MEASURES_HEADING, "", NOTHING_MEASURED]
    body = look.table(header, rows).rstrip("\n").split("\n")
    bullets = [f"- {row[0]}: " + " ".join(comparison.measures[row[0]].lines) for row in rows]
    return [MEASURES_HEADING, "", *body, "", *bullets]


FAILURES_HEADING = "## Failures by kind"
SIGNALS_LINE = "Signals seen on tries, failed or not:"
BUILT_IN_RULES = "by the built-in rules"
OWN_RULES = "by your own rules and the built-in ones"


def _share(n: int, tries: int) -> str:
    """A count over a run's tries, as the report prints a failure share: one decimal."""
    from poisson_trace.report import _percent

    return _percent(n / tries) if tries else "-"


def _points_between(n_a: int, tries_a: int, n_b: int, tries_b: int) -> str:
    """The second run's share less the first's, in points as the per-input table prints a
    change: one decimal, signed, no sign on no change."""
    from poisson_trace.report import _points

    if not tries_a or not tries_b:
        return "-"
    return _points(n_b / tries_b - n_a / tries_a, signed=True, places=1) + " points"


def _no_outcome_line(c: Counted, diff: Mapping[str, Any]) -> str:
    """The sentence under the tries line where a run has tries with no outcome: how many
    each run has, that the counts above include them, and how many tries the verdict counts,
    which only the inputs both runs carry with an outcome give it."""
    assert c.arms is not None
    a, b = c.arms
    if c.kind == "fix-check":
        name_a, name_b = "the old version", "the new version"
    else:
        name_a, name_b = c.labels
    none, tries, used = diff["no_outcome"], diff["tries"], diff["verdict_tries"]
    picked = " and --failing-from picked" if c.data.get("_failing_from") else ""
    counted = (
        f"{count(used[a])} tries of each"
        if used[a] == used[b]
        else f"{count(used[a])} tries of {name_a} and {count(used[b])} of {name_b}"
    )
    return (
        f"Tries with no outcome: {count(none[a])} of {name_a}'s {count(tries[a])} and "
        f"{count(none[b])} of {name_b}'s {count(tries[b])}; the counts above include them. "
        f"The verdict counts only inputs both runs carry with an outcome{picked}, "
        f"so it counts {counted}."
    )


def _labels_note(labels: Sequence[str]) -> str:
    """The one paragraph ``Failures by kind`` gives the labels Trace has no kind for, as the
    diff lists them (sorted): what their tries count as, and how a team names a label's kind,
    the first label written as ``trace.toml`` writes a key."""
    from poisson_trace.config import label_key
    from poisson_trace.ingest.rows import FAILURE_KINDS

    kinds = [k for k in FAILURE_KINDS if k != "unclassified_error"]
    if len(labels) == 1:
        first = f"Trace has no kind for the label {labels[0]}, so its failed tries"
    else:
        named = ", ".join(labels[:-1]) + " and " + labels[-1]
        first = f"Trace has no kind for the labels {named}, so their failed tries"
    return (
        f"{first} count as unclassified_error. To name a label's kind, add it to trace.toml "
        f'under [taxonomy.labels], as {label_key(labels[0])} = "KIND", where KIND is '
        f"{', '.join(kinds[:-1])} or {kinds[-1]}."
    )


def _breakdown_section(c: Counted) -> list[str]:
    """The report's ``Failures by kind`` section, the counts of the failure-type diff
    the saved verdict holds: one sentence on what is counted; a table of each kind either run
    has, by its count over both runs (a tie in the diff's order, the kinds' precedence),
    ``all failures`` last; the tries; once, the labels of a run Prove swept that Trace has no
    kind for, when the diff names any; and, when either run has a signal, the signals' table.
    Runs classified by different rules get the note and each run's digest, no counts.
    ``compare`` and ``changes`` name their runs as their reports do, A and B."""
    from poisson_trace.ingest.taxonomy import taxonomy_sha256

    assert c.arms is not None and c.diff is not None
    diff = c.diff[0]
    a, b = c.arms
    label_a, label_b = c.labels
    digests = diff["taxonomy_sha256"]
    if not diff["same_rules"]:
        return [
            FAILURES_HEADING,
            "",
            DIFFERENT_RULES,
            "",
            f"- {label_a}: {digests[a]}",
            f"- {label_b}: {digests[b]}",
        ]
    built_in = taxonomy_sha256((), None)
    whose = BUILT_IN_RULES if all(d == built_in for d in digests.values()) else OWN_RULES
    about = "inputs one by one" if c.kind == "changes" else "all failures together"
    tries_a, tries_b = diff["tries"][a], diff["tries"][b]

    def row(name: str, n_a: int, n_b: int) -> list[str]:
        return [
            name,
            count(n_a),
            _share(n_a, tries_a),
            count(n_b),
            _share(n_b, tries_b),
            _points_between(n_a, tries_a, n_b, tries_b),
        ]

    # by the count over both runs, the sort stable so a tie keeps the diff's precedence order
    kinds = sorted(diff["kinds"], key=lambda k: -(k[a] + k[b]))
    rows = [row(k["failure_kind"], k[a], k[b]) for k in kinds]
    all_a, all_b = portable.isum(k[a] for k in kinds), portable.isum(k[b] for k in kinds)
    rows.append(row("all failures", all_a, all_b))
    header = ["kind", label_a, f"{label_a} share", label_b, f"{label_b} share", "change"]
    if c.kind == "fix-check":
        of = f"of {count(tries_a)} tries of the old version and {count(tries_b)} of the new"
    else:
        of = f"of {count(tries_a)} tries of {label_a} and {count(tries_b)} of {label_b}"
    lines = [
        FAILURES_HEADING,
        "",
        f"Each failed try's kind of failure, {whose}; the same rules classified both runs. "
        f"Counts, not a test: the verdict above is about {about}.",
        "",
        *look.table(header, rows).rstrip("\n").split("\n"),
        "",
        f"{of}; a try has one kind",
    ]
    if "no_outcome" in diff:
        lines += ["", _no_outcome_line(c, diff)]
    if diff.get("labels_without_kind"):
        lines += ["", _labels_note([x["label"] for x in diff["labels_without_kind"]])]
    if diff["signals"]:
        signal_rows = [
            [s["signal"], count(s[a]), _share(s[a], tries_a), count(s[b]), _share(s[b], tries_b)]
            for s in diff["signals"]
        ]
        lines += ["", SIGNALS_LINE, ""]
        lines += look.table(["signal", *header[1:5]], signal_rows).rstrip("\n").split("\n")
    return lines


def _with_breakdown(c: Counted) -> Counted:
    """A verb of two runs with its failure-type diff read and its section's lines made for the
    report (the section prints on every run). The lines are made here, so that the report
    reads no count it did not get from the verb."""
    c.diff_part()
    c.data["_breakdown_section"] = _breakdown_section(c)
    return c


def _none(x: Any) -> float | None:
    return None if x is None else float(x)


def _where_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    placement = data["run"]["placement"]
    band = 0.95
    rows = [Row("tries", placement["placed"], "a"), Row("failed", placement["died"], "a")]
    for point in data["curve"]:
        step = int(point["step"])
        rows.append(Row("survival", point["survival"], "a", step=step))
        for bound in ("lo", "hi"):
            value = _none(point[bound])
            rows.append(Row(f"survival_{bound}", value, "a", level=band, step=step, note="no band"))
    rows.append(Row("median_step", _none(data["median_step"]), "a", note="none failed"))
    for cause in data["causes"]:
        k = cause["cause"]
        rows.append(Row("share", cause["f"], "a", cause=k))
        rows.append(Row("share_lo", _none(cause["lo"]), "a", level=band, cause=k, note="no band"))
        rows.append(Row("share_hi", _none(cause["hi"]), "a", level=band, cause=k, note="no band"))
    return rows


def _compare_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    c = data["comparison"]
    band = 0.95
    rows = []
    for arm in ("a", "b"):
        placement = data["runs"][arm]["placement"]
        rows += [Row("tries", placement["placed"], arm), Row("failed", placement["died"], arm)]
    rows += [
        Row("p", c["p"]),
        Row("hr", _none(c["hazard_ratio"]), note="no information"),
        Row("hr_lo", _none(c["hazard_ratio_lo"]), level=band, note="no information"),
        Row("hr_hi", _none(c["hazard_ratio_hi"]), level=band, note="no information"),
        Row("mde_hr", _none(c["mde_hazard_ratio"]), note="no information"),
        Row("max_mde_hr", c["max_mde_hr"]),
    ]
    for per in data["per_cause"]:
        k = per["cause"]
        rows += [
            Row("failed", per["deaths_a"], "a", cause=k),
            Row("failed", per["deaths_b"], "b", cause=k),
            Row("p", per["p"], cause=k),
            Row("q", _none(per["q"]), cause=k, note="no correction"),
            Row("mde_hr", _none(per["mde_hazard_ratio"]), cause=k, note="no information"),
        ]
    for at in data["at"]:
        step = int(at["step"])
        rows += [
            Row("survival", at["survival_a"], "a", step=step),
            Row("survival", at["survival_b"], "b", step=step),
            Row("diff", at["diff"], step=step),
            Row("diff_lo", at["lo"], level=band, step=step),
            Row("diff_hi", at["hi"], level=band, step=step),
        ]
    return rows


def _input_rows(input_: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    condition, h = input_["config"], input_["config_hash"]
    rows = []
    for arm, key in (("a", "a"), ("b", "b")):
        runs, failed = input_[f"runs_{key}"], input_[f"failed_{key}"]
        rows += [
            Row("tries", runs, arm, condition, h),
            Row("failed", failed, arm, condition, h),
            Row("share", failed / runs if runs else None, arm, condition, h, note="no try"),
        ]
    rows.append(Row("p", input_["p"], "both", condition, h))
    rows.append(Row("q", _none(input_["q"]), "both", condition, h, note="no correction"))
    return rows


def _fix_check_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    level = 1.0 - data["test"]["alpha"]
    rows = []
    for arm, key in (("a", "old"), ("b", "new")):
        held = data["rows"][key]
        runs, failed = held["runs"], held["failed"]
        rows += [
            Row("tries", runs, arm),
            Row("failed", failed, arm),
            Row("share", failed / runs if runs else None, arm, note="no try"),
        ]
    d, limits = data["difference"], data["limits"]
    rows += [
        Row("difference", d["points"]),
        Row("range_lo", _none(d["lo"]), level=level, note="no interval"),
        Row("range_hi", _none(d["hi"]), level=level, note="no interval"),
        Row("p", data["test"]["p"]),
        Row("drop_limit", _none(limits["drop"]), level=level, note="none detectable"),
        Row("rise_limit", _none(limits["rise"]), level=level, note="none detectable"),
        Row("max_mde", limits["max_mde"]),
    ]
    for input_ in data["changes"]["rows"]:
        rows += _input_rows(input_)
    return rows


def _changes_rows(data: Mapping[str, Any]) -> list[Any]:
    from poisson_trace.saved import Row

    rows = []
    for arm, key in (("a", "a"), ("b", "b")):
        runs = portable.isum(r[f"runs_{key}"] for r in data["rows"])
        failed = portable.isum(r[f"failed_{key}"] for r in data["rows"])
        rows += [
            Row("tries", runs, arm),
            Row("failed", failed, arm),
            Row("share", failed / runs if runs else None, arm, note="no try"),
        ]
    for input_ in data["rows"]:
        rows += _input_rows(input_)
    return rows


_TABLE_ROWS: dict[str, Callable[[Mapping[str, Any]], list[Any]]] = {
    "where": _where_rows,
    "compare": _compare_rows,
    "fix-check": _fix_check_rows,
    "changes": _changes_rows,
}


def _with_tail(doc: Mapping[str, Any], tail: Mapping[str, Any]) -> dict[str, Any]:
    """The verb's JSON with ``tail``'s keys before ``next``."""
    out = {k: v for k, v in doc.items() if k != "next"}
    out.update(tail)
    out["next"] = doc["next"]
    return out


def _result_document(
    printed: Mapping[str, Any],
    data: Mapping[str, Any],
    added: Mapping[str, Any],
    notes: Sequence[str],
    saved_at: str | None,
) -> dict[str, Any]:
    """``result.json``: the printed JSON with the keys a save adds: the
    summary's lines, the caveats, ``note`` as a list, the versions, and the two-run blocks;
    ``saved`` and ``next`` last."""
    from poisson_trace import saved

    body = {k: v for k, v in printed.items() if k not in ("saved", "next")}
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key == "note":
            held = [value] if isinstance(value, str) else list(value)
            out[key] = [*held, *[n for n in notes if n not in held]]
        else:
            out[key] = value
    more = {
        "summary": [[label, text] for label, text in data.get("_summary") or ()],
        "before_you_act": list(data.get("_before_you_act") or ()),
        "note": list(notes),
        "versions": {"trace": saved.trace_version(), "prove": saved.prove_version()},
        **added,
    }
    for key, value in more.items():
        if key not in out:
            out[key] = value
    out["saved"] = saved_at
    out["next"] = printed["next"]
    return out


# ---------- the outcome of a counting verb, and its delivery ----------


@dataclass
class Counted:
    """What a counting verb worked out: the verdict line, the data its JSON and report are
    built from, the report, the runs read, the artifact's settings, and the call's own
    settings (``ns``). The failure-type diff is worked out by every verb of two
    runs, since its section prints on every run; the continuous measures when asked
    for (``--measures``) or first read (a save, the API), from the store the call read
    (``ns.store_root``)."""

    kind: str
    verdict: str
    sentence: str
    following: str
    data: dict[str, Any]
    report: Any
    runs: list[tuple[str, Any, Any]]
    settings: dict[str, Any]
    ns: argparse.Namespace
    arms: tuple[str, str] | None = None
    labels: tuple[str, str] = ("A", "B")
    svg_refusal: str | None = None  # where: why there is no curve to write
    signals: tuple[dict[str, tuple[Any, ...]], dict[str, tuple[Any, ...]]] | None = None
    diff: tuple[dict[str, Any], str | None] | None = None
    measures: Any = None
    # what to say of ``timings`` beside the JSON: a list the ceiling cut, or names not listed
    timings_lines: tuple[str, ...] = ()

    def diff_part(self) -> None:
        """The failure-type diff of a verb of two runs, read now if not yet: each run's rows as
        the reader classifies them, after the ``--verdicts`` join."""
        if self.arms is None or self.diff is not None:
            return
        if self.signals is None:
            self.signals = _signals(self.ns, _arm_runs(self), frozenset(self.ns.event))
        manifests = {arm: manifest for arm, _run, manifest in self.runs}
        self.diff = _taxonomy_diff(
            self.arms, self.signals[1], manifests, _verdict_tries(self), *_team(self.ns)
        )

    def two_run_parts(self) -> None:
        """The diff and the measures of a verb of two runs, read now if not yet."""
        if self.arms is None:
            return
        self.diff_part()
        if self.measures is None and self.signals is not None:
            self.measures = _measures(self.ns, self.signals[1], _arm_runs(self), self.labels)

    def printed(self) -> dict[str, Any]:
        """The verb's JSON as the command prints it without a delivery: the failure-type diff
        of a verb of two runs, the measures when asked for, the join block, ``next``
        last."""
        ns = self.ns
        tail: dict[str, Any] = {}
        if self.arms is not None:
            self.diff_part()
            assert self.diff is not None
            tail["failure_taxonomy_diff"] = self.diff[0]
        if self.measures is not None and ns.measures:
            tail["continuous_measures"] = self.measures.to_dict()
        if ns.joined is not None:
            tail["verdicts"] = ns.joined
        enveloped = _enveloped(self.data, self.verdict, self.sentence, self.following)
        return _with_tail({k: v for k, v in enveloped.items() if not k.startswith("_")}, tail)

    def result_document(self) -> dict[str, Any]:
        """``result.json`` as a save would write it, paths as the call gave them."""
        self.two_run_parts()
        added, notes = _added(self)
        return _result_document(self.printed(), self.data, added, notes, None)

    def markdown(self) -> str:
        return str(self.report.to_markdown())

    def charts(self) -> list[tuple[str, str, dict[str, Any]]]:
        """The charts a saved verdict carries beside its table, each ``(name, svg, data)``:
        ``where``'s curve as ``--svg`` writes it; ``compare``'s two charts, the
        two runs' where curves under compare's failures and the hazard ratio with its range."""
        if self.kind == "compare":
            return _compare_charts(self)
        if self.kind != "where" or self.svg_refusal is not None:
            return []
        chart = {"curve": self.data["curve"], "at": self.data["at"], "causes": self.data["causes"]}
        return [("curve", str(self.report.to_svg()), chart)]

    def svg(self) -> str:
        """The curve as SVG text; refused where the run has no traces."""
        if self.svg_refusal is not None:
            raise _Refusal(self.svg_refusal)
        return str(self.report.to_svg())


def _verdict_tries(c: Counted) -> dict[str, int]:
    """The tries each run gave the verdict: those with an outcome on the inputs both runs carry
    with one (and, on ``fix-check``, that the inputs asked for picked), as the verb counted them."""
    assert c.arms is not None
    a, b = c.arms
    if c.kind == "compare":
        return {arm: int(c.data["_common"][arm]["tries"]) for arm in c.arms}
    if c.kind == "fix-check":
        rows = c.data["rows"]
        return {a: int(rows["old"]["runs"]), b: int(rows["new"]["runs"])}
    return {arm: int(c.data["_verdict_tries"][arm]) for arm in (a, b)}


def _arm_runs(c: Counted) -> list[tuple[str, Any]]:
    return [(arm, run) for arm, run, _manifest in c.runs]


def _added(c: Counted) -> tuple[dict[str, Any], list[str]]:
    """What a save adds to the printed JSON: the failure-type diff, its note when the rules
    differ, and the continuous measures."""
    added: dict[str, Any] = {}
    notes: list[str] = []
    if c.diff is not None:
        added["failure_taxonomy_diff"] = c.diff[0]
        if c.diff[1] is not None:
            notes.append(c.diff[1])
    if c.measures is not None:
        added["continuous_measures"] = c.measures.to_dict()
    notes.extend(c.timings_lines)
    return added, notes


@dataclass(frozen=True)
class Delivered:
    """What a delivery left: the SVG and the bundle written, where the verdict was saved in
    the store and its artifact id, and the notes it added (a store that could not be written
    to)."""

    svg: str | None = None
    out: str | None = None
    saved_at: str | None = None
    identity: str | None = None
    notes: tuple[str, ...] = ()


def document(c: Counted, d: Delivered) -> dict[str, Any]:
    """The JSON the command prints with this delivery: ``saved`` before ``next`` once saved."""
    doc = c.printed()
    if d.saved_at is not None:
        doc["saved"] = d.saved_at
        doc = _with_tail(doc, {})
    return doc


def details(c: Counted, d: Delivered) -> list[str]:
    """The detail lines under the verdict line, in the command's order: the join, the SVG
    written, the bundle written, the verdict saved."""
    out = []
    if c.ns.joined is not None:
        out.append(_verdicts_line(c.ns.joined))
    out.extend(f"  {line}" for line in c.timings_lines)
    if d.svg is not None:
        out.append(f"  wrote  {d.svg}")
    if d.out is not None:
        out.append(f"  wrote  {d.out}")
    if d.saved_at is not None and d.identity is not None:
        out.append(f"  saved  {c.kind} {d.identity[:12]}")
    return out


def text(c: Counted, d: Delivered) -> str:
    return _said(c.verdict, c.sentence, c.markdown(), c.following, *details(c, d))


def write_svg(c: Counted, d: Delivered, path: str, force: bool) -> Delivered:
    """``--svg``: the curve written to ``path``, refused before anything is written where the
    path cannot be written, the file is there without ``force``, or the run has no traces."""
    if path == "":
        raise _Refusal("--svg takes the name of the file to write")
    _check_svg(path, force)
    if c.svg_refusal is not None:
        raise _Refusal(c.svg_refusal)
    _write_svg(path, c.svg())
    return Delivered(path, d.out, d.saved_at, d.identity, d.notes)


def save(c: Counted, d: Delivered, out: str | None, force: bool) -> Delivered:
    """``--save``, and ``--out`` with it: the verdict built as an artifact in a staging
    folder, saved into the runs' store (a store that cannot be written to is a note, and the
    result goes on), and handed over as a bundle into ``out`` where asked. A verdict
    saved already is not saved again; its bundle is a copy of the artifact
    as the store holds it. A store whose descriptor is not one, or is in a newer format, is
    refused with nothing written: what is wrong there is the store's, not this save's."""
    import shutil
    import tempfile

    from poisson_trace import saved

    ns = c.ns
    if out is not None:
        if out == "":
            raise _Refusal("--out takes the name of the folder to write")
        _check_out(out, force)
    artifact, absolute = _artifact_of(c)
    identity = artifact.id
    saved_at, held_notes = d.saved_at, list(d.notes)
    staging = Path(tempfile.mkdtemp(prefix="poisson-trace-"))
    try:
        saved.build_artifact(staging, artifact)
        if saved_at is None:
            if ns.temp_store:
                held_notes.append(
                    "the verdict was not saved: the runs were read from folders, not a store"
                )
            else:
                # the store as it was given, while the process is still where it read it from,
                # so that a refusal names the file by the path the user knows
                moved = os.path.abspath(ns.store) != ns.store_root
                root = Path(ns.store_root if moved else ns.store)
                try:
                    saved.save_artifact(root, staging, c.kind, identity)
                except saved.Unwritable as e:
                    raise _Refusal(f"{e}; nothing was written") from None
                except OSError as e:
                    held_notes.append(f"the verdict was not saved: {look.why(e)}")
                else:
                    saved_at = saved.saved_path(c.kind, identity)
                    # every command that saves rebuilds the store's pages; pages that
                    # cannot be written are one note, and the save stands
                    try:
                        rebuild_pages(ns)
                    except OSError as e:
                        held_notes.append(f"the pages were not rebuilt: {look.why(e)}")
                    except look.Refused as e:
                        held_notes.append(f"the pages were not rebuilt: {e}")
        if out is not None:
            held = None if ns.from_folders else saved.short(ns.store, absolute)
            refs = [saved.RunRef(run.run_id, run.name, held) for _, run, _ in c.runs]
            # the bundle is a copy of the artifact as the store holds it, so a second --out on
            # the same runs hands over the same bytes; the staging folder
            # stands in when the store could not be written to
            source = staging if saved_at is None else Path(ns.store_root) / saved_at
            try:
                saved.write_bundle(source, Path(out), c.kind, refs, force=force)
            except OSError as e:
                raise look.Failed(
                    f"could not write {out} ({look.why(e)}); the report was not printed"
                ) from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return Delivered(
        d.svg, out if out is not None else d.out, saved_at, identity, tuple(held_notes)
    )


# ---------- the bundle read back and checked (handover --check) ----------


@dataclass(frozen=True)
class BundleChecked:
    verdict: str
    sentence: str
    exit_code: int
    following: str | None = None


def validate_bundle(folder: str) -> BundleChecked:
    """``poisson-trace handover --check DIR``: ok and exit 0 on a bundle that holds what it
    promises, ``not valid`` with the first failing line and exit 4 otherwise, a refusal when
    DIR is not a bundle. A bundle that holds what it promises
    gets its next command: the HTML report, written, or opened once it is there."""
    from poisson_trace import saved

    prove_present()
    try:
        checked = saved.check_bundle(Path(folder))
    except saved.NotABundle as e:
        raise _Refusal(str(e)) from None
    except saved.Invalid as e:
        return BundleChecked("not valid", str(e), look.CHECK_FAILED)
    opened = ["--open"] if (Path(folder) / REPORT_PAGE).is_file() else []
    following = look.command("poisson-trace", "report", folder, *opened)
    return BundleChecked("ok", checked.sentence, look.DONE, following)


@dataclass(frozen=True)
class BundleRead:
    verb: str
    result: dict[str, Any]
    handover: dict[str, Any]
    artifact: dict[str, Any]
    report: str


def load_bundle(folder: str) -> BundleRead:
    """A bundle read back: checked first, as ``handover --check`` checks it, and refused with
    the first failing line when it does not hold what it promises; then its four files."""
    import json

    from poisson_trace import saved

    prove_present()
    try:
        checked = saved.check_bundle(Path(folder))
    except saved.NotABundle as e:
        raise _Refusal(str(e)) from None
    except saved.Invalid as e:
        raise _Refusal(f"{folder} does not hold what it promises: {e}") from None
    root = Path(folder)
    try:
        return BundleRead(
            verb=checked.verb,
            result=json.loads((root / "result.json").read_text(encoding="utf-8")),
            handover=json.loads((root / "handover.json").read_text(encoding="utf-8")),
            artifact=json.loads((root / "artifact.json").read_text(encoding="utf-8")),
            report=(root / "report.md").read_text(encoding="utf-8"),
        )
    except (OSError, ValueError) as e:
        raise _Refusal(f"cannot read the bundle at {folder} ({look.why(e)})") from e


def _plural(n: int, one: str, many: str) -> str:
    return f"{count(n)} {one if n == 1 else many}"


# the key under the listing for a start that is a file's modification time
FILE_MARK = "(file): the start is when the file was written or copied, not when the run ran"


def _utc_minute(run: Any) -> str:
    return str(run.started.strftime("%Y-%m-%d %H:%M"))


@dataclass(frozen=True)
class Listed:
    """What ``runs`` or a form of ``name`` printed: the JSON document (``runs`` alone) and the
    text."""

    data: dict[str, Any] | None
    text: str
    sentence: str = ""
    following: str = ""


def runs(ns: argparse.Namespace) -> Listed:
    store, index = _named(ns)
    events = list(dict.fromkeys(ns.event or ()))
    complete = index.complete
    if ns.all:
        listed = list(index.runs)
    else:
        listed = [r for r in index.runs if r.complete and r.number <= _LISTED]
    if not events:
        where = "" if ns.settings is None else f" and {ns.settings.shown} names no failures"
        ns.notes.append(f"no --event was given{where}, so the failed column is not counted")
    if ns.all and len(complete) > _LISTED:
        ns.notes.append(
            f"--all reads the rows of every one of the {count(len(index.runs))} runs, "
            "which may take a while on a store this size"
        )
    if index.unreadable:
        unread = _plural(len(index.unreadable), "run", "runs")
        ns.notes.append(
            f"Prove could not read the record or the start time of {unread} of this store, "
            "not listed: "
            f"{', '.join(index.unreadable)}"
        )
    rows = []
    carried: set[str] = set()
    read: list[Any] = []
    for run in listed:
        try:
            tally = store.tally(run.run_id)
            frame = store.read(run.run_id, meta=False, trace="envelope")
        except Exception as e:
            # one run whose rows cannot be read leaves the listing of the others whole
            ns.notes.append(
                f"Prove could not read the rows of {run.shown()} ({look.why(e)}), not listed"
            )
            continue
        read.append(run)
        outcomes = [o for o in frame["outcome"] if not _no_value(o)]
        carried.update(outcomes)
        rows.append(
            {
                "number": run.number,
                "name": run.name,
                "run_id": run.run_id,
                "named_by": run.named_by,
                "rows": int(tally.rows),
                "failed": portable.isum(1 for o in outcomes if o in events) if events else None,
                "traced": bool(frame["trace"].notna().any()) if len(frame) else False,
                "created_at": run.created_at,
                "status": run.status,
                "target_id": run.target_id,
                "backend": run.backend,
            }
        )
    missing = [e for e in events if e not in carried]
    if listed and len(missing) == len(events) and events:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs listed carry the outcomes: "
            f"{', '.join(sorted(carried)) or 'none'}"
        )
    yours = portable.isum(1 for r in index.runs if r.named_by == "you")
    total = len(index.runs)
    theirs = total - yours
    sentence = (
        f"{_plural(total, 'run', 'runs')} in {ns.store} (newest first); {count(yours)} named "
        f"by you, {count(theirs)} named from {'its manifest' if theirs == 1 else 'their manifests'}"
    )
    traced = next(
        (index.by_id(r["run_id"]) for r in rows if r["traced"] and r["status"] == "complete"),
        None,
    )
    if traced is None:
        following = look.command("poisson-trace", "fix-check", "--help")
    else:
        following = _next(index, "where", (traced,), ns)
    doc = {
        "schema": "poisson-trace.runs/1",
        "verdict": "ok",
        "sentence": sentence,
        "store": ns.store,
        "runs": rows,
        "next": following,
    }
    hidden = 0 if ns.all else total - len(complete)
    older = 0 if ns.all else max(0, len(complete) - _LISTED)
    from poisson_trace.names import FILE_TIME

    filed = [run.started_from == FILE_TIME for run in read]
    lines = _runs_table(
        rows,
        [_utc_minute(run) + (" (file)" if f else "") for run, f in zip(read, filed, strict=True)],
    )
    if any(filed):
        lines.append(FILE_MARK)
    if older:
        lines.append(
            f"  {_plural(older, 'older complete run is', 'older complete runs are')} not listed; "
            "--all lists them"
        )
    if hidden:
        lines.append(
            f"  {_plural(hidden, 'partial run is', 'partial runs are')} not listed; "
            "--all lists them"
        )
    report = "\n".join(lines) + "\n\n" if lines else ""
    return Listed(doc, f"ok  {sentence}\n\n{report}next: {following}\n", sentence, following)


def _runs_table(rows: Sequence[Mapping[str, Any]], started: Sequence[str]) -> list[str]:
    """The listing's columns, numbers to the right; the start as UTC to the minute."""
    if not rows:
        return []
    cells = [
        (
            "–" if r["number"] is None else str(r["number"]),
            r["name"],
            count(r["rows"]),
            "–" if r["failed"] is None else count(r["failed"]),
            "yes" if r["traced"] else "no",
            at,
            r["status"],
        )
        for r, at in zip(rows, started, strict=True)
    ]
    head = ("#", "name", "rows", "failed", "traces", "started", "status")
    widths = [max(len(c[i]) for c in [head, *cells]) for i in range(len(head))]
    right = (True, False, True, True, False, False, False)

    def line(cell: Sequence[str]) -> str:
        parts = [
            c.rjust(w) if r else c.ljust(w) for c, w, r in zip(cell, widths, right, strict=True)
        ]
        return ("  " + "  ".join(parts)).rstrip()

    return [line(head), *(line(c) for c in cells)]


# ---------- name ----------


def name(ns: argparse.Namespace) -> Listed:
    from poisson_trace import names

    store, index = _named(ns, lenient=True)
    shown = index.names_shown()
    listing = index.listing()
    if ns.list:
        return _name_list(index, shown, listing)
    given = ns.run.strip()
    entries = dict(index.entries)
    damage = index.damage()
    if ns.forget:
        if damage is not None and given in entries:
            # an entry the file should not hold: this one name is taken back, and no other
            held = entries.pop(given)
            names.write_names_file(index.root, shown, entries)
            where = "" if index.by_id(held) is not None else ", which this store does not hold"
            return _named_line(
                f'forgot the name "{given}" of the run {held}{where}, in {shown}', listing
            )
        if damage is not None:
            raise damage
        run = index.resolve(ns.run)
        mine = [n for n, r in entries.items() if r == run.run_id]
        if not mine:
            if run.imported:
                whose = "the one it was imported under"
            elif run.swept is not None:
                whose = "the one it was given when it was swept"
            else:
                whose = "from its manifest"
            raise _Refusal(f"{run.shown()} has no name of yours to forget; its name is {whose}")
        for old in mine:
            del entries[old]
        names.write_names_file(index.root, shown, entries)
        again = run.without_yours
        return _named_line(
            f'forgot the name "{mine[0]}" of {run.run_id}, which is named "{again}" again, '
            f"in {shown}",
            listing,
        )
    if damage is not None:
        raise damage
    run = index.resolve(ns.run)
    if run.status == "unreadable":
        raise _Refusal(
            f"Prove could not read the record or the start time of the run {run.run_id}, so it "
            "cannot be named; it is reached by its id"
        )
    new = ns.new.strip()
    why = names.unfit(new)
    if why is not None:
        raise _Refusal(f'"{new or ns.new}" cannot be a name: {why}')
    if any(r.run_id == new for r in index.runs) or new in index.unreadable:
        raise _Refusal(f'"{new}" cannot be a name: it is the id of a run of this store')
    others = index.holder(new) - {run.run_id}
    if others:
        other = index.by_id(sorted(others)[0])
        whose = other.shown() if other is not None else "another run"
        raise _Refusal(f'"{new}" cannot be a name: {whose} answers to it already')
    if entries.get(new) == run.run_id:
        return _named_line(f'{run.run_id} is named "{new}" already, in {shown}', listing)
    entries = {n: r for n, r in entries.items() if r != run.run_id}
    entries[new] = run.run_id
    names.write_names_file(index.root, shown, entries)
    return _named_line(f'named {run.run_id} "{new}" in {shown}', listing)


def _named_line(sentence: str, listing: str) -> Listed:
    return Listed(None, f"ok  {sentence}\n\nnext: {listing}\n", sentence, listing)


def _name_list(index: Any, shown: str, listing: str) -> Listed:
    entries = index.entries
    if not entries:
        return _named_line(f"no names of yours in {index.store}", listing)
    cells = []
    for name in sorted(entries):
        run = index.by_id(entries[name])
        if run is None and entries[name] in index.unreadable:
            own = "its record cannot be read"
        elif run is None:
            own = "not in this store"
        else:
            own = run.without_yours
        cells.append((name, own, entries[name]))
    head = ("name", "name from its manifest", "run")
    widths = [max(len(c[i]) for c in [head, *cells]) for i in range(3)]
    lines = [
        ("  " + "  ".join(c.ljust(w) for c, w in zip(cell, widths, strict=True))).rstrip()
        for cell in [head, *cells]
    ]
    sentence = f"{_plural(len(entries), 'name', 'names')} of yours in {shown}"
    return Listed(
        None, f"ok  {sentence}\n\n" + "\n".join(lines) + f"\n\nnext: {listing}\n", sentence, listing
    )


# ---------- where ----------


def where(ns: argparse.Namespace) -> Counted:
    import poisson_prove
    from poisson_prove.steps import declaration_check

    from poisson_trace import steps, summary
    from poisson_trace.clock import _reached_by, conversations
    from poisson_trace.clock import placement as placement_of
    from poisson_trace.report import CANNOT_SAY, WhereReport
    from poisson_trace.survival import competing, competing_band

    store, index = _named(ns)
    run = index.resolve(ns.run)
    manifest, frame, tally = _load(store, run)
    events = frozenset(ns.event)
    present = _outcomes(frame)
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the run carries the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    rows = conversations(manifest, frame, events=events, by=ns.by)
    named = _timings_named(ns)
    if named is not None:
        _refuse_unheld(
            named,
            steps.held(rows),
            f"of the run {look.word(index.word_for(run))}",
            _next(index, "where", (run,), ns, "--timings", "--json"),
        )
    placement = placement_of(rows, manifest, tally)
    index_steps = _arrays(placement)[0]
    causes = _ordered({p.cause for p in placement.rows if p.died})
    tries = _tries(placement)
    aj = competing(tries, causes)
    band = competing_band(tries, causes, ns.at, b=ns.boot, seed=ns.seed) if tries else None
    curve = []
    for i, step in enumerate(aj.steps):
        curve.append(
            {
                "step": int(step),
                "at_risk": int(aj.at_risk[i]),
                "died": int(aj.failed[i]),
                "survival": float(aj.share[i]),
                # the band resamples inputs; no variance formula stands behind it
                "var": None,
                "lo": None if band is None else float(band.curve[0][i]),
                "hi": None if band is None else float(band.curve[1][i]),
            }
        )
    at_rows = []
    for j, (q, s) in enumerate(zip(ns.at, aj.at(ns.at), strict=True)):
        at_rows.append(
            {
                "step": q,
                "survival": float(s),
                "lo": None if band is None else float(band.at[0][j]),
                "hi": None if band is None else float(band.at[1][j]),
            }
        )
    cause_rows = []
    for k in causes:
        cause_rows.append(
            {
                "cause": k,
                "deaths": int(portable.isum(1 for p in placement.rows if p.died and p.cause == k)),
                "f": aj.final[k],
                "lo": None if band is None else band.final[k][0],
                "hi": None if band is None else band.final[k][1],
            }
        )
    failed_steps = sorted(p.index for p in placement.rows if p.died)
    # the median step of the failed tries: the lower middle one where their number is even
    median = failed_steps[(len(failed_steps) - 1) // 2] if failed_steps else None
    data: dict[str, Any] = {
        "schema": "poisson-trace.where/1",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "run": _header(run, manifest, placement),
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "curve": curve,
        "median_step": median,
        "at": at_rows,
        "causes": cause_rows,
        "bootstrap": {"b": ns.boot, "seed": ns.seed},
        # the share of tries that timed out, an end of its own beside the kinds, with its band;
        # the first step by which half of all tries had failed; the last step a try reached
        "_timed_out": {
            "count": portable.isum(1 for p in placement.rows if p.reason == "timed out"),
            "f": aj.timed_out,
            "lo": None if band is None else band.timed_out[0],
            "hi": None if band is None else band.timed_out[1],
        },
        "_half_step": aj.half(),
        "_last_step": int(index_steps.max()) if len(index_steps) else None,
    }
    check = declaration_check(manifest, frame)
    if check is not None:
        data["declared"] = check.provenance()
        data["_reached"] = _reached_by(rows)
    data["steps"] = steps.steps_of(rows, causes, steps.last_step(rows), _ordered)
    timings_lines: list[str] = []
    if ns.timings or named is not None:
        data["timings"], timings_lines = _timings(ns, rows)
    data["cannot_say"] = list(CANNOT_SAY)
    traced = _traced(frame)
    svg_refusal = None
    if not traced:
        svg_refusal = (
            f"{look.word(index.word_for(run))} has no traces{_from(run)}, so there is no "
            "curve for --svg to draw; fix-check and changes read it"
        )
        data["note"] = _no_traces(run)
    before = _run_before(index, run)
    if before is None:
        following = look.command("poisson-trace", "fix-check", "--help")
    elif traced:
        following = _next(index, "compare", (before, run), ns)
    else:
        # compare reads traces, and this run has none: the fix check reads its outcomes
        following = _next(index, "fix-check", (before, run), ns, "--inputs", "all")
    this = look.word(index.word_for(run))
    data["_how"] = (
        f"it was imported from {run.backend[len('import:') :]}"
        if run.imported
        else "it was stored without traces"
    )
    plain = summary.where(
        data,
        compare=None if before is None else _next(index, "compare", (before, run), ns),
        passing=look.command(
            "poisson-trace", "where", this, *_reach(ns), "--event", "PASSING-OUTCOME"
        ),
        fix_check=(
            look.command("poisson-trace", "fix-check", "OLD", this, *_flags(ns), "--inputs", "all")
            if before is None
            else _next(index, "fix-check", (before, run), ns, "--inputs", "all")
        ),
    )
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    report = WhereReport(
        data=data,
        last_step=int(index_steps.max()) if len(index_steps) else 0,
        incidence={k: [float(x) for x in aj.incidence[k]] for k in causes},
    )
    return Counted(
        "where",
        "ok",
        sentence,
        following,
        data,
        report,
        [("a", run, manifest)],
        _settings(ns, "where"),
        ns,
        svg_refusal=svg_refusal,
        timings_lines=tuple(timings_lines),
    )


def _check_svg(path: str, force: bool) -> None:
    """Refuse, before any work, an SVG path that cannot be written or would replace a file
    without --force."""
    try:
        _refuse_svg(path, force)
    except OSError as e:
        raise _Refusal(f"cannot write {path} ({look.why(e)})") from e


def _refuse_svg(path: str, force: bool) -> None:
    target = Path(path)
    folder = target.parent
    # a link counts as there, even when what it points to is not
    there = target.exists() or target.is_symlink()
    if target.is_dir():
        raise _Refusal(f"cannot write {path}: it is a folder")
    if not folder.is_dir():
        what = "is not a folder" if folder.exists() else "does not exist"
        raise _Refusal(f"cannot write {path}: the folder {folder} {what}")
    if not os.access(folder, os.W_OK):
        raise _Refusal(f"cannot write {path}: the folder {folder} cannot be written to")
    if there and not force:
        raise _Refusal(f"{path} exists; add --force to replace it")
    if target.exists() and not os.access(target, os.W_OK):
        raise _Refusal(f"cannot write {path}: the file cannot be written to")


def _write_svg(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as e:
        raise look.Failed(
            f"could not write {path} ({look.why(e)}); the report was not printed"
        ) from e


# ---------- compare ----------


def compare(ns: argparse.Namespace) -> Counted:
    import numpy as np
    import poisson_prove

    from poisson_trace import steps, summary
    from poisson_trace.clock import conversations
    from poisson_trace.clock import placement as placement_of
    from poisson_trace.report import CANNOT_SAY, CompareReport
    from poisson_trace.survival import (
        bh,
        competing,
        difference_band,
        information_limit,
        logrank_stratified,
        one_step,
    )

    store, index = _named(ns)
    # two words that reach one run are refused as changes and fix-check refuse them
    run_a, run_b = _two(index, ns.a, ns.b, ("A", "B"))
    manifest_a, frame_a, tally_a = _load(store, run_a)
    manifest_b, frame_b, tally_b = _load(store, run_b)
    signals = None
    if ns.verdicts is not None or ns.temp_store:
        signals = _signals(ns, [("a", run_a), ("b", run_b)], frozenset(ns.event))
        frame_a = _filled(frame_a, signals[0]["a"], signals[1]["a"], frozenset(ns.event))
        frame_b = _filled(frame_b, signals[0]["b"], signals[1]["b"], frozenset(ns.event))
    untraced = [r for r, f in ((run_a, frame_a), (run_b, frame_b)) if not _traced(f)]
    if untraced:
        # compare places deaths at steps, which a run with no traces has none of; the fix check
        # reads the outcomes alone
        named = {r.run_id: r for r in untraced}.values()
        said = " and ".join(f"{look.word(index.word_for(r))}{_from(r)}" for r in named)
        has, its = ("has", "its") if len(named) == 1 else ("have", "their")
        raise _Refusal(
            f"{said} {has} no traces, so compare has no step to place {its} episodes on; "
            "fix-check compares the runs by their outcomes",
            _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all"),
        )
    events = frozenset(ns.event)
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = out_a | out_b
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    notes = [
        f"event {e}: carried by {'A' if e in out_a else 'B'} only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]
    read_a = conversations(manifest_a, frame_a, events=events, by=ns.by)
    read_b = conversations(manifest_b, frame_b, events=events, by=ns.by)
    asked = _timings_named(ns)
    if asked is not None:
        # a setting the command typed goes on the next command; one trace.toml gave is read
        # there again
        carried = ["--max-mde-hr", f"{ns.max_mde_hr:g}"] if "--max-mde-hr" in ns.typed_flags else []
        _refuse_unheld(
            asked,
            steps.held(read_a) | steps.held(read_b),
            "of A (before) or of B (after)",
            _next(index, "compare", (run_a, run_b), ns, *carried, "--timings", "--json"),
        )
    placement_a = placement_of(read_a, manifest_a, tally_a)
    placement_b = placement_of(read_b, manifest_b, tally_b)
    rows_a, rows_b = placement_a.rows, placement_b.rows
    if not any(p.died for p in rows_a) and not any(p.died for p in rows_b):
        raise _Refusal(
            f"no death in either run for the events {', '.join(sorted(events))}; "
            "there is no curve to compare"
        )
    cells_a = {p.config_hash for p in rows_a}
    cells_b = {p.config_hash for p in rows_b}
    common = cells_a & cells_b
    if not common:
        raise _Refusal("the runs share no config cell, so there is nothing to stratify by")
    common_a = [p for p in rows_a if p.config_hash in common]
    common_b = [p for p in rows_b if p.config_hash in common]
    deaths_common = portable.isum(p.died for p in common_a)
    deaths_common += portable.isum(p.died for p in common_b)
    if deaths_common == 0:
        raise _Refusal("no death in either run over the common cells; nothing to compare")
    lr = logrank_stratified(
        [(p.config_hash, p.index, p.died) for p in rows_a],
        [(p.config_hash, p.index, p.died) for p in rows_b],
    )
    # the limit from the log-rank's own information over the common cells
    mde = information_limit(lr.variance, alpha=ns.alpha)
    estimate = one_step(lr)
    if lr.observed_a < lr.expected_a:
        direction = "runs die later in A (before) than in B (after): runs die earlier in B"
        in_b = "earlier"
    elif lr.observed_a > lr.expected_a:
        direction = "runs die earlier in A (before) than in B (after): runs die later in B"
        in_b = "later"
    else:
        direction = "no direction"
        in_b = "neither earlier nor later"
    p_text = f"{lr.p:.3f}" if lr.p >= 0.001 else f"{lr.p:.2e}"
    if lr.p < ns.alpha:
        verdict = "different"
        sentence = (
            f"runs die {in_b} in B (after) than in A (before) "
            f"(log-rank, stratified by cell, p = {p_text})"
        )
        verdict_line = f"different: {sentence}"
    elif mde is not None and mde <= ns.max_mde_hr:
        verdict = "no significant difference"
        limit = f"could not have detected a hazard ratio below {mde:.3f}"
        sentence = f"p = {p_text}; {limit}"
        verdict_line = f"no significant difference (p = {p_text}); {limit}"
    else:
        verdict = "too small to tell"
        if mde is None:
            sentence = (
                "the log-rank has no information on these runs, so it could not have detected "
                f"any hazard ratio, and {ns.max_mde_hr:g} was asked for"
            )
        else:
            sentence = (
                f"could not have detected a hazard ratio below {mde:.3f}, "
                f"and {ns.max_mde_hr:g} was asked for"
            )
        verdict_line = f"too small to tell: {sentence}"
    guidance = information = None
    if verdict == "too small to tell":
        guidance, information = _compare_guidance(ns, common_a, common_b, mde)
    causes = _ordered({p.cause for p in rows_a + rows_b if p.died})
    tries_a, tries_b = _tries(placement_a), _tries(placement_b)
    at_rows = []
    if ns.at:
        share_a = competing(tries_a, causes).at(ns.at)
        share_b = competing(tries_b, causes).at(ns.at)
        lo, hi = difference_band(tries_a, tries_b, causes, ns.at, draws=_AT_DRAWS, seed=0)
        for j, q in enumerate(ns.at):
            at_rows.append(
                {
                    "step": q,
                    "survival_a": float(share_a[j]),
                    "survival_b": float(share_b[j]),
                    "diff": float(share_b[j] - share_a[j]),
                    "lo": float(lo[j]),
                    "hi": float(hi[j]),
                }
            )
    per: list[dict[str, Any]] = []
    for k in causes:
        lr_k = logrank_stratified(
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_a],
            [(p.config_hash, p.index, p.died and p.cause == k) for p in rows_b],
        )
        per.append(
            {
                "cause": k,
                "deaths_a": portable.isum(1 for p in rows_a if p.died and p.cause == k),
                "deaths_b": portable.isum(1 for p in rows_b if p.died and p.cause == k),
                "statistic": lr_k.statistic,
                "p": lr_k.p,
                "q": None,
                # each kind's limit from its own cause-specific log-rank information
                "mde_hazard_ratio": information_limit(lr_k.variance, alpha=ns.alpha),
            }
        )
    if per:
        qs = bh(np.array([r["p"] for r in per], dtype=np.float64), ns.alpha)
        for row, q_value in zip(per, qs, strict=True):
            row["q"] = float(q_value)
    # both runs on one axis: each side is listed to the later of the two runs' last steps
    last = max(steps.last_step(read_a), steps.last_step(read_b))
    timings: dict[str, Any] = {}
    timings_lines: list[str] = []
    if ns.timings or asked is not None:
        for arm, read, side in (("a", read_a, " of A (before)"), ("b", read_b, " of B (after)")):
            timings[arm], lines = _timings(ns, read, side)
            timings_lines += lines
    data: dict[str, Any] = {
        "schema": "poisson-trace.compare/1",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {
            "a": _header(run_a, manifest_a, placement_a),
            "b": _header(run_b, manifest_b, placement_b),
        },
        "events": sorted(events),
        "clock": {"unit": "leaf span index", "by": ns.by},
        "at": at_rows,
        "comparison": {
            "cells": lr.cells,
            "excluded_cells": {"a_only": len(cells_a - common), "b_only": len(cells_b - common)},
            "observed_a": lr.observed_a,
            "expected_a": lr.expected_a,
            "variance": lr.variance,
            "statistic": lr.statistic,
            "p": lr.p,
            "alpha": ns.alpha,
            "direction": direction,
            "paired": False,
            # after against before, Peto's one-step estimate from the numbers above
            "hazard_ratio": None if estimate is None else estimate[0],
            "hazard_ratio_lo": None if estimate is None else estimate[1],
            "hazard_ratio_hi": None if estimate is None else estimate[2],
            "mde_hazard_ratio": mde,
            "max_mde_hr": ns.max_mde_hr,
            "verdict": verdict,
            "guidance": guidance,
        },
        "per_cause": per,
        "steps": {
            "a": steps.steps_of(read_a, causes, last, _ordered),
            "b": steps.steps_of(read_b, causes, last, _ordered),
        },
        **({"timings": timings} if timings else {}),
        "cannot_say": list(CANNOT_SAY),
        "_observed_b": float(portable.isum(p.died for p in common_b)),
        "_deaths_common": deaths_common,
        "_verdict_line": verdict_line,
        "_same_salt": manifest_a.run_salt == manifest_b.run_salt,
        "_event_notes": notes,
        "_placed_common": len(common_a) + len(common_b),
        "_at_draws": _AT_DRAWS,
        # the information a hazard ratio of the size asked needs, and what the tries offered
        # are expected to give, for the guidance
        "_information": information,
        "_tries_per_input": _tries_per_input(common_a, common_b),
        # for the summary: the tries and failures over the common cells, how far apart the two
        # started, and whether every common input failed as often of as many tries in both
        "_common": {
            arm: {"tries": len(rows), "failed": portable.isum(1 for p in rows if p.died)}
            for arm, rows in (("a", common_a), ("b", common_b))
        },
        "_gap_seconds": _gap_between(run_a, manifest_a, run_b, manifest_b),
        "_matching": _per_cell(common_a) == _per_cell(common_b),
        # for the summary: when a try counts as failed in each run
        "_rules": {
            "a": summary.failed_when(manifest_a, sorted(events)),
            "b": summary.failed_when(manifest_b, sorted(events)),
        },
    }
    following = _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all")
    plain = summary.compare(data, verdict, following)
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    counted = Counted(
        "compare",
        verdict,
        sentence,
        following,
        data,
        CompareReport(data=data),
        [("a", run_a, manifest_a), ("b", run_b, manifest_b)],
        _settings(ns, "compare"),
        ns,
        arms=("a", "b"),
        labels=("A", "B"),
        signals=signals,
        timings_lines=tuple(timings_lines),
    )
    return _with_breakdown(counted)


# compare's --at band: resamples of the inputs, and their seed
_AT_DRAWS = 2_000


def _per_cell(rows: Sequence[Any]) -> dict[str, tuple[int, int]]:
    """Each cell's tries and failures among placed tries."""
    held: dict[str, tuple[int, int]] = {}
    for p in rows:
        n, died = held.get(p.config_hash, (0, 0))
        held[p.config_hash] = (n + 1, died + int(p.died))
    return held


def _gap_between(run_a: Any, manifest_a: Any, run_b: Any, manifest_b: Any) -> float | None:
    """How far apart two runs started, in seconds; None where a start cannot be read."""
    try:
        return abs((_started(run_b, manifest_b) - _started(run_a, manifest_a)).total_seconds())
    except _Refusal:
        return None


def _tries_per_input(common_a: Sequence[Any], common_b: Sequence[Any]) -> int | None:
    """The tries per input per run over the common cells, where every one carries the same
    number; ``None`` where they differ."""
    held: dict[tuple[int, str], int] = {}
    for arm, rows in enumerate((common_a, common_b)):
        for p in rows:
            held[(arm, p.config_hash)] = held.get((arm, p.config_hash), 0) + 1
    numbers = set(held.values())
    return numbers.pop() if len(numbers) == 1 else None


def _compare_guidance(
    ns: argparse.Namespace, common_a: Sequence[Any], common_b: Sequence[Any], mde: float | None
) -> tuple[dict[str, Any], dict[str, float | None]]:
    """The tries per input per version whose expected log-rank information under no change,
    on the per-input model fitted to the two runs' common cells, reaches what the ratio asked
    for needs, and more than any input had in either run: these runs fell short, so the model
    reaching the target at their own tries does not make them enough. The ceiling offered is
    the detectable hazard ratio rounded up, so it accepts the design as it stands. Deaths, runs
    and inputs do not size the guidance and hold no value."""
    from poisson_trace.paired import accepts_at
    from poisson_trace.survival import (
        expected_information,
        fit_cells,
        information_needed,
        tries_needed,
    )

    fit = fit_cells([(p.config_hash, p.index, p.died) for p in [*common_a, *common_b]])
    repeats = tries_needed(fit, ns.max_mde_hr, alpha=ns.alpha)
    if repeats is not None:
        had = Counter(("a", p.config_hash) for p in common_a)
        had.update(("b", p.config_hash) for p in common_b)
        repeats = max(repeats, max(had.values()) + 1)
    return {
        "deaths": None,
        "runs": None,
        "inputs": None,
        "repeats": repeats,
        "accepts_at": None if mde is None else accepts_at(mde, decimals=3),
    }, {
        "needed": information_needed(ns.max_mde_hr, alpha=ns.alpha),
        "expected": None if repeats is None else expected_information(fit, repeats),
    }


# ---------- fix-check and changes ----------


@dataclass
class _Input:
    """One input's rows in one arm: how many ran to an outcome, how many of those failed, and
    how many had no outcome, split by Prove's timeout mark."""

    config: Any
    runs: int = 0
    failed: int = 0
    timed_out: int = 0
    no_outcome: int = 0


def _no_value(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _by_input(frame: Any, events: frozenset[str]) -> dict[str, _Input]:
    arm: dict[str, _Input] = {}
    for h, config, outcome, error in zip(
        frame["config_hash"], frame["config"], frame["outcome"], frame["error"], strict=True
    ):
        row = arm.setdefault(str(h), _Input(config=config))
        if _no_value(outcome):
            if error == "timeout":
                row.timed_out += 1
            else:
                row.no_outcome += 1
        else:
            row.runs += 1
            row.failed += outcome in events
    return arm


def _declared_repeats(manifest: Any) -> int | None:
    environment = manifest.environment
    sweep = environment.get("sweep") if isinstance(environment, Mapping) else None
    declared = sweep.get("replicates") if isinstance(sweep, Mapping) else None
    if isinstance(declared, bool) or not isinstance(declared, int):
        return None
    return declared


def _paired_header(run: Any, manifest: Any, tally: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "run_name": run.name,
        "target_id": manifest.target_id,
        "status": manifest.status,
        "created_at": manifest.created_at,
        "declared_repeats": _declared_repeats(manifest),
        "tally": tally.to_dict(),
        "_imported": run.imported,
        "_start": _start_of(manifest),
        # what sweep --note recorded for the run, as Prove reads it; None where there is none
        "_note": getattr(manifest, "note", None),
    }


def _started(run: Any, manifest: Any) -> datetime:
    try:
        at = datetime.fromisoformat(manifest.created_at)
        # a start with no zone is read as UTC, as Prove writes every start and as names read it
        return at.replace(tzinfo=UTC) if at.tzinfo is None else at
    except (TypeError, ValueError) as e:
        held = manifest.created_at
        shown = f' ("{held}")' if isinstance(held, str) else ""
        raise _Refusal(
            f"the run {run.shown()} carries no readable start time{shown}, so the gap between "
            "the two runs cannot be told"
        ) from e


def _check_events(
    events: frozenset[str], frame_a: Any, frame_b: Any, first: str, second: str
) -> list[str]:
    """The rule for event names: a name neither run carries is refused; a name one run carries
    is allowed, and noted."""
    out_a, out_b = _outcomes(frame_a), _outcomes(frame_b)
    present = {o for o in out_a | out_b if not _no_value(o)}
    missing = sorted(events - present)
    if missing:
        raise _Refusal(
            f"unknown event {', '.join(missing)}; the runs carry the outcomes: "
            f"{', '.join(sorted(present)) or 'none'}"
        )
    return [
        f"event {e}: carried by the {first if e in out_a else second} run only"
        for e in sorted(events)
        if (e in out_a) != (e in out_b)
    ]


def _check_fix_events(events: frozenset[str], frame_old: Any, frame_new: Any) -> list[str]:
    """The fix check's rule for a name neither run carries. Where every outcome
    the two runs carry is a word for success, no run failed under any name, and the fix check
    answers that: the name counts no failure and is noted. Where a run carries an outcome that
    is no word for success, a name neither carries may be that outcome misspelt, and it is
    refused as every verb refuses it."""
    from poisson_trace.setup import SUCCESS_WORDS

    out_old, out_new = _outcomes(frame_old), _outcomes(frame_new)
    present = {o for o in out_old | out_new if not _no_value(o)}
    missing = sorted(events - present)
    if not missing or not all(o in SUCCESS_WORDS for o in present):
        return _check_events(events, frame_old, frame_new, "old", "new")
    carried = _check_events(events - set(missing), frame_old, frame_new, "old", "new")
    return sorted([*carried, *(f"event {e}: carried by neither run" for e in missing)])


def _arm_rows(arm: Mapping[str, _Input], compared: Sequence[str], declared: int | None) -> Any:
    rows = [arm[h] for h in compared]
    return {
        "runs": portable.isum(r.runs for r in rows),
        "failed": portable.isum(r.failed for r in rows),
        "timed_out": portable.isum(r.timed_out for r in rows),
        "no_outcome": portable.isum(r.no_outcome for r in rows),
        "short": 0 if declared is None else portable.isum(1 for r in rows if r.runs < declared),
        "mixed": portable.isum(1 for r in rows if 0 < r.failed < r.runs),
    }


def _changes_block(
    counts: Sequence[Any], configs: Mapping[str, Any], alpha: float
) -> dict[str, Any]:
    """The per-input flags and what the design could not have flagged."""
    from poisson_trace.paired import CANNOT_SAY, Counts, _fisher, flags

    by_hash = {c.config_hash: c for c in counts}
    rows = []
    for f in sorted(flags(counts, alpha=alpha), key=lambda f: (f.p, f.config_hash)):
        c = by_hash[f.config_hash]
        rows.append(
            {
                "config_hash": f.config_hash,
                "config": configs[f.config_hash],
                "failed_a": c.failed_old,
                "runs_a": c.runs_old,
                "failed_b": c.failed_new,
                "runs_b": c.runs_new,
                "change": f.change,
                "p": f.p,
                "q": f.q,
                "flag": f.flag,
            }
        )

    def extreme(runs_old: int, runs_new: int) -> float:
        # none of the old arm's runs failed and every one of the new arm's did
        return _fisher(Counts("", 0, runs_old, runs_new, runs_new))

    tested = len(counts)
    smallest = min(extreme(a, b) for a, b in {(c.runs_old, c.runs_new) for c in counts})
    together = next((j for j in range(1, tested + 1) if smallest * tested / j < alpha), None)
    # a lone input is flagged only where its p is below alpha / M, so the repeats are the first at
    # which the most extreme table's p is below it; at exactly the threshold it is not flagged
    repeats = 1
    while extreme(repeats, repeats) >= alpha / tested:
        repeats += 1
    return {
        "tested": tested,
        "flagged": portable.isum(1 for r in rows if r["flag"] is not None),
        "alpha": alpha,
        "lone_threshold": alpha / tested,
        "smallest_attainable_p": smallest,
        "together": together,
        "lone_flip_repeats": repeats,
        "rows": rows,
        "cannot_say": list(CANNOT_SAY),
    }


def _number(x: float) -> float | None:
    return x if math.isfinite(x) else None


def fix_check(ns: argparse.Namespace) -> Counted:
    import poisson_prove

    from poisson_trace import paired, summary
    from poisson_trace.report import FixCheckReport, _p_is, _points

    ns.measures = ns.measures or bool(ns.max_change)
    store, index = _named(ns)
    run_old, run_new = _two(index, ns.old, ns.new, ("OLD", "NEW"))
    selecting = None if ns.failing_from is None else index.resolve(ns.failing_from)
    for arm, run in (("old", run_old), ("new", run_new)):
        if selecting is not None and selecting.run_id == run.run_id:
            raise _Refusal(
                f"the selecting run {selecting.shown()} is also the {arm} arm; both arms must "
                "be fresh re-runs, because the selecting run's failures on these inputs are "
                "there by selection"
            )
    manifest_old, frame_old, tally_old = _load(store, run_old, trace="none")
    manifest_new, frame_new, tally_new = _load(store, run_new, trace="none")
    events = frozenset(ns.event)
    signals = None
    if ns.verdicts is not None or ns.measures or ns.temp_store:
        signals = _signals(ns, [("old", run_old), ("new", run_new)], events)
        frame_old = _filled(frame_old, signals[0]["old"], signals[1]["old"], events)
        frame_new = _filled(frame_new, signals[0]["new"], signals[1]["new"], events)
    notes = _check_fix_events(events, frame_old, frame_new)
    arm_old, arm_new = _by_input(frame_old, events), _by_input(frame_new, events)
    if selecting is not None:
        min_failures = 1 if ns.min_failures is None else ns.min_failures
        _, frame_sel, _ = _load(store, selecting, trace="none")
        selected = sorted(
            h for h, row in _by_input(frame_sel, events).items() if row.failed >= min_failures
        )
        rule = {"rule": "failing-from", "failing_from": selecting.run_id}
        rule["min_failures"] = min_failures
    else:
        selected = sorted(set(arm_old) | set(arm_new))
        rule = {"rule": "all", "failing_from": None, "min_failures": None}
    left_out = dict.fromkeys(paired.LEFT_OUT, 0)
    compared = []
    for h in selected:
        if h not in arm_old:
            left_out[paired.LEFT_OUT[0]] += 1
        elif h not in arm_new:
            left_out[paired.LEFT_OUT[1]] += 1
        elif arm_old[h].runs == 0:
            left_out[paired.LEFT_OUT[2]] += 1
        elif arm_new[h].runs == 0:
            left_out[paired.LEFT_OUT[3]] += 1
        else:
            compared.append(h)
    if not compared:
        reasons = "; ".join(f"{reason} {count(n)}" for reason, n in left_out.items() if n)
        raise _Refusal(
            f"no input is left to compare: {count(len(selected))} selected"
            + (f", left out: {reasons}" if reasons else "")
        )
    counts = [
        paired.Counts(h, arm_old[h].failed, arm_old[h].runs, arm_new[h].failed, arm_new[h].runs)
        for h in compared
    ]
    header_old = _paired_header(run_old, manifest_old, tally_old)
    header_new = _paired_header(run_new, manifest_new, tally_new)
    started_old, started_new = _started(run_old, manifest_old), _started(run_new, manifest_new)
    gap = abs((started_new - started_old).total_seconds())
    rows_old = _arm_rows(arm_old, compared, header_old["declared_repeats"])
    rows_new = _arm_rows(arm_new, compared, header_new["declared_repeats"])

    test = paired.paired_test(counts)
    points, variance, lo, hi = paired.difference(counts, alpha=ns.alpha)
    by_p, moved, method = paired.by_input(counts, seed=ns.seed, draws=_DRAWS)
    drawn = method != "exact"
    share, again, kappa, within, pooled = paired.consistency(counts)
    # with one run per input per version, no input was run twice on one version, and the
    # only pairs of runs there are compare the versions, not a version with itself
    one_run = all(c.runs_old == 1 and c.runs_new == 1 for c in counts)
    # an input repeats when one version holds two or more of its runs with an outcome; where
    # fewer than half the compared inputs repeat, most pairs of runs of one input still set
    # the two versions side by side rather than a version beside itself
    repeating = portable.isum(1 for c in counts if c.runs_old >= 2 or c.runs_new >= 2)
    few_repeat = 0 < 2 * repeating < len(counts)
    if one_run or few_repeat:
        again = kappa = math.nan
    drop = paired.detection_limit(counts, direction="drop", alpha=ns.alpha)
    rise = paired.detection_limit(counts, direction="rise", alpha=ns.alpha)

    if points < 0:
        direction, word = "failed less in new", "less"
    elif points > 0:
        direction, word = "failed more in new", "more"
    else:
        direction, word = "no direction", ""
    p_is = _p_is(test.p)
    # every failure gone, and every run failing, as shifts in failure share: the largest a
    # proportional change can be on these inputs; math.fsum so that every Python adds the same bytes
    weights = [c.runs_old * c.runs_new / (c.runs_old + c.runs_new) for c in counts]
    rates = [(c.failed_old + c.failed_new) / (c.runs_old + c.runs_new) for c in counts]
    largest_drop = math.fsum(w * r for w, r in zip(weights, rates, strict=True)) / math.fsum(
        weights
    )
    asked = f"{100.0 * ns.max_mde:g}"
    limit_text = None if drop is None else _points(drop)
    excludes_zero = lo is not None and hi is not None and paired.excludes_zero(lo, hi)
    disagree = variance is not None and ((test.p < ns.alpha) != excludes_zero)
    # the range reads the verdict only where it is reliable; where it is not, the drop limit
    # against the size asked reads it
    rough = paired.rough(
        counts, informative=test.informative, disagree=disagree, alpha=ns.alpha
    )
    reliable = lo is not None and hi is not None and not rough
    inside = (
        reliable and lo is not None and hi is not None and paired.lies_inside(lo, hi, ns.max_mde)
    )
    enough = drop is not None and drop <= ns.max_mde
    guidance = None
    if test.p < ns.alpha and points != 0:
        verdict, decided = "different", "test"
        sentence = (
            f"the new version failed {word} on these inputs (exact "
            f"Cochran-Mantel-Haenszel, stratified by input, {p_is})"
        )
        verdict_line = f"different: {sentence}"
    elif reliable:
        decided = "range"
        span = _range_text(lo, hi, ns.alpha)
        if inside:
            verdict = "no significant difference"
            sentence = f"{p_is}; {span}, lies inside ±{asked}"
            verdict_line = f"no significant difference ({p_is}); {span}, lies inside ±{asked}"
        else:
            verdict = "too small to tell"
            sentence = f"{span}, does not lie inside ±{asked}, which was asked for"
            verdict_line = f"too small to tell: {sentence}"
    elif enough:
        verdict, decided = "no significant difference", "limit"
        limit = f"could not have detected a drop in failure share below {limit_text} points"
        sentence = f"{p_is}; {limit}"
        verdict_line = f"no significant difference ({p_is}); {limit}"
    else:
        verdict, decided = "too small to tell", "limit"
        if paired.none_failed(counts) and rough:
            # neither version failed and the range is rough: there is no drop to speak of
            sentence = (
                f"neither version failed, and the range is too rough to read ({rough[0]}); "
                f"{asked} points was asked for"
            )
        elif drop is None:
            sentence = (
                "could not have detected a drop in failure share below or "
                f"at {_points(largest_drop)} points, which is every failure gone, and {asked} "
                "was asked for"
            )
        else:
            sentence = (
                "could not have detected a drop in failure share below "
                f"{limit_text} points, and {asked} was asked for"
            )
        verdict_line = f"too small to tell: {sentence}"
    # no run failed in either version on the inputs compared. Where the range is
    # reliable there it has read the verdict above, and the guidance is the range's own; where
    # it is rough (fewer than three inputs, or very unequal tries) the drop limit
    # has, as on any rough range, and the guidance is the drop limit's
    none_failed = paired.none_failed(counts)
    clean = none_failed and reliable
    if verdict == "too small to tell":
        guidance = _fix_check_guidance(
            ns, counts, drop, lo, hi, reliable=reliable, enough=enough, clean=clean
        )
    configs = {h: arm_old[h].config for h in compared}
    block = _changes_block(counts, configs, ns.alpha)
    data: dict[str, Any] = {
        "schema": "poisson-trace.fix-check/2",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {"old": header_old, "new": header_new},
        "gap_seconds": gap,
        "events": sorted(events),
        "inputs": {
            **rule,
            "selected": len(selected),
            "compared": len(compared),
            "informative": test.informative,
            "left_out": left_out,
        },
        "rows": {"old": rows_old, "new": rows_new},
        "control": {
            "old_did_not_fail_share": 1.0 - rows_old["failed"] / rows_old["runs"],
            "new_did_not_fail_share": 1.0 - rows_new["failed"] / rows_new["runs"],
        },
        "test": {
            "name": "exact conditional Cochran-Mantel-Haenszel",
            "observed_new": test.observed_new,
            "expected_new": test.expected_new,
            "variance": test.variance,
            "weight": test.weight,
            "p": test.p,
            "alpha": ns.alpha,
        },
        "difference": {
            "points": points,
            "lo": lo,
            "hi": hi,
            "variance": variance,
            "interval": paired.INTERVAL,
        },
        "by_input": {
            "moved": moved,
            "p": by_p,
            "method": method,
            "draws": _DRAWS if drawn else None,
            "seed": ns.seed if drawn else None,
        },
        "consistency": {
            "failure_share": share,
            "fails_again": _number(again),
            "kappa": _number(kappa),
            "within": within,
            "pooled": pooled,
        },
        "limits": {"drop": drop, "rise": rise, "power": 0.8, "max_mde": ns.max_mde},
        "direction": direction,
        "guidance": guidance,
        "changes": block,
        "cannot_say": list(paired.CANNOT_SAY),
        "_verdict_line": verdict_line,
        "_failing_from": None if selecting is None else selecting.name,
        "_event_notes": notes,
        "_top": ns.top,
        "_one_run": one_run,
        "_few_repeat": (repeating, len(counts)) if few_repeat else None,
        "_largest": {"drop": largest_drop, "rise": 1.0 - largest_drop},
        "_disagree": disagree,
        # what the verdict rests on, for the summary: "test", "range" or "limit"
        "_decided_by": decided,
        # the range's level in percent, and why it is rough here (empty where it is reliable)
        "_level": 100.0 * (1.0 - ns.alpha),
        "_rough": list(rough),
        "_reliable": reliable,
        # the drop limit is at or under the size asked
        "_tries_enough": enough,
        # no run failed in either version on the inputs compared
        "_none_failed": none_failed,
        # neither version failed and the range is rough: the tries per input that bring the
        # range inside the size asked on the fewest inputs a range is reliable on
        "_clean_tries": (
            paired.clean_repeats_on(paired.CLEAN_FEW_INPUTS, ns.max_mde, alpha=ns.alpha)
            if none_failed and not reliable
            else None
        ),
        # the size asked, where a reliable range leaves out a drop (or a rise) of that size or more
        "_drop_ruled_out": ns.max_mde if reliable and lo is not None and lo > -ns.max_mde else None,
        "_rise_ruled_out": ns.max_mde if reliable and hi is not None and hi < ns.max_mde else None,
        "_unconfirmed": (
            _unconfirmed(counts, block) if verdict == "different" and by_p >= ns.alpha else None
        ),
        "_copies": [
            arm
            for arm, held in (("old", arm_old), ("new", arm_new))
            if all(held[h].runs >= 2 and not 0 < held[h].failed < held[h].runs for h in compared)
        ],
        # for the summary: when a try counts as failed in each run, whether the run given as new
        # started first, and each version's tries with no outcome on the inputs selected
        "_rules": {
            "old": summary.failed_when(manifest_old, sorted(events)),
            "new": summary.failed_when(manifest_new, sorted(events)),
        },
        "_new_first": started_new < started_old,
        "_no_outcome": {
            name: portable.isum(arm[h].no_outcome + arm[h].timed_out for h in selected if h in arm)
            for name, arm in (("old", arm_old), ("new", arm_new))
        },
    }
    plain = summary.fix_check(data, verdict, _next(index, "changes", (run_old, run_new), ns))
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    following = plain.follows or _fix_check_next(
        index, ns, run_old, run_new, guidance, len(compared)
    )
    counted = Counted(
        "fix-check",
        verdict,
        sentence,
        following,
        data,
        FixCheckReport(data=data),
        [("old", run_old, manifest_old), ("new", run_new, manifest_new)],
        _settings(ns, "fix-check", selecting),
        ns,
        arms=("old", "new"),
        labels=("old", "new"),
        signals=signals,
    )
    _with_breakdown(counted)
    if ns.measures:
        counted.two_run_parts()
        data["_measures_section"] = _measures_section(counted.measures)
    return counted


def _range_text(lo: float | None, hi: float | None, alpha: float) -> str:
    """``the 95% range, -6.0 to +8.1 points``, at the level the range was computed at."""
    from poisson_trace.report import _points

    assert lo is not None and hi is not None
    places = 2 if all(abs(100.0 * x) < 1.0 for x in (lo, hi)) else 1
    low, high = (_points(x, signed=True, places=places) for x in (lo, hi))
    return f"the {100.0 * (1.0 - alpha):g}% range, {low} to {high} points"


def _fix_check_guidance(
    ns: argparse.Namespace,
    counts: Sequence[Any],
    drop: float | None,
    lo: float | None,
    hi: float | None,
    *,
    reliable: bool,
    enough: bool,
    clean: bool = False,
) -> dict[str, Any]:
    """What too small to tell offers: the repeats and the inputs that bring the drop limit to
    the size asked, and the ceiling that accepts the design as it stands. Where a reliable range
    decided and the drop limit is already under the size asked, more tries of the same design
    are not what is short, and nothing is offered. Where a reliable range decides, the ceiling
    offered is the smallest the range lies inside, so that given, it reads otherwise. Where no
    run failed in either version (``clean``) there is no drop limit to bring anywhere, and the
    repeats and the inputs are those that bring the range inside the size asked, with still no
    failure."""
    from poisson_trace import paired

    if reliable and enough:
        return {"repeats": None, "inputs": None, "accepts_at": None}
    ceiling = drop
    if reliable and lo is not None and hi is not None:
        # the range alone decides: the smallest size asked that it lies inside, whatever the
        # drop limit says
        ceiling = max(-lo, hi)
    if clean:
        return {
            "repeats": paired.clean_repeats_needed(counts, ns.max_mde, alpha=ns.alpha),
            "inputs": paired.clean_inputs_needed(counts, ns.max_mde, alpha=ns.alpha),
            "accepts_at": None if ceiling is None else paired.accepts_at(ceiling, decimals=4),
        }
    return {
        "repeats": paired.repeats_needed(counts, ns.max_mde, alpha=ns.alpha),
        "inputs": paired.inputs_needed(counts, ns.max_mde, alpha=ns.alpha),
        "accepts_at": None if ceiling is None else paired.accepts_at(ceiling, decimals=4),
    }


def _unconfirmed(counts: Sequence[Any], block: Mapping[str, Any]) -> dict[str, Any]:
    """For a difference the by-input check does not bear out: the inputs the per-input check
    flagged, their share of the net extra failures, and the gap and the exact test without
    them. An input's extra failures are its new failures less the old version's rate at the
    new version's tries; the net is their sum over every compared input."""
    from poisson_trace import paired

    flagged = {r["config_hash"]: r for r in block["rows"] if r["flag"] is not None}

    def extra(c: Any) -> float:
        return float(c.failed_new - c.failed_old * c.runs_new / c.runs_old)

    rest = [c for c in counts if c.config_hash not in flagged]
    points_without = p_without = None
    if flagged and rest:
        points_without = paired.difference(rest)[0]
        p_without = paired.paired_test(rest).p
    return {
        "inputs": [
            {
                "config_hash": c.config_hash,
                "config": flagged[c.config_hash]["config"],
                "extra": extra(c),
            }
            for c in counts
            if c.config_hash in flagged
        ],
        "extra": math.fsum(extra(c) for c in counts if c.config_hash in flagged),
        "net_extra": math.fsum(extra(c) for c in counts),
        "compared_without": len(rest),
        "points_without": points_without,
        "p_without": p_without,
    }


def _fix_check_next(
    index: Any,
    ns: argparse.Namespace,
    old: Any,
    new: Any,
    guidance: Mapping[str, Any] | None,
    inputs: int,
) -> str:
    """Too small to tell: the repeats or the inputs the guidance gives, then the fix check
    again. Otherwise the inputs that moved, on the same two runs."""
    if guidance is None:
        return _next(index, "changes", (old, new), ns)
    again = "then poisson-trace fix-check on the two new runs"
    if guidance["repeats"] is not None:
        return (
            f"run {count(guidance['repeats'])} repeats per arm on these {count(inputs)} "
            f"{'input' if inputs == 1 else 'inputs'}, {again}"
        )
    if guidance["inputs"] is not None:
        return f"run {count(guidance['inputs'])} inputs like these at the present repeats, {again}"
    return look.command("poisson-trace", "fix-check", "--help")


def changes(ns: argparse.Namespace) -> Counted:
    import poisson_prove

    from poisson_trace import paired, summary
    from poisson_trace.report import ChangesReport

    store, index = _named(ns)
    run_a, run_b = _two(index, ns.a, ns.b, ("A", "B"))
    manifest_a, frame_a, tally_a = _load(store, run_a, trace="none")
    manifest_b, frame_b, tally_b = _load(store, run_b, trace="none")
    events = frozenset(ns.event)
    signals = None
    if ns.verdicts is not None or ns.temp_store:
        signals = _signals(ns, [("a", run_a), ("b", run_b)], events)
        frame_a = _filled(frame_a, signals[0]["a"], signals[1]["a"], events)
        frame_b = _filled(frame_b, signals[0]["b"], signals[1]["b"], events)
    notes = _check_events(events, frame_a, frame_b, "A", "B")
    arm_a, arm_b = _by_input(frame_a, events), _by_input(frame_b, events)
    compared = sorted(h for h in set(arm_a) & set(arm_b) if arm_a[h].runs and arm_b[h].runs)
    if not compared:
        raise _Refusal(
            "no input has a run with an outcome in both runs, so there is nothing to compare"
        )
    counts = [
        paired.Counts(h, arm_a[h].failed, arm_a[h].runs, arm_b[h].failed, arm_b[h].runs)
        for h in compared
    ]
    gap = abs((_started(run_b, manifest_b) - _started(run_a, manifest_a)).total_seconds())
    data: dict[str, Any] = {
        "schema": "poisson-trace.changes/2",
        "prove": {"version": poisson_prove.__version__, "store": _store_shown(ns)},
        "runs": {
            "a": _paired_header(run_a, manifest_a, tally_a),
            "b": _paired_header(run_b, manifest_b, tally_b),
        },
        "events": sorted(events),
        **_changes_block(counts, {h: arm_a[h].config for h in compared}, ns.alpha),
        "_event_notes": notes,
        "_top": ns.top,
        "_gap_seconds": gap,
        "_verdict_tries": {
            "a": portable.isum(arm_a[h].runs for h in compared),
            "b": portable.isum(arm_b[h].runs for h in compared),
        },
        "_inputs": {
            "a": len(arm_a),
            "b": len(arm_b),
            "a_only": len(set(arm_a) - set(arm_b)),
            "b_only": len(set(arm_b) - set(arm_a)),
        },
    }
    # for the summary: each run's tries with no outcome, and the inputs both carry that one of
    # them gives no outcome on
    data["_no_outcome"] = {
        "a": portable.isum(r.no_outcome + r.timed_out for r in arm_a.values()),
        "b": portable.isum(r.no_outcome + r.timed_out for r in arm_b.values()),
        "left_out": portable.isum(
            1 for h in set(arm_a) & set(arm_b) if not (arm_a[h].runs and arm_b[h].runs)
        ),
    }
    following = _next(index, "fix-check", (run_a, run_b), ns, "--inputs", "all")
    plain = summary.changes(data, following)
    data["_summary"], data["_before_you_act"] = plain.lines, plain.caveats
    sentence = plain.sentence
    counted = Counted(
        "changes",
        "ok",
        sentence,
        following,
        data,
        ChangesReport(data=data),
        [("a", run_a, manifest_a), ("b", run_b, manifest_b)],
        _settings(ns, "changes"),
        ns,
        arms=("a", "b"),
        labels=("A", "B"),
        signals=signals,
    )
    return _with_breakdown(counted)


VERBS: dict[str, Callable[[argparse.Namespace], Counted]] = {
    "where": where,
    "compare": compare,
    "fix-check": fix_check,
    "changes": changes,
}


# ---------- the static pages and the HTML report ----------

#: Where a store's pages are, under its ``.poisson/ui/``: Trace's own
#: folder beside Prove's dashboard, which Trace never writes, rebuilds or deletes.
PAGES = "trace"
REPORT_PAGE = "report.html"
#: The kinds Trace saves, each with a page; Prove's own saved comparisons get none.
_KINDS = ("where", "compare", "fix-check", "changes")


@dataclass(frozen=True)
class View:
    """The object behind one page: its kind (``runs``, a verdict's kind, or ``could not
    say``), its address inside the UI (``trace/fix-check/<id>.html``) and every fact the page
    shows, as data. ``pages.render`` formats a view and computes nothing in it."""

    kind: str
    address: str
    document: dict[str, Any]


def _artifact_of(c: Counted) -> tuple[Any, dict[str, str]]:
    """The artifact a verdict saves, as ``--save`` builds it and
    ``to_html`` renders it: every path the call carried written short, the charts drawn."""
    from poisson_trace import saved

    ns = c.ns
    c.two_run_parts()
    absolute = _absolute(ns)
    added, notes = _added(c)
    ids = [run.run_id for _, run, _ in c.runs]
    identity = saved.artifact_id(c.kind, {"runs": ids}, c.settings)
    place = None if ns.temp_store else saved.saved_path(c.kind, identity)
    result = saved.shortened(_result_document(c.printed(), c.data, added, notes, place), absolute)
    joined_line = details(c, Delivered())[:1] if ns.joined is not None else []
    report = saved.short(
        _said(c.verdict, c.sentence, c.markdown(), c.following, *joined_line), absolute
    )
    artifact = saved.Artifact(
        kind=c.kind,
        runs=ids,
        settings=c.settings,
        result=result,
        report=report,
        events=sorted(ns.event),
        rows=_TABLE_ROWS[c.kind](result),
        detail=[(label, line) for label, line in result["summary"]],
        charts=c.charts(),
    )
    return artifact, absolute


def _compare_charts(c: Counted) -> list[tuple[str, str, dict[str, Any]]]:
    """``compare``'s two charts: ``curves``, each run's ``where`` curve under
    compare's failures with where's own defaults, in compare's order; ``hazard-ratio``, the
    verdict's hazard ratio with its range, the limit and the ratio asked for. Each is saved as
    a file of its own, with its data beside it."""
    from poisson_trace import api, pages

    runs = []
    bootstrap: dict[str, Any] = {}
    units: set[str] = set()
    for arm, run, _manifest in c.runs:
        found = api.where(c.ns.store_root, run.run_id, event=sorted(c.ns.event))
        bootstrap = dict(found.bootstrap)
        units.add(_unit_of(found.run))
        runs.append(
            {"arm": arm, "run_id": run.run_id, "name": found.run["run_name"], "curve": found.curve}
        )
    unit = units.pop() if len(units) == 1 else "step"
    events = sorted(c.ns.event)
    curves = {"runs": runs, "events": events, "bootstrap": bootstrap, "unit": unit}
    series = [
        {"cls": "before" if r["arm"] == "a" else "after", "name": r["name"], "curve": r["curve"]}
        for r in runs
    ]
    title = pages.curve_words(events, bootstrap, unit)
    curves_svg = pages.curves_svg("curves", series, unit=unit, title=title, standalone=True)
    comparison = c.data["comparison"]
    hazard = {
        key: comparison.get(key)
        for key in (
            "hazard_ratio",
            "hazard_ratio_lo",
            "hazard_ratio_hi",
            "mde_hazard_ratio",
            "max_mde_hr",
        )
    }
    hazard["alpha"] = comparison.get("alpha")
    hazard["cells"] = comparison.get("cells")
    words = pages.hazard_words(hazard)
    hazard_svg = pages.hazard_svg("hazard-ratio", hazard, title=words, standalone=True)
    return [("curves", curves_svg, curves), ("hazard-ratio", hazard_svg, hazard)]


def _read_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def artifact_folders(root: Path) -> list[Path]:
    """Every saved verdict of Trace's in a store, by kind then id."""
    base = root / ".poisson" / "artifacts"
    out: list[Path] = []
    for kind in _KINDS:
        if (base / kind).is_dir():
            out += sorted(d for d in (base / kind).iterdir() if (d / "artifact.json").is_file())
    return out


def _saved_verdict(folder: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    """A saved verdict's descriptor, result and report, read; one that cannot be read is
    refused with its place and the system's words, never its content."""
    try:
        art = _read_json(folder / "artifact.json")
        result = _read_json(folder / "result.json")
        report = (folder / "report.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        place = f".poisson/artifacts/{folder.parent.name}/{folder.name}"
        raise _Refusal(f"the saved verdict at {place} cannot be read ({look.why(e)})") from e
    if not isinstance(art, Mapping) or not isinstance(result, Mapping):
        place = f".poisson/artifacts/{folder.parent.name}/{folder.name}"
        raise _Refusal(f"the saved verdict at {place} cannot be read (not a saved verdict)")
    return dict(art), dict(result), report


def _report_sections(report: str) -> tuple[str, list[dict[str, Any]]]:
    """The report's title line and its body split at its ``##`` headings: the lines before the
    first heading under None, the ``next:`` line left out."""
    lines = report.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("# "))
    sections: list[dict[str, Any]] = [{"heading": None, "lines": []}]
    for line in lines[start + 1 :]:
        if line.startswith("next: "):
            continue
        if line.startswith("## "):
            sections.append({"heading": line[3:].strip(), "lines": []})
        else:
            sections[-1]["lines"].append(line)
    return lines[start][2:], [
        s for s in sections if s["heading"] is not None or any(x.strip() for x in s["lines"])
    ]


def _measures_from(doc: Mapping[str, Any]) -> list[str]:
    """The continuous-measures section as ``fix-check --measures`` prints it, rebuilt from the
    measures ``result.json`` saved: the saved ``report.md`` has the section only when the
    verdict was saved with ``--measures``."""
    from poisson_trace.stats.continuous import Measure

    fields = set(Measure.__dataclass_fields__)
    measures: dict[str, Measure] = {}
    for m in doc.get("measures", ()):
        kw: dict[str, Any] = {}
        for key, value in m.items():
            if key not in fields:
                continue
            if key == "unfinished":
                kw[key] = {
                    label: tuple((kind, int(n)) for kind, n in kinds.items())
                    for label, kinds in value.items()
                }
            elif key == "changes":
                kw[key] = [(case, v) for case, v in value]
            else:
                kw[key] = value
        measures[str(m["measure"])] = Measure(**kw)
    held = argparse.Namespace(measures=measures)
    return _measures_section(held)


def _run_names(kind: str, result: Mapping[str, Any]) -> list[str]:
    if kind == "where":
        return [str(result["run"]["run_name"])]
    return [str(r["run_name"]) for r in result["runs"].values()]


def _unit_of(run: Mapping[str, Any]) -> str:
    return "turn" if run.get("t_unit") == "turns" else "step"


def verdict_view(folder: Path, store: str) -> View:
    """The view behind a saved verdict's page (and the HTML report of its bundle): the verdict
    line, the report's title, every section of the report as the plain command prints it, the
    continuous measures where ``fix-check --measures`` prints them, what was saved, and the
    charts' data. Nothing a save alone decides is in it."""
    art, result, report = _saved_verdict(folder)
    kind, ident = str(art["kind"]), str(art["id"])
    title, sections = _report_sections(report)
    if (
        kind == "fix-check"
        and result.get("continuous_measures")
        and not any(s["heading"] == MEASURES_HEADING[3:] for s in sections)
    ):
        extra = _measures_from(result["continuous_measures"])
        at = next(
            (i for i, s in enumerate(sections) if s["heading"] == "What this cannot say"),
            len(sections),
        )
        sections.insert(at, {"heading": extra[0][3:], "lines": extra[1:]})
    names = _run_names(kind, result)
    doc: dict[str, Any] = {
        "view": kind,
        "address": f"{PAGES}/{kind}/{ident}.html",
        "kind": kind,
        "id": ident,
        "verdict": result["verdict"],
        "sentence": result["sentence"],
        "title": title,
        "name": " → ".join(names),
        "saved": f".poisson/artifacts/{kind}/{ident}",
        "files": [str(f["path"]) for f in art.get("files", ())],
        "versions": dict(result.get("versions") or {}),
        "sections": sections,
        "cannot_say": list(result.get("cannot_say") or ()),
        "store": store,
    }
    detected = next(
        (s["lines"] for s in sections if s["heading"] == "What it could not have detected"), None
    )
    if detected is not None:
        doc["detected"] = [line for line in detected if line.strip()]
    if kind == "where" and result.get("curve"):
        doc["curve"] = {
            "name": names[0],
            "curve": result["curve"],
            "events": list(result.get("events") or ()),
            "bootstrap": dict(result.get("bootstrap") or {}),
            "unit": _unit_of(result["run"]),
        }
    if kind == "compare":
        charts = folder / "charts"
        if (charts / "curves.json").is_file():
            curves = _read_json(charts / "curves.json")
            doc["curves"] = {
                "runs": curves["runs"],
                "events": list(curves.get("events") or result.get("events") or ()),
                "bootstrap": dict(curves.get("bootstrap") or {}),
                "unit": curves.get("unit") or "step",
            }
        if (charts / "hazard-ratio.json").is_file():
            hazard = _read_json(charts / "hazard-ratio.json")
            doc["hazard"] = {k: v for k, v in hazard.items() if k != "schema"}
    return View(kind, doc["address"], doc)


def could_not_say_view(folder: Path, store: str) -> View:
    """The view behind a verdict's could-not-say page: the verdict line, everything the verdict
    cannot say, what it could not have detected, and the way back."""
    full = verdict_view(folder, store)
    doc = {
        **{
            k: full.document[k]
            for k in ("kind", "id", "verdict", "sentence", "title", "name", "cannot_say", "store")
        },
        "view": "could not say",
        "address": f"{PAGES}/{full.kind}/{full.document['id']}/could-not-say.html",
    }
    if "detected" in full.document:
        doc["detected"] = full.document["detected"]
    return View("could not say", doc["address"], doc)


def _tool_of(run: Mapping[str, Any]) -> str:
    """The target of a Prove run, or the tool an import came from."""
    backend = str(run.get("backend") or "")
    if backend.startswith("import:"):
        return backend[len("import:") :]
    return str(run.get("target_id"))


def runs_view(
    root: Path,
    listing: Mapping[str, Any],
    events: Sequence[str] | None,
    others: Sequence[tuple[str, str]],
) -> View:
    """The view behind a store's runs page: the line ``runs`` prints, the
    store written as its folder's name; a row a run; a row a saved verdict, newest
    first, linking its page; a run's name linking its newest saved where page; the config's
    other stores' pages; Prove's dashboard when it is beside these pages."""
    name = root.name or Path(os.path.abspath(root)).name
    saved: list[dict[str, Any]] = []
    newest_where: dict[str, tuple[str, str]] = {}
    for folder in artifact_folders(root):
        art, result, _report = _saved_verdict(folder)
        kind, ident, at = str(art["kind"]), str(art["id"]), str(art.get("created_at", ""))
        saved.append(
            {
                "kind": kind,
                "runs": " → ".join(_run_names(kind, result)),
                "verdict": result["verdict"],
                "sentence": result["sentence"],
                "id": ident,
                "saved_at": at,
                "address": f"{kind}/{ident}.html",
            }
        )
        if kind == "where":
            run_id = str(result["run"]["run_id"])
            if run_id not in newest_where or newest_where[run_id][0] < at:
                newest_where[run_id] = (at, ident)
    saved.sort(key=lambda s: (s["saved_at"], s["kind"], s["id"]), reverse=True)
    rows = []
    for run in listing["runs"]:
        where = newest_where.get(str(run["run_id"]))
        rows.append(
            {
                "number": run["number"],
                "name": run["name"],
                "run_id": run["run_id"],
                "tool": _tool_of(run),
                "rows": run["rows"],
                "failed": run["failed"],
                "traced": run["traced"],
                "created_at": run["created_at"],
                "status": run["status"],
                "where": None if where is None else f"where/{where[1]}.html",
            }
        )
    sentence = str(listing["sentence"]).replace(f" in {listing['store']} ", f" in {name} ", 1)
    prove = root / ".poisson" / "ui" / "index.html"
    doc: dict[str, Any] = {
        "view": "runs",
        "address": f"{PAGES}/index.html",
        "verdict": listing["verdict"],
        "sentence": sentence,
        "store": name,
        "events": list(events) if events else None,
        "runs": rows,
        "saved": saved,
        "others": [{"name": n, "href": h} for n, h in others],
        "prove": "../index.html" if prove.is_file() else None,
    }
    return View("runs", doc["address"], doc)


def store_views(
    root: Path,
    listing: Mapping[str, Any],
    events: Sequence[str] | None,
    others: Sequence[tuple[str, str]],
) -> dict[str, View]:
    """Every view of a store's pages, by address under ``ui/``: the runs page, a page and a
    could-not-say page per saved verdict of Trace's."""
    name = root.name or Path(os.path.abspath(root)).name
    views = {f"{PAGES}/index.html": runs_view(root, listing, events, others)}
    for folder in artifact_folders(root):
        v = verdict_view(folder, name)
        views[v.address] = v
        w = could_not_say_view(folder, name)
        views[w.address] = w
    return views


def _dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


_STAGING_PAGES = re.compile(r"^\.trace-(?:new|old)-(\d+)")


def _clean_dead_page_builds(ui: Path) -> None:
    """Staging and set-aside trees a build that died left behind under ``ui/``; a live build's
    are its own (Prove sweeps its own, ``.ui-*``, the same way)."""
    for stale in ui.glob(".trace-*"):
        found = _STAGING_PAGES.match(stale.name)
        if stale.is_dir() and found and _dead(int(found.group(1))):
            import shutil

            shutil.rmtree(stale, ignore_errors=True)


def build_store_pages(
    root: Path,
    listing: Mapping[str, Any],
    events: Sequence[str] | None,
    others: Sequence[tuple[str, str]] = (),
) -> Path:
    """Write a store's pages: every view rendered into a staging folder under the store's
    ``ui/`` with Prove's bundle beside them, then renamed into ``ui/trace/`` last, so an
    interrupted build leaves the previous pages and nothing of Prove's is touched. Raises
    ``OSError`` where the pages cannot be written, and a refusal where the
    installed Prove lacks the bundle. Returns the index."""
    import shutil
    import tempfile

    from poisson_trace import pages

    # a Prove installed without its bundle is refused before the store is touched
    pages.check_bundle()
    views = store_views(root, listing, events, others)
    name = root.name or Path(os.path.abspath(root)).name
    ui = root / ".poisson" / "ui"
    ui.mkdir(parents=True, exist_ok=True)
    _clean_dead_page_builds(ui)
    target = ui / PAGES
    staging = Path(tempfile.mkdtemp(prefix=f".trace-new-{os.getpid()}-", dir=ui))
    aside: Path | None = None
    try:
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(staging, 0o777 & ~mask)
        for address, view in views.items():
            page = staging / address.removeprefix(f"{PAGES}/")
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(pages.render(view.document, name), encoding="utf-8")
        for file_name, data in pages.bundle_files().items():
            (staging / file_name).write_bytes(data)
        if target.exists():
            aside = ui / f".trace-old-{os.getpid()}"
            os.replace(target, aside)
        try:
            os.replace(staging, target)
        except BaseException:
            if aside is not None and not target.exists():
                os.replace(aside, target)
                aside = None
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if aside is not None and aside.exists() and target.exists():
            shutil.rmtree(aside, ignore_errors=True)
    return target / "index.html"


def rebuild_pages(ns: argparse.Namespace) -> None:
    """The pages of the store a verdict was just saved into, rebuilt: its runs listed
    under the call's own failures, or uncounted where the store does not carry them; a
    link to each other store the call's config names whose pages are there. Raises
    ``OSError`` where the pages cannot be written, a refusal where a saved verdict cannot be
    read."""
    root = Path(ns.store_root)
    events = sorted(ns.event)
    try:
        listed = store_listing(ns.store, events)
    except _Refusal:
        listed, events = store_listing(ns.store, None), []
    build_store_pages(root, listed, events, other_pages(root, ns.settings))


def other_pages(root: Path, held: Any) -> list[tuple[str, str]]:
    """The config's other stores whose pages are there, each as its folder's name and the
    relative address of its index from this store's (never absolute)."""
    if held is None:
        return []
    index = root / ".poisson" / "ui" / PAGES / "index.html"
    out: list[tuple[str, str]] = []
    paths = [str(held.store)] if held.store is not None else []
    paths += [str(p) for p in held.named.values()]
    for path in paths:
        other = Path(path)
        there = other / ".poisson" / "ui" / PAGES / "index.html"
        if os.path.realpath(other) == os.path.realpath(root) or not there.is_file():
            continue
        start = os.path.dirname(os.path.abspath(index))
        href = os.path.relpath(os.path.abspath(there), start=start).replace(os.sep, "/")
        out.append((other.name or Path(os.path.abspath(other)).name, href))
    return out


def store_listing(store: str, events: Sequence[str] | None) -> dict[str, Any]:
    """``runs`` on a store, as its JSON gives it, with the failures given counted, for a page
    built from inside the core."""
    ns = argparse.Namespace(
        verb="runs",
        store=store,
        config=None,
        event=list(events) if events else None,
        all=False,
        json=False,
        debug=False,
    )
    ns.typed_flags = set()
    ns.notes = []
    prepare(ns)
    listed = runs(ns)
    assert listed.data is not None
    return listed.data


def report_page(bundle: Path, store: str) -> str:
    """The HTML report of a bundle: the static UI's page for its
    artifact, rendered self-contained."""
    from poisson_trace import pages

    return pages.render(verdict_view(bundle, store).document, store, standalone=True)


def to_html(c: Counted) -> str:
    """``to_html()``: the HTML report of a verdict, saved or not, the text ``report DIR`` writes
    for the bundle its ``to_bundle`` wrote: the artifact built in a folder
    of its own and rendered as the bundle is."""
    import shutil
    import tempfile

    from poisson_trace import saved

    ns = c.ns
    artifact, absolute = _artifact_of(c)
    store = "" if ns.from_folders else Path(saved.short(str(ns.store), absolute)).name
    staging = Path(tempfile.mkdtemp(prefix="poisson-trace-"))
    try:
        saved.build_artifact(staging, artifact)
        return report_page(staging, store)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ---------- the objects only the terminal app needs ----------
# Three core functions, not part of the public API: what the app's screens show that no verb
# prints (the saved verdicts as a list, a run's target or the tool it was imported from, and
# the result files init finds with their import lines). Each reads the paths it is given and
# nothing else, prints nothing and writes nothing.


@dataclass(frozen=True)
class SavedVerdict:
    """One of Trace's saved verdicts in a store: its kind, its id, the runs it is about by name
    and by id, its verdict line, when it was saved (as its descriptor records it), its folder
    under the store and its page under the store's pages."""

    kind: str
    id: str
    runs: tuple[str, ...]
    run_ids: tuple[str, ...]
    verdict: str
    sentence: str
    saved_at: str
    folder: str
    page: str


@dataclass(frozen=True)
class RunSource:
    """Where a run came from: a Prove run's target, or the reader an import came from and the
    files it was read from (their names, no folder); ``target_or_tool`` is the one the listing
    shows."""

    run_id: str
    target: str | None
    tool: str | None
    files: tuple[str, ...]
    target_or_tool: str


@dataclass(frozen=True)
class FoundResult:
    """A result file ``init`` finds under a folder and would offer to import: its path as init
    prints it, the reader that reads it, init's words for it, the import line init prints for
    it, the words in capitals the user must fill in before that line can run, and whether a run
    of a store under the folder was imported from a file with these bytes."""

    path: str
    tool: str
    said: str
    command: str
    fill: tuple[str, ...]
    imported: bool


def _store_runs(store: Any) -> list[dict[str, Any]]:
    """The runs of a store as ``runs`` lists them, in its order; a store that is not one is
    ``runs``'s refusal."""
    from poisson_trace import api

    return list(api.runs(str(store)).runs)


def saved_verdicts(store: Any) -> list[SavedVerdict]:
    """Trace's saved verdicts in a store, newest first (by save time, then kind, then id, as the
    runs page orders them); a store that is not one is ``runs``'s refusal."""
    root = Path(store)
    if not artifact_folders(root):
        _store_runs(store)
        return []
    out = []
    for folder in artifact_folders(root):
        art, result, _report = _saved_verdict(folder)
        kind, ident = str(art.get("kind", folder.parent.name)), str(art.get("id", folder.name))
        if kind == "where":
            held = [result.get("run") or {}]
        else:
            runs = result.get("runs")
            held = list(runs.values()) if isinstance(runs, Mapping) else []
        out.append(
            SavedVerdict(
                kind=kind,
                id=ident,
                runs=tuple(str(r.get("run_name", "")) for r in held),
                run_ids=tuple(str(r.get("run_id", "")) for r in held),
                verdict=str(result.get("verdict", "")),
                sentence=str(result.get("sentence", "")),
                saved_at=str(art.get("created_at", "")),
                folder=f".poisson/artifacts/{kind}/{ident}",
                page=f"{PAGES}/{kind}/{ident}.html",
            )
        )
    out.sort(key=lambda v: (v.saved_at, v.kind, v.id), reverse=True)
    return out


def run_sources(store: Any) -> list[RunSource]:
    """Each run ``runs`` lists, in its order, with where it came from: a Prove run's target, or
    an import's reader and files (from the record the import wrote beside Prove's)."""
    from poisson_trace import names
    from poisson_trace.ingest.writer import read_produced_by

    out = []
    for run in _store_runs(store):
        run_id, backend = str(run["run_id"]), str(run.get("backend") or "")
        if backend.startswith(names.IMPORTED):
            tool = backend[len(names.IMPORTED) :]
            made = read_produced_by(Path(store), run_id)
            files = tuple(str(f.get("name", "")) for f in made.get("from") or ())
            out.append(RunSource(run_id, None, tool, files, tool))
        else:
            target = str(run.get("target_id") or "")
            out.append(RunSource(run_id, target, None, (), target))
    return out


def found_results(folder: Any, *, store: str = "trace-store") -> list[FoundResult]:
    """The result files ``init`` finds under ``folder`` and would offer to import (a JUnit
    report with no test case is left out, as init leaves it out), in the order its search finds
    them, each with the import line init prints for it (``--store STORE``), every file its own
    line past the twelve init shows, and whether a run of a store under the folder
    was imported from a file with these bytes (by the digest the run's record keeps).
    A file init prints no line for is no run of its own and is left out (a LangSmith feedback
    list, which goes on its runs' line; a Weave file that holds no case); a file init prints
    several lines for, one for each evaluation a Weave file holds, is here once for each.
    init's search reads paths relative to the current folder, so the folder is the current one
    while it runs."""
    import contextlib
    import hashlib

    from poisson_trace import setup
    from poisson_trace.ingest.writer import read_produced_by

    root = Path(folder)
    with contextlib.chdir(root):
        found = setup.search(Path("."))
        files = setup._not_empty(found.files)
        commands_of = {
            f.path: lines for f, lines in setup.lines_by_file(files, store, limit=None)
        }
        digests: set[str] = set()
        for held in found.stores:
            for run in held.runs:
                made = read_produced_by(Path(held.path), run.run_id)
                digests.update(
                    str(f["sha256"]) for f in made.get("from") or () if f.get("sha256")
                )
        out = []
        for f in files:
            commands = commands_of.get(f.path, ())
            if not commands:
                continue
            digest = hashlib.sha256(Path(f.path).read_bytes()).hexdigest()
            for command in commands:
                fill = tuple(w for w in command.split() if w.isupper() and w.isalpha())
                out.append(FoundResult(f.path, f.reader, f.said, command, fill, digest in digests))
    return out
