from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerActionCommand:
    player_id: str
    action: str
    issued_at: float
