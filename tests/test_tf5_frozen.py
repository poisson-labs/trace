"""TF5-99: TF5's tests are frozen. Green by construction: the digests of its files as its
Session A froze them on ``trace-tf5-a``, as TF26-72 holds TF26's. A ruled change to one of them
moves its digest here in the same commit."""

from __future__ import annotations

import hashlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FROZEN = {
    "tf5_support.py": "c9fb7f7fa4b7968bb13bcc06bc1806379c0a835960515815661d8a3398b5418b",
    "tf5_pins.py": "de21957269747c522c62d068d66e61245c3eb6037e93bf3cc238a47a4249a8a4",
    "test_tf5_unchanged.py": "111165aaa3c0d4b8e5734ff270e9bd42dafb7ab94885ccb65ca330a50349efad",
    "test_tf5_blocks.py": "5ba9df36a8e7049a2dc442af51a35d69f3d00eaec9360747d40d8cd4217b25c8",
    "test_tf5_readers.py": "f216740c2ee2c2879ed280d0805f237f4e557380b6e04d9e451a8a7e70022a80",
    "test_tf5_stale.py": "c54f706c1956a2c2f46dab7867f3076f90ab7b7c0f3fc2248d548dc079cf3e2d",
    "test_tf5_readme.py": "d665ddb2d71fd2e13fcc76402b60f55d6861765882715d1baecf73dc09769cf6",
    "test_tf5_changelog.py": "8f4d8d98b42e42f93f782d2d4fc20541f56e116d7114c3682fe192e3bd46e9c5",
    "test_tf5_docs.py": "7d015f2860c067ebcbce9571a114703f352e2cf285545795e3880e5268a79bf7",
    "test_tf5_recipes.py": "a96e48f40a77f2d94a84ffdfd9ae664fe6188b19b4f4ecf8eef500a9522f9b81",
    "test_tf5_checker.py": "957f1c46e45f48fada61fb35e62f90894f60e8788fc34c7980f479bb9f71e322",
    "test_tf5_ci.py": "bd4411bbe74e39d8cfa5e9c808377fef327af2b97bf3fc3549d584c7705b5078",
    "test_tf5_units.py": "3967549965bf10a5cf62f7b2e5b6f45f2c7fb597c83bc6ce886ddbea6ca9fa91",
    "fixtures/tf5/make_main_pins.py": "170aec717549e3e311a8a3bb66e032bd51445fb22fb1c2de71b7f2b13bf3d50a",
    "fixtures/tf5/main-pins.json": "356d2c60d9a7455f21cf7eba7040cf850861146212186a61269f1c210db38bad",
}


def test_tf5_99_no_frozen_tf5_test_is_edited() -> None:
    got = {name: hashlib.sha256((TESTS / name).read_bytes()).hexdigest() for name in FROZEN}
    assert got == FROZEN
    assert len(FROZEN) == 15
