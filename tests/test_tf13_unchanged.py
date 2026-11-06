"""TF13-32 and TF13-33: every verb's plain and ``--json`` output stays byte for byte as main
667e42c prints it, through the command line now calling the API (invariant 4).

TF13-32: each invocation's exit code, stdout and stderr, pinned as digests with the workspace's
own path written ``<WORK>``: the counting verbs on each kind of store with each option, ``runs``,
the three forms of ``name``, the import of every reader, the deliveries (``--save``, ``--out``,
``--svg``, and the files they write), ``handover --check``, and every refusal of TF13-19 to
TF13-21. TF6-1 and TF21-64 pin the larger fixtures' outputs and stay as they are. ``init`` and
``doctor`` are pinned by their own pairs' tests (TF2, TF3, TF17), which their builds are
changing now; TF13-18 holds them to the command line instead.

TF13-33: the help of every verb but ``init`` and ``doctor`` (which the setup agent changes,
TF17), of the import and of each reader, byte for byte.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tf13_support import (
    EV, IMPORT_ARGV, IMPORT_REFUSALS_ARGV, REFUSALS_ARGV, SLOW_IMPORTS, VERBS_ARGV, cli, cli_import, workspace,
)


def _cases() -> dict[str, tuple[str, list[list[str]]]]:
    out: dict[str, tuple[str, list[list[str]]]] = {}
    for label, argv in VERBS_ARGV.items():
        out[f"verb: {label}"] = ("trace", [argv, [*argv, "--json"]])
    for label, argv in IMPORT_ARGV.items():
        out[f"import: {label}"] = ("import", [argv])
        out[f"import json: {label}"] = ("import", [[*argv, "--json"]])
    for label, (argv, _code) in REFUSALS_ARGV.items():
        out[f"refusal: {label}"] = ("trace", [argv, [*argv, "--json"]])
    for label, (argv, _code) in IMPORT_REFUSALS_ARGV.items():
        out[f"import refusal: {label}"] = ("import", [argv, [*argv, "--json"]])
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
SLOW = {f"import: {k}" for k in SLOW_IMPORTS} | {f"import json: {k}" for k in SLOW_IMPORTS}

# Each case's steps on main 667e42c: (exit code, stdout's digest, stderr's digest), the
# workspace's path as <WORK>.
PINNED: dict[str, list[tuple[int, str, str]]] = {
    'verb: where': [
        (0, 'cd551e7b7f74494e77961c3fb675f69137821724139ac98058c159397fc47c9f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '2535f52b5b0202f79446e2beab365017f19510292cce995bdf1fc20470ca0f92',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: where by step': [
        (0, '3b9ef8095873a06d5872f5e72ae9fafa41f88b593793c283e94b98e84a552c7b',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'fd81d449062faae70bc388a99ea1d5b350911db0944946deb11c0e420e6271f4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: where untraced': [
        (0, '501dfc113d8f35cb1d1a0ee0d982fa5a00c2af23ec6a844cdab9583f24328c79',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '72dd5a4eb326037a9ba06f20c756e0fb798d03e887f18f9778baf6236c735796',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: where by number': [
        (0, 'e414674c1c5dde572464a627cbe16f10faa4ad530bfd63f117117b51ea97c1a0',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'b4f24694c937bd3650627956e14de6a37881960cf16e3347a3d41b653f9ec9bc',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: where latest': [
        (0, 'e414674c1c5dde572464a627cbe16f10faa4ad530bfd63f117117b51ea97c1a0',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'b4f24694c937bd3650627956e14de6a37881960cf16e3347a3d41b653f9ec9bc',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: compare': [
        (0, 'aa1d307159abbf4d732dbfb10aa9849bde2d741ef237558ff5f51c62e0348131',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '71ef525783fc629c76a81140c6c168f924e5c63b82b2d22e3ee3ee520fab0002',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: compare at': [
        (0, '67884a0b38e7b2dfaf70885ad1f50d4520e0504ba045f01eea614e20f30dab36',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'e649c82f8c0a5724d9048fed0df8ae475f7202e41dfdaa5cdbaa22d48b050d20',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: compare previous latest': [
        (0, 'aa1d307159abbf4d732dbfb10aa9849bde2d741ef237558ff5f51c62e0348131',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '71ef525783fc629c76a81140c6c168f924e5c63b82b2d22e3ee3ee520fab0002',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check': [
        (0, '4fd09f6a5e169752c4b4bfb4db5fefb6302fd3ed1d219893752dcb5f4d7e6516',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '499fd8b69c695e43e1e822395fc17b229b1d221b6da5820f50fc0caca4f05e1a',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check measures': [
        (0, 'b6ebd294c4489a52e73edf247e4d0bb276e2fb98af7e2dcf66b46e56fc6a5c8f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '02d32af522bc8a9dc22a4e7b2cde75b4eb1b658208ddefb26e80f012749990e4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check max-change': [
        (0, 'b6ebd294c4489a52e73edf247e4d0bb276e2fb98af7e2dcf66b46e56fc6a5c8f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'd9659c434a958434edf45b51af001a7e21f20e003b394dc55929eddcbcb6e809',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check top': [
        (0, '46b64b49dc3e8808c7b9cc6535bbc450a315c222e4a5eaad49c465dce94b8d20',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '6ef2654fae2d42ebcabf8bb083f7ea6334892818115a4c8aef5d35b590b18557',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check tables': [
        (0, 'a7849d7918b9cd8dc22621dab5e717b4e10db6c9646f3a50b9230a1fb63d3e2d',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'e48608a9b5ef2f196475c771d92cf278b69b94c096c04a2220af39d51ae9fc64',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check verdicts': [
        (0, 'e5b285e9048e1517582ff1e2e07eb45e09c014e95dd0c72ea0d6464e42e99afe',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'e56a8ad301e54dedebe8c5cc291319c378c917175925dafa80af68ffe6518636',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check junit': [
        (0, '77f238a470ed9923bb2afe2b29f1720ecc5b1f0d1c121f3464d470a20e845c53',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'b6ea484a73cdce56cbcdcf9d58c81131148249df9734e5d56707a4fd9b00ccf9',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: changes': [
        (0, '9682171c27791bdf265440f071f6e5d20819b8fdf5f06c0afaaa935273a487dd',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'c604a0ef561baf4cadcb1d619f83974b8a4507acd5e519e08172d4698cd1a4ca',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: changes top': [
        (0, '3f3dba900b9e54b5267039ffa142ae20d4ac192b7be12271cbc9e5f415cec6c3',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'd32e9dfd2967249c32500de81b10875609e6e97ab4b6bbf72f49ab738b41ea7c',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: changes verdicts': [
        (0, 'ed5ba6a8bf4a891979a905b880607ab6c9cf21fba46c26705d7c93da3296d503',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '190793d61aadd73ac1b724a71ffe42fa01942d534a1b66b9895c607ea65e652d',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: runs': [
        (0, 'd8cda444eb2916b7f119d2d804b7e918310f7a689fa1e01a629b6537ae825f16',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, 'fcc1f8d0c8728e4058c13973d40cc2c7aa85f645f06308e7871a9793377aa581',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: where with a run Prove cannot read': [
        (0, 'a348b1e6b105612cfc91a0c1ef38e995d0783ffc2e5a34a01196a8ff3a997d75',
         '8bac7e2d9d7be6c8e6c1921377837bd398ed5183951d4e3d460370b0e794ae1d'),
        (0, 'd89fa67607f22cd3e370666f146301839bf573f66e3ba3d9defda7359a915d88',
         '8bac7e2d9d7be6c8e6c1921377837bd398ed5183951d4e3d460370b0e794ae1d'),
    ],
    'verb: fix-check with a run Prove cannot read': [
        (0, '4fd09f6a5e169752c4b4bfb4db5fefb6302fd3ed1d219893752dcb5f4d7e6516',
         '4eaa49e01280b090f1931f43344bc9604eb8ee2bbca8dfb99f70d15c753fadd6'),
        (0, 'acc19a6eb962fdac75ab03a974332a73ab356fa0d9515c7929f0061de5745935',
         '4eaa49e01280b090f1931f43344bc9604eb8ee2bbca8dfb99f70d15c753fadd6'),
    ],
    'verb: runs with a run Prove cannot read': [
        (0, '051533e2d0b5bf65bdc604d26fd84cb44d174c06ffe72ca7d652f75910fa42e2',
         '1851632c70ff245f47b05858d339f574a671eba044f136d50afedcf4c337d9dc'),
        (0, 'a7d6928020ae03198ecc9085a42593eb5d1fe968843e8201febb0c9017055a43',
         '1851632c70ff245f47b05858d339f574a671eba044f136d50afedcf4c337d9dc'),
    ],
    'verb: runs all': [
        (0, 'ef04dbb887d2de964157da27049e6910afd3bdbbf9c1c9cc0bdd7c2b185bf898',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '459d32942e00faf7c8d458b917b6f56a983d77c128160c00791f7eb43202097e',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: runs no event': [
        (0, 'b54d5ac3011af1dacc5ff03671f8de8aaaaa29de1dded10c966c79a951fb749a',
         '0c9e5d610cdc67b8f54d29e4ab7657b87638708569752abab82aeb024cb34dcb'),
        (0, '820b1e1947c42f808ed423f08d8e0b6735dd059c4986dc1bca92059736a3e541',
         '0c9e5d610cdc67b8f54d29e4ab7657b87638708569752abab82aeb024cb34dcb'),
    ],
    'verb: where config': [
        (0, '5487364d6d9c41a9e3f96eac13e15988ca9d51ab794e0602e677aad1c1b53adf',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '5b8886aa63010886d8d6c8f939b053d5b6129055abd2987563a0abc4e0eb0fbd',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: fix-check config': [
        (0, '4fd09f6a5e169752c4b4bfb4db5fefb6302fd3ed1d219893752dcb5f4d7e6516',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '499fd8b69c695e43e1e822395fc17b229b1d221b6da5820f50fc0caca4f05e1a',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: compare config': [
        (0, '030c2e3b3ab46f1b4027dacc34f40f556f24a7a5a413c634056a7427326a6d0c',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '3524abdb1f2f2ded964124c57fd38759da8f5acf2066d8ccef6fddea161563aa',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'verb: changes config name': [
        (0, '6f5d8c9163adc882fd72fbade0ae19eda41f47bb1b74a24a785b0bcb78e7859b',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '2415f6f78a03bae4ebc0f99d50440e3b7c30aaad1a84bbff3efe7ee03b81afe4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: junit': [
        (0, '26d42369f27cded907417b826fe245b558f168772bd1d7ab1bee28098f812069',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: junit': [
        (0, '32f80c181d4f973d9bb008f8872169e70d7b329a2f1a5e09d9ef0665a7942dbd',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: junit two files': [
        (0, '8b23d539067d2d0bd0f872eeeb516fe651fb6cc3ac0b435688beb5ac63f8fce6',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: junit two files': [
        (0, '8ce7ca989ff783f848bc03db7e4376682bd485e90cbcde2307ed0756e080ad72',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: ragas': [
        (0, '39d4fd765f2a6e148d43f383b77032ef9563e4c477f441339f09466c9d1a89ca',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: ragas': [
        (0, '9268911fb70b7bff5a22a7ac2c6b50d0fca8bbd589d88e72b9bda0fa10de6353',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: table': [
        (0, '30117114869612967b479998dd2f5ec2bf210f050e93625d83883e3e3648e0fa',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: table': [
        (0, 'a79db1acc6c4f72186b9c41d6e5a1878756d2072d9b5590f29aef4b7c003ff97',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: openai-evals': [
        (0, '631ebe659facad275437abb781ca3e3c939b101f30fc0d2eb5b3fb5d2f796bda',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: openai-evals': [
        (0, '546bfb32476c1d6f65d7c83325051baa9f1746d729832b2ca3b0f872bca817da',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: promptfoo': [
        (0, '7ac2241f6880cefffeabf8bc364e9facd41e6d55f016337255368889fe9358c1',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: promptfoo': [
        (0, '6e67c964b90edaf0d2e886b3065b3331656dd5e6dd5622f64050abd7fb61a52e',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: inspect': [
        (0, 'dc3debfcc831e466f6ee39c21ff90fabff60a57ee4cbd2a0b533267c6ed03e8f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: inspect': [
        (0, 'f9679c3c6f5e33343281ec931279a5595a2f13e186d4157a7f1b3e6ed69655e7',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: deepeval': [
        (0, 'fbc3cf7710913715bdbfd99cc889397e2c46f06f396dad78e5923d8890697ae4',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: deepeval': [
        (0, 'e9f9a065acb8fde6e8caa8e5721a4f7e9d3ee01efc5747b0082ff85e38023135',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import: table verdicts': [
        (0, 'aab3cfd574ccb509322d9590f57168398120533d0abd223a031e9af43aea0c2d',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'import json: table verdicts': [
        (0, '3c90be7cf766f59d9ba306d79da29a1eee21d41b0e5ca398edb96a20e5cd0edd',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    "import: folder in the tool's place": [
        (0, '5af529b2e3699caff8d12abba50885e24cfb14a52a4c59b09c9646c64dcc256f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    "import json: folder in the tool's place": [
        (0, '803537bd57bb33e9cce3a930f276b35070ea83476738b9489cf0e41b6eafd25d',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'refusal: an unknown run': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f79555751bfd7aa5ecf64f31d6ebc2a29f0ef3424dd642501f548e3152a02a98'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f79555751bfd7aa5ecf64f31d6ebc2a29f0ef3424dd642501f548e3152a02a98'),
    ],
    'refusal: an unknown event': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '4b6dc61931844b4efc96de46dee3c558bf3c72163133a4b199f0d0a750a5d575'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '4b6dc61931844b4efc96de46dee3c558bf3c72163133a4b199f0d0a750a5d575'),
    ],
    'refusal: a store that is not there': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1a0f3cfc1bb314a8943e6ef0573846b416ace41508422457c6bdf67fc843aa86'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1a0f3cfc1bb314a8943e6ef0573846b416ace41508422457c6bdf67fc843aa86'),
    ],
    'refusal: a store that is a file': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'c8814095b18976c6a085f9115ed4804b0cd46c5904b0411e098a43b07f334a71'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'c8814095b18976c6a085f9115ed4804b0cd46c5904b0411e098a43b07f334a71'),
    ],
    'refusal: a folder that holds no run': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '39b84b8fca786bcdc45b22c533639d08c656c7d9a1fcc97be04ee8019fa3a246'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '39b84b8fca786bcdc45b22c533639d08c656c7d9a1fcc97be04ee8019fa3a246'),
    ],
    'refusal: no store and no config': [
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '48f1237f69642aa9cc5b0c2e64217e25ce83cb784cd97a71da347ac59bd2a8fc'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '48f1237f69642aa9cc5b0c2e64217e25ce83cb784cd97a71da347ac59bd2a8fc'),
    ],
    'refusal: no event and no config': [
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f4d92191ec1552ed61cb459d6d4347f4efd50b2c6501d91d6be127ada24bec36'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f4d92191ec1552ed61cb459d6d4347f4efd50b2c6501d91d6be127ada24bec36'),
    ],
    'refusal: a bootstrap of none': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'b8cfa90d7cab3b5d00abd90e7f03ef1764fac2e4941736eb4dd6c4503a5195c2'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'b8cfa90d7cab3b5d00abd90e7f03ef1764fac2e4941736eb4dd6c4503a5195c2'),
    ],
    'refusal: a negative seed': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'aee4c44e67fe30f5e9976408adf2eeec290010f3d0f7dd9b8ec4fb3c3d7ab3fa'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'aee4c44e67fe30f5e9976408adf2eeec290010f3d0f7dd9b8ec4fb3c3d7ab3fa'),
    ],
    'refusal: no hazard-ratio ceiling': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '89f48cf408606936884dd43807ccd27e4d5e48a8f2afb3da2f46c94eb6f912c3'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '89f48cf408606936884dd43807ccd27e4d5e48a8f2afb3da2f46c94eb6f912c3'),
    ],
    'refusal: an alpha out of range': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '5f4a5e509f817167d2c68e04a42596bb689c07af64b9f8e4145876dc9410867f'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '5f4a5e509f817167d2c68e04a42596bb689c07af64b9f8e4145876dc9410867f'),
    ],
    'refusal: a ceiling out of range': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '82ca4bf3158c4b8b37a59261d02d96320251bf066be39b57f0a3f7904382c1ec'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '82ca4bf3158c4b8b37a59261d02d96320251bf066be39b57f0a3f7904382c1ec'),
    ],
    'refusal: no ceiling': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '6380d629b7c0f3a9228c692c3dc7f2f4c9751d84542ad97e3026cddd4754b391'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '6380d629b7c0f3a9228c692c3dc7f2f4c9751d84542ad97e3026cddd4754b391'),
    ],
    'refusal: inputs other than all': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'bf3351262d73850ba91272e61e73e926d26c462834dbd0623965cee067df18a7'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'bf3351262d73850ba91272e61e73e926d26c462834dbd0623965cee067df18a7'),
    ],
    'refusal: neither inputs nor failing-from': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'dd3e2cfcc69306cbd1b9b5088c895f05da81b6a7ab69d53e439f9c99c3a1df85'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'dd3e2cfcc69306cbd1b9b5088c895f05da81b6a7ab69d53e439f9c99c3a1df85'),
    ],
    'refusal: min-failures without failing-from': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '37c18a074723a06a45fef84515df7236ba6d0499f059042bfeade41bb18f644c'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '37c18a074723a06a45fef84515df7236ba6d0499f059042bfeade41bb18f644c'),
    ],
    'refusal: the same run twice': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'b66560fbee281491770978e488d09f65e37d3c561b472fe0094b7bd231192cd1'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'b66560fbee281491770978e488d09f65e37d3c561b472fe0094b7bd231192cd1'),
    ],
    'refusal: verdicts matching neither run': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '4a6d541119f41ac260a5594f1f7deb093cc455fac4e7065e47afd9efbb31d6ed'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '4a6d541119f41ac260a5594f1f7deb093cc455fac4e7065e47afd9efbb31d6ed'),
    ],
    'refusal: the same run by two words': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '243cf5d973cf1a5952405c4490927e0db7d28d9d39e5bbd0c15dc56d441a1b51'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '243cf5d973cf1a5952405c4490927e0db7d28d9d39e5bbd0c15dc56d441a1b51'),
    ],
    'refusal: the selecting run as an arm': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'ae59f3f409221167c481f0600787600487c2f6013ce9861449ef4553b55c51be'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'ae59f3f409221167c481f0600787600487c2f6013ce9861449ef4553b55c51be'),
    ],
    'refusal: a verdicts file that is not there': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'fd641c9d44ea84a093672b76170738012149f55585148ad2ba82112234ea64f7'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'fd641c9d44ea84a093672b76170738012149f55585148ad2ba82112234ea64f7'),
    ],
    'refusal: a verdicts file matching nothing': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '41c13ebf37859e096e9a64acff586fba5e1c9e9d783f3a9359db1cbcde3ee1e2'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '41c13ebf37859e096e9a64acff586fba5e1c9e9d783f3a9359db1cbcde3ee1e2'),
    ],
    'refusal: compare on runs with no traces': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '00f9d2a8a6bc03eda7a4d28c92359f31594f3d51dc82449497738721fcd418d5'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '00f9d2a8a6bc03eda7a4d28c92359f31594f3d51dc82449497738721fcd418d5'),
    ],
    'refusal: a config that is not there': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f574ceeefc8f1064f8049a3c047f1a0d623d19e39b8090825110b975ca158705'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'f574ceeefc8f1064f8049a3c047f1a0d623d19e39b8090825110b975ca158705'),
    ],
    'refusal: a store name the config lacks': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'fca1634a118687cd54d4e1cc6a23cabd091188fc9f854b0f181bdfdef0679a50'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'fca1634a118687cd54d4e1cc6a23cabd091188fc9f854b0f181bdfdef0679a50'),
    ],
    'refusal: runs on a store that is not there': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1a0f3cfc1bb314a8943e6ef0573846b416ace41508422457c6bdf67fc843aa86'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '1a0f3cfc1bb314a8943e6ef0573846b416ace41508422457c6bdf67fc843aa86'),
    ],
    'refusal: previous and latest that cannot be ordered': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '9eb2ce32171fea0e0b583325612df55bb3ef73376a92cc35220f328feea3db40'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'c64367a959c6156fe8916829aacb50b0bce3ed3337a541556361244d0fe0d214'),
    ],
    'refusal: latest of two that cannot be ordered': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '4c0e3e18d40dd36dd4539dae41bbb310d41a5c7127596e13e7f9b89ce47f7a50'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'ba5c202178530e9abff2e25d52516fdda825487679c596f553ed10dd67a9bef1'),
    ],
    'refusal: latest alone, of two that cannot be ordered': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '852dcb73942acce9f0e95c8de73b0335fb2e08a659a35624632171852b0e6c45'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '852dcb73942acce9f0e95c8de73b0335fb2e08a659a35624632171852b0e6c45'),
    ],
    'import refusal: a file that is not there': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '9b88e37d0da74047a4d5b52821304de4d241112ac8a99086b8a7751f64acca5d'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '9b88e37d0da74047a4d5b52821304de4d241112ac8a99086b8a7751f64acca5d'),
    ],
    'import refusal: a run name in use': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'e4343b317dd3a34f52d024880ead91bc0e1da572460ae12c8c5f319a0a618493'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'e4343b317dd3a34f52d024880ead91bc0e1da572460ae12c8c5f319a0a618493'),
    ],
    'import refusal: a metric no case carries': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'ae44815c235e18453d0e64160a194d1a8c0f4aca29b2586e09f3cbb842179a32'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'ae44815c235e18453d0e64160a194d1a8c0f4aca29b2586e09f3cbb842179a32'),
    ],
    'import refusal: a start with no zone': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '8cc91ac88ceb5abae5e1d6af503dc744a80838600b28d45a0084291b46e907d6'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '8cc91ac88ceb5abae5e1d6af503dc744a80838600b28d45a0084291b46e907d6'),
    ],
    'import refusal: a start that is not a time': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '98a86da6d0d1444f57e528aaf5e3b9d6929ead6eedd17813ca4a9e3c97153481'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '98a86da6d0d1444f57e528aaf5e3b9d6929ead6eedd17813ca4a9e3c97153481'),
    ],
    'import refusal: a cut with no side': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a9dc531feeba1b566a4d05369601702298013374b139cb4d1b125f6267721df2'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a9dc531feeba1b566a4d05369601702298013374b139cb4d1b125f6267721df2'),
    ],
    'import refusal: a run name that cannot be a folder': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a21440221721180faa8a172c50f6fe40270e2d8dc82eee23ecbb33cf87b42572'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a21440221721180faa8a172c50f6fe40270e2d8dc82eee23ecbb33cf87b42572'),
    ],
    'import refusal: no store and no config': [
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '76f07257adb1931699ced58702328905aa2100a4199abee712fd6c91a62dbbe8'),
        (2, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         '76f07257adb1931699ced58702328905aa2100a4199abee712fd6c91a62dbbe8'),
    ],
    'import refusal: a tool not in this install': [
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a86cc4b8b0f0d6c2e0aaf6f8e27b34fd42547cd857725f87e41d4cb870e0dc52'),
        (1, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
         'a86cc4b8b0f0d6c2e0aaf6f8e27b34fd42547cd857725f87e41d4cb870e0dc52'),
    ],
    'save: where': [
        (0, '059ed63192014937228496010e478c4b67d159e5988de759d30e458e688ddbf9',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '61339e61de9f31b4b11956cfd6b5649e3dcbea2b80fa73ebf3ee9e49cd14bc5f',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ],
    'out: where': [
        (0, '471de063e86507b69d589ed54f039e084cbc45403cb5f6dd3bdff94e8a6d498a',
         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
        (0, '581a94ae11c70fa6fe8fc12b8c4529ee97b142aa1b3d027762bbc5af5a5fc3c8',
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
        (0, 'bc5307878e7a0246b9ae68cd3e728041e7343869c325573efbecf83db1b8bb95',
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
        (0, '302172031abae4cf4c5d2ade9e8711c9867f6b1ea4843b854298dd6aa740c92b',
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
        (0, 'e5e425507cdf9059d47c3f96845a74d2b5b9dd261e99cac15957f0a37933ca4d',
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
    return hashlib.sha256(text.replace(str(work), "<WORK>").encode("utf-8")).hexdigest()


def run_case(tmp: Path, label: str) -> tuple[list[tuple[int, str, str]], Path]:
    kind, steps = CASES[label]
    work = workspace(tmp)
    got = []
    for step in steps:
        ran = (cli if kind == "trace" else cli_import)(work, step)
        got.append((ran.code, _digest(ran.out, work), _digest(ran.err, work)))
    return got, work


# ---------- TF13-32 ----------


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CASES])
def test_tf13_32_every_output_is_as_main_prints_it(tmp_path: Path, label: str) -> None:
    got, _work = run_case(tmp_path, label)
    assert [tuple(g) for g in got] == [tuple(p) for p in PINNED[label]], label


def test_tf13_32_a_every_case_is_pinned() -> None:
    assert set(PINNED) == set(CASES), sorted(set(PINNED) ^ set(CASES))


# ---------- TF13-33 ----------

HELPS: dict[str, tuple[str, list[str]]] = {
    **{f"{verb} help": ("trace", [verb, "--help"]) for verb in ("runs", "name", "where", "compare", "fix-check", "changes", "handover")},
    "import help": ("import", ["--help"]),
    **{f"import {tool} help": ("import", [tool, "--help"]) for tool in
       ("deepeval", "ragas", "table", "junit", "promptfoo", "inspect", "openai-evals")},
}
HELP_PINNED: dict[str, str] = {
    'runs help': '894f28cb20c9785ea6707f2c062ed5695e33ef7b92e3c1cebe2ea4c85552fcfa',
    'name help': '684ff0cfba5808cd12acc3266a73d4fb73fd1f921a8fc1fbb1767137e413c503',
    'where help': 'e59d9ba1fa932127a7c76e6f2286ac5b36bbd28219289159711b4024627618a0',
    'compare help': '92552d3fa83e131ee875e8417175def029a56bada0d0a1fd3afd8c000fe6cbb0',
    'fix-check help': 'e6b54d82cd40ab0b8cac8db007b858fd9a286e4bdfa6815dd58c7cf923b16497',
    'changes help': '79d1c0cbacb5c852c9e4f7185734056811d5591aa325d6f14c0438d21d7365e4',
    'handover help': 'ea2c22ea7a6b4c73156ebf0317ec6a7d412d917e5a3192a1c8f27c8b430e447b',
    'import help': '3550d042f3e2967f6c8e308f83eb83a371a333603ca3d013838c14879ddd3dd9',
    'import deepeval help': 'fa997eb02bd609e9e62e14a7ab4c9ca960e33b3534cefe5a259631424ab1390d',
    'import ragas help': '2fd4273275204f7ff58bcd03e1acb7a66b8861b22fe08d2b9ea6149893dbadd9',
    'import table help': '82a3700050edd09b2a9e9c6f76ee978d986576af4af29bf5cdb1ce5e86620dd9',
    'import junit help': '1e27de024b2bfb2472992d18d9e1d08eb987dbbfc3086122bf3c53f0163ad0ef',
    'import promptfoo help': '630c67a185ba860b0c1ff7fb21c7dc7062bfbb812143388797ea46c5cab8188c',
    'import inspect help': '78113700c8b80fa81f7569220f205f03972a13514ee9df32e055b0edff3abcd6',
    'import openai-evals help': 'df22a5490a1ba56aee1b9a2eb1b8dfcc34b89394530b244e198793ea621e8587',
}


@pytest.mark.parametrize("label", list(HELPS))
def test_tf13_33_every_help_is_as_main_prints_it(tmp_path: Path, label: str) -> None:
    kind, argv = HELPS[label]
    work = tmp_path / "w"
    work.mkdir()
    ran = (cli if kind == "trace" else cli_import)(work, argv)
    assert ran.code == 0 and ran.err == ""
    assert _digest(ran.out, work) == HELP_PINNED[label], label
