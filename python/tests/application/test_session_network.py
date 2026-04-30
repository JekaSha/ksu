"""Tests for network/LAN multiplayer logic in GameSession.

Covers serialization roundtrips, network snapshot application, player id
remapping, host-event handling, and player–player collision resolution.
No actual sockets or pygame display are opened.
"""
from __future__ import annotations

import pytest

from ksusha_game.infrastructure.lan_presence import HostEvent
from ksusha_game.application.session import GameSession
from ksusha_game.config import GameConfig
from ksusha_game.domain.direction import Direction
from ksusha_game.domain.inventory import Inventory
from ksusha_game.domain.player import PlayerStats
from ksusha_game.domain.world import (
    BalloonObject,
    ItemObject,
    ObjectTransition,
    SprayTag,
    WorldMap,
    WorldObject,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session() -> GameSession:
    return GameSession(GameConfig())


def make_world(**kwargs) -> WorldMap:
    defaults = dict(width=2000, height=2000, spawn_x=100, spawn_y=200)
    defaults.update(kwargs)
    return WorldMap(**defaults)


def make_stats() -> PlayerStats:
    return PlayerStats()


def add(session: GameSession, player_id: str, x: float = 0.0, y: float = 0.0) -> None:
    session.add_player(player_id=player_id, spawn_x=x, spawn_y=y, stats=make_stats())


# ---------------------------------------------------------------------------
# Inventory serialization roundtrip
# ---------------------------------------------------------------------------

class TestInventoryPayloadRoundtrip:
    def _roundtrip(self, inv: Inventory) -> Inventory:
        session = make_session()
        payload = session._inventory_payload(inv)
        result = Inventory(base_capacity=inv.base_capacity, capacity=inv.capacity)
        session._apply_inventory_payload(result, payload)
        return result

    def test_slots_preserved(self):
        inv = Inventory(base_capacity=3, capacity=3)
        inv.slots = ["key", None, "backpack"]
        out = self._roundtrip(inv)
        assert out.slots == ["key", None, "backpack"]

    def test_active_index_preserved(self):
        inv = Inventory(base_capacity=5, capacity=5)
        inv.active_index = 3
        out = self._roundtrip(inv)
        assert out.active_index == 3

    def test_bonus_capacity_preserved(self):
        inv = Inventory(base_capacity=5, capacity=8)
        inv.bonus_capacity = 3
        inv.bonus_weight_limit_kg = 7.5
        out = self._roundtrip(inv)
        assert out.bonus_capacity == 3
        assert out.bonus_weight_limit_kg == pytest.approx(7.5)

    def test_move_mode_preserved(self):
        inv = Inventory(base_capacity=5, capacity=5)
        inv.slots[0] = "item"
        inv.begin_move_mode()
        out = self._roundtrip(inv)
        assert out.move_mode is True
        assert out.move_source_index == 0

    def test_invalid_payload_is_ignored(self):
        session = make_session()
        inv = Inventory(base_capacity=5, capacity=5)
        inv.slots[2] = "key"
        session._apply_inventory_payload(inv, {"base_capacity": "bad", "capacity": "bad"})
        assert inv.slots[2] == "key"  # unchanged

    def test_active_index_clamped_to_capacity(self):
        session = make_session()
        inv = Inventory(base_capacity=3, capacity=3)
        session._apply_inventory_payload(inv, {"base_capacity": 3, "capacity": 3, "active_index": 999})
        assert inv.active_index == 2

    def test_move_source_out_of_range_is_cleared(self):
        session = make_session()
        inv = Inventory(base_capacity=3, capacity=3)
        session._apply_inventory_payload(inv, {"base_capacity": 3, "capacity": 3, "move_source_index": 99, "move_mode": True})
        assert inv.move_mode is False
        assert inv.move_source_index is None

    def test_empty_slots_padded_to_capacity(self):
        session = make_session()
        inv = Inventory(base_capacity=5, capacity=5)
        session._apply_inventory_payload(inv, {"base_capacity": 5, "capacity": 5, "slots": ["a"]})
        assert len(inv.slots) == 5
        assert inv.slots[0] == "a"
        assert inv.slots[1] is None


# ---------------------------------------------------------------------------
# SprayTag serialization roundtrip
# ---------------------------------------------------------------------------

class TestSprayTagRoundtrip:
    def _roundtrip(self, tag: SprayTag) -> SprayTag | None:
        session = make_session()
        payload = session._spray_tag_payload(tag)
        return session._spray_tag_from_payload(payload)

    def test_basic_roundtrip(self):
        tag = SprayTag(x=10.0, y=20.0, width=80, height=60, target_kind="door", target_id="d1",
                       spray_area_id="room1", profile_id="graffiti", sequence_index=2, frame_index=3)
        out = self._roundtrip(tag)
        assert out is not None
        assert out.x == pytest.approx(10.0)
        assert out.y == pytest.approx(20.0)
        assert out.width == 80
        assert out.height == 60
        assert out.target_kind == "door"
        assert out.target_id == "d1"
        assert out.profile_id == "graffiti"
        assert out.sequence_index == 2
        assert out.frame_index == 3

    def test_zero_size_returns_none(self):
        session = make_session()
        assert session._spray_tag_from_payload({"width": 0, "height": 60, "target_kind": "wall", "target_id": "w1"}) is None
        assert session._spray_tag_from_payload({"width": 80, "height": 0, "target_kind": "wall", "target_id": "w1"}) is None

    def test_missing_target_returns_none(self):
        session = make_session()
        assert session._spray_tag_from_payload({"width": 80, "height": 60}) is None

    def test_default_profile_id(self):
        session = make_session()
        tag = session._spray_tag_from_payload(
            {"x": 0, "y": 0, "width": 10, "height": 10, "target_kind": "wall", "target_id": "w1"}
        )
        assert tag is not None
        assert tag.profile_id == "default"


# ---------------------------------------------------------------------------
# WorldObject serialization roundtrip
# ---------------------------------------------------------------------------

class TestWorldObjectRoundtrip:
    def _roundtrip(self, obj: WorldObject) -> WorldObject | None:
        session = make_session()
        payload = session._world_object_payload(obj)
        return session._world_object_from_payload(payload)

    def test_basic_object_roundtrip(self):
        obj = WorldObject(object_id="sofa1", kind="sofa", x=100.0, y=200.0, state=1, blocking=True)
        out = self._roundtrip(obj)
        assert out is not None
        assert out.object_id == "sofa1"
        assert out.kind == "sofa"
        assert out.x == pytest.approx(100.0)
        assert out.y == pytest.approx(200.0)
        assert out.state == 1
        assert out.blocking is True

    def test_lock_key_sets_preserved(self):
        obj = WorldObject(
            object_id="door1", kind="door", x=0.0, y=0.0,
            lock_key_sets=[["key_red", "key_blue"], ["key_green"]],
            lock_open_flags=[True, False],
        )
        out = self._roundtrip(obj)
        assert out is not None
        assert out.lock_key_sets == [["key_red", "key_blue"], ["key_green"]]
        assert out.lock_open_flags == [True, False]

    def test_transitions_preserved(self):
        t = ObjectTransition(state=2, blocking=False)
        obj = WorldObject(object_id="o1", kind="door", x=0.0, y=0.0, transitions={"open": t})
        out = self._roundtrip(obj)
        assert out is not None
        tr = out.transitions.get("open")
        assert tr is not None
        assert tr.state == 2
        assert tr.blocking is False

    def test_tint_rgb_preserved(self):
        obj = WorldObject(object_id="o1", kind="sofa", x=0.0, y=0.0, tint_rgb=(200, 100, 50))
        out = self._roundtrip(obj)
        assert out is not None
        assert out.tint_rgb == (200, 100, 50)

    def test_tint_rgb_none_preserved(self):
        obj = WorldObject(object_id="o1", kind="sofa", x=0.0, y=0.0, tint_rgb=None)
        out = self._roundtrip(obj)
        assert out is not None
        assert out.tint_rgb is None

    def test_item_object_roundtrip(self):
        obj = ItemObject(object_id="key1", kind="key", x=0.0, y=0.0, item_id="key_red", uses_per_room_limit=2)
        session = make_session()
        payload = session._world_object_payload(obj)
        out = session._world_object_from_payload(payload)
        assert isinstance(out, ItemObject)
        assert out.item_id == "key_red"
        assert out.uses_per_room_limit == 2

    def test_balloon_object_roundtrip(self):
        obj = BalloonObject(object_id="b1", kind="ballon", x=0.0, y=0.0,
                            item_id="ballon", balloon_id="default", graffiti_profile_id="tag1")
        session = make_session()
        payload = session._world_object_payload(obj)
        out = session._world_object_from_payload(payload)
        assert isinstance(out, BalloonObject)
        assert out.balloon_id == "default"
        assert out.graffiti_profile_id == "tag1"

    def test_missing_object_id_returns_none(self):
        session = make_session()
        assert session._world_object_from_payload({"kind": "sofa", "x": 0, "y": 0}) is None

    def test_missing_kind_returns_none(self):
        session = make_session()
        assert session._world_object_from_payload({"object_id": "o1", "x": 0, "y": 0}) is None


# ---------------------------------------------------------------------------
# _apply_network_snapshot — player state
# ---------------------------------------------------------------------------

class TestApplyNetworkSnapshotPlayers:
    def _make_player_entry(self, player_id: str, x: float = 50.0, y: float = 50.0,
                           facing: str = "down") -> dict:
        return {
            "id": player_id,
            "x": x, "y": y,
            "facing": facing,
            "walk_time": 0.0,
            "jump_time_left": 0.0,
            "inventory": {"base_capacity": 5, "capacity": 5, "slots": [None]*5,
                          "active_index": 0, "open": True, "move_mode": False,
                          "move_source_index": None, "bonus_capacity": 0,
                          "bonus_weight_limit_kg": 0.0},
        }

    def _snapshot(self, session: GameSession, world: WorldMap, players: list[dict]) -> dict:
        return {
            "level": world.spawn_x,  # will be overridden
            "players": players,
        }

    def _apply(self, session: GameSession, world: WorldMap, players: list[dict],
               assigned_local_id: str | None = None) -> None:
        snap = {
            "level": GameConfig().map_path.stem,
            "players": players,
        }
        session._apply_network_snapshot(snap, world, assigned_local_id=assigned_local_id)

    def test_updates_existing_player_position(self):
        session = make_session()
        world = make_world()
        add(session, "p1", x=10.0, y=10.0)
        self._apply(session, world, [self._make_player_entry("p1", x=200.0, y=300.0)])
        state = session._player_states["p1"]
        assert state.player.x == pytest.approx(200.0)
        assert state.player.y == pytest.approx(300.0)

    def test_adds_missing_player(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        self._apply(session, world, [
            self._make_player_entry("p1"),
            self._make_player_entry("p2", x=100.0, y=150.0),
        ])
        assert "p2" in session._player_states
        assert session._player_states["p2"].player.x == pytest.approx(100.0)

    def test_removes_player_not_in_snapshot(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        add(session, "p2")
        # snapshot contains only p1
        self._apply(session, world, [self._make_player_entry("p1")])
        assert "p2" not in session._player_states
        assert "p1" in session._player_states

    def test_wrong_level_name_rejected(self):
        session = make_session()
        world = make_world()
        add(session, "p1", x=10.0)
        snap = {"level": "__wrong_level__", "players": [self._make_player_entry("p1", x=999.0)]}
        session._apply_network_snapshot(snap, world)
        assert session._player_states["p1"].player.x == pytest.approx(10.0)  # unchanged

    def test_facing_updated(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        self._apply(session, world, [self._make_player_entry("p1", facing="up_right")])
        assert session._player_states["p1"].player.facing == Direction.UP_RIGHT

    def test_invalid_facing_leaves_player_intact(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        original_facing = session._player_states["p1"].player.facing
        entry = self._make_player_entry("p1")
        entry["facing"] = "totally_invalid"
        self._apply(session, world, [entry])
        # Exception is caught; player state should remain (not removed)
        assert "p1" in session._player_states

    def test_local_id_remapping(self):
        """Client receives rN id from host; it should be treated as local p1."""
        session = make_session()
        world = make_world()
        add(session, "p1", x=5.0)
        # Host assigned this client the id "r2"; snapshot has p1 (host's local) and r2 (us)
        self._apply(session, world, [
            self._make_player_entry("p1", x=100.0),   # host's own player
            self._make_player_entry("r2", x=42.0),    # this client's slot
        ], assigned_local_id="r2")
        # our local p1 must have x=42
        assert session._player_states["p1"].player.x == pytest.approx(42.0)
        # host's p1 must be stored under a different key
        assert "p1" in session._player_states  # still exists (our local player)

    def test_host_p1_remapped_to_avoid_collision(self):
        """When assigned_local_id=r2, host's p1 must not overwrite our local p1."""
        session = make_session()
        world = make_world()
        add(session, "p1", x=5.0)
        self._apply(session, world, [
            self._make_player_entry("p1", x=999.0),  # host's p1 — must NOT touch our p1
            self._make_player_entry("r2", x=10.0),   # our slot
        ], assigned_local_id="r2")
        # Our local p1 gets x=10 (from r2 entry), NOT 999 (from host's p1 entry)
        assert session._player_states["p1"].player.x == pytest.approx(10.0)

    def test_objects_replaced_from_snapshot(self):
        session = make_session()
        world = make_world()
        world.objects = [WorldObject(object_id="old", kind="sofa", x=0.0, y=0.0)]
        add(session, "p1")
        new_obj = WorldObject(object_id="new1", kind="sofa", x=50.0, y=60.0, state=2, blocking=True)
        session_for_payload = make_session()
        snap = {
            "level": GameConfig().map_path.stem,
            "players": [self._make_player_entry("p1")],
            "objects": [session_for_payload._world_object_payload(new_obj)],
        }
        session._apply_network_snapshot(snap, world)
        assert len(world.objects) == 1
        assert world.objects[0].object_id == "new1"

    def test_spray_tags_replaced_from_snapshot(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        session._spray_tags = [SprayTag(x=1, y=1, width=10, height=10,
                                        target_kind="wall", target_id="w1")]
        tag = SprayTag(x=5.0, y=6.0, width=80, height=60, target_kind="door", target_id="d1")
        session_for_payload = make_session()
        snap = {
            "level": GameConfig().map_path.stem,
            "players": [self._make_player_entry("p1")],
            "spray_tags": [session_for_payload._spray_tag_payload(tag)],
        }
        session._apply_network_snapshot(snap, world)
        assert len(session._spray_tags) == 1
        assert session._spray_tags[0].target_id == "d1"

    def test_room_use_counts_restored(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        snap = {
            "level": GameConfig().map_path.stem,
            "players": [self._make_player_entry("p1")],
            "room_item_use_counts": [
                {"room_id": "r1", "item_id": "ballon", "count": 3}
            ],
        }
        session._apply_network_snapshot(snap, world)
        assert session._room_item_use_counts[("r1", "ballon")] == 3

    def test_grabbed_object_cleared_if_object_removed(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        session._player_states["p1"].grabbed_object_id = "sofa_gone"
        # Snapshot replaces objects with empty list (sofa_gone is gone)
        snap = {
            "level": GameConfig().map_path.stem,
            "players": [self._make_player_entry("p1")],
            "objects": [],
        }
        session._apply_network_snapshot(snap, world)
        assert session._player_states["p1"].grabbed_object_id is None


# ---------------------------------------------------------------------------
# _build_network_snapshot
# ---------------------------------------------------------------------------

class TestBuildNetworkSnapshot:
    def test_contains_level_name(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        snap = session._build_network_snapshot(world)
        assert snap["level"] == GameConfig().map_path.stem

    def test_contains_all_players(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        add(session, "p2")
        snap = session._build_network_snapshot(world)
        ids = {p["id"] for p in snap["players"]}
        assert ids == {"p1", "p2"}

    def test_player_position_included(self):
        session = make_session()
        world = make_world()
        add(session, "p1", x=77.0, y=88.0)
        snap = session._build_network_snapshot(world)
        p = next(p for p in snap["players"] if p["id"] == "p1")
        assert p["x"] == pytest.approx(77.0)
        assert p["y"] == pytest.approx(88.0)

    def test_snapshot_roundtrip_preserves_player_positions(self):
        session_host = make_session()
        session_client = make_session()
        world_host = make_world()
        world_client = make_world()
        add(session_host, "p1", x=120.0, y=250.0)
        add(session_client, "p1")

        snap = session_host._build_network_snapshot(world_host)
        session_client._apply_network_snapshot(snap, world_client)
        assert session_client._player_states["p1"].player.x == pytest.approx(120.0)
        assert session_client._player_states["p1"].player.y == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# _apply_host_event
# ---------------------------------------------------------------------------

class TestApplyHostEvent:
    def test_join_creates_player(self):
        session = make_session()
        world = make_world()
        add(session, "p1", x=100.0, y=100.0)
        event = HostEvent(type="join", player_id="r2", player_name="Alice", player_team="B")
        session._apply_host_event(event, world)
        assert "r2" in session._player_states

    def test_join_without_local_player_is_no_op(self):
        session = make_session()
        world = make_world()
        event = HostEvent(type="join", player_id="r2", player_name="Alice", player_team="B")
        session._apply_host_event(event, world)
        assert "r2" not in session._player_states

    def test_leave_removes_player(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        add(session, "r2")
        event = HostEvent(type="leave", player_id="r2", player_name="Alice", player_team="B")
        session._apply_host_event(event, world)
        assert "r2" not in session._player_states

    def test_leave_does_not_affect_local_player(self):
        session = make_session()
        world = make_world()
        add(session, "p1")
        event = HostEvent(type="leave", player_id="p1", player_name="Local", player_team="A")
        session._apply_host_event(event, world)
        assert "p1" in session._player_states


# ---------------------------------------------------------------------------
# _can_send_client_action
# ---------------------------------------------------------------------------

class TestCanSendClientAction:
    def test_non_drop_always_allowed(self):
        session = make_session()
        add(session, "p1")
        for action in ("jump", "pickup", "use", "select_next"):
            assert session._can_send_client_action(action=action) is True

    def test_drop_allowed_with_item(self):
        session = make_session()
        add(session, "p1")
        session._player_states["p1"].inventory.slots[0] = "key"
        assert session._can_send_client_action(action="drop") is True

    def test_drop_blocked_when_no_item(self):
        session = make_session()
        add(session, "p1")
        assert session._can_send_client_action(action="drop") is False

    def test_drop_blocked_when_no_local_player(self):
        session = make_session()
        assert session._can_send_client_action(action="drop") is False


# ---------------------------------------------------------------------------
# _resolve_player_collisions (player–player push)
# ---------------------------------------------------------------------------

class TestResolvePlayerCollisions:
    """Tests for inter-player collision resolution.

    _resolve_player_collisions uses pygame.Rect internally but only for
    geometric overlap checks — no display is needed.
    """

    def test_no_collision_position_unchanged(self):
        import pygame
        pygame.init()
        session = make_session()
        add(session, "p1", x=0.0, y=0.0)
        add(session, "p2", x=500.0, y=500.0)  # far away
        session._player_states["p2"].last_player_sprite_size = (80, 100)
        prev_x, prev_y = session._player_states["p1"].player.x, session._player_states["p1"].player.y
        session._resolve_player_collisions(
            player_id="p1",
            player=session._player_states["p1"].player,
            prev_x=prev_x, prev_y=prev_y,
            sprite_w=80, sprite_h=100,
        )
        assert session._player_states["p1"].player.x == pytest.approx(prev_x)
        assert session._player_states["p1"].player.y == pytest.approx(prev_y)

    def test_overlapping_players_are_pushed_back(self):
        import pygame
        pygame.init()
        session = make_session()
        # p1 and p2 occupy the same position → overlap
        add(session, "p1", x=100.0, y=100.0)
        add(session, "p2", x=100.0, y=100.0)
        session._player_states["p2"].last_player_sprite_size = (80, 100)
        # p1 was previously not overlapping p2
        session._resolve_player_collisions(
            player_id="p1",
            player=session._player_states["p1"].player,
            prev_x=0.0, prev_y=100.0,  # was to the left → revert x
            sprite_w=80, sprite_h=100,
        )
        # p1 should have been moved back to prev_x
        assert session._player_states["p1"].player.x == pytest.approx(0.0)
