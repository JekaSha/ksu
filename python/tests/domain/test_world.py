from __future__ import annotations

import pytest

from ksusha_game.domain.world import (
    BalloonSpec,
    FogSettings,
    RoomArea,
    WorldMap,
    WorldObject,
)


def make_room(
    room_id: str = "r1",
    x: int = 0,
    y: int = 0,
    width: int = 400,
    height: int = 300,
) -> RoomArea:
    return RoomArea(room_id=room_id, x=x, y=y, width=width, height=height, floor_texture="wood")


def make_map(*rooms: RoomArea) -> WorldMap:
    return WorldMap(width=2000, height=2000, spawn_x=100, spawn_y=100, rooms=list(rooms))


def make_obj(object_id: str = "obj1", kind: str = "sofa", x: float = 100.0, y: float = 100.0) -> WorldObject:
    return WorldObject(object_id=object_id, kind=kind, x=x, y=y)


class TestRoomForPoint:
    def test_inside_room(self):
        world = make_map(make_room(x=0, y=0, width=400, height=300))
        assert world.room_for_point(200.0, 150.0) is not None

    def test_outside_returns_none(self):
        world = make_map(make_room(x=0, y=0, width=400, height=300))
        assert world.room_for_point(500.0, 500.0) is None

    def test_on_left_edge_included(self):
        world = make_map(make_room(x=100, y=100, width=400, height=300))
        assert world.room_for_point(100.0, 150.0) is not None

    def test_on_right_edge_included(self):
        world = make_map(make_room(x=100, y=100, width=400, height=300))
        assert world.room_for_point(500.0, 150.0) is not None

    def test_returns_correct_room(self):
        r1 = make_room("room1", x=0, y=0, width=200, height=200)
        r2 = make_room("room2", x=200, y=0, width=200, height=200)
        world = make_map(r1, r2)
        found = world.room_for_point(300.0, 100.0)
        assert found is not None
        assert found.room_id == "room2"

    def test_no_rooms_returns_none(self):
        world = make_map()
        assert world.room_for_point(50.0, 50.0) is None


class TestRoomIdForPointHalfOpen:
    def test_inside_room(self):
        world = make_map(make_room(x=0, y=0, width=400, height=300))
        assert world.room_id_for_point_half_open(200.0, 150.0) == "r1"

    def test_outside_returns_none(self):
        world = make_map(make_room(x=0, y=0, width=400, height=300))
        assert world.room_id_for_point_half_open(400.0, 0.0) is None

    def test_right_boundary_excluded(self):
        world = make_map(make_room(x=0, y=0, width=400, height=300))
        assert world.room_id_for_point_half_open(400.0, 150.0) is None

    def test_left_boundary_included(self):
        world = make_map(make_room(x=100, y=0, width=400, height=300))
        assert world.room_id_for_point_half_open(100.0, 150.0) == "r1"

    def test_shared_border_goes_to_last_room(self):
        r1 = make_room("room1", x=0, y=0, width=200, height=300)
        r2 = make_room("room2", x=200, y=0, width=200, height=300)
        world = make_map(r1, r2)
        # x=200 is in r2's left boundary (half-open: [200, 400))
        assert world.room_id_for_point_half_open(200.0, 150.0) == "room2"


class TestWorldObjectLocks:
    def test_has_locks_false_by_default(self):
        obj = make_obj()
        assert obj.has_locks() is False

    def test_has_locks_true_with_sets(self):
        obj = WorldObject(object_id="door1", kind="door", x=0.0, y=0.0, lock_key_sets=[["key_red"]])
        assert obj.has_locks() is True

    def test_is_fully_unlocked_false_with_no_locks(self):
        obj = make_obj()
        assert obj.is_fully_unlocked() is False

    def test_try_open_lock_returns_true_for_correct_key(self):
        obj = WorldObject(object_id="d1", kind="door", x=0.0, y=0.0, lock_key_sets=[["key_red", "key_blue"]])
        assert obj.try_open_lock_with_key("key_red") is True

    def test_try_open_lock_returns_false_for_wrong_key(self):
        obj = WorldObject(object_id="d1", kind="door", x=0.0, y=0.0, lock_key_sets=[["key_red"]])
        assert obj.try_open_lock_with_key("key_green") is False

    def test_opened_lock_cannot_be_opened_again(self):
        obj = WorldObject(object_id="d1", kind="door", x=0.0, y=0.0, lock_key_sets=[["key_red"]])
        obj.try_open_lock_with_key("key_red")
        assert obj.try_open_lock_with_key("key_red") is False

    def test_is_fully_unlocked_after_all_opened(self):
        obj = WorldObject(
            object_id="d1", kind="door", x=0.0, y=0.0,
            lock_key_sets=[["key_red"], ["key_blue"]],
        )
        obj.try_open_lock_with_key("key_red")
        obj.try_open_lock_with_key("key_blue")
        assert obj.is_fully_unlocked() is True

    def test_is_fully_unlocked_false_with_partial_open(self):
        obj = WorldObject(
            object_id="d1", kind="door", x=0.0, y=0.0,
            lock_key_sets=[["key_red"], ["key_blue"]],
        )
        obj.try_open_lock_with_key("key_red")
        assert obj.is_fully_unlocked() is False

    def test_opened_locks_count(self):
        obj = WorldObject(
            object_id="d1", kind="door", x=0.0, y=0.0,
            lock_key_sets=[["key_red"], ["key_blue"]],
        )
        obj.try_open_lock_with_key("key_red")
        assert obj.opened_locks_count() == 1
        assert obj.total_locks_count() == 2


class TestWorldObjectTransition:
    def test_transition_for_returns_none_for_unknown_event(self):
        obj = make_obj()
        assert obj.transition_for("open") is None

    def test_transition_for_empty_string_returns_none(self):
        obj = make_obj()
        assert obj.transition_for("") is None

    def test_transition_for_known_event(self):
        from ksusha_game.domain.world import ObjectTransition
        t = ObjectTransition(state=1, blocking=False)
        obj = WorldObject(object_id="o1", kind="door", x=0.0, y=0.0, transitions={"open": t})
        assert obj.transition_for("open") is t


class TestWorldMapObjects:
    def test_add_and_remove_object(self):
        world = make_map()
        obj = make_obj()
        world.add_object(obj)
        assert len(world.objects) == 1
        removed = world.remove_object("obj1")
        assert removed is obj
        assert len(world.objects) == 0

    def test_remove_nonexistent_returns_none(self):
        world = make_map()
        assert world.remove_object("ghost") is None

    def test_spray_item_ids_union(self):
        world = WorldMap(
            width=100, height=100, spawn_x=0, spawn_y=0,
            item_spray_profiles={"spray_can": "graffiti"},
            balloon_item_ids={"ballon": "default"},
        )
        ids = world.spray_item_ids()
        assert "spray_can" in ids
        assert "ballon" in ids

    def test_spray_item_ids_empty_strings_excluded(self):
        world = WorldMap(
            width=100, height=100, spawn_x=0, spawn_y=0,
            item_spray_profiles={"": "profile"},
        )
        assert "" not in world.spray_item_ids()


class TestFogSettings:
    def test_scaled_radii_ordering(self):
        fog = FogSettings()
        near, mid, far, dark = fog.scaled_radii(1.0)
        assert near < mid < far < dark

    def test_scaled_radii_scale_up(self):
        fog = FogSettings()
        near1, *_ = fog.scaled_radii(1.0)
        near2, *_ = fog.scaled_radii(2.0)
        assert near2 > near1

    def test_scaled_radii_minimum_gaps(self):
        fog = FogSettings()
        near, mid, far, dark = fog.scaled_radii(0.01)
        assert mid > near
        assert far > mid
        assert dark > far

    def test_scaled_radii_clamped_to_min(self):
        fog = FogSettings(near_radius=10.0)
        near, *_ = fog.scaled_radii(0.01)
        assert near >= 24
