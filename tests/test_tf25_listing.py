"""TF25-85: the pull follows Braintrust's experiments listing to its end (ruling B-1 of TF25's
Session B, which follows BT-31's live check; the pull itself is TF25-33 to TF25-46 in
``test_tf25_pull.py``).

What the check found: ``GET /v1/experiment`` answers at most 1,000 experiments where the request
names no limit, the newest first, under ``objects`` and with no cursor; the experiments after
them are asked for with ``starting_after``, the id of the last one returned. So a pull that asks
once cannot name an experiment older than a project's newest 1,000.

The reading frozen here: the first request is the one TF25-33 holds, unchanged. An answer that
holds 1,000 experiments is followed by a request for the ones after its last, until an answer
holds fewer; the experiment is then looked for by its whole name across every answer. An answer
that ends where an earlier one ended is a failure after the pull began (exit 3), never a loop.

No capture holds a project of 1,000 experiments, so the listing here is built: the committed
listing's four experiments, with experiments of other names and made-up ids before them. Every
other request is answered from the captures, as in ``test_tf25_pull.py``, and no test here
reaches the network.
"""

from __future__ import annotations

import json
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from tf21_support import run_import
from tf25_support import (
    API, EXACT, FETCH, LISTING, PLANTED_KEY, PROJECT, Transport, address, bt_argv, imported, pulling, raw_folder, recs,
    refused,
)

#: How many experiments Braintrust lists in one answer when the request names no limit.
FULL = 1000
REAL: list[dict[str, Any]] = json.loads((API / "experiments.json").read_text(encoding="utf-8"))["objects"]


def _filler(n: int) -> dict[str, Any]:
    """An experiment of the project that is none of the captured four."""
    return {**REAL[0], "id": str(uuid.UUID(int=n + 1)), "name": f"filler-{n:05d}"}


def _pages(*sizes: int, real_on: int, also: tuple[tuple[int, dict[str, Any]], ...] = ()) -> list[list[dict[str, Any]]]:
    """A listing in answers of the sizes given, newest first: fillers, with the captured four at
    the end of the answer ``real_on`` and each of ``also`` at the start of the answer it names."""
    pages, n = [], 0
    for at, size in enumerate(sizes):
        extra = [e for where, e in also if where == at]
        tail = REAL if at == real_on else []
        fill = size - len(extra) - len(tail)
        assert fill >= 0
        pages.append([*extra, *[_filler(n + i) for i in range(fill)], *tail])
        n += fill
    return pages


class Listed(Transport):
    """The captures' transport, with the experiments listing answered from ``pages``: the first
    answer to the request with no ``starting_after``, and each next one to the id the answer
    before it ended with. ``repeat`` answers every request with the first answer."""

    def __init__(self, pages: list[list[dict[str, Any]]], repeat: bool = False) -> None:
        super().__init__()
        self.pages = pages
        self.repeat = repeat

    def answer(self, method: str, url: str, body: bytes | None) -> bytes:
        parts = urllib.parse.urlsplit(url)
        if parts.path != "/v1/experiment":
            return super().answer(method, url, body)
        query = dict(urllib.parse.parse_qsl(parts.query))
        assert method == "GET" and body is None and query.pop("project_name") == PROJECT, url
        after = query.pop("starting_after", None)
        assert not query, f"the listing was asked with {sorted(query)}"
        if after is None or self.repeat:
            at = 0
        else:
            ends = [page[-1]["id"] for page in self.pages[:-1]]
            assert after in ends, "the listing was asked for the experiments after one no answer ended with"
            at = ends.index(after) + 1
        return json.dumps({"objects": self.pages[at]}).encode("utf-8")

    def listings(self) -> list[dict[str, str]]:
        return [q for path, q in zip(self.paths(), self.queries(), strict=True) if path == LISTING]


def _nothing_saved(root: Path) -> bool:
    return not (root / "r").exists() and not raw_folder(root, "r").exists()


def test_tf25_85_an_experiment_past_the_first_thousand_is_found(tmp_path: Path) -> None:
    pages = _pages(FULL, 4, real_on=1)
    sent = Listed(pages)
    with pulling(sent):
        data = imported(bt_argv(address("baseline"), tmp_path / "st", "r"))
    assert sent.paths() == [LISTING, LISTING, FETCH, FETCH]
    assert sent.listings() == [{"project_name": PROJECT}, {"project_name": PROJECT, "starting_after": pages[0][-1]["id"]}]
    assert all(call["headers"].get("Authorization") == f"Bearer {PLANTED_KEY}" for call in sent.calls)
    assert data["rows"] == 10 and {case: r["score"] for case, r in recs(tmp_path / "st", "r").items()} == EXACT["baseline"]


def test_tf25_85_the_first_request_is_the_one_asked_before_and_a_short_answer_is_the_end(tmp_path: Path) -> None:
    """An answer one experiment short of full is the whole listing: nothing more is asked."""
    sent = Listed(_pages(FULL - 1, real_on=0))
    with pulling(sent):
        imported(bt_argv(address("candidate"), tmp_path / "st", "r"))
    assert sent.paths() == [LISTING, FETCH, FETCH] and sent.listings() == [{"project_name": PROJECT}]


def test_tf25_85_full_answers_are_followed_until_one_is_short(tmp_path: Path) -> None:
    """Two full answers and an empty one: the experiment is at the end of the second."""
    pages = _pages(FULL, FULL, 0, real_on=1)
    sent = Listed(pages)
    with pulling(sent):
        imported(bt_argv(address("baseline"), tmp_path / "st", "r"))
    assert sent.paths() == [LISTING, LISTING, LISTING, FETCH, FETCH]
    assert [q.get("starting_after") for q in sent.listings()] == [None, pages[0][-1]["id"], pages[1][-1]["id"]]


def test_tf25_85_a_name_no_answer_holds_is_refused_after_every_answer_was_read(tmp_path: Path) -> None:
    sent = Listed(_pages(FULL, 4, real_on=1))
    with pulling(sent):
        line = refused(run_import(bt_argv(f"braintrust:{PROJECT}/no-such-experiment", tmp_path / "st", "r")))
    assert sent.paths() == [LISTING, LISTING]
    assert "no-such-experiment" in line and PROJECT in line, line
    assert _nothing_saved(tmp_path / "st")


def test_tf25_85_a_name_two_answers_hold_is_refused(tmp_path: Path) -> None:
    """The name is looked for across every answer, so a second experiment of that name on
    another answer is seen: a pull reads one."""
    twin = {**REAL[0], "id": str(uuid.UUID(int=999_999)), "name": "slice-baseline"}
    sent = Listed(_pages(FULL, 4, real_on=1, also=((0, twin),)))
    with pulling(sent):
        line = refused(run_import(bt_argv(address("baseline"), tmp_path / "st", "r")))
    assert sent.paths() == [LISTING, LISTING]
    assert "slice-baseline" in line and "2" in line, line
    assert _nothing_saved(tmp_path / "st")


def test_tf25_85_a_listing_that_repeats_is_a_failure_and_never_a_loop(tmp_path: Path) -> None:
    sent = Listed(_pages(FULL, 4, real_on=1), repeat=True)
    with pulling(sent):
        result = run_import(bt_argv(address("baseline"), tmp_path / "st", "r"))
    assert result.code == 3 and result.out == "", result.out + result.err
    assert result.err.startswith("error: the pull failed") and "nothing was saved" in result.err, result.err
    assert sent.paths() == [LISTING, LISTING]
    assert _nothing_saved(tmp_path / "st")
