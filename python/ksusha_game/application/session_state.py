from __future__ import annotations

from dataclasses import dataclass, field

from ksusha_game.domain.inventory import Inventory
from ksusha_game.domain.player import Player


@dataclass
class SessionPlayerState:
    player: Player
    inventory: Inventory
    net_target_x: float | None = None
    net_target_y: float | None = None
    net_target_walk_time: float | None = None
    net_target_at: float | None = None
    net_velocity_x: float = 0.0
    net_velocity_y: float = 0.0
    net_update_gap_ema: float = 1.0 / 30.0
    active_ride_item_id: str | None = None
    standing_on_object_id: str | None = None
    grabbed_object_id: str | None = None
    spray_active_target: tuple[str, str] | None = None
    spray_active_tag_index: int | None = None
    spray_hold_accum: float = 0.0
    spray_spent_slots: dict[int, str] = field(default_factory=dict)
    door_overlap_ids: set[str] = field(default_factory=set)
    active_area_id: str | None = None
    last_player_sprite_size: tuple[int, int] = (100, 120)
