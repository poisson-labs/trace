"""BD-6: the failure breakdown pair's tests are frozen. Green by construction: the digests of its
files as Session A froze them on ``trace-breakdown-a``, as TF23-35 and TF6-36 hold theirs. A
ruled change to one of them moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "test_bd_colour.py": "8f6cee449d05e826625d666d949f185284bdc7455522874c44157de424ccb8fb",
    "test_bd_json.py": "c1fd825d54f04cac87fca803e184ad1aa3436cd872ab0f808608d3c22899b0e3",
    "test_bd_section.py": "d7635eb5733dccf3bb083a33ec40eaaf0d16cbf6de0ed9a8d422b87dfc24225a",
    "test_bd_table.py": "588a07de139bd5066d598547dac43d4a0ff6e7b062fab2e7374e7525c2eeda43",
    "test_bd_terminal.py": "ff6b9f113a10ba657a0f1c60c03abe89dabf522769770ad499fca83aa569db77",
    "test_bd_unchanged.py": "6d88112e28c1d02976724abbae8ded059924dc484e75e7f4d6460ce69f5ba74e",
    "breakdown_support.py": "42cb664ccdc12020f070450fe377612741ab8ec2ccc4fe0bca7fe50ca3f472e4",
    "fixtures/breakdown/main-pins.json": "09677790dff4d2a2eca9d2a3e275fad21b06df9022a9e4ce3b6e4386e2f678a7",
    "fixtures/breakdown/make_main_pins.py": "3cea70c32b1db0814651fa33b01970668358e04cc3dd2b20650cd188c8bb6314",
    "fixtures/breakdown/mockups/breakdown-prove-140-plain.txt": "a1c31c7b7739d38ce1a196875d9adbf94d269bf96608eb4bfd20cf9684d998c6",
    "fixtures/breakdown/mockups/breakdown-prove-140-pretty.txt": "53527a3a055d58bf7f8947e6e914173c0c1702767bda2a19048ac3e1a7e822af",
    "fixtures/breakdown/mockups/breakdown-prove-80-plain.txt": "a753b5f8f30df562a2536d994a02cbbb24364c16c3112c1deb4cc35719aac1de",
    "fixtures/breakdown/mockups/breakdown-prove-80-pretty.txt": "f8216da7b14f213d2bd0553661b635d3fb67fe8f54fa63ff85aa2eee90ebb0b3",
    "fixtures/breakdown/mockups/continuous-deepeval-80-pretty.txt": "437de26cc99f556fc46105f79646f328ba0f478083a368455168c75530862a72",
    "fixtures/breakdown/mockups/continuous-inspect-80-pretty.txt": "55f626ace33699971da4fe29668e3cb9c52105ba08a169db39d0a2c966fc276f",
    "fixtures/breakdown/mockups/continuous-proposed-deepeval-140-pretty.txt": "0ade559bb1b290f819a81ddc2755163067764a354fb4284639b7005242d0e7c4",
    "fixtures/breakdown/mockups/continuous-proposed-deepeval-80-pretty.txt": "a42618b71a4f9b32b7207942804bf29f0083b5a96a7193bdbdc9492fefe5c3ea",
    "fixtures/breakdown/mockups/continuous-proposed-inspect-140-pretty.txt": "442144b28260558d17fcfe91070f42d776ee41ec4dbc34d16f5618bc7fbf5579",
    "fixtures/breakdown/mockups/continuous-proposed-inspect-80-pretty.txt": "85d1502c21994c4961877626202671857e16ecf9429ef5982b83197316c14b73",
}


def test_bd_6_no_frozen_breakdown_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN


def test_bd_6_every_file_of_the_pair_is_frozen() -> None:
    mine = {p.name for p in TESTS.glob("test_bd_*.py")} - {"test_bd_frozen.py"}
    fixtures = {str(p.relative_to(TESTS)) for p in (TESTS / "fixtures" / "breakdown").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    assert mine | fixtures | {"breakdown_support.py"} == set(FROZEN)
