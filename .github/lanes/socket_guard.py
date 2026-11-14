"""The socket guard of the clean-install job: copied into a folder on PYTHONPATH as
`sitecustomize.py`, so that every Python started after it refuses a connection to any address
that is not this machine's, and writes the address down.

The docs check answers the three services from files on the loopback address, so loopback is
let through. Anything else is a page's command, or Trace itself, reaching for the network,
which the job is there to prove never happens. The refused addresses are appended to the file
`POISSON_TRACE_REFUSED` names, and the job fails if that file exists at its end.
Standard library only.
"""

import os
import socket

_connect = socket.socket.connect


def _guarded(self, address):  # type: ignore[no-untyped-def]
    host = address[0] if isinstance(address, tuple) else address
    here = isinstance(host, str) and (
        host in ("localhost", "::1") or host.startswith("127.") or host.startswith("/")
    )
    if here:
        return _connect(self, address)
    log = os.environ.get("POISSON_TRACE_REFUSED")
    if log:
        with open(log, "a", encoding="utf-8") as out:
            out.write(repr(address) + "\n")
    raise OSError(f"the docs check reached for the network: {address!r}")


socket.socket.connect = _guarded  # type: ignore[method-assign]
