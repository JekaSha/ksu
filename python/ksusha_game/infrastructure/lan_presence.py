from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import threading
import time
import uuid


@dataclass(frozen=True)
class ServerEntry:
    server_id: str
    host_name: str
    player_name: str
    level_name: str
    host: str
    port: int
    players: int
    max_players: int
    last_seen: float


@dataclass(frozen=True)
class HostEvent:
    type: str
    player_id: str
    player_name: str


@dataclass
class _ClientSession:
    conn: socket.socket
    player_id: str
    player_name: str


def _recv_json_line(conn: socket.socket, recv_buffer: bytearray) -> dict | None:
    while True:
        newline_idx = recv_buffer.find(b"\n")
        if newline_idx >= 0:
            raw = bytes(recv_buffer[:newline_idx]).strip()
            del recv_buffer[: newline_idx + 1]
            if not raw:
                continue
            return json.loads(raw.decode("utf-8"))
        try:
            chunk = conn.recv(4096)
        except socket.timeout:
            return None
        if chunk == b"":
            raise OSError("closed")
        recv_buffer.extend(chunk)
        if len(recv_buffer) > 65535:
            raise OSError("oversized")


class LanPresenceHost:
    def __init__(
        self,
        *,
        host_name: str,
        player_name: str,
        level_name: str,
        server_port: int,
        max_players: int,
        discovery_port: int = 45891,
        announce_interval_sec: float = 1.0,
    ) -> None:
        self.server_id = str(uuid.uuid4())
        self.host_name = host_name
        self.player_name = player_name
        self.level_name = level_name
        self.server_port = int(server_port)
        self.max_players = int(max_players)
        self.discovery_port = int(discovery_port)
        self.announce_interval_sec = max(0.3, float(announce_interval_sec))

        self._stop = threading.Event()
        self._udp_thread: threading.Thread | None = None
        self._tcp_thread: threading.Thread | None = None
        self._server_socket: socket.socket | None = None
        self._active_clients: dict[str, _ClientSession] = {}
        self._next_remote_id = 2
        self._lock = threading.Lock()
        self._events: list[HostEvent] = []
        self._remote_inputs: dict[str, tuple[int, int, bool, float]] = {}
        self._remote_actions: list[tuple[str, str]] = []
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def connected_clients(self) -> int:
        with self._lock:
            return len(self._active_clients)

    def total_players(self) -> int:
        return 1 + self.connected_clients()

    def start(self) -> bool:
        if self._enabled:
            return True
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("", self.server_port))
            server.listen(16)
            server.settimeout(0.5)
            self._server_socket = server
        except OSError:
            try:
                server.close()  # type: ignore[name-defined]
            except Exception:
                pass
            self._server_socket = None
            return False

        self._stop.clear()
        self._udp_thread = threading.Thread(target=self._run_udp_broadcast, daemon=True)
        self._tcp_thread = threading.Thread(target=self._run_tcp_server, daemon=True)
        self._udp_thread.start()
        self._tcp_thread.start()
        self._enabled = True
        return True

    def stop(self) -> None:
        if not self._enabled:
            return
        self._stop.set()

        try:
            if self._server_socket is not None:
                self._server_socket.close()
        except Exception:
            pass
        self._server_socket = None

        with self._lock:
            for client in self._active_clients.values():
                try:
                    client.conn.close()
                except Exception:
                    pass
            self._active_clients.clear()
            self._remote_inputs.clear()
        self._enabled = False

    def poll_events(self) -> list[HostEvent]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def poll_remote_inputs(self) -> list[tuple[str, int, int, bool, float]]:
        with self._lock:
            items = [(pid, *vals) for pid, vals in self._remote_inputs.items()]
            self._remote_inputs.clear()
        return items

    def poll_remote_actions(self) -> list[tuple[str, str]]:
        with self._lock:
            items = list(self._remote_actions)
            self._remote_actions.clear()
        return items

    def broadcast_snapshot(self, snapshot: dict) -> None:
        if not self._enabled:
            return
        payload = self._encode_line({"type": "snapshot", "snapshot": snapshot})
        stale_ids: list[str] = []
        with self._lock:
            for client_id, client in self._active_clients.items():
                try:
                    client.conn.sendall(payload)
                except OSError:
                    stale_ids.append(client_id)
            for client_id in stale_ids:
                client = self._active_clients.pop(client_id, None)
                if client is None:
                    continue
                self._remote_inputs.pop(client.player_id, None)
                self._events.append(HostEvent(type="leave", player_id=client.player_id, player_name=client.player_name))
                try:
                    client.conn.close()
                except Exception:
                    pass

    def _announcement_payload(self) -> bytes:
        payload = {
            "type": "ksu_server_announce",
            "server_id": self.server_id,
            "host_name": self.host_name,
            "player_name": self.player_name,
            "level_name": self.level_name,
            "port": self.server_port,
            "players": self.total_players(),
            "max_players": self.max_players,
            "ts": time.time(),
        }
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def _run_udp_broadcast(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self._stop.is_set():
                try:
                    sock.sendto(self._announcement_payload(), ("255.255.255.255", self.discovery_port))
                except OSError:
                    pass
                self._stop.wait(self.announce_interval_sec)
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _run_tcp_server(self) -> None:
        server = self._server_socket
        if server is None:
            return
        while not self._stop.is_set():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()

    def _handle_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        client_key = f"{addr[0]}:{addr[1]}"
        accepted = False
        client_player_id = ""
        client_player_name = ""
        recv_buffer = bytearray()
        try:
            conn.settimeout(2.0)
            first = _recv_json_line(conn, recv_buffer)
            is_join = isinstance(first, dict) and first.get("type") == "join_request"
            client_player_name = str(first.get("player_name", "player")).strip() if isinstance(first, dict) else "player"
            if not client_player_name:
                client_player_name = "player"

            with self._lock:
                can_join = len(self._active_clients) < max(0, self.max_players - 1)
                if is_join and can_join:
                    client_player_id = f"r{self._next_remote_id}"
                    self._next_remote_id += 1
                    self._active_clients[client_key] = _ClientSession(
                        conn=conn,
                        player_id=client_player_id,
                        player_name=client_player_name,
                    )
                    self._events.append(
                        HostEvent(type="join", player_id=client_player_id, player_name=client_player_name)
                    )
                    accepted = True

            if accepted:
                resp = {
                    "type": "join_accept",
                    "server_id": self.server_id,
                    "host_name": self.host_name,
                    "level_name": self.level_name,
                    "players": self.total_players(),
                    "max_players": self.max_players,
                    "player_id": client_player_id,
                }
            else:
                resp = {"type": "join_reject", "reason": "server_full_or_bad_request"}
            conn.sendall(self._encode_line(resp))

            if not accepted:
                return

            conn.settimeout(0.25)
            while not self._stop.is_set():
                data = _recv_json_line(conn, recv_buffer)
                if data is None:
                    continue
                if not isinstance(data, dict):
                    continue
                msg_type = str(data.get("type", "")).strip().lower()
                if msg_type == "input":
                    try:
                        dx = int(data.get("dx", 0))
                        dy = int(data.get("dy", 0))
                        holding = bool(data.get("holding_pickup", False))
                        run = float(data.get("run_multiplier", 1.0))
                    except Exception:
                        continue
                    dx = 0 if dx == 0 else (1 if dx > 0 else -1)
                    dy = 0 if dy == 0 else (1 if dy > 0 else -1)
                    run = max(1.0, min(4.0, run))
                    with self._lock:
                        self._remote_inputs[client_player_id] = (dx, dy, holding, run)
                elif msg_type == "action":
                    action = str(data.get("action", "")).strip()
                    if not action:
                        continue
                    with self._lock:
                        self._remote_actions.append((client_player_id, action))
                elif msg_type == "disconnect":
                    break
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            if accepted:
                with self._lock:
                    prev = self._active_clients.pop(client_key, None)
                    if prev is not None:
                        self._remote_inputs.pop(prev.player_id, None)
                        self._events.append(HostEvent(type="leave", player_id=prev.player_id, player_name=prev.player_name))
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _encode_line(payload: dict) -> bytes:
        return (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")

class LanServerBrowser:
    def __init__(self, *, discovery_port: int = 45891, ttl_sec: float = 3.2) -> None:
        self.discovery_port = int(discovery_port)
        self.ttl_sec = max(1.0, float(ttl_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._entries: dict[str, ServerEntry] = {}

        self._active_connection: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._connected_server_id: str | None = None
        self._assigned_player_id: str | None = None
        self._snapshot_queue: list[dict] = []
        self._rx_thread: threading.Thread | None = None

        self._connect_thread: threading.Thread | None = None
        self._connect_result: tuple[bool, str] | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_listener, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.disconnect()

    def servers(self) -> list[ServerEntry]:
        now = time.time()
        with self._lock:
            stale = [sid for sid, entry in self._entries.items() if (now - entry.last_seen) > self.ttl_sec]
            for sid in stale:
                self._entries.pop(sid, None)
            result = list(self._entries.values())
        result.sort(key=lambda e: (e.host_name.lower(), e.player_name.lower(), e.server_id))
        return result

    def connected_server_id(self) -> str | None:
        return self._connected_server_id

    def connected_player_id(self) -> str | None:
        return self._assigned_player_id

    def is_connected(self) -> bool:
        return self._active_connection is not None and self._connected_server_id is not None

    def disconnect(self) -> None:
        self._connected_server_id = None
        self._assigned_player_id = None
        with self._send_lock:
            conn = self._active_connection
            self._active_connection = None
        if conn is not None:
            try:
                conn.sendall(self._encode_line({"type": "disconnect"}))
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def connect_async(self, entry: ServerEntry, *, player_name: str, timeout_sec: float = 1.0) -> None:
        if self._connect_thread is not None and self._connect_thread.is_alive():
            return
        self._connect_result = None
        self._connect_thread = threading.Thread(
            target=self._connect_worker,
            args=(entry, player_name, timeout_sec),
            daemon=True,
        )
        self._connect_thread.start()

    def poll_connect_result(self) -> tuple[bool, str] | None:
        result = self._connect_result
        self._connect_result = None
        return result

    def send_input_update(self, *, dx: int, dy: int, holding_pickup: bool, run_multiplier: float) -> None:
        if not self.is_connected():
            return
        payload = {
            "type": "input",
            "dx": int(dx),
            "dy": int(dy),
            "holding_pickup": bool(holding_pickup),
            "run_multiplier": float(run_multiplier),
            "ts": time.time(),
        }
        self._send_json(payload)

    def send_action(self, *, action: str) -> None:
        if not self.is_connected():
            return
        token = str(action).strip()
        if not token:
            return
        self._send_json({"type": "action", "action": token, "ts": time.time()})

    def poll_snapshots(self) -> list[dict]:
        with self._lock:
            snaps = list(self._snapshot_queue)
            self._snapshot_queue.clear()
        return snaps

    def _connect_worker(self, entry: ServerEntry, player_name: str, timeout_sec: float) -> None:
        self.disconnect()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        recv_buffer = bytearray()
        try:
            sock.settimeout(max(0.35, float(timeout_sec)))
            sock.connect((entry.host, int(entry.port)))
            req = {"type": "join_request", "player_name": player_name, "ts": time.time()}
            sock.sendall(self._encode_line(req))
            data = _recv_json_line(sock, recv_buffer)
            if not isinstance(data, dict) or data.get("type") != "join_accept":
                reason = str(data.get("reason", "join_reject")) if isinstance(data, dict) else "join_reject"
                try:
                    sock.close()
                except Exception:
                    pass
                self._connect_result = (False, reason)
                return
            assigned_player_id = str(data.get("player_id", "")).strip()
            with self._send_lock:
                self._active_connection = sock
            self._connected_server_id = entry.server_id
            self._assigned_player_id = assigned_player_id if assigned_player_id else None
            self._connect_result = (True, "ok")
            self._rx_thread = threading.Thread(
                target=self._run_connection_reader,
                args=(recv_buffer,),
                daemon=True,
            )
            self._rx_thread.start()
        except Exception as exc:
            try:
                sock.close()
            except Exception:
                pass
            self._connect_result = (False, str(exc))

    def _run_connection_reader(self, recv_buffer: bytearray) -> None:
        while self.is_connected():
            conn = self._active_connection
            if conn is None:
                break
            try:
                conn.settimeout(0.4)
                data = _recv_json_line(conn, recv_buffer)
            except (OSError, ValueError, json.JSONDecodeError):
                self.disconnect()
                break
            if data is None or not isinstance(data, dict):
                continue
            if str(data.get("type", "")).strip().lower() == "snapshot":
                snap = data.get("snapshot")
                if isinstance(snap, dict):
                    with self._lock:
                        self._snapshot_queue.append(snap)

    def _send_json(self, payload: dict) -> None:
        with self._send_lock:
            conn = self._active_connection
            if conn is None:
                return
            try:
                conn.sendall(self._encode_line(payload))
            except OSError:
                self.disconnect()

    def _run_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.discovery_port))
            sock.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    payload, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    continue
                try:
                    data = json.loads(payload.decode("utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict) or data.get("type") != "ksu_server_announce":
                    continue
                sid = str(data.get("server_id", "")).strip()
                if not sid:
                    continue
                host_name = str(data.get("host_name", "")).strip() or addr[0]
                player_name = str(data.get("player_name", "")).strip() or "player"
                level_name = str(data.get("level_name", "")).strip() or "unknown"
                try:
                    port = int(data.get("port", 0))
                except Exception:
                    port = 0
                if port <= 0:
                    continue
                try:
                    players = max(0, int(data.get("players", 1)))
                except Exception:
                    players = 1
                try:
                    max_players = max(1, int(data.get("max_players", 5)))
                except Exception:
                    max_players = 5

                entry = ServerEntry(
                    server_id=sid,
                    host_name=host_name,
                    player_name=player_name,
                    level_name=level_name,
                    host=addr[0],
                    port=port,
                    players=players,
                    max_players=max_players,
                    last_seen=time.time(),
                )
                with self._lock:
                    self._entries[sid] = entry
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _encode_line(payload: dict) -> bytes:
        return (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
