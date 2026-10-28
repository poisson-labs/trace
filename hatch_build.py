"""The source archive leaves out the repository's ignore file, which hatchling adds to every sdist
it builds; the file is about this repository, not about the source a user gets."""

from __future__ import annotations

from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "sdist":
            return
        forced = build_data["force_include"]
        for source in [s for s, target in forced.items() if target == ".gitignore"]:
            del forced[source]
