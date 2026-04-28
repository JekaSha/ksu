from __future__ import annotations

import math
from dataclasses import dataclass, field

from ksusha_game.domain.direction import Direction


@dataclass(frozen=True)
class PlayerStats:
    speed: float = 1.0
    vision: float = 1.0
    jump_power: float = 1.0
    weight_kg: float = 25.0
    height_cm: float = 120.0

    def speed_multiplier(self) -> float:
        return max(0.25, min(self.speed, 3.0))

    def vision_multiplier(self) -> float:
        return max(0.35, min(self.vision, 3.0))

    def jump_multiplier(self) -> float:
        return max(0.35, min(self.jump_power, 3.0))

    def mass_kg(self) -> float:
        return max(1.0, min(self.weight_kg, 500.0))

    def height_multiplier(self, baseline_cm: float = 120.0) -> float:
        base = max(1.0, float(baseline_cm))
        return max(0.65, min(self.height_cm / base, 1.65))


@dataclass
class Player:
    x: float
    y: float
    stats: PlayerStats = field(default_factory=PlayerStats)
    facing: Direction = Direction.DOWN
    walk_time: float = 0.0
    jump_time_left: float = 0.0
    jump_duration_base: float = 0.36
    jump_height_base: float = 22.0

    _DIRECTION_BY_INPUT = {
        (0, 1): Direction.DOWN,
        (0, -1): Direction.UP,
        (-1, 0): Direction.LEFT,
        (1, 0): Direction.RIGHT,
        (1, -1): Direction.UP_RIGHT,
        (-1, -1): Direction.UP_LEFT,
        (-1, 1): Direction.DOWN_LEFT,
        (1, 1): Direction.DOWN_RIGHT,
    }

    def apply_input(self, dx: int, dy: int, speed: float, dt: float, anim_fps: float) -> bool:
        moving = dx != 0 or dy != 0
        if not moving:
            self.walk_time = 0.0
            return False

        length = math.hypot(dx, dy)
        nx = dx / length
        ny = dy / length

        self.x += nx * speed * dt
        self.y += ny * speed * dt
        self.walk_time += dt * anim_fps

        self.facing = self._DIRECTION_BY_INPUT[(dx, dy)]

        return True

    def clamp_to_bounds(self, max_x: float, max_y: float) -> None:
        self.x = max(0.0, min(self.x, max(0.0, max_x)))
        self.y = max(0.0, min(self.y, max(0.0, max_y)))

    def try_start_jump(self) -> bool:
        if self.jump_time_left > 0.0:
            return False
        self.jump_time_left = self.jump_duration()
        return True

    def update_jump(self, dt: float) -> None:
        if self.jump_time_left <= 0.0:
            return
        self.jump_time_left = max(0.0, self.jump_time_left - dt)

    def jump_offset(self) -> float:
        if self.jump_time_left <= 0.0:
            return 0.0
        duration = self.jump_duration()
        phase = 1.0 - (self.jump_time_left / duration)
        return -math.sin(math.pi * phase) * self.jump_height()

    def jump_duration(self) -> float:
        return self.jump_duration_base

    def jump_height(self) -> float:
        return self.jump_height_base * self.stats.jump_multiplier()
