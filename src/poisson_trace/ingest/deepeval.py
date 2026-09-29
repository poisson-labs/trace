"""DeepEval's saved test runs, as DeepEval 4.2.6 writes them."""

from __future__ import annotations

import argparse

from poisson_trace.ingest.rows import Run

ENVELOPES: tuple[str, ...] = ("test run", "wrapped test run")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    raise NotImplementedError


def read(ns: argparse.Namespace) -> Run:
    raise NotImplementedError
