"""Tests for multiplayer session management in GameSession.

Covers the public API (add_player, remove_player, set_player_movement_input,
queue_player_action) and the invariants that ensure players can't corrupt each
other's state through the context-switching mechanism.

GameSession.__init__ does not touch pygame or the filesystem.
run() is never called in these tests.
"""
from __future__ import annotations

import random

import pytest

from ksusha_game.application.commands import PlayerActionCommand
from ksusha_game.application.session import GameSession
from ksusha_game.config import GameConfig
from ksusha_game.domain.player import PlayerStats
from ksusha_game.domain.world import SprayTag, WorldMap, WorldObject


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session() -> GameSession:
    return GameSession(GameConfig())


@pytest.fixture
def stats() -> PlayerStats:
    return PlayerStats()


@pytest.fixture
def world() -> WorldMap:
    return WorldMap(width=2000, height=2000, spawn_x=100, spawn_y=100)


def add(session: GameSession, player_id: str, stats: PlayerStats, x: float = 0.0, y: float = 0.0) -> None:
    session.add_player(player_id=player_id, spawn_x=x, spawn_y=y, stats=stats)


# ---------------------------------------------------------------------------
# add_player
# ---------------------------------------------------------------------------

class TestAddPlayer:
    def test_adds_player_state(self, session, stats):
        add(session, "p1", stats)
        assert "p1" in session._player_states

    def test_initialises_movement_input_to_zero(self, session, stats):
        add(session, "p1", stats)
        assert session._movement_inputs["p1"] == (0, 0, False, 1.0)

    def test_spawn_position_set(self, session, stats):
        add(session, "p1", stats, x=42.0, y=99.0)
        player = session._player_states["p1"].player
        assert player.x == pytest.approx(42.0)
        assert player.y == pytest.approx(99.0)

    def test_idempotent_same_id(self, session, stats):
        add(session, "p1", stats, x=1.0)
        add(session, "p1", stats, x=999.0)  # second call ignored
        assert session._player_states["p1"].player.x == pytest.approx(1.0)

    def test_multiple_players_independent(self, session, stats):
        add(session, "p1", stats, x=10.0)
        add(session, "p2", stats, x=20.0)
        assert len(session._player_states) == 2
        assert session._player_states["p1"].player.x != session._player_states["p2"].player.x

    def test_respects_max_players(self, session, stats):
        for i in range(1, GameSession._MAX_PLAYERS + 2):
            add(session, f"p{i}", stats)
        assert len(session._player_states) == GameSession._MAX_PLAYERS

    def test_each_player_has_own_inventory(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        inv1 = session._player_states["p1"].inventory
        inv2 = session._player_states["p2"].inventory
        assert inv1 is not inv2

    def test_default_inventory_capacity(self, session, stats):
        add(session, "p1", stats)
        assert session._player_states["p1"].inventory.capacity == 5

    def test_custom_inventory_capacity(self, session, stats):
        session.add_player(player_id="p1", spawn_x=0, spawn_y=0, stats=stats, base_inventory_capacity=3)
        assert session._player_states["p1"].inventory.capacity == 3


# ---------------------------------------------------------------------------
# remove_player
# ---------------------------------------------------------------------------

class TestRemovePlayer:
    def test_removes_extra_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.remove_player(player_id="p2")
        assert "p2" not in session._player_states

    def test_removes_movement_input(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.remove_player(player_id="p2")
        assert "p2" not in session._movement_inputs

    def test_local_player_cannot_be_removed(self, session, stats):
        add(session, GameSession._LOCAL_PLAYER_ID, stats)
        session.remove_player(player_id=GameSession._LOCAL_PLAYER_ID)
        assert GameSession._LOCAL_PLAYER_ID in session._player_states

    def test_remove_nonexistent_is_silent(self, session, stats):
        add(session, "p1", stats)
        session.remove_player(player_id="ghost")  # must not raise
        assert "p1" in session._player_states

    def test_other_players_unaffected(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        add(session, "p3", stats)
        session.remove_player(player_id="p2")
        assert "p1" in session._player_states
        assert "p3" in session._player_states

    def test_remove_player_releases_math_assignments(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._math_tasks.unlock_math_quest()
        session._math_tasks.select_task(player_id="p1", task_no=1, now_ts=1.0, team_id="A")
        rng = random.Random(123)
        session._math_tasks.pick_digit(player_id="p1", digit=4, rng=rng, online_player_ids=["p1", "p2"])
        session._math_tasks.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
        session._math_tasks.reassign_round_stage(
            stage="pick_first",
            assignee_player_id="p2",
            requested_by_player_id="p1",
            online_player_ids=["p1", "p2"],
        )
        pending = session._math_tasks.active_pending_answer()
        assert pending is not None
        assert pending.assigned_player_id == "p2"
        session.remove_player(player_id="p2")
        assert pending.assigned_player_id is None
        assert pending.accepted is True
        assert session._math_tasks.current_round is not None
        assert session._math_tasks.current_round.assignments["pick_first"] is None

    def test_remove_player_reelects_dispatcher_from_same_team(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        add(session, "p3", stats)
        session._set_player_team("p1", "A")
        session._set_player_team("p2", "A")
        session._set_player_team("p3", "B")
        session._math_tasks.unlock_math_quest()
        session._math_tasks.select_task(player_id="p2", task_no=1, now_ts=1.0, team_id="A")
        assert session._math_tasks.dispatcher_player_id == "p2"
        session.remove_player(player_id="p2")
        assert session._math_tasks.dispatcher_player_id == "p1"


# ---------------------------------------------------------------------------
# set_player_movement_input
# ---------------------------------------------------------------------------

class TestSetPlayerMovementInput:
    def test_stores_normalised_direction(self, session, stats):
        add(session, "p1", stats)
        session.set_player_movement_input(player_id="p1", dx=5, dy=-3)
        dx, dy, _, _ = session._movement_inputs["p1"]
        assert dx == 1
        assert dy == -1

    def test_zero_stays_zero(self, session, stats):
        add(session, "p1", stats)
        session.set_player_movement_input(player_id="p1", dx=0, dy=0)
        dx, dy, _, _ = session._movement_inputs["p1"]
        assert dx == 0
        assert dy == 0

    def test_holding_pickup_stored(self, session, stats):
        add(session, "p1", stats)
        session.set_player_movement_input(player_id="p1", dx=1, dy=0, holding_pickup=True)
        _, _, holding, _ = session._movement_inputs["p1"]
        assert holding is True

    def test_run_multiplier_clamped_to_min_one(self, session, stats):
        add(session, "p1", stats)
        session.set_player_movement_input(player_id="p1", dx=1, dy=0, run_multiplier=0.1)
        _, _, _, run = session._movement_inputs["p1"]
        assert run == pytest.approx(1.0)

    def test_run_multiplier_above_one_stored(self, session, stats):
        add(session, "p1", stats)
        session.set_player_movement_input(player_id="p1", dx=1, dy=0, run_multiplier=1.8)
        _, _, _, run = session._movement_inputs["p1"]
        assert run == pytest.approx(1.8)

    def test_inputs_independent_per_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.set_player_movement_input(player_id="p1", dx=1, dy=0)
        session.set_player_movement_input(player_id="p2", dx=0, dy=1)
        dx1, dy1, _, _ = session._movement_inputs["p1"]
        dx2, dy2, _, _ = session._movement_inputs["p2"]
        assert (dx1, dy1) == (1, 0)
        assert (dx2, dy2) == (0, 1)


# ---------------------------------------------------------------------------
# queue_player_action / command queue
# ---------------------------------------------------------------------------

class TestCommandQueue:
    def test_queue_appends_command(self, session, stats):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        assert len(session._command_queue) == 1

    def test_command_has_correct_fields(self, session, stats):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=42.0)
        cmd = session._command_queue[0]
        assert cmd.player_id == "p1"
        assert cmd.action == "jump"
        assert cmd.issued_at == pytest.approx(42.0)

    def test_multiple_commands_fifo_order(self, session, stats):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        session.queue_player_action(player_id="p1", action="select_next", issued_at=2.0)
        actions = [cmd.action for cmd in session._command_queue]
        assert actions == ["jump", "select_next"]

    def test_commands_for_different_players(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        session.queue_player_action(player_id="p2", action="jump", issued_at=2.0)
        pids = [cmd.player_id for cmd in session._command_queue]
        assert pids == ["p1", "p2"]

    def test_issued_at_defaults_to_now(self, session, stats):
        import time
        add(session, "p1", stats)
        before = time.monotonic()
        session.queue_player_action(player_id="p1", action="jump")
        after = time.monotonic()
        cmd = session._command_queue[0]
        assert before <= cmd.issued_at <= after

    def test_command_is_frozen(self, session, stats):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        cmd = session._command_queue[0]
        with pytest.raises((AttributeError, TypeError)):
            cmd.action = "drop"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _process_command_queue — jump action dispatch
# ---------------------------------------------------------------------------

class TestProcessCommandQueueJump:
    def test_jump_starts_player_jump(self, session, stats, world):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._player_states["p1"].player.jump_time_left > 0.0

    def test_queue_empty_after_processing(self, session, stats, world):
        add(session, "p1", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert len(session._command_queue) == 0

    def test_command_for_unknown_player_is_skipped(self, session, stats, world):
        add(session, "p1", stats)
        session.queue_player_action(player_id="ghost", action="jump", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert len(session._command_queue) == 0  # consumed but not crashed

    def test_context_restored_after_processing(self, session, stats, world):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._active_player_context_id = "p1"
        session.queue_player_action(player_id="p2", action="jump", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._active_player_context_id == "p1"

    def test_context_restored_even_if_action_raises(self, session, stats, world):
        """Context switch is inside try/finally — must be restored even on error."""
        add(session, "p1", stats)
        session._active_player_context_id = "p1"

        # Inject a command whose player disappears mid-processing to provoke early return.
        session._command_queue.append(PlayerActionCommand(player_id="p1", action="jump", issued_at=0.0))
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._active_player_context_id == "p1"


# ---------------------------------------------------------------------------
# _process_command_queue — inventory nav dispatch (needs world)
# ---------------------------------------------------------------------------

class TestProcessCommandQueueInventory:
    def test_select_next_advances_active_index(self, session, stats, world):
        add(session, "p1", stats)
        inv = session._player_states["p1"].inventory
        inv.slots = ["a", "b", "c", None, None]
        inv.active_index = 0
        session.queue_player_action(player_id="p1", action="select_next", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert inv.active_index == 1

    def test_select_prev_decrements_active_index(self, session, stats, world):
        add(session, "p1", stats)
        inv = session._player_states["p1"].inventory
        inv.slots = ["a", "b", "c", None, None]
        inv.active_index = 2
        session.queue_player_action(player_id="p1", action="select_prev", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert inv.active_index == 1


# ---------------------------------------------------------------------------
# Per-player state isolation
# ---------------------------------------------------------------------------

class TestPlayerStateIsolation:
    def test_jump_only_affects_target_player(self, session, stats, world):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.queue_player_action(player_id="p2", action="jump", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._player_states["p1"].player.jump_time_left == pytest.approx(0.0)
        assert session._player_states["p2"].player.jump_time_left > 0.0

    def test_inventory_action_only_affects_target_player(self, session, stats, world):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._player_states["p1"].inventory.active_index = 0
        session._player_states["p2"].inventory.active_index = 0
        session.queue_player_action(player_id="p1", action="select_next", issued_at=1.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._player_states["p1"].inventory.active_index == 1
        assert session._player_states["p2"].inventory.active_index == 0

    def test_grabbed_object_per_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._player_states["p1"].grabbed_object_id = "sofa_1"
        assert session._player_states["p2"].grabbed_object_id is None

    def test_spray_state_per_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._player_states["p1"].spray_active_target = ("wall", "r1")
        assert session._player_states["p2"].spray_active_target is None

    def test_standing_on_per_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._player_states["p1"].standing_on_object_id = "platform_1"
        assert session._player_states["p2"].standing_on_object_id is None

    def test_sequential_commands_for_multiple_players(self, session, stats, world):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session.queue_player_action(player_id="p1", action="jump", issued_at=1.0)
        session.queue_player_action(player_id="p2", action="jump", issued_at=2.0)
        session._process_command_queue(world=world, object_sprites=None)  # type: ignore[arg-type]
        assert session._player_states["p1"].player.jump_time_left > 0.0
        assert session._player_states["p2"].player.jump_time_left > 0.0


# ---------------------------------------------------------------------------
# Context switch correctness
# ---------------------------------------------------------------------------

class TestContextSwitch:
    def test_context_player_state_raises_for_unknown_id(self, session, stats):
        add(session, "p1", stats)
        session._active_player_context_id = "nonexistent"
        with pytest.raises(RuntimeError, match="nonexistent"):
            session._context_player_state()

    def test_context_player_state_returns_correct_player(self, session, stats):
        add(session, "p1", stats, x=10.0)
        add(session, "p2", stats, x=20.0)
        session._active_player_context_id = "p2"
        state = session._context_player_state()
        assert state.player.x == pytest.approx(20.0)

    def test_property_proxy_reads_correct_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._player_states["p2"].grabbed_object_id = "chair"
        session._active_player_context_id = "p2"
        assert session._grabbed_object_id == "chair"

    def test_property_proxy_writes_correct_player(self, session, stats):
        add(session, "p1", stats)
        add(session, "p2", stats)
        session._active_player_context_id = "p2"
        session._grabbed_object_id = "table"
        assert session._player_states["p2"].grabbed_object_id == "table"
        assert session._player_states["p1"].grabbed_object_id is None

    def test_primary_player_state_raises_when_no_local_player(self, session):
        with pytest.raises(RuntimeError):
            session._primary_player_state()

    def test_primary_player_state_returns_local_player(self, session, stats):
        add(session, GameSession._LOCAL_PLAYER_ID, stats, x=55.0)
        state = session._primary_player_state()
        assert state.player.x == pytest.approx(55.0)


# ---------------------------------------------------------------------------
# _apply_network_snapshot
# ---------------------------------------------------------------------------


class TestApplyNetworkSnapshot:
    def test_client_mapping_keeps_local_and_host_distinct(self, session, stats, world):
        add(session, GameSession._LOCAL_PLAYER_ID, stats, x=0.0, y=0.0)
        snapshot = {
            "level": session._config.map_path.stem,
            "players": [
                {"id": "p1", "team": "A", "x": 11.0, "y": 12.0, "facing": "down", "walk_time": 0.0, "jump_time_left": 0.0},
                {"id": "r2", "team": "B", "x": 21.0, "y": 22.0, "facing": "left", "walk_time": 0.3, "jump_time_left": 0.1},
            ],
        }

        session._apply_network_snapshot(snapshot, world, assigned_local_id="r2")

        assert session._player_states["p1"].player.x == pytest.approx(21.0)
        assert session._player_states["p1"].player.y == pytest.approx(22.0)
        assert "host:p1" in session._player_states
        assert session._player_states["host:p1"].player.x == pytest.approx(11.0)
        assert session._player_states["host:p1"].player.y == pytest.approx(12.0)
        assert session._player_team("p1") == "B"
        assert session._player_team("host:p1") == "A"
        assert session._network_outbound_player_id("p1") == "r2"
        assert session._network_outbound_player_id("host:p1") == "p1"

    def test_snapshot_removes_stale_remote_players(self, session, stats, world):
        add(session, GameSession._LOCAL_PLAYER_ID, stats)
        add(session, "host:p1", stats)
        add(session, "r3", stats)
        snapshot = {
            "level": session._config.map_path.stem,
            "players": [
                {"id": "p1", "x": 10.0, "y": 10.0, "facing": "down", "walk_time": 0.0, "jump_time_left": 0.0},
                {"id": "r2", "x": 20.0, "y": 20.0, "facing": "down", "walk_time": 0.0, "jump_time_left": 0.0},
            ],
        }

        session._apply_network_snapshot(snapshot, world, assigned_local_id="r2")

        assert "host:p1" in session._player_states
        assert "r3" not in session._player_states

    def test_snapshot_syncs_objects_and_spray_tags(self, session, stats, world):
        add(session, GameSession._LOCAL_PLAYER_ID, stats)
        world.objects = [
            WorldObject(
                object_id="door_1",
                kind="door",
                x=100.0,
                y=120.0,
                state=0,
                blocking=True,
                lock_open_flags=[False],
                lock_key_sets=[["key_red"]],
            ),
            WorldObject(object_id="old_obj", kind="plant", x=1.0, y=1.0),
        ]
        session._spray_tags = [
            SprayTag(
                x=10.0,
                y=10.0,
                width=20,
                height=20,
                target_kind="wall_top",
                target_id="room_1",
            )
        ]
        snapshot = {
            "level": session._config.map_path.stem,
            "players": [
                {"id": "p1", "x": 0.0, "y": 0.0, "facing": "down", "walk_time": 0.0, "jump_time_left": 0.0}
            ],
            "objects": [
                {
                    "class": "WorldObject",
                    "object_id": "door_1",
                    "kind": "door",
                    "x": 101.0,
                    "y": 121.0,
                    "door_orientation": "top",
                    "state": 1,
                    "blocking": False,
                    "cycle_sprites": False,
                    "occlude_top": False,
                    "occlude_split": None,
                    "jump_platform_w": None,
                    "jump_platform_h": None,
                    "jump_platform_offset_y": 0.0,
                    "collider_w": None,
                    "collider_h": None,
                    "label": None,
                    "pickup_item_id": None,
                    "required_item_id": None,
                    "lock_key_sets": [["key_red"]],
                    "lock_open_flags": [True],
                    "consume_required_item": False,
                    "use_set_state": None,
                    "use_set_blocking": None,
                    "transitions": {},
                    "tint_rgb": None,
                    "tint_strength": 1.0,
                    "lock_marker_rgb": None,
                    "lock_marker_text": None,
                    "weight_kg": 0.0,
                    "spray_zoom_coef": 1.0,
                    "width": 64,
                    "height": 64,
                },
                {
                    "class": "WorldObject",
                    "object_id": "new_obj",
                    "kind": "backpack",
                    "x": 45.0,
                    "y": 55.0,
                    "door_orientation": "top",
                    "state": 0,
                    "blocking": False,
                    "cycle_sprites": False,
                    "occlude_top": False,
                    "occlude_split": None,
                    "jump_platform_w": None,
                    "jump_platform_h": None,
                    "jump_platform_offset_y": 0.0,
                    "collider_w": None,
                    "collider_h": None,
                    "label": None,
                    "pickup_item_id": "backpack",
                    "required_item_id": None,
                    "lock_key_sets": [],
                    "lock_open_flags": [],
                    "consume_required_item": False,
                    "use_set_state": None,
                    "use_set_blocking": None,
                    "transitions": {},
                    "tint_rgb": None,
                    "tint_strength": 1.0,
                    "lock_marker_rgb": None,
                    "lock_marker_text": None,
                    "weight_kg": 0.0,
                    "spray_zoom_coef": 1.0,
                    "width": 64,
                    "height": 64,
                },
            ],
            "spray_tags": [
                {
                    "x": 90.0,
                    "y": 91.0,
                    "width": 40,
                    "height": 30,
                    "target_kind": "door",
                    "target_id": "door_1",
                    "spray_area_id": "room_2",
                    "profile_id": "default",
                    "sequence_index": 1,
                    "frame_index": 3,
                }
            ],
        }

        session._apply_network_snapshot(snapshot, world, assigned_local_id=None)

        assert [obj.object_id for obj in world.objects] == ["door_1", "new_obj"]
        assert world.objects[0].state == 1
        assert world.objects[0].blocking is False
        assert world.objects[0].lock_open_flags == [True]
        assert len(session._spray_tags) == 1
        assert session._spray_tags[0].target_id == "door_1"

    def test_snapshot_queues_inventory_icon_preloads(self, session, stats, world):
        add(session, GameSession._LOCAL_PLAYER_ID, stats)
        snapshot = {
            "level": session._config.map_path.stem,
            "players": [
                {
                    "id": "p1",
                    "x": 0.0,
                    "y": 0.0,
                    "facing": "down",
                    "walk_time": 0.0,
                    "jump_time_left": 0.0,
                    "inventory": {
                        "base_capacity": 5,
                        "capacity": 5,
                        "slots": ["backpack", "key", None, "ballon", None],
                        "active_index": 0,
                        "open": True,
                        "move_mode": False,
                        "move_source_index": None,
                        "bonus_capacity": 0,
                        "bonus_weight_limit_kg": 0.0,
                    },
                }
            ],
        }

        session._apply_network_snapshot(snapshot, world, assigned_local_id=None)

        queued = list(session._async_preload_queue)
        assert ("item_icon", "backpack") in queued
        assert ("item_icon", "key") in queued
        assert ("item_icon", "ballon") in queued


class TestPlayerVsPlayerCollision:
    def test_player_collision_blocks_movement(self, session, stats):
        add(session, "p1", stats, x=100.0, y=100.0)
        add(session, "p2", stats, x=100.0, y=100.0)
        session._player_states["p1"].last_player_sprite_size = (100, 120)
        session._player_states["p2"].last_player_sprite_size = (100, 120)

        p1 = session._player_states["p1"].player
        p1.x = 120.0
        p1.y = 120.0
        session._resolve_player_collisions(
            player_id="p1",
            player=p1,
            prev_x=80.0,
            prev_y=80.0,
            sprite_w=100,
            sprite_h=120,
        )

        assert p1.x == pytest.approx(80.0)
        assert p1.y == pytest.approx(80.0)

    def test_player_collision_reverts_single_axis_when_possible(self, session, stats):
        add(session, "p1", stats, x=100.0, y=100.0)
        add(session, "p2", stats, x=130.0, y=100.0)
        session._player_states["p1"].last_player_sprite_size = (100, 120)
        session._player_states["p2"].last_player_sprite_size = (100, 120)

        p1 = session._player_states["p1"].player
        # Move mostly on X into p2; X should be reverted while Y can stay.
        p1.x = 130.0
        p1.y = 118.0
        session._resolve_player_collisions(
            player_id="p1",
            player=p1,
            prev_x=90.0,
            prev_y=118.0,
            sprite_w=100,
            sprite_h=120,
        )

        assert p1.x == pytest.approx(90.0)
        assert p1.y == pytest.approx(118.0)
