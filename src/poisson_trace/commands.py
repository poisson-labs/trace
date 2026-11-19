"""The verbs that touch the environment rather than a store: ``init``, ``doctor`` and
``report`` (spec section 11.8), and the browser the command line opens a page in. Not public:
``poisson_trace.api`` is the surface; these are what the command line calls for the three
verbs, each taking every option of its parser as a keyword.

``init`` asks its questions on the terminal (stderr) when ``yes`` is False, as the command
does, and ``doctor`` reads the current folder's ``trace.toml`` when no config is named: the
rules the API keeps (nothing printed, nothing read it was not given) are the API's, not these
verbs'. What each prints on stdout comes back on its result; a refusal is an ``api.Refusal``;
Ctrl-C inside ``init`` raises ``look.Interrupted`` carrying the line that says what was kept.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from poisson_trace import api, look


@dataclass(frozen=True)
class InitResult:
    """What ``init`` did: the JSON's fields (None for ``--agent --print``, which prints the
    skill as text) and the text summary."""

    data: dict[str, Any] | None
    exit_code: int
    _text: str = field(repr=False, compare=False)

    def to_json(self) -> str:
        from poisson_trace import report

        if self.data is None:
            raise api.Refusal(
                "--print prints the skill as text and takes no --json",
                next=("poisson-trace init --agent --print",),
                exit_code=look.USAGE,
            )
        return report.json_text(self.data)

    def to_markdown(self) -> str:
        return self._text


@dataclass(frozen=True)
class DoctorResult:
    """What ``doctor`` found: the report, its verdict and sentence, the exit code the command
    gives (0 ready; 4 not ready; with ``setup``, 1 not ready), and, for a setup check that is
    not ready, the refusal the plain command prints in place of the report."""

    report: dict[str, Any]
    verdict: str
    sentence: str
    next: str
    exit_code: int
    refusal: api.Refusal | None
    _text: str = field(repr=False, compare=False)

    def to_json(self) -> str:
        from poisson_trace import report

        return report.json_text(self.report)

    def to_markdown(self) -> str:
        return self._text


# the flags init --agent takes beside --agent; every other flag of init is the guided setup's
_AGENT_FLAGS = frozenset({"--agent", "--repo", "--print", "--force", "--json", "--debug"})


def init(
    *,
    agent: bool = False,
    repo: str | None = None,
    print: bool = False,  # noqa: A002
    store: Sequence[str] | None = None,
    add_store: str | None = None,
    event: Sequence[str] | None = None,
    names: str | None = None,
    import_: bool | None = None,
    metric: str | None = None,
    cut: str | None = None,
    below: bool = False,
    above: bool = False,
    case: str | None = None,
    case_column: str | None = None,
    outcome_column: str | None = None,
    failed: Sequence[str] | None = None,
    max_mde: float | None = None,
    max_mde_hr: float | None = None,
    fail_on: Sequence[str] | None = None,
    force: bool = False,
    config: str | None = None,
    yes: bool = False,
) -> InitResult:
    """``poisson-trace init``: the guided setup, or with ``agent`` the setup written for the
    person's coding agent. Every keyword is the flag of the same name; ``import_`` is
    ``--import`` (True) or ``--no-import`` (False)."""
    given = {
        k: v
        for k, v in locals().items()
        if v is not None and v is not False and v != () and v != []
    }
    ns = argparse.Namespace(
        verb="init",
        agent=agent,
        repo=repo,
        print=print,
        store=None if store is None else list(store),
        add_store=add_store,
        event=None if event is None else list(event),
        names=names,
        import_=import_,
        metric=metric,
        cut=cut,
        below=below,
        above=above,
        case=case,
        case_column=case_column,
        outcome_column=outcome_column,
        failed=None if failed is None else list(failed),
        max_mde=max_mde,
        max_mde_hr=max_mde_hr,
        fail_on=None if fail_on is None else tuple(fail_on),
        force=force,
        config=config,
        yes=yes,
        json=False,
        debug=False,
    )
    ns.typed_flags = {"--" + k.replace("_", "-").rstrip("-") for k in given}
    if import_ is False:
        ns.typed_flags.add("--no-import")
    ns.notes = []
    with api._calling(ns):
        if agent or repo is not None or print:
            return _init_agent(ns)
        from poisson_trace import setup

        refusal = look.prove_refusal("poisson-trace init reads stores")
        if refusal is not None:
            raise look.Refused(refusal, *look.prove_nexts())
        line = [setup.STOPPED]

        def written(said: str) -> None:
            # once anything is on disk, Ctrl-C says what was kept
            line[0] = said

        try:
            done = setup.init(ns, written)
        except KeyboardInterrupt as e:
            raise look.Interrupted(line[0]) from e
    return InitResult(done.data, look.DONE, done.text)


def _init_agent(ns: argparse.Namespace) -> InitResult:
    """``init --agent``: the setup for the person's coding agent, written or printed."""
    from poisson_trace import skills

    if not ns.agent:
        flag = "--repo" if ns.repo is not None else "--print"
        raise look.Usage(f"{flag} goes with --agent", "poisson-trace init --agent --help")
    other = sorted(ns.typed_flags - _AGENT_FLAGS)
    if other:
        raise look.Usage(
            f"--agent writes the setup for your coding agent and takes no {', '.join(other)}",
            "poisson-trace init --agent",
            "poisson-trace init --help",
        )
    if ns.print:
        return InitResult(None, look.DONE, skills.skill_text())
    typed = ["init", "--agent", *([] if ns.repo is None else [look.option("--repo", ns.repo)])]
    written = skills.write_setup(ns.repo, force=ns.force, typed=typed)
    doc = {
        "schema": "poisson-trace.init/1",
        "verdict": "ok",
        "sentence": written.sentence,
        "wrote": list(written.wrote),
        "prompt": skills.PROMPT,
        "next": skills.NEXT,
    }
    lines = [f"ok  {written.sentence}"]
    lines += [f"  wrote  {path}" for path in written.wrote]
    lines.append(f"  prompt  {skills.PROMPT}")
    lines.append(f"  next: {skills.NEXT}")
    return InitResult(doc, look.DONE, "\n".join(lines) + "\n")


def doctor(*, config: str | None = None, setup: bool = False) -> DoctorResult:
    """``poisson-trace doctor``: whether this environment is ready, one line per check; with
    ``setup``, the check a coding agent runs on the ``trace.toml`` it wrote, with the setup
    check's exit codes (0 ready, 1 not ready, 2 a wrong setting)."""
    from poisson_trace import config as configuration
    from poisson_trace import doctor as checks

    if setup:
        try:
            report = checks.setup_check(config)
        except configuration.ConfigError as e:
            raise api.Refusal(str(e), exit_code=look.USAGE) from None
        ready = report["verdict"] == "ok"
        refusal = None
        if not ready:
            nexts = [c["next"] for c in report["checks"] if not c["ok"] and c["next"] is not None]
            refusal = api.Refusal(report["sentence"], next=nexts, exit_code=look.REFUSED)
        code = look.DONE if ready else look.REFUSED
    else:
        report = checks.check(config)
        refusal = None
        code = look.DONE if report["verdict"] == "ok" else look.CHECK_FAILED
    return DoctorResult(
        report=report,
        verdict=report["verdict"],
        sentence=report["sentence"],
        next=report["next"],
        exit_code=code,
        refusal=refusal,
        _text=checks.text(report),
    )


# ---------- report DIR: the HTML report (section 17.3 item 8; section 11.7) ----------


@dataclass(frozen=True)
class ReportResult:
    """What ``report`` did: the bundle's verb, the folder as it was given, and the page, written
    (``wrote``) or, under ``open`` on a page that was there, opened as it was (``opened``)."""

    verb: str
    folder: str
    wrote: str
    next: str
    exit_code: int
    opened: bool = False
    notes: tuple[str, ...] = ()

    @property
    def sentence(self) -> str:
        return (
            f"the {self.verb} verdict in {self.folder} as one page that opens from disk with "
            "nothing else present"
        )

    def to_markdown(self) -> str:
        done = "opened" if self.opened else "wrote"
        return f"ok  {self.sentence}\n  {done}  {self.wrote}\nnext: {self.next}\n"


def report(folder: str, *, open: bool = False, force: bool = False) -> ReportResult:  # noqa: A002
    """``poisson-trace report DIR``: the bundle's verdict rendered as the static UI shows it,
    self-contained, written into the bundle as ``report.html`` and listed in ``handover.json``;
    a page that is there is refused without ``force``; a bundle that fails the validator is
    refused before anything is written, with the validator's words; ``open`` opens the page in
    the default browser.

    ``open`` on a page that is there opens that page as it is and writes nothing, so
    the ``report DIR --open`` that ``handover --check`` prints runs; when the page is not the
    one ``report`` would write now (another version of Trace's, or one edited and re-listed),
    a note says so and names the command that writes it again."""
    from poisson_trace import core

    checked = api.validate_bundle(folder)
    if checked.exit_code != look.DONE:
        raise api.Refusal(checked.sentence)
    target = Path(folder)
    page = target / core.REPORT_PAGE
    name = f"{folder}/{core.REPORT_PAGE}"
    there = page.exists() and not force
    if there and not open:
        raise api.Refusal(f"{name} exists; add --force to replace it")
    notes: tuple[str, ...] = ()
    try:
        bundle = api.load_bundle(folder)
        store = next(
            (r.get("store") for r in bundle.handover.get("runs", ()) if r.get("store")), None
        )
        text = core.report_page(target, Path(str(store)).name if store else "")
        if there:
            if page.read_bytes() != text.encode("utf-8"):
                again = look.command("poisson-trace", "report", folder, "--force")
                notes = (
                    f"{name} is not the page this version of Trace writes for the bundle; "
                    f"{again} writes it again",
                )
        else:
            _write_report_page(target, bundle.handover, text)
    except OSError as e:
        verb = "read" if there else "write"
        raise api.Refusal(f"cannot {verb} {name}: {look.why(e)}") from None
    if open:
        show_page(page.resolve().as_uri())
    return ReportResult(
        verb=bundle.verb,
        folder=folder,
        wrote=name,
        next=look.command("poisson-trace", "handover", "--check", folder),
        exit_code=look.DONE,
        opened=there,
        notes=notes,
    )


def _write_report_page(target: Path, handover: dict[str, Any], text: str) -> None:
    """``report.html`` written into the bundle, then ``handover.json`` rewritten with the page's
    name, digest and size added to ``files`` and every other entry as it was (section 11.7)."""
    from poisson_trace import saved

    page = target / "report.html"
    page.write_text(text, encoding="utf-8")
    entry = {"name": page.name, "sha256": saved.sha256_of(page), "bytes": page.stat().st_size}
    files = [e for e in handover["files"] if e.get("name") != page.name] + [entry]
    handover["files"] = sorted(files, key=lambda e: str(e["name"]))
    (target / "handover.json").write_text(saved.document(handover), encoding="utf-8")


def show_page(address: str) -> None:
    """A page opened in the default browser (``webbrowser``, the standard library), for
    ``ui --open`` and ``report --open``."""
    import webbrowser

    webbrowser.open(address)


# ---------- the terminal app (section 17.2) ----------


def app(*, config: str | None = None, store: str | None = None) -> Any:
    """The terminal app, built and not yet run: ``poisson-trace`` with no verb on a terminal.
    ``config`` and ``store`` are the bare command's ``--config`` and ``--store`` values as typed.
    Textual, the app's framework, is imported here and nowhere a verb reaches; a Textual that
    cannot be imported is one refusal (A16)."""
    try:
        from poisson_trace._app import TraceApp
    except ImportError:
        raise look.Refused(
            "the terminal app cannot start: Textual cannot be imported", "poisson-trace --help"
        ) from None
    return TraceApp(config=config, store=store)


def run_app(built: Any) -> int:
    """The app run until it is left, and its exit code (0 for ``q``, 130 for Ctrl-C). Textual
    draws on stderr; the app belongs on the terminal stdout is (A2), so a piped stderr takes
    stdout's terminal for as long as the app runs."""
    import os
    import sys

    saved = None
    if not look._is_terminal(sys.__stderr__):
        saved = os.dup(2)
        os.dup2(1, 2)
    try:
        built.run()
    finally:
        if saved is not None:
            os.dup2(saved, 2)
            os.close(saved)
    return int(built.return_code or 0)
