"""TF15-S46: with its limit taken from the log-rank's own information, compare's guidance is the
tries per input per version alone; the keys that held Schoenfeld's deaths, runs and inputs stay in
the JSON with no value, and the report's guidance names no deaths.
"""

from __future__ import annotations

from conftest import TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, compare, norm
from summaries_support import section


def test_tf15_s46_compares_guidance_holds_the_tries_alone() -> None:
    g = compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3, "--json").json()["comparison"]["guidance"]
    assert (g["deaths"], g["runs"], g["inputs"]) == (None, None, None) and g["repeats"] == 11
    body = norm(" ".join(section(compare(TAU2, TAU2_A, TAU2_B, TAU2_EVENTS, 1.3).out, "Guidance")))
    assert "deaths" not in body and "11" in body, body
