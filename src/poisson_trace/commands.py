"""The two verbs that touch the environment rather than a store: ``init`` and ``doctor``
(spec section 11.8). Not public: ``poisson_trace.api`` is the surface; these are what the
command line calls for the two verbs, each taking every option of its parser as a keyword.

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
            raise look.Refused(refusal, look.INSTALL_PROVE)
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
