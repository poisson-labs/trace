"""Shared helpers for the fix-check tests (TR37 to TR70): the committed fixtures the new verbs
read, the reports' fixed texts, a CLI runner per verb, a builder for synthetic stores written
through Prove's own ``Store.create_run`` / ``Store.append``, a rebuilder that copies a stored run
through Prove with its replicate indices or seeds changed, and the in-test oracles (full
enumeration, exact fractions) the property tests compare against.

Not a test module and not collected. Nothing here touches a Parquet file or a manifest directly.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash

from conftest import FIXTURES, CliResult, events_args, run_cli

PILOT = "20260917T140219Z-2b2d"
HUMANEVAL = FIXTURES / "humaneval"
HE_A = "20260905T185407Z-0313"
HE_B = "20260905T195009Z-18ac"
HE_EVENTS = ("failed_assertion", "crashed")
TAU2_EVENTS = ("unsolved",)

# the reasons an input is left out, in the order the report gives them
SPEC_LEFT_OUT = (
    "not re-run on the old version",
    "not re-run on the new version",
    "no outcome on the old version",
    "no outcome on the new version",
)

# fix-check's cannot-say block, verbatim, one line each
SPEC_CANNOT_SAY = (
    "A difference between two stored runs is a difference between the runs. The version, the "
    "provider and the hour changed together unless the two were run side by side, and this "
    "test cannot separate them.",
    "Repeat runs of one input are read as separate draws and never as replays: a served model "
    "is not bit-identical on repeat, so nothing here matches a run of the old version to a run "
    "of the new by seed.",
    "If repeat runs of one input are near copies of one another, the run-level test overstates "
    "its confidence. The by-input line does not depend on that.",
    "Rows with no outcome are left out of both arms and counted in the header. A new version "
    "that times out where the old one failed does not show as a failure here.",
    "Trace reads the runs it is given. If the inputs were chosen by the old arm's own outcomes, "
    "or the more favourable of several runs was handed over, the confidence printed does not "
    "hold.",
    "The detection limit and the run counts are computed from these runs' own failure rates, "
    "which are estimates. They are a guide to the next design, not a promise about it.",
)

# fix-check's JSON keys, top level in order; nested objects as key sets
# the verdict and its sentence after the schema, next last (docs/cli-look.md, rule 9);
# run_name beside run_id
FIX_KEYS = (
    "schema", "verdict", "sentence", "prove", "runs", "gap_seconds", "events", "inputs", "rows",
    "control", "test", "difference", "by_input", "consistency", "limits", "direction", "guidance",
    "changes", "cannot_say", "failure_taxonomy_diff", "next",
)
CHANGES_KEYS = (
    "schema", "verdict", "sentence", "prove", "runs", "events", "tested", "flagged", "alpha",
    "lone_threshold", "smallest_attainable_p", "together", "lone_flip_repeats", "rows",
    "cannot_say", "failure_taxonomy_diff", "next",
)
CHANGES_BLOCK_KEYS = CHANGES_KEYS[6:-2]
HEADER_KEYS = {"run_id", "run_name", "target_id", "status", "created_at", "declared_repeats", "tally"}
INPUTS_KEYS = {"rule", "failing_from", "min_failures", "selected", "compared", "informative", "left_out"}
ROWS_KEYS = {"runs", "failed", "timed_out", "no_outcome", "short", "mixed"}
CONTROL_KEYS = {"old_did_not_fail_share", "new_did_not_fail_share"}
TEST_KEYS = {"name", "observed_new", "expected_new", "variance", "weight", "p", "alpha"}
DIFFERENCE_KEYS = {"points", "lo", "hi", "variance", "interval"}
BY_INPUT_KEYS = {"moved", "p", "method", "draws", "seed"}
CONSISTENCY_KEYS = {"failure_share", "fails_again", "kappa", "within", "pooled"}
LIMITS_KEYS = {"drop", "rise", "power", "max_mde"}
GUIDANCE_KEYS = {"repeats", "inputs", "accepts_at"}
# a row carries no per-input "could not have detected a rise below", and no key for it
FLAG_ROW_KEYS = {
    "config_hash", "config", "failed_a", "runs_a", "failed_b", "runs_b", "change", "p", "q",
    "flag",
}
COMPARE_GUIDANCE_KEYS = {"deaths", "runs", "inputs", "repeats", "accepts_at"}

VERDICT_PHRASES = ("different:", "no significant difference", "too small to tell")
BANNED = (
    "unchanged", "verified", "guaranteed", "pass", "sure", "better", "worse", "fixed",
    "validated", "confirmed",
)
POINTER = (
    "For the share of runs that fail, input by input, and the inputs that changed: "
    "poisson-trace fix-check"
)


def fix_check(store: Path | str, old: str, new: str, events: Sequence[str], *extra: str) -> CliResult:
    return run_cli(["fix-check", old, new, "--store", str(store), *events_args(events), *extra])


def changes(store: Path | str, a: str, b: str, events: Sequence[str], *extra: str) -> CliResult:
    return run_cli(["changes", a, b, "--store", str(store), *events_args(events), *extra])


def one_sentence(result: CliResult) -> None:
    lines = [line for line in result.text.splitlines() if line.strip()]
    assert result.code == 1, result.text
    # one sentence, then the commands to run on their own next: lines (docs/cli-look.md rule 4)
    assert lines and all(line.startswith("  next: ") for line in lines[1:]), result.text


def ok(result: CliResult) -> CliResult:
    """A report printed: exit 0, too small to tell included."""
    assert result.code == 0, result.text
    assert result.out, result.text
    return result


# ---------- synthetic stores, through Prove ----------


@dataclass(frozen=True)
class Obs:
    """One synthetic row: an outcome, or no outcome and an ``error``. No trace is stored."""

    input: str
    outcome: str | None
    error: str | None = None
    replicate_index: int = 0
    seed: int = 0


def cfg(name: str) -> dict[str, Any]:
    return {"input": name}


def build_run(
    root: Path,
    run_id: str,
    rows: Sequence[Obs],
    *,
    replicates: int | None = None,
    created_at: str = "2026-01-01T00:00:00.000000Z",
    run_salt: str = "salt",
    target_id: str = "synthetic/target",
) -> None:
    environment: dict[str, Any] = {}
    if replicates is not None:
        environment["sweep"] = {"replicates": replicates}
    store = Store(root)
    store.create_run(
        RunManifest(
            run_id=run_id, target_id=target_id, t_unit="steps", run_salt=run_salt, axis_types={},
            backend="local", environment=environment, created_at=created_at,
        )
    )
    records = []
    for row in rows:
        config = cfg(row.input)
        if row.outcome is None:
            assert row.error is not None
            records.append(EpisodeRecord.errored(
                run_id=run_id, config=config, seed=row.seed, replicate_index=row.replicate_index,
                error=row.error, wall_time=1.0,
            ))
        else:
            records.append(EpisodeRecord(
                run_id=run_id, config_hash=config_hash(config), config=config, seed=row.seed,
                replicate_index=row.replicate_index, outcome=row.outcome, t=1.0, horizon=10.0,
                confidence=None, meta={}, error=None, wall_time=1.0, backend_meta={},
            ))
    store.append(run_id, records)
    store.mark_complete(run_id)


def arm_rows(tab: Sequence[tuple[int, int, int, int]], arm: str, *, prefix: str = "i") -> list[Obs]:
    """Rows for one arm of a table of ``(x_old, n_old, x_new, n_new)``: input ``k`` is named
    ``{prefix}{k}``, its first ``x`` rows fail."""
    out = []
    for k, (xa, na, xb, nb) in enumerate(tab):
        x, n = (xa, na) if arm == "old" else (xb, nb)
        for j in range(n):
            out.append(Obs(f"{prefix}{k}", "fail" if j < x else "ok", replicate_index=j, seed=1000 * k + j))
    return out


def pair_store(
    root: Path,
    tab: Sequence[tuple[int, int, int, int]],
    *,
    old_created: str = "2026-01-01T00:00:00.000000Z",
    new_created: str = "2026-01-01T01:00:00.000000Z",
    replicates: tuple[int | None, int | None] = (None, None),
) -> Path:
    """A store holding runs ``old`` and ``new`` built from a table."""
    build_run(root, "old", arm_rows(tab, "old"), created_at=old_created, replicates=replicates[0])
    build_run(root, "new", arm_rows(tab, "new"), created_at=new_created, replicates=replicates[1])
    return root


def rebuild(
    src_root: Path | str,
    run: str,
    dst_root: Path,
    *,
    reindex: Mapping[tuple[str, int], int] | None = None,
    seeds: Mapping[tuple[str, int], int] | None = None,
) -> None:
    """Copy ``run`` through Prove into ``dst_root``: the manifest as stored (``created_at``
    included), every row's config, outcome, error, t and horizon; no trace and no meta. With
    ``reindex`` or ``seeds``, a row keyed ``(config_hash, replicate_index)`` gets that replicate
    index or seed instead."""
    src = Store(src_root)
    manifest = src.manifest(run)
    frame = src.read(run, meta=False, trace="none")
    dst = Store(dst_root)
    dst.create_run(dataclasses.replace(manifest, status="partial"))
    records = []
    for h, config, seed, rep, outcome, t, horizon, error, wall in zip(
        frame["config_hash"], frame["config"], frame["seed"], frame["replicate_index"],
        frame["outcome"], frame["t"], frame["horizon"], frame["error"], frame["wall_time"],
        strict=True,
    ):
        key = (str(h), int(rep))
        new_rep = int(rep) if reindex is None else int(reindex[key])
        new_seed = int(seed) if seeds is None else int(seeds[key])
        if outcome is None:
            records.append(EpisodeRecord.errored(
                run_id=run, config=dict(config), seed=new_seed, replicate_index=new_rep,
                error=str(error), wall_time=float(wall),
            ))
        else:
            records.append(EpisodeRecord(
                run_id=run, config_hash=str(h), config=dict(config), seed=new_seed,
                replicate_index=new_rep, outcome=str(outcome), t=float(t), horizon=float(horizon),
                confidence=None, meta={}, error=None, wall_time=float(wall), backend_meta={},
            ))
    dst.append(run, records)
    dst.mark_complete(run)


def scrambles(root: Path | str, run: str, rng: np.random.Generator) -> tuple[dict[tuple[str, int], int], dict[tuple[str, int], int]]:
    """A permutation of the replicate indices within every input, and a fresh seed per row."""
    frame = Store(root).read(run, meta=False, trace="none")
    reindex: dict[tuple[str, int], int] = {}
    seeds: dict[tuple[str, int], int] = {}
    by_input: dict[str, list[int]] = {}
    for h, rep in zip(frame["config_hash"], frame["replicate_index"], strict=True):
        by_input.setdefault(str(h), []).append(int(rep))
    for h, reps in by_input.items():
        for old, new in zip(reps, rng.permutation(reps), strict=True):
            reindex[(h, old)] = int(new)
            seeds[(h, old)] = int(rng.integers(0, 2**31 - 1))
    return reindex, seeds


# ---------- oracles ----------


def hyper(n_old: int, n_new: int, t: int, k: int) -> Fraction:
    big = n_old + n_new
    return Fraction(math.comb(t, k) * math.comb(big - t, n_new - k), math.comb(big, n_new))


def exact_p_enumerated(tab: Sequence[tuple[int, int, int, int]]) -> float:
    """Every table with the observed margins, enumerated input by input: the distribution of the
    sum of new-arm failures in exact fractions, then the two-sided p by Fisher's convention."""
    ranges = []
    for xa, na, xb, nb in tab:
        t = xa + xb
        ranges.append([(k, hyper(na, nb, t, k)) for k in range(max(0, t - na), min(t, nb) + 1)])
    dist: dict[int, Fraction] = {}
    for combo in itertools.product(*ranges):
        s = sum(k for k, _ in combo)
        pr = Fraction(1)
        for _, q in combo:
            pr *= q
        dist[s] = dist.get(s, Fraction(0)) + pr
    observed = sum(xb for _, _, xb, _ in tab)
    at = dist[observed]
    return float(sum(q for q in dist.values() if q <= at * Fraction(10_000_001, 10_000_000)))


def moves(tab: Sequence[tuple[int, int, int, int]]) -> list[Fraction]:
    return [Fraction(xb * na - xa * nb, na + nb) for xa, na, xb, nb in tab if xb * na != xa * nb]


def sign_flip_enumerated(tab: Sequence[tuple[int, int, int, int]]) -> float:
    v = moves(tab)
    if not v:
        return 1.0
    observed = abs(sum(v))
    hits = sum(
        1 for signs in itertools.product((1, -1), repeat=len(v))
        if abs(sum(s * x for s, x in zip(signs, v, strict=True))) >= observed
    )
    return hits / 2 ** len(v)


def counts_of(tab: Sequence[tuple[int, int, int, int]]) -> list[Any]:
    from poisson_trace.paired import Counts

    return [Counts(f"h{k:03d}", xa, na, xb, nb) for k, (xa, na, xb, nb) in enumerate(tab)]


WORKED = [(3, 4, 1, 4), (4, 4, 4, 4), (2, 4, 0, 4), (0, 4, 1, 4), (4, 4, 2, 4)]
