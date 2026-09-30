"""Ragas's per-row score tables, saved as CSV, JSON Lines, JSON or Parquet."""

from __future__ import annotations

import argparse

from poisson_trace.ingest.rows import Run

FORMATS: tuple[str, ...] = ("csv", "jsonl", "json", "parquet")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registers no flag yet: the command builds one parser for every reader present, so a body
    that raised here would stop every other reader too."""


def read(ns: argparse.Namespace) -> Run:
    raise NotImplementedError
