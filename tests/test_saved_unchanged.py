"""TF6-1 to TF6-3: what TF6 must not change, and the one spelling it does.

TF6-1: every verb's plain output and ``--json`` stay byte for byte as on the pinned main, on the
committed fixtures, without the new options: pinned as digests of the output with the
repository's own path written ``<REPO>``. A ``[check] max_change`` in ``trace.toml`` changes
nothing printed either: the continuous table prints only when asked.

TF6-2: the one line TF6 changes in an existing output is the plus-minus sign on a stream that
cannot write it. Today ``fix-check``'s *no significant difference* and *too small to tell* lines
read ``lies inside ±20``; on such a stream the sign comes out as the escape ``\\xb1``, against
TF0-17's rule. It is spelt ``+/-`` there. A stream that can write it, UTF-8
or Latin-1, keeps it.

TF6-3: each new option is on the help of the verbs it belongs to and on no other.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from look_support import (
    REPO, changes_he, compare_tau2, fix_check_tau2, fix_check_tau2_all, run_sub, trace, where_cs,
)
from saved_support import PROVE_013, argv012, env_ascii, write

# Each invocation's digests on the pinned main: (plain, --json), the repository's path as <REPO>.
# With Prove pinned at 0.1.3 the JSON digests differ from 0.1.2's by Prove's version string alone,
# the plain ones not at all; the four pins on the committed Prove store are taken on its 0.1.3
# store.
PINNED: dict[str, tuple[list[str], str, str]] = {
    "where cs": (where_cs("--at", "20"),
        "bfb5db225986b5eef9fb5346c318a60a854b38d8ea7d678971733ac7e0154dd9",
        "747f52f7e750d2ac91762d6e135accf1cf070bbfe4aeff0aaf64fdb17bd2091e"),
    "compare tau2": (compare_tau2("1.3", "--at", "10"),
        "9fd29c1f1cb2ec0ac3a3c9a359a34f064215ec4a37d16796d13768f71ede88ce",
        "b36d6db51251da2f1583fc36ad3aa8d56d52a8d1fdaca4d2276b5bef057f6d6c"),
    "fix-check tau2": (fix_check_tau2(),
        "241d89d793d5b237686a6fcb48b7e1c35ca6981238b696c697b1916e8c95952b",
        "a0dfaa074b4f2d673db7d1bedd004eb5feba21458c10cd12cb0afc00d62fdbdd"),
    "fix-check tau2 all": (fix_check_tau2_all("0.2"),
        "0a613e96602246304baaedd1768370c6abb8d4157f2b02935f239a1ff200b87b",
        "98a9ca25f0407d89bceecbeda35a1e6bf038e81b267509d7abffe0839d896763"),
    "changes humaneval": (changes_he(),
        "802445ef051d7815e2a3ed2739b3d11ad83eee58902e56c30bcc446ffb445628",
        "d05aa184019f6fa1b5bd763aed691c83349fbbd8d30370db1147e2c10240bcb1"),
    "where prove-0.1.3": (argv012("where", PROVE_013),
        "917564530fdfe939b31c99ba4d760a938967a194728792ca2d409ebe6ab07892",
        "0283688c5eb354126560b29fad496825f5b7a82ca44dbd536da203af106a39c4"),
    "compare prove-0.1.3": (argv012("compare", PROVE_013),
        "0eb05506a72fe4e40421513646e36bedb81c9277d82f06a970967b9c871bd766",
        "4ac24dce997111989c49767fedb0d1d38ac4a2b643e5386a68939bf59391c2ee"),
    "fix-check prove-0.1.3": (argv012("fix-check", PROVE_013),
        "4fd09f6a5e169752c4b4bfb4db5fefb6302fd3ed1d219893752dcb5f4d7e6516",
        "f401d84557f85994a8c81ecac42bba7091908529ed847e01040e4cb38d444147"),
    "changes prove-0.1.3": (argv012("changes", PROVE_013),
        "bda1140b36c1600d8f594b611a2b1a8a453ce6eef90ebb9390983b6ca929def5",
        "5645fa0b5333107cab506c929ba678c404230f5d9ba8ff37edbaaa716af5fb8c"),
}
def _digest(text: str) -> str:
    from pin_support import as_pinned

    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned)
    return hashlib.sha256(as_pinned(text.replace(str(REPO), "<REPO>")).encode("utf-8")).hexdigest()


# ---------- TF6-1 ----------


# the pins on the larger fixtures run in the slow lane; the Prove 0.1.3 store's four and tau2's
# fix-check are their fast twins
SLOW_PINS = ("where cs", "compare tau2", "fix-check tau2 all", "changes humaneval")
#: The four outputs that naming Prove's label kinds moves.
LABELS_MOVED = ("fix-check tau2", "fix-check tau2 all", "compare tau2", "changes humaneval")


@pytest.mark.parametrize("name", [pytest.param(n, marks=pytest.mark.slow) if n in SLOW_PINS else n for n in PINNED])
def test_tf6_1_every_verb_prints_what_it_printed_before(name: str) -> None:
    argv, plain_digest, json_digest = PINNED[name]
    plain, as_json = trace(argv), trace([*argv, "--json"])
    assert plain.code == 0 and as_json.code == 0, plain.text + as_json.text
    # on tau2 and HumanEval the labels that have no kind are named (test_label_kinds_unchanged.py, PL-52,
    # holds that); this goes on holding every other byte of them
    from label_kinds_pins import unmoved_text

    out, out_json = (unmoved_text(plain.out), unmoved_text(as_json.out)) if name in LABELS_MOVED else (plain.out, as_json.out)
    assert (_digest(out), _digest(out_json)) == (plain_digest, json_digest), name
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
        # on tau2 the labels that have no kind are named (test_label_kinds_unchanged.py, PL-52, holds
        # that); this goes on holding every other byte of them
        from label_kinds_pins import unmoved_text

        out, out_json = (unmoved_text(plain.out), unmoved_text(as_json.out)) if name in LABELS_MOVED else (plain.out, as_json.out)
        assert _digest(out.replace(flag, "")) == plain_digest, name
        assert _digest(out_json.replace(flag, "")) == json_digest, name


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
    from look_support import TAU2, TAU2_A, TAU2_B
    from saved_support import measures_store

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
