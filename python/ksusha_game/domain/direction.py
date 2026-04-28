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
