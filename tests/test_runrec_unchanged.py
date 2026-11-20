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
from runrec_support import READERS
from tf0_support import Ran, trace
from tf21_support import IMPORTS, STARTED, run_import


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
        "6ae6f825cec6175c330b725646b3679828fa52f4f2d1a79f403889002a6bcf5d",
    "fix-check junit-a junit-b --event missed --inputs all --max-mde 0.5":
        "94a44a83f89185b38aaa8abbd06ed9e2cecbb00abafcb96066571f0162932c70",
    "fix-check junit-a junit-b --event missed --inputs all --max-mde 0.5 --json":
        "2bd9c27e89cf14a2882001760217d156a7ad2ad0119b7e0a19f9850729e8dafc",
    "changes junit-a junit-b --event missed":
        "7c068abd33af08d24eb8172a8d19401750a41fe3abece507f6c87f6b48f6343f",
    "changes junit-a junit-b --event missed --json":
        "aa1d3d19d222fe2f37ef0222dc2db2e706482fb30a1c572ed4f98e6fa7127f73",
    "fix-check ragas-base ragas-raft --event missed --inputs all --max-mde 0.5":
        "b144013bf9f5dcb5abed72b5a986a23e0d1ce119324a7d32f1713190eb4a0aaf",
    "fix-check ragas-base ragas-raft --event missed --inputs all --max-mde 0.5 --json":
        "f5c2e1c8c210676fcc54b4d6606089682db736583b37fb832fb520873437cc56",
    "changes ragas-base ragas-raft --event missed":
        "5b3486b74e33334687a60b14b3e45496c215fa0b59ee124dc9f6ca599ad2b55d",
    "changes ragas-base ragas-raft --event missed --json":
        "a3ccd76406e75bef811955f2f4274768e7df65ec2341a74168df34d8896bf06d",
    "fix-check promptfoo-old promptfoo-new --event missed --inputs all --max-mde 0.5":
        "948a5c702342e07a5ac24a0a4a17606b94ee27901a21591c1a6993bfc6bd8baa",
    "fix-check promptfoo-old promptfoo-new --event missed --inputs all --max-mde 0.5 --json":
        "a78fa64340a7273c8aa1bbd84e99d2ca3afe674b18c4e72058f780f372bb95ee",
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
        "22403b58d761a51041227bbcfb3aab27cf647b0f81931a993a3915debc824137",
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
        "9c645b738c04866d650a15b03c0e4c6d98ab168dcd5a36779d1109f83756dc2b",
    "fix-check deepeval-a deepeval-b --event missed --inputs all --max-mde 0.5":
        "42bcda89bfa4ade5845fa83354160b79b258a862945ee40063d344f19acbc13c",
    "fix-check deepeval-a deepeval-b --event missed --inputs all --max-mde 0.5 --json":
        "72c2bff908fa7edc140cf89782e3ad2f9f13084bb7c94de9b608e9a6c2a641f0",
    "changes deepeval-a deepeval-b --event missed":
        "7d3d12a3defb039babf0549f4509b2fd38e9597fed80b5e8ccc20966734b8daa",
    "changes deepeval-a deepeval-b --event missed --json":
        "42c8d8bc62126db7f26072472373f0673718d47a1191ec180622e5bb22325788",
    "fix-check table-a table-b --event missed --inputs all --max-mde 0.5":
        "12662229211201b02f4a0fcb9c0d770c80d6602e3061958fd1e208ed6565910e",
    "fix-check table-a table-b --event missed --inputs all --max-mde 0.5 --json":
        "b9c133a8fcfae2f5a539fcee45df982ac88ebfca8e82a2ec7f45a5cc71b27d1d",
    "changes table-a table-b --event missed":
        "d8c7d915b7f6535fc1f351658b4d3b436623cddab1d2bad699d86b115942af7b",
    "changes table-a table-b --event missed --json":
        "cf1f97d8d847b48d3b75423d67a040f3fe11ede4de423112b205d540f81d082f",
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
