"""TF6-1 to TF6-3: what TF6 must not change (invariant 5), and the one spelling it does.

TF6-1: every verb's plain output and ``--json`` stay byte for byte as on main 1de6936, on the
committed fixtures, without the new options: pinned as digests of the output with the
repository's own path written ``<REPO>``. A ``[check] max_change`` in ``trace.toml`` changes
nothing printed either: the continuous table prints only when asked (SV2).

TF6-2: the one line TF6 changes in an existing output is the plus-minus sign on a stream that
cannot write it. Today ``fix-check``'s *no significant difference* and *too small to tell* lines
read ``lies inside ±20``; on such a stream the sign comes out as the escape ``\\xb1``, against
TF0-17's rule. It is spelt ``+/-`` there (Taylor, 2026-11-04). A stream that can write it, UTF-8
or Latin-1, keeps it.

TF6-3: each new option is on the help of the verbs it belongs to and on no other.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tf0_support import (
    REPO, changes_he, compare_tau2, fix_check_tau2, fix_check_tau2_all, run_sub, trace, where_cs,
)
from tf6_support import PROVE_013, argv012, env_ascii, write

# Each invocation's digests on main 1de6936: (plain, --json), the repository's path as <REPO>.
# The Prove pin moved to 0.1.3 on main (SB7, ruled by Taylor 2026-11-04): the JSON digests moved
# for Prove's version string alone, the plain ones not at all, and the four pins on the committed
# Prove store were taken again on the 0.1.3 store that replaced the 0.1.2 one.
PINNED: dict[str, tuple[list[str], str, str]] = {
    "where cs": (where_cs("--at", "20"),
        "bfb5db225986b5eef9fb5346c318a60a854b38d8ea7d678971733ac7e0154dd9",
        "7ee22fa634dc87db5c2d5104cb7fa027d13f3584c5f94caa2e5babe9ea171231"),
    "compare tau2": (compare_tau2("1.3", "--at", "10"),
        "97d91846674476d59cf22bbb1fe16975da016e1a6427606b8b51f28b310d4aed",
        "e27479dfecc64b79e73db2fb2b854960bf2b48d2d68f338bda5d0dbc783f522b"),
    "fix-check tau2": (fix_check_tau2(),
        "20b25c99736592a96d20baa8f8a528f577e9a7c2efc3bde80cf9333dfdeb6d4e",
        "7a505da037a8758129e9ef634d4e853072fce7da4599cd70e473c6d590c2e430"),
    "fix-check tau2 all": (fix_check_tau2_all("0.2"),
        "ed2078117e83fceaf87b148d4e28dfd37432f2cf16ec8431cdcec030d593b02f",
        "ed1829e0bb15be5113da98b57d8521d3108735046293729f93f6e2fb39828112"),
    "changes humaneval": (changes_he(),
        "94554dfa0bdef30aa64498c529bf4d215b17a56cb4843745967cf740b68ff964",
        "d1319f60018b27070b5ce35c6b52e948651d6153351eee5d5a467e51f2fa5b68"),
    "where prove-0.1.3": (argv012("where", PROVE_013),
        "917564530fdfe939b31c99ba4d760a938967a194728792ca2d409ebe6ab07892",
        "6d23820d85b57f1ccb623878890976b74c02d2edf5f8d95c9c42b558c93e0775"),
    "compare prove-0.1.3": (argv012("compare", PROVE_013),
        "fdbce35451dfe5d522a425305ba8c37f42d9b575c278f92e847ac331d6994a78",
        "cd8f1c2eabeadf7dc3e39828037bff76ccc9d08bcd4e165c6ccb19019c9a9ab0"),
    "fix-check prove-0.1.3": (argv012("fix-check", PROVE_013),
        "28355fa4e8dda4eb49efa6478c2619b6abc63fdba6512e2738241d205bc74cc9",
        "82b43481580dcc2b91956ae8bed1cc9a9a08240267e31031410253ff4cdc8c9e"),
    "changes prove-0.1.3": (argv012("changes", PROVE_013),
        "7260a6f89ab2c9fe29d8a8d2738bb4e193c6c20355c8b814b69da14b021698e7",
        "5c46429071bf5790d11819ae578277c78284ee2cd7057e9be7a2a1f1fbcc6c7e"),
}
def _digest(text: str) -> str:
    return hashlib.sha256(text.replace(str(REPO), "<REPO>").encode("utf-8")).hexdigest()


# ---------- TF6-1 ----------


# the pins on the larger fixtures run in the slow lane; the Prove 0.1.3 store's four and tau2's
# fix-check are their fast twins
SLOW_PINS = ("where cs", "compare tau2", "fix-check tau2 all", "changes humaneval")


@pytest.mark.parametrize("name", [pytest.param(n, marks=pytest.mark.slow) if n in SLOW_PINS else n for n in PINNED])
def test_tf6_1_every_verb_prints_what_it_printed_before(name: str) -> None:
    argv, plain_digest, json_digest = PINNED[name]
    plain, as_json = trace(argv), trace([*argv, "--json"])
    assert plain.code == 0 and as_json.code == 0, plain.text + as_json.text
    assert (_digest(plain.out), _digest(as_json.out)) == (plain_digest, json_digest), name
    assert plain.err == as_json.err == ""


@pytest.mark.parametrize("names", [
    ("fix-check prove-0.1.3", "changes prove-0.1.3", "compare prove-0.1.3"),
    pytest.param(("fix-check tau2 all", "compare tau2"), marks=pytest.mark.slow),
])
def test_tf6_1_a_max_change_in_the_config_prints_nothing_new(tmp_path: Path, names: tuple[str, ...]) -> None:
    config = write(tmp_path / "trace.toml",
                   'version = 1\n\n[check]\nmax_change = { wall_time_s = "10%", input_tokens = "5%" }\n')
    for name in names:
        argv, plain_digest, json_digest = PINNED[name]
        given = [*argv, "--config", str(config)]
        plain, as_json = trace(given), trace([*given, "--json"])
        assert plain.code == 0 and as_json.code == 0, plain.text + as_json.text
        # the next commands carry --config, as they do for any config named by flag; nothing else moves
        flag = f" --config {config}"
        assert _digest(plain.out.replace(flag, "")) == plain_digest, name
        assert _digest(as_json.out.replace(flag, "")) == json_digest, name


# ---------- TF6-2 ----------


def _nsd_line(out: str) -> str:
    return next(line for line in out.splitlines() if "lies inside" in line)


def test_tf6_2_the_plus_minus_sign_is_spelt_on_a_stream_that_cannot_write_it() -> None:
    from poisson_trace import look

    assert look.fit("lies inside ±20", "ascii") == "lies inside +/-20"
    assert look.fit("±", "ascii") == "+/-"
    # a stream that can write it keeps it
    assert look.fit("lies inside ±20", "utf-8") == "lies inside ±20"
    assert look.fit("lies inside ±20", "latin-1") == "lies inside ±20"


def test_tf6_2_fix_check_says_plus_minus_in_ascii_and_nothing_else_moves() -> None:
    from poisson_trace import look

    argv = fix_check_tau2_all("0.2")
    wide = run_sub("trace", argv)
    narrow = run_sub("trace", argv, env=env_ascii())
    assert wide.code == narrow.code == 0 and narrow.err == "", narrow.text
    assert "lies inside ±20" in _nsd_line(wide.out)
    assert "lies inside +/-20" in _nsd_line(narrow.out)
    assert "\\xb1" not in narrow.out and narrow.out.isascii()
    # every line that held the sign differs only by it; every other line as before
    for w, n in zip(wide.out.splitlines(), narrow.out.splitlines(), strict=True):
        if "±" in w:
            assert n == look.fit(w.replace("±", "+/-"), "ascii"), (w, n)
        else:
            assert n == look.fit(w, "ascii"), (w, n)


@pytest.mark.parametrize("which", ["small", pytest.param("tau2", marks=pytest.mark.slow)])
def test_tf6_2_the_continuous_lines_say_plus_minus_in_ascii(tmp_path: Path, which: str) -> None:
    """The continuous measures' lines hold the sign (TF23-17's "changes smaller than about
    ±X"); on fix-check, through a stream that cannot write it, they read ``+/-``."""
    from tf0_support import TAU2, TAU2_A, TAU2_B
    from tf6_support import measures_store

    if which == "small":
        argv = ["fix-check", "old", "new", "--store", str(measures_store(tmp_path)), "--event", "missed",
                "--inputs", "all", "--max-mde", "0.5", "--measures"]
    else:
        argv = ["fix-check", TAU2_A, TAU2_B, "--store", str(TAU2), "--event", "unsolved", "--inputs", "all",
                "--max-mde", "0.2", "--measures"]
    wide = run_sub("trace", argv)
    narrow = run_sub("trace", argv, env=env_ascii())
    assert wide.code == narrow.code == 0 and narrow.err == "", narrow.text
    assert "changes smaller than about ±" in wide.out, "the continuous lines hold a sign to fall back from"
    assert narrow.out.isascii() and "\\xb1" not in narrow.out
    assert "changes smaller than about +/-" in narrow.out
    assert narrow.out.count("+/-") == wide.out.count("±") + wide.out.count("+/-")


# ---------- TF6-3 ----------


NEW_OPTIONS = {
    "--save": ("where", "compare", "fix-check", "changes"),
    "--out": ("where", "compare", "fix-check", "changes"),
    "--verdicts": ("compare", "fix-check", "changes"),
    "--max-change": ("fix-check",),
    "--measures": ("fix-check",),
}


@pytest.mark.parametrize("verb", ["runs", "name", "where", "compare", "fix-check", "changes", "doctor"])
def test_tf6_3_each_new_option_is_on_the_verbs_it_belongs_to(verb: str) -> None:
    ran = trace([verb, "--help"])
    assert ran.code == 0, ran.text
    for option, verbs in NEW_OPTIONS.items():
        listed = any(line.lstrip().startswith(option) for line in ran.out.splitlines())
        assert listed == (verb in verbs), (verb, option)


def test_tf6_3_handover_is_a_verb_with_check() -> None:
    top = trace(["--help"])
    assert top.code == 0 and any(line.lstrip().startswith("handover") for line in top.out.splitlines()), top.out
    ran = trace(["handover", "--help"])
    assert ran.code == 0 and "--check" in ran.out, ran.text
