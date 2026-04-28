from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    DOWN = "down"
    UP = "up"
    LEFT = "left"
    RIGHT = "right"
    UP_RIGHT = "up_right"
    UP_LEFT = "up_left"
    DOWN_LEFT = "down_left"
    DOWN_RIGHT = "down_right"


FACING_VECTOR: dict[Direction, tuple[float, float]] = {
    Direction.DOWN: (0.0, 1.0),
    Direction.UP: (0.0, -1.0),
    Direction.LEFT: (-1.0, 0.0),
    Direction.RIGHT: (1.0, 0.0),
    Direction.UP_RIGHT: (0.7071, -0.7071),
    Direction.UP_LEFT: (-0.7071, -0.7071),
    Direction.DOWN_LEFT: (-0.7071, 0.7071),
    Direction.DOWN_RIGHT: (0.7071, 0.7071),
}
