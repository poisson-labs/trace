"""The suite's block on the network (``conftest.py``): a test that reaches for another machine fails,
and one that stays on this machine goes on working.

- A connection to an address that is not this machine's fails the test before anything is sent; so does a
  look-up of a name that is not this machine's.
- A connection to this machine's loopback address is made as before.
- The block does not rest on the error being left uncaught: code that catches every ``Exception`` and
  every ``OSError`` on the way does not hide it.
"""

from __future__ import annotations

import socket

import pytest

#: An address of TEST-NET-1 (RFC 5737): it is no machine's, so nothing is reached even if the block were gone.
ELSEWHERE = ("192.0.2.1", 9)


def test_a_connection_to_another_machine_fails_the_test() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        with pytest.raises(pytest.fail.Exception, match="reached for the network: a connection to"):
            s.connect(ELSEWHERE)
        with pytest.raises(pytest.fail.Exception, match="reached for the network: a connection to"):
            s.connect_ex(ELSEWHERE)


def test_a_look_up_of_another_machines_name_fails_the_test() -> None:
    with pytest.raises(pytest.fail.Exception, match="reached for the network: a look-up of 'example.invalid'"):
        socket.getaddrinfo("example.invalid", 443)
    with pytest.raises(pytest.fail.Exception, match="a look-up of"):
        socket.create_connection(("example.invalid", 443), timeout=0.2)


def test_code_that_catches_every_error_does_not_hide_it() -> None:
    def careless() -> str:
        try:
            socket.create_connection(ELSEWHERE, timeout=0.2)
        except (Exception, OSError):  # noqa: B014
            return "hidden"
        return "connected"

    with pytest.raises(pytest.fail.Exception):
        careless()


def test_this_machine_is_still_reached() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5) as client:
            peer, _ = server.accept()
            with peer:
                client.sendall(b"here")
                assert peer.recv(4) == b"here"
    assert socket.getaddrinfo("localhost", 80)
    assert socket.getaddrinfo(None, 80)
