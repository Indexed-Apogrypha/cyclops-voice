# tests/test_daemon.py
import socket
from cyclops_voice.daemon import _reserve_port


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_reserve_port_is_exclusive():
    port = _free_port()
    first = _reserve_port("127.0.0.1", port)
    assert first is not None
    # A second reservation of the same port must fail while the first holds it.
    assert _reserve_port("127.0.0.1", port) is None
    # After releasing, the port is reservable again.
    first.close()
    again = _reserve_port("127.0.0.1", port)
    assert again is not None
    again.close()


def test_reserve_port_returns_bound_socket():
    port = _free_port()
    sock = _reserve_port("127.0.0.1", port)
    assert sock is not None
    assert sock.getsockname()[1] == port
    sock.close()
