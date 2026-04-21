from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    DOWN = "down"
    UP = "up"
    LEFT = "left"
    RIGHT = "right"
