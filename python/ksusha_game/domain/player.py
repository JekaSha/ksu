from __future__ import annotations

import math
from dataclasses import dataclass

from ksusha_game.domain.direction import Direction


@dataclass
class Player:
    x: float
    y: float
    facing: Direction = Direction.DOWN
    walk_time: float = 0.0

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

        if abs(nx) > abs(ny):
            self.facing = Direction.RIGHT if nx > 0 else Direction.LEFT
        else:
            self.facing = Direction.DOWN if ny > 0 else Direction.UP

        return True

    def clamp_to_bounds(self, max_x: float, max_y: float) -> None:
        self.x = max(0.0, min(self.x, max(0.0, max_x)))
        self.y = max(0.0, min(self.y, max(0.0, max_y)))
