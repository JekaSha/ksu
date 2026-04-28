from __future__ import annotations

import socket

from ksusha_game.infrastructure.lan_presence import LanPresenceHost, LanServerBrowser, _recv_json_line


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


def test_lan_host_joinable_flag_roundtrip() -> None:
    host = LanPresenceHost(
        host_name="h",
        player_name="p",
        level_name="lvl",
        server_port=27880,
        max_players=5,
    )
    assert host.is_joinable() is True
    host.set_joinable(False)
    assert host.is_joinable() is False
    host.set_joinable(True)
    assert host.is_joinable() is True


def test_browser_is_connecting_default_false() -> None:
    browser = LanServerBrowser()
    assert browser.is_connecting() is False
