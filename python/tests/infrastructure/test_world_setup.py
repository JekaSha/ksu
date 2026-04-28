from __future__ import annotations

import pytest

from ksusha_game.domain.world import WorldObject
from ksusha_game.infrastructure.world_setup import object_collider_metrics


def make_obj(kind: str = "sofa", **kwargs) -> WorldObject:
    defaults = dict(object_id="o1", kind=kind, x=100.0, y=100.0, blocking=True)
    defaults.update(kwargs)
    return WorldObject(**defaults)


class TestObjectColliderMetrics:
    def test_returns_three_values(self):
        obj = make_obj(kind="plant")
        result = object_collider_metrics(obj, sprite_w=100, sprite_h=200)
        assert len(result) == 3

    def test_default_object_uses_ratio(self):
        obj = make_obj(kind="key")
        w, h, anchor = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        assert w == pytest.approx(72, abs=1)
        assert h == pytest.approx(32, abs=1)

    def test_explicit_collider_w_overrides(self):
        obj = make_obj(kind="key", collider_w=50.0)
        w, h, anchor = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        assert w == 50

    def test_explicit_collider_h_overrides(self):
        obj = make_obj(kind="key", collider_h=25.0)
        w, h, anchor = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        assert h == 25

    def test_minimum_size_is_8(self):
        obj = make_obj(kind="key", collider_w=1.0, collider_h=1.0)
        w, h, _ = object_collider_metrics(obj, sprite_w=1, sprite_h=1)
        assert w >= 8
        assert h >= 8

    def test_plant_has_larger_collider_than_default(self):
        obj_plant = make_obj(kind="plant")
        obj_key = make_obj(kind="key")
        _, h_plant, _ = object_collider_metrics(obj_plant, sprite_w=100, sprite_h=100)
        _, h_key, _ = object_collider_metrics(obj_key, sprite_w=100, sprite_h=100)
        assert h_plant > h_key

    def test_closed_door_has_tall_collider(self):
        obj = make_obj(kind="door", blocking=True, state=0)
        w, h, anchor = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        assert w >= 66
        assert h >= 64
        assert anchor == pytest.approx(18.0)

    def test_open_door_has_smaller_collider(self):
        obj_closed = make_obj(kind="door", blocking=True, state=0)
        obj_open = make_obj(kind="door", blocking=True, state=1)
        _, h_closed, _ = object_collider_metrics(obj_closed, sprite_w=100, sprite_h=100)
        _, h_open, _ = object_collider_metrics(obj_open, sprite_w=100, sprite_h=100)
        assert h_closed > h_open

    def test_sofa_is_wide(self):
        obj = make_obj(kind="sofa")
        w, h, _ = object_collider_metrics(obj, sprite_w=200, sprite_h=100)
        assert w > int(200 * 0.72)

    def test_sofa_has_higher_collider_than_default(self):
        obj_sofa = make_obj(kind="sofa")
        obj_other = make_obj(kind="key")
        _, h_sofa, _ = object_collider_metrics(obj_sofa, sprite_w=100, sprite_h=100)
        _, h_other, _ = object_collider_metrics(obj_other, sprite_w=100, sprite_h=100)
        assert h_sofa > h_other

    def test_y_anchor_is_float(self):
        obj = make_obj(kind="key")
        _, _, anchor = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        assert isinstance(anchor, float)

    def test_y_anchor_proportional_to_sprite_height(self):
        obj = make_obj(kind="key")
        _, _, anchor_small = object_collider_metrics(obj, sprite_w=100, sprite_h=100)
        _, _, anchor_large = object_collider_metrics(obj, sprite_w=100, sprite_h=200)
        assert anchor_large > anchor_small
