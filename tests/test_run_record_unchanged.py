"""RUNREC-40 to RUNREC-42: what the run record leaves as it is (invariant 5).

No verb's plain or ``--json`` output changes on imported runs, and the import's own plain and
``--json`` output keeps the shape TF21 holds: the import is run, then ``runs``, ``where``,
``fix-check``, ``changes``, ``compare`` and ``name --list`` over what it wrote, and every exit
code and both streams are byte for byte what the pinned main printed, the store's and the
fixtures' folders written as placeholders. Green on main by construction; a deliberate change moves
its digest here. TF21-64 already pins the import's ``--json`` and the stored columns a verb
reads, and TF6-1 every verb's output on the committed Prove stores."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import FIXTURES
from run_record_support import READERS
from look_support import Ran, trace
from signals_support import IMPORTS, STARTED, run_import


def _tf21(key: str) -> Callable[[Path, str], list[str]]:
    return lambda root, run: [*IMPORTS[key], "--store", str(root), "--run", run, "--started", STARTED]


ARGV: dict[str, Callable[[Path, str], list[str]]] = {
    **{k: argv for k, (_, argv) in READERS.items()},
    "junit-b": _tf21("junit-b"), "ragas-raft": _tf21("ragas-raft"),
    "deepeval-b": _tf21("deepeval-b"), "table-b": _tf21("table-b"),
}
FAST_PAIRS = [("junit-a", "junit-b"), ("ragas-base", "ragas-raft"),
              ("promptfoo-old", "promptfoo-new"), ("openai-evals-old", "openai-evals-new"),
              ("inspect-eval", "inspect-json")]
SLOW_PAIRS = [("deepeval-a", "deepeval-b"), ("table-a", "table-b")]
EVENT = ["--event", "missed"]


def _digest(ran: Ran, places: dict[str, str]) -> str:
    text = f"{ran.code}\n{ran.out}\n{ran.err}"
    for path, word in places.items():
        text = text.replace(path, word)
    from pin_support import as_pinned

    # Prove's version, where Trace prints it, is written as the pins hold it (pin_support.as_pinned)
    return hashlib.sha256(as_pinned(text).encode("utf-8")).hexdigest()


def outputs(tmp: Path, pairs: list[tuple[str, str]]) -> dict[str, str]:
    """Every import of ``pairs`` (plain into one store, ``--json`` into another under the same
    names) and every reading verb over the plain store, plain and ``--json``, by a label."""
    plain, as_json = tmp / "store", tmp / "store-json"
    places = {str(plain): "<store>", str(as_json): "<store>", str(FIXTURES): "<fixtures>",
              str(tmp): "<tmp>"}
    got: dict[str, str] = {}
    keys = [k for pair in pairs for k in pair]
    for key in keys:
        ran = run_import(ARGV[key](plain, key))
        got[f"import {key}"] = _digest(Ran(ran.code, ran.out, ran.err), places)
        ran = run_import([*ARGV[key](as_json, key), "--json"])
        got[f"import {key} --json"] = _digest(Ran(ran.code, ran.out, ran.err), places)
    verbs: list[list[str]] = [["runs"], ["name", "--list"], ["where", keys[0], *EVENT]]
    for a, b in pairs:
        verbs += [["fix-check", a, b, *EVENT, "--inputs", "all", "--max-mde", "0.5"],
                  ["changes", a, b, *EVENT]]
    verbs.append(["compare", pairs[0][0], pairs[0][1], *EVENT, "--max-mde-hr", "1.5"])
    for argv in verbs:
        for extra in ([], ["--json"]):
            read = trace([*argv, "--store", str(plain), *extra])
            got[" ".join([*argv, *extra])] = _digest(read, places)
    return got


# as the pinned main printed them, but for the four fix-check and changes readings of the
# Ragas pair, whose section says how many tries had no outcome
MAIN_FAST: dict[str, str] = {
    "import junit-a":
        "991d33a73c8bebd27ad0b9698d321b5318cb65f17362ef0385f6a3fcd438697e",
    "import junit-a --json":
        "d9beff6b683e25ffb3afeb218c74b40d6d50e34851aa63d346976eba29ea089a",
    "import junit-b":
        "8cb33da6d96f74df674436d5da426272e74a11f078f1f3b6a8b69b7c4dd63222",
    "import junit-b --json":
        "27fa906fec3f4d8c5cebc7563d62f6f679627f0b218ccfb48d6b3fff54f77e6f",
    "import ragas-base":
        "98ea91370794f4ffcccdeafd7e1b684f0ea1422581a37d30cfd0074d5eb6345e",
    "import ragas-base --json":
        "00ee38d2f1e7632cc15764450238e444229383e3bb8bf7d74a390b8f95db26b1",
    "import ragas-raft":
        "162d20e131eef40f5f74dd071efc6fb6f886fc6a37c0bd0a7b5d672682d4886d",
    "import ragas-raft --json":
        "afb723719353563aef0222345a10bee284843594cb8cebafb296ebff1ae29ada",
    "import promptfoo-old":
        "85192864a8f3a4ba520d832e48096a95521485adea0e3e827a9dea9bf3b84014",
    "import promptfoo-old --json":
        "87b886035b7824d77d8d183bda3d7719629e670890efbc9ceee9f6e7c0a38e20",
    "import promptfoo-new":
        "ab59b12ad34c970a844cc5453f6437353f79f06e835f1eb4fdb5e9e236615a09",
    "import promptfoo-new --json":
        "b1ac265d7e7398643cdda316728991803cf41a0ad3ed4b9198879037e6b9287c",
    "import openai-evals-old":
        "086c0784cf053cba430d2d36941b37626b0837637cc8ce054c0bb75b814139c2",
    "import openai-evals-old --json":
        "a73b3ec219e84ea69eb576745780c93b48595b9b561c31346e5e795b2298ad2b",
    "import openai-evals-new":
        "703a33969d1cc8cc4052cabb24831372ec8fa2ceaf2b0539041632186a020b55",
    "import openai-evals-new --json":
        "76b37ffaf67f032d6a0e76975239643b16933dcccc095ded45e3d1d1f4923e7c",
    "import inspect-eval":
        "96c058e29961a48cb62af02a4d8e64c9ae85592844ec719c74cfd914f11f31e5",
    "import inspect-eval --json":
        "015de7c1d33d413f63f7144b55f85119a3a66fd35c087bb0dbe9f90b8a61ae99",
    "import inspect-json":
        "31a17614c6f94a38cd01ce2e9473bdc57ac0bd61b88aa6667e18dd63b3aa6399",
    "import inspect-json --json":
        "1c38edd4448693127313b26570ba620bb62448806c747236d114d795eb21a815",
    "runs":
        "ef15f9360ef1cdbde073d6be062c92f817b29cecad35a06ab2cd25fea4e0f710",
    "runs --json":
        "b9f1e0098417ab62ddc0436108c95ac8590d367b3c34da171694741d7ea1c0f8",
    "name --list":
        "0a863737c0d3a332eb329ecb83bef0509b2b7b269a9b2075383e44a02c5fc3f0",
    "name --list --json":
        "db3edfea70a5a2b8c0917a63babb1ad965e7ce2e38a63c65f0ef12ca91d58281",
    "where junit-a --event missed":
        "237958984a97f3d70c70b22ec5af37a691e83cd45263e8d9feb48d45492e0d1c",
    "where junit-a --event missed --json":
        "94b1e1a9ec31e272acbc283b2450fc3c46233ae1fe3ae7dd4f5a731d4963ff60",
    "fix-check junit-a junit-b --event missed --inputs all --max-mde 0.5":
        "94a44a83f89185b38aaa8abbd06ed9e2cecbb00abafcb96066571f0162932c70",
    "fix-check junit-a junit-b --event missed --inputs all --max-mde 0.5 --json":
        "56b337d90497dab491681a7fee5be99fe1a6bb1391c560be331e91c5eded263b",
    "changes junit-a junit-b --event missed":
        "7c068abd33af08d24eb8172a8d19401750a41fe3abece507f6c87f6b48f6343f",
    "changes junit-a junit-b --event missed --json":
        "aa1d3d19d222fe2f37ef0222dc2db2e706482fb30a1c572ed4f98e6fa7127f73",
    "fix-check ragas-base ragas-raft --event missed --inputs all --max-mde 0.5":
        "b144013bf9f5dcb5abed72b5a986a23e0d1ce119324a7d32f1713190eb4a0aaf",
    "fix-check ragas-base ragas-raft --event missed --inputs all --max-mde 0.5 --json":
        "aa197f0551206175c647afa157e32dfafd845a11284afdc621f8ef7c02409bcd",
    "changes ragas-base ragas-raft --event missed":
        "5b3486b74e33334687a60b14b3e45496c215fa0b59ee124dc9f6ca599ad2b55d",
    "changes ragas-base ragas-raft --event missed --json":
        "e963002e824491298d0556fe365d6b53746714000e073a4605e9044727344105",
    "fix-check promptfoo-old promptfoo-new --event missed --inputs all --max-mde 0.5":
        "948a5c702342e07a5ac24a0a4a17606b94ee27901a21591c1a6993bfc6bd8baa",
    "fix-check promptfoo-old promptfoo-new --event missed --inputs all --max-mde 0.5 --json":
        "be3e524f071c74e25f92c4d852e0fd1057dc5bbe2b07e83cc1f41f1df6901c24",
    "changes promptfoo-old promptfoo-new --event missed":
        "ba89d2cb1a1a9998a4f498f41490c9e3eb427650957c9718fe0fdfe670c7a852",
    "changes promptfoo-old promptfoo-new --event missed --json":
        "5c79f2f9972df2fc48b8d68668c3d2b1a91ff74cdc09f5fe6227b0d96e07c547",
    "fix-check openai-evals-old openai-evals-new --event missed --inputs all --max-mde 0.5":
        "83db41fc74332dae4c176310e43f09752d4761662ab3c5d54188e6d55c56aba7",
    "fix-check openai-evals-old openai-evals-new --event missed --inputs all --max-mde 0.5 --json":
        "0634e28ddb2b7707a88ec855101e2bd085279631b3b40c0e837dfbc76f3c8afc",
    "changes openai-evals-old openai-evals-new --event missed":
        "7639f7af6303284f13564833ac52bc3b5508fe91c012207a00784eb481f025b3",
    "changes openai-evals-old openai-evals-new --event missed --json":
        "e42baef8ca0d59f634954a7f1e89e6e4bd6ab7eda6cdd4c1a52da453b58639b6",
    "fix-check inspect-eval inspect-json --event missed --inputs all --max-mde 0.5":
        "99e89214b3f63ce286395b4d458260050a4b7cdd3321c28e0a844cafd1310441",
    "fix-check inspect-eval inspect-json --event missed --inputs all --max-mde 0.5 --json":
        "cd3c2bb2736636cb8e69bd9e6c75d3f66680893c3a094b0d5a4edf08883e31ce",
    "changes inspect-eval inspect-json --event missed":
        "23f69f7ea8df989f6e0b188a753b6da40e714153942588ed37f7e8ba7210445f",
    "changes inspect-eval inspect-json --event missed --json":
        "2e8fd15f2c7ad42cbf037e084453ed99539d2dd6ca54efe5ff3c73ea877d801c",
    "compare junit-a junit-b --event missed --max-mde-hr 1.5":
        "4dc033049cbcbca467979cd788935ef6aad3f2a2dbd5e662dd959821a15549e2",
    "compare junit-a junit-b --event missed --max-mde-hr 1.5 --json":
        "4dc033049cbcbca467979cd788935ef6aad3f2a2dbd5e662dd959821a15549e2",
}
MAIN_SLOW: dict[str, str] = {
    "import deepeval-a":
        "67a95c53eb08d4f70080687c73eeaff3610d5a6b23c1f2fac181ddd86cd36a0d",
    "import deepeval-a --json":
        "70452f30955b9fd0e9bcd817776622a0baa458f14072da4e1ab772671be87564",
    "import deepeval-b":
        "ec23a1251fa28e637e33e5484a61ac762d34338c310576f56e805ab563041daa",
    "import deepeval-b --json":
        "5da09b26077d9de0255067d853a331691487a95166a072933bbae28f7427202f",
    "import table-a":
        "ff3127e2a1f6f89deba65a9614f9b4bb671726869d746004c5e0fc5c25c19d0e",
    "import table-a --json":
        "68809e9ec527ab3fdcf474cdfd54cc36c04af07d4f1ec209999f1d95541dffbe",
    "import table-b":
        "08d9adb1874b87364d186c2f0c34677a285a1828179b43204a2c3beb37238941",
    "import table-b --json":
        "1671b0fde50229997779c7b9a954fde9ca24913bffe78288b2505c3bf83c416a",
    "runs":
        "edf3c3f57cd221b631dcd544d0fe6e8e7ef449d4e4230887e4792056578024f8",
    "runs --json":
        "1846724915730817c36e08acc2624126f9cad7ac03fa9b275cc0747b5b9d223c",
    "name --list":
        "0a863737c0d3a332eb329ecb83bef0509b2b7b269a9b2075383e44a02c5fc3f0",
    "name --list --json":
        "db3edfea70a5a2b8c0917a63babb1ad965e7ce2e38a63c65f0ef12ca91d58281",
    "where deepeval-a --event missed":
        "0f0bc4da906d0f6519c6299690de107b6b5ccd064da9d73e9f0dd5d269e7f858",
    "where deepeval-a --event missed --json":
        "9dd71cf9054ddc0304e9588b12b58ed3cb31ebaf11daddf4973805a74dd3fd1f",
    "fix-check deepeval-a deepeval-b --event missed --inputs all --max-mde 0.5":
        "85aa2b55babfb00b63e790d9e1a85d425bebca8b20f6313f28ceba48f67cd21b",
    "fix-check deepeval-a deepeval-b --event missed --inputs all --max-mde 0.5 --json":
        "1cf48c2907953317b75a1d20774a9588bdf187f00ea2831cf69d9ef44ac9d2ef",
    "changes deepeval-a deepeval-b --event missed":
        "fa90d3305916efd1e470378289f437f8c907360c1390232229766a91377a2905",
    "changes deepeval-a deepeval-b --event missed --json":
        "560f3247d9ba374cd736ed9e040d962bdf1479da2298521ef1bb2a89d7d80493",
    "fix-check table-a table-b --event missed --inputs all --max-mde 0.5":
        "e6be2dfdf02e8b0a384481586183eb11d9621cf096913e61967ae8d6252d50d0",
    "fix-check table-a table-b --event missed --inputs all --max-mde 0.5 --json":
        "5b3c9b2337f91456fcd438b43609b7defa078e85bf39edb834d588fad6508bc6",
    "changes table-a table-b --event missed":
        "008b19151a2ad16e63c6f2167bd98baac176d374d6c7dba106c29d7297dbdef5",
    "changes table-a table-b --event missed --json":
        "87eb3d04f48751c326d70426faed79729a55f2ebda3630943cee631f7a96b60c",
    "compare deepeval-a deepeval-b --event missed --max-mde-hr 1.5":
        "d4d24a3ef836fa4a2764f4eabcfd78ea2a28535470739a4fed26d9e56046099d",
    "compare deepeval-a deepeval-b --event missed --max-mde-hr 1.5 --json":
        "d4d24a3ef836fa4a2764f4eabcfd78ea2a28535470739a4fed26d9e56046099d",
}


def test_runrec_40_every_reading_verb_and_the_import_print_as_on_main(tmp_path: Path) -> None:
    got = outputs(tmp_path, FAST_PAIRS)
    assert set(got) == set(MAIN_FAST)
    assert {k: v for k, v in got.items() if MAIN_FAST[k] != v} == {}


@pytest.mark.slow
def test_runrec_40_slow_the_large_imports_print_as_on_main(tmp_path: Path) -> None:
    got = outputs(tmp_path, SLOW_PAIRS)
    assert set(got) == set(MAIN_SLOW)
    assert {k: v for k, v in got.items() if MAIN_SLOW[k] != v} == {}


def test_runrec_41_the_import_json_keeps_its_keys(tmp_path: Path) -> None:
    import json

    out = run_import([*ARGV["junit-a"](tmp_path / "s", "r"), "--json"])
    assert out.code == 0, out.out + out.err
    assert list(json.loads(out.out)) == [
        "schema", "verdict", "sentence", "run", "store", "tool", "files", "declared", "started",
        "rows", "cases", "repeats", "outcomes", "no_outcome", "counts", "next"]


def test_runrec_42_the_runs_listing_never_shows_the_stores_own_folder(tmp_path: Path) -> None:
    root = tmp_path / "store"
    out = run_import(ARGV["junit-a"](root, "r"))
    assert out.code == 0, out.out + out.err
    listing = trace(["runs", "--store", str(root), "--json"])
    assert listing.code == 0, listing.out + listing.err
    assert ".poisson" not in listing.out
    import json

    assert [r["run_id"] for r in json.loads(listing.out)["runs"]] == ["r"]
