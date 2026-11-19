"""TF13-32: the deliveries' output stays byte for byte as the pinned main prints it, through
the command line now calling the API.

TF13-32: each invocation's exit code, stdout and stderr, pinned as digests with the workspace's
own path written ``<WORK>``: the deliveries (``--save``, ``--out``, ``--svg``, and the files they
write), their refusals, the three forms of ``name``, and ``handover --check`` on what is not a
bundle. These are the twelve cases whose steps no later list runs.

The other commands (the counting verbs on each kind of store with each option, ``runs``, the
import of every reader, the refusals, and the helps) are not pinned here:
``test_pl_unchanged.py`` (PL-51) runs each of those commands whole and holds it at its pinned
bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tf13_support import (
    EV, VERBS_ARGV, cli, cli_import, workspace,
)


def _cases() -> dict[str, tuple[str, list[list[str]]]]:
    out: dict[str, tuple[str, list[list[str]]]] = {}
    for verb, argv in (("where", VERBS_ARGV["where"]), ("compare", VERBS_ARGV["compare"]),
                       ("fix-check", VERBS_ARGV["fix-check measures"]), ("changes", VERBS_ARGV["changes verdicts"])):
        out[f"save: {verb}"] = ("trace", [[*argv, "--save"], [*argv, "--save", "--json"]])
        out[f"out: {verb}"] = ("trace", [[*argv, "--out", "bundle"], ["handover", "--check", "bundle"],
                                         [*argv, "--out", "bundle", "--json"], [*argv, "--out", "bundle", "--force", "--json"]])
    out["svg: where"] = ("trace", [[*VERBS_ARGV["where"], "--svg", "curve.svg"],
                                   [*VERBS_ARGV["where"], "--svg", "curve.svg", "--force", "--out", "bundle", "--save"]])
    out["refusal: svg and out"] = ("trace", [[*VERBS_ARGV["where"], "--svg", "no-such-dir/c.svg"], [*VERBS_ARGV["where"], "--svg", "grades.csv"],
                                             [*VERBS_ARGV["where"], "--svg", "conf"], [*VERBS_ARGV["where"], "--out", "conf"],
                                             [*VERBS_ARGV["where untraced"], "--svg", "c.svg"],
                                             [*VERBS_ARGV["where"], "--force"], [*VERBS_ARGV["fix-check"], "--force"]])
    out["names"] = ("trace", [["name", "agent after", "shipped", "--store", "store"], ["name", "shipped", "shipped", "--store", "store"],
                              ["name", "--list", "--store", "store"], ["where", "shipped", "--store", "store", *EV],
                              ["runs", "--store", "store", "--json"], ["name", "shipped", "--forget", "--store", "store"],
                              ["name", "--list", "--store", "store"], ["name", "agent after", "latest", "--store", "store"],
                              ["name", "agent after", "--store", "store"], ["name", "--list", "agent after", "--store", "store"]])
    out["handover: not a bundle"] = ("trace", [["handover", "--check", "conf"], ["handover", "--check", "no-such"],
                                               ["handover", "--check", "grades.csv"], ["handover"]])
    return out


CASES = _cases()

# Each case's steps on the pinned main: (exit code, stdout's digest, stderr's digest), the
# workspace's path as <WORK>.
# TF18: the four out cases' handover --check step prints main's line, a blank line
# and next: poisson-trace report bundle; compare's bundle lists its four chart files besides
PINNED: dict[str, list[tuple[int, str, str]]] = {
    'save: where': [
        (0, '059ed63192014937228496010e478c4b67d159e5988de759d30e458e688ddbf9',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '61339e61de9f31b4b11956cfd6b5649e3dcbea2b80fa73ebf3ee9e49cd14bc5f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'out: where': [
        (0, '471de063e86507b69d589ed54f039e084cbc45403cb5f6dd3bdff94e8a6d498a',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'fdbb2935b0e68759220830a00f06379151991d471ebe2195c8955abdf926459e',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1fd1bbcea4819052b7284b02d43c5669d429b48456cd10317f88583704f48738'),
        (0, '61339e61de9f31b4b11956cfd6b5649e3dcbea2b80fa73ebf3ee9e49cd14bc5f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'save: compare': [
        (0, 'ae881376b33d74808916ee7c8bf4cee592f308e1d70be9cf531188b3ba6a0ef0',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '6ed2cc20b2e45bca98ad5c63dd0faec496672b18fb7d167f0ff1ef1b6750f5bf',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'out: compare': [
        (0, '17268fbd6488935f0a407bff51e95f9b55877925d0a2cc8f1149e5295afc5729',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'b3042f352b42d4c4635a8fccb3d8c78d4217df20740c4b8c436ca3ebd9fb6265',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1fd1bbcea4819052b7284b02d43c5669d429b48456cd10317f88583704f48738'),
        (0, '6ed2cc20b2e45bca98ad5c63dd0faec496672b18fb7d167f0ff1ef1b6750f5bf',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'save: fix-check': [
        (0, 'cd1bea34c9b3a78b426c12202da485a2290111d53203ad0fb0201b9a04249e74',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '750bd01f953d7df00c96e6c9607fcae393224ac0218a5c8b6b5bba1b269272c4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'out: fix-check': [
        (0, '0c43a31b4a028f46c9627ccc59d3137f06c46dd1e6f5c1b21263d139ba9fee73',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '87336e7c6f350893ac6c50cfce2965122e61e2136328566ceeeedbbb587cb2e6',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1fd1bbcea4819052b7284b02d43c5669d429b48456cd10317f88583704f48738'),
        (0, '750bd01f953d7df00c96e6c9607fcae393224ac0218a5c8b6b5bba1b269272c4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'save: changes': [
        (0, '08ac9d7654abd582f5534685f6dcb91ffffaf8c146cb574de615278512b398be',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '4af15a607a97e3649b20542ed8f92b88f3532709e8a1b3cc2b1449f3c6b1e33e',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'out: changes': [
        (0, 'c4760614752471bb4f208f7b540b59545aa47f3a7e1d3bf9ee9e27e5e2b4a395',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'a96548afc02b0ad8fc654666f05613057265933a5b4a335d0d472f26a7ad6efd',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1fd1bbcea4819052b7284b02d43c5669d429b48456cd10317f88583704f48738'),
        (0, '4af15a607a97e3649b20542ed8f92b88f3532709e8a1b3cc2b1449f3c6b1e33e',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'svg: where': [
        (0, 'bd755603397ce97237f8956c6fd59a4dd806f6a4292b191c848e109c901deac6',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '1911adac6ec3562dfe90f6eea92334d9b0dba9df7ddca93f8ccf3ba4dce852e7',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'refusal: svg and out': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '79a35197ff704adc44ddd3a052882c223bc96e235f8ee23c94783e79e46d3fd8'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '15fe5243eb314ba57ea3f3b4799c204c2c1ef0ea1a8148769b22a9756e74cd15'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '7a10e4c3adf8bc897bb9b357f48f576e2226bd9eff9b547cdb47f53a4cb82387'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '726e51222603567f1b92ab7438e106131dfad7b97cb4141692f09c7fb43ffc8c'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'adb6c8bb5f9ead385e2c46f2ab59127188cc7545744518b1e057f1699135c103'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '034754157f742f3f4e6db99d28b4204c8e7e49af46c3f9911a7af7f8d1a7a941'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '113b7b9989319382279d589083313972c894701bda5e3070522d697925903d71'),
    ],
    'names': [
        (0, '8723e6dc93cc54e42a70783d2781a26d57e2f37b1f8e038f0c15a3445fde8f74',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '723fccece18f9de44907d4e7f0452dbb0c0b286d73c7b9ca378263572276b947',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '9b78f0b461f69fe8f65e289006f39965422fef96ea91ca63e36a9d942cdaeb0d',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '575a538e8e171c654865119d3c2309eb362c38827ef4a44759960d93b6e63ee7',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '02a4c80fb5a1d2a78e7512deb01d71a7f0969bb3709423d44d18d79efacef214',
         '0c9e5d610cdc67b8f54d29e4ab7657b87638708569752abab82aeb024cb34dcb'),
        (0, 'f4343498709ab5296f7858cd4c021dbf22be262a44a411fa571027f9260e0b46',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '697da8dff00248229eec0a02d41046bf21d616339e3dd2108ab4ab3c465810a8',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'dc4cb03b01c9b40331933e33ec6024b6ea5d8d7a14f930e151a40a40e397836e'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1571f3f6c53408beb9f717ccfc4f11ac209086e65aa0525029f8d6ed5cf9e17b'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1ed4bbf239fb62b511a4072c6626f99ee6656ba1fc986abf66691b8e4a345859'),
    ],
    'handover: not a bundle': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '2851b332c646f06f4c4dc632cd776d1a06a6f09f9ccd78a7f8744c384c1771aa'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '84d45478d565ef982af371b7eb1d30f98c9721ac7345f79d0f23fa25b6769aea'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'de7826cde40f60b5d7c5573d8f151a8b5404f7b040af784b58c5f0fff418ea1a'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '44cd3627b53167017c6d04b280ccbeda9b51e19811a52d727a710ec68331c557'),
    ],
}


def _digest(text: str, work: Path) -> str:
    from pin_support import as_pinned

    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned)
    return hashlib.sha256(as_pinned(text.replace(str(work), "<WORK>")).encode("utf-8")).hexdigest()


def run_case(tmp: Path, label: str) -> tuple[list[tuple[int, str, str]], Path]:
    kind, steps = CASES[label]
    work = workspace(tmp)
    got = []
    for step in steps:
        ran = (cli if kind == "trace" else cli_import)(work, step)
        got.append((ran.code, _digest(ran.out, work), _digest(ran.err, work)))
    return got, work


# ---------- TF13-32 ----------


@pytest.mark.parametrize("label", list(CASES))
def test_tf13_32_every_output_is_as_main_prints_it(tmp_path: Path, label: str) -> None:
    got, _work = run_case(tmp_path, label)
    assert [tuple(g) for g in got] == [tuple(p) for p in PINNED[label]], label


def test_tf13_32_a_every_case_is_pinned() -> None:
    assert set(PINNED) == set(CASES), sorted(set(PINNED) ^ set(CASES))
