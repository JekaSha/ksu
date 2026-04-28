from __future__ import annotations

import math

import pytest

from ksusha_game.domain.direction import Direction
from ksusha_game.domain.player import Player, PlayerStats


def make_player(x: float = 0.0, y: float = 0.0) -> Player:
    return Player(x=x, y=y)


class TestApplyInput:
    def test_idle_returns_false(self):
        p = make_player()
        moved = p.apply_input(dx=0, dy=0, speed=100.0, dt=0.016, anim_fps=8.0)
        assert moved is False

    def test_moving_returns_true(self):
        p = make_player()
        moved = p.apply_input(dx=1, dy=0, speed=100.0, dt=0.016, anim_fps=8.0)
        assert moved is True

    def test_moves_right(self):
        p = make_player(x=0.0, y=0.0)
        p.apply_input(dx=1, dy=0, speed=100.0, dt=1.0, anim_fps=8.0)
        assert p.x == pytest.approx(100.0)
        assert p.y == pytest.approx(0.0)

    def test_moves_down(self):
        p = make_player()
        p.apply_input(dx=0, dy=1, speed=100.0, dt=1.0, anim_fps=8.0)
        assert p.y == pytest.approx(100.0)
        assert p.x == pytest.approx(0.0)

    def test_diagonal_speed_normalized(self):
        p = make_player()
        p.apply_input(dx=1, dy=1, speed=100.0, dt=1.0, anim_fps=8.0)
        dist = math.hypot(p.x, p.y)
        assert dist == pytest.approx(100.0, rel=1e-4)

    def test_facing_right(self):
        p = make_player()
        p.apply_input(dx=1, dy=0, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.RIGHT

    def test_facing_left(self):
        p = make_player()
        p.apply_input(dx=-1, dy=0, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.LEFT

    def test_facing_up(self):
        p = make_player()
        p.apply_input(dx=0, dy=-1, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.UP

    def test_facing_down(self):
        p = make_player()
        p.apply_input(dx=0, dy=1, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.DOWN

    def test_facing_up_right(self):
        p = make_player()
        p.apply_input(dx=1, dy=-1, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.UP_RIGHT

    def test_facing_down_left(self):
        p = make_player()
        p.apply_input(dx=-1, dy=1, speed=1.0, dt=0.016, anim_fps=8.0)
        assert p.facing == Direction.DOWN_LEFT

    def test_idle_resets_walk_time(self):
        p = make_player()
        p.walk_time = 3.5
        p.apply_input(dx=0, dy=0, speed=100.0, dt=0.016, anim_fps=8.0)
        assert p.walk_time == 0.0

    def test_walk_time_advances(self):
        p = make_player()
        p.apply_input(dx=1, dy=0, speed=100.0, dt=0.5, anim_fps=8.0)
        assert p.walk_time == pytest.approx(4.0)


class TestClampToBounds:
    def test_clamps_x_max(self):
        p = make_player(x=500.0, y=0.0)
        p.clamp_to_bounds(max_x=200.0, max_y=1000.0)
        assert p.x == pytest.approx(200.0)

    def test_clamps_y_max(self):
        p = make_player(x=0.0, y=600.0)
        p.clamp_to_bounds(max_x=1000.0, max_y=400.0)
        assert p.y == pytest.approx(400.0)

    def test_clamps_x_min(self):
        p = make_player(x=-10.0, y=0.0)
        p.clamp_to_bounds(max_x=200.0, max_y=200.0)
        assert p.x == pytest.approx(0.0)

    def test_clamps_y_min(self):
        p = make_player(x=0.0, y=-5.0)
        p.clamp_to_bounds(max_x=200.0, max_y=200.0)
        assert p.y == pytest.approx(0.0)

    def test_no_op_inside_bounds(self):
        p = make_player(x=50.0, y=75.0)
        p.clamp_to_bounds(max_x=200.0, max_y=200.0)
        assert p.x == pytest.approx(50.0)
        assert p.y == pytest.approx(75.0)

    def test_zero_max_clamps_to_zero(self):
        p = make_player(x=100.0, y=100.0)
        p.clamp_to_bounds(max_x=0.0, max_y=0.0)
        assert p.x == pytest.approx(0.0)
        assert p.y == pytest.approx(0.0)


class TestJump:
    def test_try_start_jump_sets_timer(self):
        p = make_player()
        started = p.try_start_jump()
        assert started is True
        assert p.jump_time_left > 0.0

    def test_try_start_jump_fails_if_airborne(self):
        p = make_player()
        p.try_start_jump()
        started = p.try_start_jump()
        assert started is False

    def test_update_jump_decrements_timer(self):
        p = make_player()
        p.try_start_jump()
        before = p.jump_time_left
        p.update_jump(dt=0.1)
        assert p.jump_time_left == pytest.approx(before - 0.1)

    def test_update_jump_clamps_at_zero(self):
        p = make_player()
        p.try_start_jump()
        p.update_jump(dt=999.0)
        assert p.jump_time_left == pytest.approx(0.0)

    def test_jump_offset_zero_when_grounded(self):
        p = make_player()
        assert p.jump_offset() == pytest.approx(0.0)

    def test_jump_offset_negative_at_midpoint(self):
        p = make_player()
        p.try_start_jump()
        duration = p.jump_duration()
        p.jump_time_left = duration * 0.5
        offset = p.jump_offset()
        assert offset < 0.0

    def test_jump_offset_returns_to_zero_at_end(self):
        p = make_player()
        p.try_start_jump()
        p.jump_time_left = 0.001
        p.update_jump(dt=0.001)
        assert p.jump_offset() == pytest.approx(0.0)

    def test_can_jump_again_after_landing(self):
        p = make_player()
        p.try_start_jump()
        p.update_jump(dt=999.0)
        assert p.try_start_jump() is True


class TestPlayerStats:
    def test_speed_multiplier_clamped_low(self):
        stats = PlayerStats(speed=0.0)
        assert stats.speed_multiplier() == pytest.approx(0.25)

    def test_speed_multiplier_clamped_high(self):
        stats = PlayerStats(speed=10.0)
        assert stats.speed_multiplier() == pytest.approx(3.0)

    def test_speed_multiplier_passthrough(self):
        stats = PlayerStats(speed=1.5)
        assert stats.speed_multiplier() == pytest.approx(1.5)

    def test_vision_multiplier_clamped_low(self):
        stats = PlayerStats(vision=0.0)
        assert stats.vision_multiplier() == pytest.approx(0.35)

    def test_jump_multiplier_clamped_low(self):
        stats = PlayerStats(jump_power=0.0)
        assert stats.jump_multiplier() == pytest.approx(0.35)

    def test_mass_kg_clamped(self):
        assert PlayerStats(weight_kg=0.0).mass_kg() == pytest.approx(1.0)
        assert PlayerStats(weight_kg=9999.0).mass_kg() == pytest.approx(500.0)

    def test_height_multiplier_normal(self):
        stats = PlayerStats(height_cm=120.0)
        assert stats.height_multiplier(baseline_cm=120.0) == pytest.approx(1.0)

    def test_height_multiplier_tall(self):
        stats = PlayerStats(height_cm=180.0)
        mult = stats.height_multiplier(baseline_cm=120.0)
        assert mult == pytest.approx(min(180.0 / 120.0, 1.65))
