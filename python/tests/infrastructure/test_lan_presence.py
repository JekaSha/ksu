from __future__ import annotations

import socket

from ksusha_game.infrastructure.lan_presence import _recv_json_line


def test_recv_json_line_keeps_tail_for_next_message() -> None:
    left, right = socket.socketpair()
    recv_buffer = bytearray()
    try:
        left.settimeout(0.2)
        right.sendall(b'{"type":"a","n":1}\n{"type":"b","n":2}\n')
        first = _recv_json_line(left, recv_buffer)
        second = _recv_json_line(left, recv_buffer)
        assert first == {"type": "a", "n": 1}
        assert second == {"type": "b", "n": 2}
    finally:
        left.close()
        right.close()


def test_recv_json_line_preserves_partial_until_timeout() -> None:
    left, right = socket.socketpair()
    recv_buffer = bytearray()
    try:
        left.settimeout(0.05)
        right.sendall(b'{"type":"partial"')
        assert _recv_json_line(left, recv_buffer) is None
        right.sendall(b',"ok":true}\n')
        full = _recv_json_line(left, recv_buffer)
        assert full == {"type": "partial", "ok": True}
    finally:
        left.close()
        right.close()
