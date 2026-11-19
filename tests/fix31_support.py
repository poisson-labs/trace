"""Shared helpers for the FIX31 tests: ``fix-check`` on runs that hold no failed run.

Not a test module and not collected.

Three things live here.

- **The stores.** Synthetic pairs written through Prove (``fixcheck_support.pair_store``), a
  pair of JUnit folders in which every case passed, and the committed fixture of Break's case
  (``tests/fixtures/fix31/break-case.json``: a control arm and two candidate arms, 6 cases by 5
  repeats, shaped as a run of Break's confirm stage). The fixture is the description
  of the arms; :func:`break_case` writes it into a store through Prove's own ``Store`` each
  time, so the suite holds no Prove-written file of its own for it (PF-14 lists every one that
  is committed, in a frozen file).
- **The corpus of every other fix-check output** (:func:`corpus`): each invocation's exit code
  and the digests of its two streams are pinned in ``tests/fixtures/fix31/main-pins.json`` as
  main printed them at :data:`MAIN`, before any change (``make_main_pins.py`` beside it).
- **The independent computations** the zero-failure numbers are checked against: the exact
  test by full enumeration in fractions (``fixcheck_support.exact_p_enumerated``) and by
  scipy's Fisher test on one input; the Mantel-Haenszel difference in fractions; the stratified
  Miettinen-Nurminen range from a score written here on its own, with each input's constrained
  rates found by scipy's bounded maximiser of the likelihood and never by the package's closed
  form; the range's closed form at zero failures; the exact chance of a clean run; the limits
  from fix-check's power formula written here on its own; and the exact test's power by full
  enumeration.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from conftest import FIXTURES
from fixcheck_support import Obs, arm_rows, build_run, pair_store
from tf0_support import Ran, chdir, trace

# the commit of main the pins were taken at
MAIN = "a4bc065"
FIX31 = FIXTURES / "fix31"
PINS = FIX31 / "main-pins.json"
BREAK_CASE = FIX31 / "break-case.json"
# Break's arms, as its confirm stage names them, and what it asks (confirm._command)
CONTROL, CANDIDATE_1, CANDIDATE_2 = "confirm-control", "confirm-1", "confirm-2"
BREAK_CASES, BREAK_REPEATS = 6, 5
BREAK_FAILED_1 = 28  # candidate 1 fails 28 of its 30 runs, as in the issue's run

Table = Sequence[tuple[int, int, int, int]]

T_OLD = "2026-01-01T00:00:00.000000Z"
T_NEW = "2026-01-01T01:00:00.000000Z"


# ---------- stores ----------


def clean(inputs: int, old: int, new: int | None = None) -> list[tuple[int, int, int, int]]:
    """A table in which neither version failed: ``inputs`` inputs, ``old`` and ``new`` tries."""
    return [(0, old, 0, old if new is None else new)] * inputs


def stray_store(root: Path, tab: Table) -> Path:
    """``tab``, and one more input that only the old run holds, on which it failed: the old run
    carries the event and the inputs compared hold no failure."""
    build_run(root, "old", [*arm_rows(tab, "old"), Obs("stray", "fail")], created_at=T_OLD)
    build_run(root, "new", arm_rows(tab, "new"), created_at=T_NEW)
    return root


def selecting_store(root: Path, tab: Table) -> Path:
    """A selecting run ``sel`` in which every input of ``tab`` failed once, beside ``old`` and
    ``new`` built from ``tab``."""
    pair_store(root, tab)
    build_run(root, "sel", [Obs(f"i{k}", "fail") for k in range(len(tab))],
              created_at="2025-12-31T00:00:00.000000Z")
    return root


def no_outcome_store(root: Path, inputs: int = 4) -> Path:
    """Two runs in which no try has an outcome: every row is an error."""
    for run, at in (("old", T_OLD), ("new", T_NEW)):
        build_run(root, run, [Obs(f"i{k}", None, "boom") for k in range(inputs)], created_at=at)
    return root


def other_outcome_store(root: Path) -> Path:
    """Neither run carries ``fail``; both carry ``crashed``, which is no word for success."""
    for run, at in (("old", T_OLD), ("new", T_NEW)):
        rows = [Obs(f"i{k}", "crashed" if k == 0 else "ok", replicate_index=j)
                for k in range(4) for j in range(3)]
        build_run(root, run, rows, created_at=at)
    return root


def junit_clean(folder: Path, cases: int = 12, started: str = "2026-11-01T10:00:00") -> Path:
    """A JUnit report of ``cases`` cases, every one passed, in a folder of its own."""
    folder.mkdir(parents=True, exist_ok=True)
    suites = ET.Element("testsuites")
    suite = ET.SubElement(suites, "testsuite", {
        "name": "clean", "tests": str(cases), "failures": "0", "errors": "0", "skipped": "0",
        "timestamp": started, "time": "1.0",
    })
    for k in range(cases):
        ET.SubElement(suite, "testcase", {"classname": "clean.Suite", "name": f"case_{k:02d}", "time": "0.1"})
    (folder / "report.xml").write_bytes(ET.tostring(suites, encoding="utf-8", xml_declaration=True))
    return folder


def break_case(tmp: Path) -> Path:
    """The committed fixture written into a store of the test's own, through Prove: each arm a
    run of ``cases`` by ``repeats`` rows, every row with an outcome (``ok`` or ``failed``, as
    Break writes it) and none with a trace; an arm's first ``failed`` rows fail, case by case."""
    from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash

    held = json.loads(BREAK_CASE.read_text(encoding="utf-8"))
    cases, repeats = int(held["cases"]), int(held["repeats"])
    assert (cases, repeats) == (BREAK_CASES, BREAK_REPEATS)
    dest = tmp / "break-case"
    store = Store(dest)
    for arm in held["arms"]:
        run = arm["run"]
        store.create_run(RunManifest(
            run_id=run, target_id=held["target"], t_unit="steps", run_salt="fix31", axis_types={},
            backend="local", environment={"sweep": {"replicates": repeats}}, created_at=arm["started"],
        ))
        records = []
        for k in range(cases):
            config = {"case": f"case-{k + 1}"}
            for j in range(repeats):
                failed = k * repeats + j < int(arm["failed"])
                records.append(EpisodeRecord(
                    run_id=run, config_hash=config_hash(config), config=config, seed=1000 * k + j,
                    replicate_index=j, outcome="failed" if failed else "ok", t=1.0, horizon=10.0,
                    confidence=None, meta={}, error=None, wall_time=1.0, backend_meta={},
                ))
        store.append(run, records)
        store.mark_complete(run)
    return dest


def break_argv(old: str, new: str, store: Path | str, max_difference: float = 0.2) -> list[str]:
    """The words Break's confirm module hands Trace (``poisson_break.confirm._command``)."""
    return ["fix-check", old, new, "--inputs", "all", "--event", "failed",
            "--max-mde", repr(float(max_difference)), "--store", str(store), "--json"]


def asked(store: Path | str, *extra: str, event: str = "fail", ceiling: str = "0.2") -> Ran:
    return trace(["fix-check", "old", "new", "--store", str(store), "--event", event,
                  "--inputs", "all", "--max-mde", ceiling, *extra])


# ---------- the corpus of every other fix-check output ----------


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normal(text: str, *roots: Path) -> str:
    from pin_support import as_pinned

    for root in roots:
        for shown in {str(root), str(root.resolve())}:
            text = text.replace(shown, "<ROOT>")
    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned)
    return as_pinned(text)


# Synthetic pairs: the table, the event's name is ``fail``. None of them is a pair in which the
# inputs compared hold no failure in either run.
MANY = [(2, 6, 1, 6), (3, 6, 3, 6), (1, 6, 2, 6), (4, 6, 3, 6), (2, 6, 2, 6), (0, 6, 1, 6),
        (5, 6, 4, 6), (3, 6, 2, 6), (1, 6, 1, 6), (2, 6, 3, 6), (4, 6, 4, 6), (3, 6, 1, 6)]
TABLES: dict[str, list[tuple[int, int, int, int]]] = {
    "worked": [(3, 4, 1, 4), (4, 4, 4, 4), (2, 4, 0, 4), (0, 4, 1, 4), (4, 4, 2, 4)],
    "old none, new some": [(0, 5, 0, 5)] * 5 + [(0, 5, 3, 5)],
    "new none, old some": [(0, 5, 0, 5)] * 5 + [(3, 5, 0, 5)],
    "old none, new every try": [(0, 4, 4, 4)] * 3,
    "new none, old every try": [(4, 4, 0, 4)] * 3,
    "old none, new on several inputs": [(0, 6, 2, 6), (0, 6, 1, 6), (0, 6, 0, 6), (0, 6, 3, 6)] * 3,
    "new none, old on several inputs": [(2, 6, 0, 6), (1, 6, 0, 6), (0, 6, 0, 6), (3, 6, 0, 6)] * 3,
    "one input, one try, old failed": [(1, 1, 0, 1)],
    "one input, one try, new failed": [(0, 1, 1, 1)],
    "every try failed in both": [(5, 5, 5, 5)] * 6,
    "twelve inputs that vary": MANY,
    "twelve inputs, twice the tries": [(2 * a, 2 * b, 2 * c, 2 * d) for a, b, c, d in MANY],
    "a clear drop": [(5, 6, 0, 6)] * 4 + [(4, 6, 1, 6)] * 4 + [(6, 6, 2, 6)] * 4,
    "a clear rise": [(0, 6, 5, 6)] * 4 + [(1, 6, 4, 6)] * 4 + [(2, 6, 6, 6)] * 4,
    "one try per input": [(1, 1, 0, 1)] * 8 + [(0, 1, 0, 1)] * 8 + [(0, 1, 1, 1)] * 3,
    "unequal tries": [(1, 3, 2, 7), (0, 9, 1, 2), (2, 4, 2, 4), (3, 5, 0, 8), (0, 2, 0, 6)],
    "old none on unequal tries": [(0, 3, 2, 7), (0, 9, 1, 2), (0, 4, 0, 4)],
}
# each table is asked at these, in plain and in --json
ASKS: tuple[tuple[str, ...], ...] = (
    ("--max-mde", "0.2"),
    ("--max-mde", "0.5", "--alpha", "0.1", "--top", "2", "--seed", "7"),
)


def tr70_store(root: Path) -> Path:
    """The store of ``test_fix_check_cli.tr70_store``: a selecting run, an old arm and a new
    arm with inputs left out for each of the four reasons."""
    from test_fix_check_cli import tr70_store as build

    built: Path = build(root)
    return built


def synthetic(tmp: Path) -> Iterator[tuple[str, list[str]]]:
    """Every synthetic invocation, the stores built under ``tmp``; run from inside ``tmp``."""
    for k, (label, tab) in enumerate(TABLES.items()):
        pair_store(tmp / f"t{k}", tab)
        for ask in ASKS:
            for shape in ((), ("--json",)):
                words = " ".join((*ask, *shape))
                yield (f"{label}: {words}",
                       ["fix-check", "old", "new", "--store", f"t{k}", "--event", "fail",
                        "--inputs", "all", *ask, *shape])
    pair_store(tmp / "named", TABLES["worked"])
    # a name only one run carries beside one both carry, and a name neither carries beside it
    for label, events in (("two events, one carried by neither run", ["fail", "crashed"]),
                          ("an event neither run carries, the runs holding failures", ["faild"])):
        yield (label, ["fix-check", "old", "new", "--store", "named",
                       *[w for e in events for w in ("--event", e)], "--inputs", "all", "--max-mde", "0.2"])
    tr70_store(tmp / "tr70")
    for shape in ((), ("--json",)):
        yield (f"failing-from {' '.join(shape)}".strip(),
               ["fix-check", "old", "new", "--store", "tr70", "--event", "fail",
                "--failing-from", "sel", "--max-mde", "0.5", *shape])
        yield (f"failing-from, at least twice {' '.join(shape)}".strip(),
               ["fix-check", "old", "new", "--store", "tr70", "--event", "fail",
                "--failing-from", "sel", "--min-failures", "2", "--max-mde", "0.5", *shape])
        yield (f"every input of the tr70 store {' '.join(shape)}".strip(),
               ["fix-check", "old", "new", "--store", "tr70", "--event", "fail",
                "--inputs", "all", "--max-mde", "0.5", *shape])
    # the verbs beside fix-check on a pair that never failed: they are not changed
    pair_store(tmp / "clean", clean(6, 5))
    yield ("changes on a pair that never failed",
           ["changes", "old", "new", "--store", "clean", "--event", "fail"])
    yield ("where on a run that never failed",
           ["where", "old", "--store", "clean", "--event", "fail"])
    yield ("runs on a store that never failed",
           ["runs", "--store", "clean", "--event", "fail"])
    other_outcome_store(tmp / "other")
    yield ("an event neither run carries, the runs holding another failure",
           ["fix-check", "old", "new", "--store", "other", "--event", "fail",
            "--inputs", "all", "--max-mde", "0.2"])


def workspace_argv() -> dict[str, list[str]]:
    """Every fix-check invocation of TF13's corpus, in plain and in ``--json``, and each of its
    fix-check refusals; run from inside ``tf13_support.workspace``."""
    from tf13_support import REFUSALS_ARGV, VERBS_ARGV

    out: dict[str, list[str]] = {}
    for label, argv in VERBS_ARGV.items():
        if argv[0] == "fix-check":
            out[f"workspace {label}"] = list(argv)
            out[f"workspace {label} --json"] = [*argv, "--json"]
    for label, (argv, _) in REFUSALS_ARGV.items():
        if argv[0] == "fix-check":
            out[f"workspace refusal: {label}"] = list(argv)
    return out


def fixture_argv() -> dict[str, list[str]]:
    """fix-check on the committed stores, by their paths under the repository."""
    from tf0_support import fix_check_he, fix_check_tau2, fix_check_tau2_all

    out: dict[str, list[str]] = {}
    for label, argv in (("tau2 failing-from", fix_check_tau2()),
                        ("tau2 every input", fix_check_tau2_all("0.20")),
                        ("tau2 every input at 0.05", fix_check_tau2_all("0.05")),
                        ("humaneval", fix_check_he())):
        out[f"fixture {label}"] = argv
        out[f"fixture {label} --json"] = [*argv, "--json"]
    return out


def folder_argv(tmp: Path) -> dict[str, list[str]]:
    """fix-check on two JUnit folders built from the committed HumanEval reports."""
    from tf22_support import JUNIT, copy_into, junit_shards

    junit_shards(tmp / "junit-old")
    copy_into(tmp / "junit-new", JUNIT / "humaneval-b.xml")
    base = ["fix-check", "junit-old", "junit-new", "--event", "missed", "--inputs", "all", "--max-mde", "0.2"]
    return {"folders": [*base, "--plain"], "folders --json": [*base, "--json"]}


def run_corpus(tmp: Path) -> dict[str, list[Any]]:
    """Every invocation of the corpus run: ``label -> [exit code, digest of stdout, digest of
    stderr]``, with the folders the test made written ``<ROOT>``."""
    from tf0_support import REPO
    from tf13_support import cli, workspace

    got: dict[str, list[Any]] = {}

    def pin(label: str, ran: Ran, *roots: Path) -> None:
        assert label not in got, label
        got[label] = [ran.code, digest(normal(ran.out, *roots)), digest(normal(ran.err, *roots))]

    synth = tmp / "synthetic"
    synth.mkdir()
    for label, argv in list(synthetic(synth)):
        pin(label, cli(synth, argv), synth)
    work = workspace(tmp)
    for label, argv in workspace_argv().items():
        pin(label, cli(work, argv), work)
    for label, argv in fixture_argv().items():
        with chdir(REPO):
            ran = trace(argv)
        # the Prove label kinds rule names, on tau2 and HumanEval, the labels that have no kind (test_pl_unchanged.py,
        # PL-52, holds that); this goes on holding every other byte of them
        from pl_pins import unmoved_text

        pin(label, Ran(ran.code, unmoved_text(ran.out), ran.err), REPO)
    folders = tmp / "folders"
    folders.mkdir()
    for label, argv in folder_argv(folders).items():
        pin(label, cli(folders, argv), folders)
    return got


# ---------- the independent computations ----------


def exact_p(tab: Table) -> float:
    """The exact test's two-sided p: the distribution of the new version's failures given each
    input's total, built input by input in exact fractions (the sum of hypergeometrics), then
    Fisher's convention. The same number as ``fixcheck_support.exact_p_enumerated``, which
    lists every table, and fast enough to be asked thousands of times."""
    dist: dict[int, Fraction] = {0: Fraction(1)}
    for xa, na, xb, nb in tab:
        t, big = xa + xb, na + nb
        step = {k: Fraction(math.comb(t, k) * math.comb(big - t, nb - k), math.comb(big, nb))
                for k in range(max(0, t - na), min(t, nb) + 1)}
        merged: dict[int, Fraction] = {}
        for s, q in dist.items():
            for k, r in step.items():
                merged[s + k] = merged.get(s + k, Fraction(0)) + q * r
        dist = merged
    at = dist[sum(xb for _, _, xb, _ in tab)]
    return float(sum(q for q in dist.values() if q <= at * Fraction(10_000_001, 10_000_000)))


def difference(tab: Table) -> Fraction:
    """The Mantel-Haenszel difference of failure shares, new minus old, in fractions."""
    weight = sum(Fraction(na * nb, na + nb) for _, na, _, nb in tab)
    moved = sum(Fraction(xb * na - xa * nb, na + nb) for xa, na, xb, nb in tab)
    return Fraction(moved) / weight


def _constrained(x_new: int, n_new: int, x_old: int, n_old: int, delta: float) -> tuple[float, float]:
    """One input's two failure rates at their most likely under ``new - old = delta``, by
    scipy's bounded maximiser of the binomial likelihood."""
    from scipy import optimize

    low, high = max(0.0, -delta), min(1.0, 1.0 - delta)

    def minus_log_likelihood(p_old: float) -> float:
        p_new = p_old + delta
        total = 0.0
        for x, n, p in ((x_old, n_old, p_old), (x_new, n_new, p_new)):
            if x:
                total -= x * math.log(max(p, 1e-300))
            if n - x:
                total -= (n - x) * math.log(max(1.0 - p, 1e-300))
        return total

    if high - low < 1e-15:
        return low + delta, low
    found = optimize.minimize_scalar(minus_log_likelihood, bounds=(low, high), method="bounded",
                                     options={"xatol": 1e-13})
    # the likelihood is unimodal on the interval; an end can beat the bounded search's answer
    p_old = min((low, high, float(found.x)), key=minus_log_likelihood)
    return p_old + delta, p_old


def score_range(tab: Table, alpha: float = 0.05) -> tuple[float, float]:
    """The stratified Miettinen-Nurminen score interval with Mantel-Haenszel weights for new
    minus old: every ``delta`` whose score lies within the normal quantile. Written from the
    paper's definition, the constrained rates found numerically."""
    from scipy import optimize, stats

    z = float(stats.norm.isf(alpha / 2.0))
    weights = [na * nb / (na + nb) for _, na, _, nb in tab]
    each = [xb / nb - xa / na for xa, na, xb, nb in tab]
    estimate = sum(w * d for w, d in zip(weights, each, strict=True)) / sum(weights)

    def score(delta: float) -> float:
        num = sum(w * (d - delta) for w, d in zip(weights, each, strict=True))
        var = 0.0
        for w, (xa, na, xb, nb) in zip(weights, tab, strict=True):
            p_new, p_old = _constrained(xb, nb, xa, na, delta)
            total = na + nb
            var += w * w * (p_new * (1.0 - p_new) / nb + p_old * (1.0 - p_old) / na) * total / (total - 1.0)
        if var > 0.0:
            return num / math.sqrt(var)
        return math.copysign(math.inf, num) if num else 0.0

    edge = 1e-9
    lo = -1.0 if score(-1.0 + edge) <= z else float(
        optimize.brentq(lambda d: score(d) - z, -1.0 + edge, estimate, xtol=1e-13))
    hi = 1.0 if score(1.0 - edge) >= -z else float(
        optimize.brentq(lambda d: score(d) + z, estimate, 1.0 - edge, xtol=1e-13))
    return lo, hi


def clean_range(design: Sequence[tuple[int, int]], alpha: float = 0.05) -> tuple[float, float]:
    """The same interval where neither version failed, in closed form. With no failure the
    constrained rates at a rise ``delta`` are ``delta`` for the new version and 0 for the old,
    so the score is ``-W delta / sqrt(delta (1 - delta) S_new)`` and the high end solves
    ``delta / (1 - delta) = z^2 S_new / W^2``; the low end is its mirror with the old version's
    tries. ``design`` is each input's ``(old tries, new tries)``."""
    from scipy import stats

    z = float(stats.norm.isf(alpha / 2.0))
    weight = sum(a * b / (a + b) for a, b in design)

    def end(tries: Sequence[int]) -> float:
        spread = sum((a * b / (a + b)) ** 2 * (a + b) / (n * (a + b - 1))
                     for (a, b), n in zip(design, tries, strict=True))
        c = z * z * spread / weight**2
        return c / (1.0 + c)

    return -end([a for a, _ in design]), end([b for _, b in design])


def clean_chance(tries: int, share: float) -> float:
    """The chance that ``tries`` independent tries, each failing ``share`` of the time, hold no
    failure: scipy's binomial at zero."""
    from scipy import stats

    return float(stats.binom.pmf(0, tries, share))


def _power(tab: Table, r: float, direction: str, alpha: float, runs: tuple[int, int] | None = None,
           scale: float = 1.0) -> tuple[float, float]:
    """fix-check's power, written out input by input: ``(power, shift in share)``."""
    from scipy import stats

    delta = v_ref = v_one = weight = 0.0
    for xa, na, xb, nb in tab:
        total_seen, failed = na + nb, xa + xb
        p = failed / total_seen
        s = failed * (total_seen - failed) / (total_seen * (total_seen - 1))
        m = failed * (failed - 1) / (total_seen * (total_seen - 1))
        n_a, n_b = (na, nb) if runs is None else runs
        total = n_a + n_b
        w = n_a * n_b / total
        if direction == "drop":
            mean_b, second_b, cross = (1 - r) * p, (1 - r) ** 2 * m, (1 - r) * m
            shift = w * (p - mean_b)
        else:
            q, q2 = 1 - p, 1 - 2 * p + m
            mean_b = 1 - (1 - r) * q
            second_b = 1 - 2 * (1 - r) * q + (1 - r) ** 2 * q2
            cross = p - (1 - r) * (p - m)
            shift = w * (mean_b - p)
        s_b = mean_b - second_b
        together = (n_a * p + n_b * mean_b) / total
        together_sq = (n_a * n_a * m + n_b * n_b * second_b + 2 * n_a * n_b * cross) / total**2
        v_ref += w * max(total * total * (together - together_sq) - n_a * s - n_b * s_b, 0.0) / (total * (total - 1))
        v_one += w * w * (s / n_a + s_b / n_b)
        delta += shift
        weight += w
    delta, v_ref, v_one, weight = (x * scale for x in (delta, v_ref, v_one, weight))
    edge = float(stats.norm.isf(alpha / 2.0)) * math.sqrt(v_ref)
    if v_one <= 0.0:
        return (1.0 if delta - 0.5 > edge else 0.0), delta / weight
    return float(stats.norm.sf((edge + 0.5 - delta) / math.sqrt(v_one))), delta / weight


def limit(tab: Table, direction: str, alpha: float = 0.05, power: float = 0.8) -> float | None:
    """fix-check's detection limit: the shift at the smallest proportional change that
    reaches ``power``, by scipy's root finder; ``None`` when the whole change falls short."""
    from scipy import optimize

    if _power(tab, 1.0, direction, alpha)[0] < power:
        return None
    r = float(optimize.brentq(lambda x: _power(tab, x, direction, alpha)[0] - power, 1e-12, 1.0, xtol=1e-14))
    return _power(tab, r, direction, alpha)[1]


def exact_power_of_a_rise(design: Sequence[tuple[int, int]], share: float, alpha: float = 0.05) -> float:
    """The chance the exact test calls a difference, the new version failing more, when the old
    version never fails and every try of the new fails ``share`` of the time: every count of
    new failures on every input enumerated, each table put to the enumerated exact test."""
    from scipy import stats

    per_input = [[(x, float(stats.binom.pmf(x, nb, share))) for x in range(nb + 1)] for _, nb in design]
    called: dict[tuple[tuple[int, int, int], ...], bool] = {}
    power = 0.0
    for combo in itertools.product(*per_input):
        tab = [(0, na, x, nb) for (na, nb), (x, _) in zip(design, combo, strict=True)]
        # the test reads the counts and not the inputs' order
        key = tuple(sorted((na, nb, x) for (_, na, x, nb) in tab))
        if key not in called:
            called[key] = any(x for _, _, x, _ in tab) and exact_p(tab) < alpha
        if called[key]:
            power += math.prod(q for _, q in combo)
    return power


def fisher_p(tab: Table) -> float:
    """scipy's Fisher test on the one table of all the tries, for a one-input pair."""
    from scipy import stats

    xa, na, xb, nb = (sum(row[i] for row in tab) for i in range(4))
    return float(stats.fisher_exact([[xa, na - xa], [xb, nb - xb]], alternative="two-sided")[1])


def clean_repeats_needed(inputs: int, ceiling: float, alpha: float = 0.05) -> int:
    """The smallest number of tries of each version on each of ``inputs`` inputs at which, with
    no failure, the range lies inside plus or minus ``ceiling``: counted up from one."""
    n = 1
    while max(-(r := clean_range([(n, n)] * inputs, alpha))[0], r[1]) > ceiling:
        n += 1
    return n


def clean_inputs_needed(design: Sequence[tuple[int, int]], ceiling: float, alpha: float = 0.05) -> int:
    """The smallest number of inputs like these, at the present tries, at which the range with
    no failure lies inside plus or minus ``ceiling``. ``k`` inputs like these divide each end's
    ``c = end / (1 - end)`` by ``k / len(design)``; counted up from one."""
    lo, hi = clean_range(design, alpha)
    ends = [-lo / (1.0 + lo), hi / (1.0 - hi)]
    k = 1
    while max(c * len(design) / k / (1.0 + c * len(design) / k) for c in ends) > ceiling:
        k += 1
    return k


def accepts_at(lo: float, hi: float) -> float:
    """The larger end, rounded up at four decimals: the smallest size asked the range lies in."""
    return math.ceil(max(-lo, hi) * 10_000 - 1e-9) / 10_000


def worst_clean_chance(design: Sequence[tuple[int, int]], share: float) -> float:
    """The largest chance of a clean new run over every way the new version's failures could be
    spread across the inputs with their Mantel-Haenszel-weighted share at ``share`` (the old
    version never failing): maximise ``prod (1 - p_i)^n_i`` subject to ``sum w_i p_i / W =
    share``. At the maximum ``p_i = max(0, 1 - t n_i / w_i)`` for one ``t``, found by bisection;
    an input the constraint drives to 1 makes a clean run impossible."""
    w = [a * b / (a + b) for a, b in design]
    n = [b for _, b in design]
    total = sum(w)

    def held(t: float) -> float:
        return sum(wi * min(1.0, max(0.0, 1.0 - t * ni / wi)) for wi, ni in zip(w, n, strict=True)) / total

    low, high = 0.0, max(wi / ni for wi, ni in zip(w, n, strict=True))
    for _ in range(200):
        mid = (low + high) / 2.0
        if held(mid) >= share:
            low = mid
        else:
            high = mid
    rates = [min(1.0, max(0.0, 1.0 - low * ni / wi)) for wi, ni in zip(w, n, strict=True)]
    if any(r >= 1.0 for r in rates):
        return 0.0
    return math.exp(sum(ni * math.log1p(-r) for ni, r in zip(n, rates, strict=True)))


# ---------- what fix-check prints for the pairs that never failed ----------

PRINTED = FIX31 / "printed"


def printed(tmp: Path) -> dict[str, str]:
    """``file name -> stdout`` of fix-check on the pairs that never failed, each run from inside
    a folder of the test's own so that no path of this machine is printed: Break's case as Break
    asks it (``--json``) and in plain, a pair too small for the size asked in both, a pair of two
    inputs (rough) in both, and the pair whose only failure is on an input not compared."""
    from tf13_support import cli

    break_case(tmp)
    pair_store(tmp / "two-by-five", clean(2, 5))
    pair_store(tmp / "three-by-four", clean(3, 4))
    stray_store(tmp / "stray", clean(6, 5))
    asks: dict[str, list[str]] = {
        "break-case.json": break_argv(CONTROL, CANDIDATE_2, "break-case"),
        "break-case.md": break_argv(CONTROL, CANDIDATE_2, "break-case")[:-1],
        "break-case-weak-candidate.json": break_argv(CONTROL, CANDIDATE_1, "break-case"),
    }
    for name in ("three-by-four", "two-by-five", "stray"):
        base = ["fix-check", "old", "new", "--store", name, "--event", "fail", "--inputs", "all", "--max-mde", "0.2"]
        asks[f"{name}.md"] = base
        asks[f"{name}.json"] = [*base, "--json"]
    out: dict[str, str] = {}
    for name, argv in asks.items():
        ran = cli(tmp, argv)
        assert ran.code == 0 and ran.err == "", (name, ran.text)
        assert str(tmp) not in ran.out, name
        from pin_support import as_pinned

        # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned)
        out[name] = as_pinned(ran.out)
    return out


# ---------- where the range at zero is rough ----------

# the one-sided miss above which a range at zero failures is labelled rough
MISS_BAR = 0.05


def clean_miss(design: Sequence[tuple[int, int]], alpha: float = 0.05) -> float:
    """The range's one-sided miss where neither version failed, at its least favourable: the
    larger of the two ends' :func:`worst_clean_chance` (the high end against a new version that
    fails, the low end against an old version that does)."""
    lo, hi = clean_range(design, alpha)
    turned = [(b, a) for a, b in design]
    return max(worst_clean_chance(design, hi), worst_clean_chance(turned, -lo))


def unequalness(design: Sequence[tuple[int, int]]) -> float:
    """How unequal the tries are across the inputs, as one number: the largest weight any input
    gives one try of a version, over the weight the tries of that version have on average. It
    is 1 when every input has its tries in the same proportion between the versions, whatever
    the proportion, and grows as one input holds many tries of one version and few of the
    other."""
    weight = sum(a * b / (a + b) for a, b in design)
    old, new = sum(a for a, _ in design), sum(b for _, b in design)
    return max(max(a / (a + b) for a, b in design) * new / weight,
               max(b / (a + b) for a, b in design) * old / weight)
