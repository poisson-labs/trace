"""Reading other tools' stored results into a store in Prove's format, one run per import.

``poisson-trace import TOOL FILE ... --store ROOT --run NAME`` reads the files a tool already
wrote and writes one new run through Prove's public API, so that Trace's verbs read it as they
read any stored run.
"""
