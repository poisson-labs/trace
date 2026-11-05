"""The support agent: a stand-in that answers from a table and calls no model.

A case ends in one of ``OUTCOMES``. The team counts the ones in ``FAILURES`` as failures:
``forbidden_action`` (the agent did something the policy forbids), ``unresolved`` (the
customer's problem was not solved), ``max_turns`` (the conversation ran out of turns) and
``app_error`` (the agent crashed). ``resolved`` is the one success.
"""

from __future__ import annotations

OUTCOMES = ("resolved", "forbidden_action", "unresolved", "max_turns", "app_error")
FAILURES = ("forbidden_action", "unresolved", "max_turns", "app_error")

_ANSWERS = {
    "refund-late": "resolved",
    "refund-early": "forbidden_action",
    "address-change": "resolved",
    "cancel-order": "unresolved",
}


def run_case(case_id: str, turns: int = 8) -> str:
    """Run one case and say how it ended."""
    if turns <= 0:
        return "max_turns"
    return _ANSWERS.get(case_id, "app_error")
