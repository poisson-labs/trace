"""``poisson-trace doctor``: whether this environment is ready for Trace, and what to run when it
is not.

Six checks, in this order: the Python running Trace, the Trace package and where it was
imported from, Prove, the config file and the stores it names, the names of yours, and the
readers of other tools' files in the install. Each says what it found; a check that fails names
the command that mends it, and the first of those is the command to run next. It fixes nothing,
asks nothing, writes nothing and contacts no host. Ready needs a config: every verb takes its
store and its failures from one.

The report is returned as data; the command line prints it.

``doctor --setup`` (``setup_check``) is the check the setup file a coding agent follows names:
it reads what ``doctor`` reads, as a setup needs it, and each pending ``[[import]]`` file with
its reader, writing nothing; its exit codes are the shared check's (0 ready, 1 not ready, 2 a
config wrong under the config's rules), not ``doctor``'s 4. Plain ``doctor`` is as it was, but
for its next command once every ``[[import]]`` file is imported: the first fix-check on the
first pair of one tool's runs.
"""

from __future__ import annotations

import sys
import sysconfig
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import poisson_trace
from poisson_trace import config, look, names
from poisson_trace.ingest.rows import Refusal

SCHEMA = "poisson-trace.doctor/1"
CHECKS = ("python", "package", "prove", "config", "names", "readers")


def _check(name: str, ok: bool, line: str, following: str | None = None) -> dict[str, Any]:
    return {"name": name, "ok": ok, "line": line, "next": None if ok else following}


def _python() -> dict[str, Any]:
    version = ".".join(str(n) for n in sys.version_info[:3])
    return _check("python", True, f"{sys.executable} ({version})")


def _inside(folder: Path) -> bool:
    """Whether ``folder`` is inside the running interpreter's environment."""
    try:
        here = folder.resolve()
        libs = {Path(sysconfig.get_paths()[k]).resolve() for k in ("purelib", "platlib")}
    except (KeyError, OSError):
        return True
    return any(lib == here or lib in here.parents for lib in libs)


def _package() -> dict[str, Any]:
    folder = Path(poisson_trace.__file__).parent
    line = f"poisson-trace {poisson_trace.__version__} at {folder}"
    if not _inside(folder):
        line += (
            "; note: imported from outside this Python's environment, as an editable install "
            "is, so another Python may import another copy"
        )
    return _check("package", True, line)


def _prove() -> dict[str, Any]:
    found = look.prove_found()
    if look.prove_refusal("Trace reads stores") is None:
        return _check("prove", True, f"poisson-prove {found} (the version Trace reads)")
    if found is None:
        try:
            import poisson_prove  # noqa: F401
        except ImportError:
            line = (
                f"poisson-prove is not installed, and Trace reads stores through it (version "
                f"{look.PROVE_VERSION})"
            )
        else:
            line = f"poisson-prove states no version, and Trace reads version {look.PROVE_VERSION}"
    else:
        line = f"poisson-prove {found} is installed, and Trace reads version {look.PROVE_VERSION}"
    return _check("prove", False, line, look.INSTALL_PROVE)


def _readers() -> dict[str, Any]:
    from poisson_trace.ingest.importing import present

    found = present()
    return _check("readers", True, ", ".join(found) if found else "none in this install")


def _held(path: str) -> list[str]:
    from poisson_prove.store import Store

    try:
        return Store(path).runs()
    except OSError:
        return []


def _counted(index: Any) -> str:
    runs = index.runs
    complete = sum(1 for r in runs if r.complete)
    parts = [
        f"{look.count(len(runs) + len(index.unreadable))} "
        f"{'run' if len(runs) + len(index.unreadable) == 1 else 'runs'}",
        f"{look.count(complete)} complete",
        f"{look.count(len(runs) - complete)} partial",
    ]
    if index.unreadable:
        parts.append(f"{look.count(len(index.unreadable))} whose record Prove cannot read")
    return ", ".join(parts)


def _store_words(name: str | None, path: str) -> str:
    return f"store {path}" if name is None else f"store {name} at {path}"


_IMPORT_HELP = "poisson-trace import --help"


def _config_and_names(given: str | None, prove_ok: bool) -> list[dict[str, Any]]:
    """The config check and the names check, which reads the stores the config names."""
    reach = [look.option("--config", given)] if given is not None else []
    init = look.command("poisson-trace", "init", *reach)
    again = look.command("poisson-trace", "init", "--force", *reach)
    nothing = _check("names", True, "no store to read names of yours from")
    path = config.path_of(given)
    shown = look.shown(given) if given is not None else config.CONFIG
    if not path.exists() and not path.is_symlink():
        if not path.parent.is_dir():
            # no command makes the folder; init would refuse to write there
            said = f"no config file at {shown}, and the folder {path.parent} is not there"
            return [_check("config", False, said, None), nothing]
        said = f"no config file at {shown}" if given is not None else f"no {shown} here"
        return [_check("config", False, said, init), nothing]
    try:
        held = config.load(given)
    except config.ConfigError as e:
        if path.is_dir() or not path.is_file():
            # init does not replace a folder or a pipe: it is the user's to move aside
            line = f"{e}; move it aside, then run {init}"
            return [_check("config", False, line, None), nothing]
        return [_check("config", False, str(e), again), nothing]
    assert held is not None
    events = held.events
    failures = f"failures {', '.join(events)}" if events else "no failures set"
    if not prove_ok:
        stores = "; ".join(_store_words(n, p) for n, p in held.stores()) or "no store"
        line = f"{shown}: {stores}, {failures} (runs not counted without Prove)"
        return [
            _check("config", events is not None and held.store is not None, line, init),
            _names_unchecked(held),
        ]
    from poisson_prove.store import Store

    described: list[str] = []
    indexes: list[tuple[str | None, str, Any]] = []
    for name, store_path in held.stores():
        runs = _held(store_path)
        if not runs:
            line = (
                f"{shown}: the {_store_words(name, store_path)} is not there (no folder under it "
                "holds a run Prove stored)"
            )
            return [_check("config", False, line, again), nothing]
        carried = tuple(reach) if name is None else (look.option("--store", name), *reach)
        try:
            index = names.index(
                Store(store_path),
                runs,
                store_path,
                lenient=True,
                form=held.names_from,
                carried=carried,
            )
        except names.Damaged as e:
            indexes.append((name, store_path, e))
            described.append(f"{_store_words(name, store_path)}")
            continue
        indexes.append((name, store_path, index))
        described.append(f"{_store_words(name, store_path)} ({_counted(index)})")
    if held.store is None and not held.named:
        beside = _store_beside(path, held.names_from)
        if beside is not None:
            line, store = beside
            line = (
                f"{shown} names no store yet, and {line}: run the command below to set Trace "
                "up with it"
            )
            following = look.command(
                "poisson-trace", "init", "--force", look.option("--store", store), *reach
            )
            return [_check("config", False, line, following), _names(indexes)]
        line = (
            f"{shown} names no store yet: make one with a Prove sweep, or import results another "
            "tool wrote (poisson-trace import --help), then set up again"
        )
        return [_check("config", False, line, again), _names(indexes)]
    if held.store is None:
        line = f"{shown} names no store every verb reads ([store] has no path)"
        return [_check("config", False, line, again), _names(indexes)]
    from poisson_trace.setup import SUCCESS_WORDS, newest_outcomes

    notes = []
    for name, store_path, index in indexes[1:]:
        if events and isinstance(index, names.Index):
            other = newest_outcomes(Store(store_path), index, quiet=True)
            if not any(e in other.counts for e in events):
                notes.append(
                    f"store {name} carries none of the failures (give --event with --store {name})"
                )
    said = f"{shown}: {'; '.join(described)}, {failures}" + "".join(f"; {n}" for n in notes)
    first = indexes[0][2]
    if not isinstance(first, names.Index):
        return [_check("config", events is not None, said, init), _names(indexes)]
    read = newest_outcomes(Store(held.store), first, quiet=True)
    if events is None:
        if not read.counts:
            # no answer to the failure question exists: the runs carry no outcome
            line = f"{said}; {read.whose} {read.carry} no outcome, so there is no failure to set"
            return [_check("config", False, line, None), _names(indexes)]
        if all(o in SUCCESS_WORDS for o in read.counts):
            # init has no failure to offer either, so it is not the command that mends this
            successes = sorted(read.counts)
            words = "a word" if len(successes) == 1 else "words"
            line = (
                f"{said}; {read.whose} {read.carry} only {', '.join(successes)}, {words} for "
                "success, so there is no failure to set"
            )
            if any(r.imported for r in first.runs):
                line += (
                    "; if they were imported with values that match no failure, import the "
                    "result files again into a new store with the values that mean a failure, "
                    "then set up with it: poisson-trace init --force --store NEW"
                )
                return [_check("config", False, line, _IMPORT_HELP), _names(indexes)]
            return [_check("config", False, line, None), _names(indexes)]
        return [_check("config", False, said, init), _names(indexes)]
    missing = [e for e in events if e not in read.counts]
    if missing:
        outcomes = ", ".join(sorted(read.counts)) or "none"
        line = (
            f"{said}; {', '.join(missing)} is carried by none of {read.whose}, which "
            f"{read.carry} {outcomes}"
        )
        return [_check("config", False, line, again), _names(indexes)]
    return [_check("config", True, said), _names(indexes)]


# the runs a line names before "and N more"
_RUNS_NAMED = 3


def _store_beside(path: Path, form: str) -> tuple[str, str] | None:
    """The store init's import writes beside the config, when it holds runs: what it holds, by
    what wrote them and the runs' names, and the store as the current folder reads it."""
    from poisson_prove.store import Store

    from poisson_trace.imports import IMPORTED_STORE

    store = config.beside(path, IMPORTED_STORE)
    runs = _held(store)
    if not runs:
        return None
    try:
        index = names.index(Store(store), runs, store, lenient=True, form=form)
    except names.Damaged:
        return None
    held = index.runs
    if not held:
        return None
    tools = sorted({r.backend[len(names.IMPORTED) :] for r in held if r.imported})
    stored = any(not r.imported for r in held)
    imported = f"imported from {' and '.join(tools)}" if tools else ""
    what = (
        imported if not stored else ("Prove stored" if not tools else f"{imported} or Prove stored")
    )
    named = sorted(r.name for r in held)
    shown = ", ".join(named[:_RUNS_NAMED])
    more = len(named) - _RUNS_NAMED
    if more > 0:
        shown += f" and {look.count(more)} more"
    total = len(held) + len(index.unreadable)
    counted = f"{look.count(total)} {'run' if total == 1 else 'runs'}"
    return f"{store} beside it holds {counted} {what} ({shown})", store


def _names_unchecked(held: config.Config) -> dict[str, Any]:
    """Without Prove, the names files are read for what they hold, not against the runs."""
    lines = []
    for _, store_path in held.stores():
        shown = names.shown_file(store_path)
        try:
            entries, _ = names.read_names_file(Path(store_path), shown)
        except names.Damaged as e:
            return _check("names", False, str(e), None)
        if entries:
            lines.append(f"{shown}: {_count_names(len(entries))}")
    said = "; ".join(lines) or "no names of yours"
    return _check("names", True, f"{said} (not checked against the runs without Prove)")


def _count_names(n: int) -> str:
    return f"{look.count(n)} {'name' if n == 1 else 'names'}"


def _names(indexes: Sequence[tuple[str | None, str, Any]]) -> dict[str, Any]:
    lines = []
    for _, _, index in indexes:
        if isinstance(index, names.Damaged):
            return _check("names", False, str(index), index.nexts[0] if index.nexts else None)
        damage = index.damage()
        if damage is not None:
            return _check("names", False, str(damage), damage.nexts[0] if damage.nexts else None)
        if index.entries:
            lines.append(
                f"{index.names_shown()}: {_count_names(len(index.entries))}; every name resolves "
                "to one run"
            )
    if not indexes:
        return _check("names", True, "no store to read names of yours from")
    if not lines:
        return _check("names", True, f"{indexes[0][1]}: no names of yours yet")
    return _check("names", True, "; ".join(lines))


def check(given: str | None) -> dict[str, Any]:
    """The report: the six checks in order, the verdict and the command to run next."""
    prove = _prove()
    checks = [_python(), _package(), prove, *_config_and_names(given, prove["ok"]), _readers()]
    failing = [c for c in checks if not c["ok"]]
    if not failing:
        reach = [look.option("--config", given)] if given is not None else []
        verdict, sentence = "ok", "this environment is ready"
        following = _after(_loaded(given), reach)
    else:
        verdict = "not ready"
        which = " and ".join(c["name"] for c in failing)
        sentence = f"{which} {'fails' if len(failing) == 1 else 'fail'}: {failing[0]['line']}"
        following = next(
            (c["next"] for c in failing if c["next"] is not None), "poisson-trace doctor"
        )
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "sentence": sentence,
        "checks": checks,
        "next": following,
    }


def _loaded(given: str | None) -> config.Config | None:
    try:
        return config.load(given)
    except config.ConfigError:
        return None


def _after(held: config.Config | None, reach: Sequence[str]) -> str:
    """The command to run next when ready: ``runs``, or, once every ``[[import]]`` file is
    imported and a tool has two or more, the first fix-check on its first two runs."""
    from poisson_trace import imports

    if held is not None:
        pair = imports.first_pair(held)
        if pair is not None:
            store = imports.imports_store(held)
            flags = [look.option("--store", store.name)] if store.name is not None else []
            return look.command(
                "poisson-trace",
                "fix-check",
                look.word(pair[0].name),
                look.word(pair[1].name),
                *flags,
                *reach,
            )
    return look.command("poisson-trace", "runs", *reach)


# ---------- doctor --setup ----------

READY = "is ready for the person to review"
SETUP = "poisson-trace doctor --setup"


def setup_check(given: str | None) -> dict[str, Any]:
    """The report of ``doctor --setup``: ``doctor``'s six checks read as a setup needs them,
    then one ``import`` check for each pending ``[[import]]`` entry, read with its reader. A
    config wrong under the config's rules raises ``ConfigError``. Nothing is written and no
    host is contacted."""
    prove = _prove()
    reach = [look.option("--config", given)] if given is not None else []
    init = look.command("poisson-trace", "init", *reach)
    path = config.path_of(given)
    shown = look.shown(given) if given is not None else config.CONFIG
    checks = [_python(), _package(), prove]
    import_checks: list[dict[str, Any]] = []
    held: config.Config | None = None
    pending = False
    if not path.exists() and not path.is_symlink():
        said = f"no config file at {shown}" if given is not None else f"no {shown} here"
        checks += [_check("config", False, said, init), _check("names", True, _NO_STORE)]
    else:
        held = config.load(given)
        assert held is not None
        if not prove["ok"]:
            checks += _config_and_names(given, False)
            import_checks = [
                _check(
                    "import",
                    False,
                    f"{e.file}: not read, since poisson-prove is not at the version Trace reads",
                    look.INSTALL_PROVE,
                )
                for e in held.imports
            ]
        else:
            config_checks, import_checks, pending = _setup_config(held, shown, reach)
            checks += config_checks
    checks.append(_readers())
    checks += import_checks
    failing = [c for c in checks if not c["ok"]]
    if failing:
        verdict = "not ready"
        sentence = str(failing[0]["line"])
        following = next((c["next"] for c in failing if c["next"] is not None), SETUP)
    else:
        verdict, sentence = "ok", f"{shown} {READY}"
        following = init if pending else look.command("poisson-trace", "runs", *reach)
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "sentence": sentence,
        "checks": checks,
        "next": following,
    }


_NO_STORE = "no store to read names of yours from"


def _setup_config(
    held: config.Config, shown: str, reach: Sequence[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """The config and names checks as a setup needs them, the import checks, and whether an
    entry is pending. A config with no store is ready when it has pending entries that read;
    the imports' store may hold no run yet; the failures are checked against the stores' runs
    and the pending files' rows together."""
    from poisson_prove.store import Store

    from poisson_trace import imports
    from poisson_trace.setup import newest_outcomes

    init = look.command("poisson-trace", "init", *reach)
    again = look.command("poisson-trace", "init", "--force", *reach)
    nothing = _check("names", True, _NO_STORE)
    store = imports.imports_store(held)
    pending = imports.pending(held, store.path)
    import_checks: list[dict[str, Any]] = []
    carried: Counter[str] = Counter()
    every_read = True
    for entry in pending:
        if imports.is_address(entry):
            # no host is contacted by a check: an address is left for init to pull
            keyed, line = imports.address_check(entry)
            every_read = every_read and keyed
            import_checks.append(_check("import", keyed, line, None if keyed else init))
            continue
        try:
            run = imports.read(held, entry)
        except Refusal as e:
            every_read = False
            help_ = look.command("poisson-trace", "import", entry.tool, "--help")
            import_checks.append(_check("import", False, str(e), e.nexts[0] if e.nexts else help_))
            continue
        carried.update(row.outcome for row in run.rows if row.outcome is not None)
        import_checks.append(_check("import", True, imports.said(entry, run)))
    described: list[str] = []
    indexes: list[tuple[str | None, str, Any]] = []
    for name, store_path in held.stores():
        runs = _held(store_path)
        if not runs:
            if store.may_be_empty and imports.same_folder(store_path, store.path):
                described.append(f"{_store_words(name, store_path)} (no run yet)")
                continue
            line = (
                f"{shown}: the {_store_words(name, store_path)} is not there (no folder under it "
                "holds a run Prove stored)"
            )
            return [_check("config", False, line, again), nothing], import_checks, bool(pending)
        try:
            index = names.index(
                Store(store_path), runs, store_path, lenient=True, form=held.names_from
            )
        except names.Damaged as e:
            indexes.append((name, store_path, e))
            described.append(_store_words(name, store_path))
            continue
        indexes.append((name, store_path, index))
        described.append(f"{_store_words(name, store_path)} ({_counted(index)})")
    events = held.events
    failures = f"failures {', '.join(events)}" if events else "no failures set"
    if held.store is None and not held.named:
        if not held.imports:
            line = (
                f"{shown} names no store and no file to import: name the store Prove wrote under "
                "[store], or the files another tool wrote under [[import]]"
            )
            return [_check("config", False, line, init), nothing], import_checks, False
        if not pending:
            line = (
                f"{shown} names no store every verb reads, and its [[import]] files are imported "
                f"already into {store.path}: set up with that store"
            )
            following = look.command(
                "poisson-trace", "init", "--force", look.option("--store", store.path), *reach
            )
            return [_check("config", False, line, following), nothing], import_checks, False
    said = f"{shown}: {'; '.join(described) or 'no store yet'}, {failures}"
    if events is None:
        line = (
            f"{said}; [events] failed names the outcomes that count as a failure, and none is set"
        )
        return [_check("config", False, line, init), _names(indexes)], import_checks, bool(pending)
    for _, store_path, index in indexes:
        if isinstance(index, names.Index):
            carried.update(newest_outcomes(Store(store_path), index, quiet=True).counts)
    if every_read:
        missing = [e for e in events if e not in carried]
        if missing:
            whose = _whose(bool(indexes), bool(pending))
            outcomes = ", ".join(sorted(carried)) or "none"
            line = f"{said}; {', '.join(missing)} is carried by {whose}, which carry {outcomes}"
            return [_check("config", False, line, again), _names(indexes)], import_checks, True
    return [_check("config", True, said), _names(indexes)], import_checks, bool(pending)


def _whose(stores: bool, pending: bool) -> str:
    if stores and pending:
        return "no run of the stores and no row of the files to import"
    if stores:
        return "no run of the stores"
    return "no row of the files to import"


def text(report: dict[str, Any]) -> str:
    """The report as text: the verdict line, one line for each check, then the next command."""
    lines = [f"{report['verdict']}  {report['sentence']}"]
    width = max(len(name) for name in CHECKS) + 1
    for item in report["checks"]:
        line = f"  {item['name'].ljust(width)}  {item['line']}"
        if item["next"] is not None:
            line += f"; run {item['next']}"
        lines.append(line)
    lines.append(f"next: {report['next']}")
    return "\n".join(lines) + "\n"
