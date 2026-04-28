from __future__ import annotations

from dataclasses import dataclass, field

from ksusha_game.domain.direction import Direction
from ksusha_game.domain.player import PlayerStats


@dataclass(frozen=True)
class FogSettings:
    enabled: bool = False
    near_radius: float = 170.0
    mid_radius: float = 300.0
    far_radius: float = 460.0
    dark_radius: float = 640.0
    medium_blur_scale: float = 0.42
    far_blur_scale: float = 0.20
    mid_dark_alpha: int = 36
    far_dark_alpha: int = 110
    outer_dark_alpha: int = 220
    color: tuple[int, int, int] = (8, 10, 16)
    transition: float = 56.0

    def scaled_radii(self, vision_multiplier: float) -> tuple[int, int, int, int]:
        scale = max(0.35, min(vision_multiplier, 3.0))
        near = int(self.near_radius * scale)
        mid = int(self.mid_radius * scale)
        far = int(self.far_radius * scale)
        dark = int(self.dark_radius * scale)

        near = max(24, near)
        mid = max(near + 24, mid)
        far = max(mid + 24, far)
        dark = max(far + 24, dark)
        return near, mid, far, dark


@dataclass(frozen=True)
class RoomArea:
    room_id: str
    x: int
    y: int
    width: int
    height: int
    floor_texture: str
    walls_enabled: bool = True
    wall_thickness: int = 52
    top_wall_height: int = 0
    top_door_width: int = 180
    top_door_offset: int = 0
    left_opening_width: int = 0
    left_opening_offset: int = 0
    right_opening_width: int = 0
    right_opening_offset: int = 0
    bottom_opening_width: int = 0
    bottom_opening_offset: int = 0
    top_left_notch_width: int = 0
    top_left_notch_height: int = 0
    top_partition_offset: int = 0
    top_partition_width: int = 0
    top_opening_layered: bool = False
    top_opening_floor_offset: int = 0
    top_opening_floor_height: int = 0
    top_opening_pass_width: int = 0
    top_opening_pass_offset: int = 0
    top_opening_hard_height: int = 0
    top_opening_occlude_depth: int = 0


@dataclass(frozen=True)
class ObjectTransition:
    state: int | None = None
    blocking: bool | None = None


@dataclass(frozen=True)
class GraffitiMark:
    x: float
    y: float
    letter: str
    target_kind: str
    target_id: str
    color: tuple[int, int, int] = (255, 96, 178)


@dataclass
class SprayTag:
    x: float
    y: float
    width: int
    height: int
    target_kind: str
    target_id: str
    spray_area_id: str = ""
    profile_id: str = "default"
    sequence_index: int = 0
    frame_index: int = 0


@dataclass(frozen=True)
class BalloonSpec:
    balloon_id: str
    item_id: str
    sprite_path: str
    world_size: tuple[int, int] = (78, 110)
    icon_size: tuple[int, int] = (30, 42)
    chroma_green_delta: int = 34
    chroma_green_min: int = 92
    default_graffiti_id: str = "default"


@dataclass(frozen=True)
class GraffitiSpec:
    profile_id: str
    sheet_paths: list[str]
    preserve_aspect: bool = True
    char_width_mult: float = 3.0
    size_mul: float = 1.0


@dataclass
class WorldObject:
    object_id: str
    kind: str
    x: float
    y: float
    door_orientation: str = "top"
    state: int = 0
    blocking: bool = False
    cycle_sprites: bool = False
    occlude_top: bool = False
    occlude_split: float | None = None
    jump_platform_w: float | None = None
    jump_platform_h: float | None = None
    jump_platform_offset_y: float = 0.0
    collider_w: float | None = None
    collider_h: float | None = None
    label: str | None = None
    pickup_item_id: str | None = None
    required_item_id: str | None = None
    lock_key_sets: list[list[str]] = field(default_factory=list)
    lock_open_flags: list[bool] = field(default_factory=list)
    consume_required_item: bool = False
    use_set_state: int | None = None
    use_set_blocking: bool | None = None
    transitions: dict[str, ObjectTransition] = field(default_factory=dict)
    tint_rgb: tuple[int, int, int] | None = None
    tint_strength: float = 1.0
    lock_marker_rgb: tuple[int, int, int] | None = None
    lock_marker_text: str | None = None
    weight_kg: float = 0.0
    spray_zoom_coef: float = 1.0
    width: int = 64
    height: int = 64

    def ensure_lock_flags(self) -> None:
        if not self.lock_key_sets:
            self.lock_open_flags = []
            return
        if len(self.lock_open_flags) != len(self.lock_key_sets):
            self.lock_open_flags = [False] * len(self.lock_key_sets)

    def has_locks(self) -> bool:
        return len(self.lock_key_sets) > 0

    def opened_locks_count(self) -> int:
        self.ensure_lock_flags()
        return sum(1 for v in self.lock_open_flags if v)

    def total_locks_count(self) -> int:
        return len(self.lock_key_sets)

    def is_fully_unlocked(self) -> bool:
        self.ensure_lock_flags()
        if not self.lock_key_sets:
            return False
        return all(self.lock_open_flags)

    def try_open_lock_with_key(self, key_item_id: str) -> bool:
        self.ensure_lock_flags()
        for idx, key_set in enumerate(self.lock_key_sets):
            if self.lock_open_flags[idx]:
                continue
            if key_item_id in key_set:
                self.lock_open_flags[idx] = True
                return True
        return False

    def transition_for(self, event_name: str) -> ObjectTransition | None:
        if not event_name:
            return None
        return self.transitions.get(event_name)


@dataclass
class ItemObject(WorldObject):
    item_id: str = ""
    uses_per_room_limit: int = 0


@dataclass
class BalloonObject(ItemObject):
    balloon_id: str = "default"
    graffiti_profile_id: str = ""


@dataclass
class WorldMap:
    width: int
    height: int
    spawn_x: int
    spawn_y: int
    show_object_labels: bool = False
    player_stats: PlayerStats = field(default_factory=PlayerStats)
    item_weights: dict[str, float] = field(default_factory=dict)
    item_inventory_bonus_slots: dict[str, int] = field(default_factory=dict)
    item_inventory_bonus_weight_limit_kg: dict[str, float] = field(default_factory=dict)
    item_backpack_storable: dict[str, bool] = field(default_factory=dict)
    item_room_use_limits: dict[str, int] = field(default_factory=dict)
    spray_profiles: dict[str, list[str]] = field(default_factory=dict)
    item_spray_profiles: dict[str, str] = field(default_factory=dict)
    balloon_specs: dict[str, BalloonSpec] = field(default_factory=dict)
    balloon_item_ids: dict[str, str] = field(default_factory=dict)
    graffiti_specs: dict[str, GraffitiSpec] = field(default_factory=dict)
    fog: FogSettings = field(default_factory=FogSettings)
    rooms: list[RoomArea] = field(default_factory=list)
    objects: list[WorldObject] = field(default_factory=list)

    def remove_object(self, object_id: str) -> WorldObject | None:
        for i, obj in enumerate(self.objects):
            if obj.object_id == object_id:
                return self.objects.pop(i)
        return None

    def add_object(self, obj: WorldObject) -> None:
        self.objects.append(obj)

    def spray_item_ids(self) -> set[str]:
        ids = set(self.item_spray_profiles.keys())
        ids.update(self.balloon_item_ids.keys())
        return {item_id for item_id in ids if item_id}

    def default_balloon_id(self) -> str:
        if "default" in self.balloon_specs:
            return "default"
        if self.balloon_specs:
            return next(iter(self.balloon_specs.keys()))
        return "default"

    def balloon_id_for_item(self, item_id: str | None) -> str | None:
        if item_id is None:
            return None
        token = str(item_id).strip()
        if not token:
            return None
        direct = self.balloon_item_ids.get(token)
        if direct:
            return direct
        if token in self.balloon_specs:
            return token
        return None

    def default_balloon_item_id(self) -> str:
        default_id = self.default_balloon_id()
        spec = self.balloon_specs.get(default_id)
        if spec is not None and spec.item_id:
            return spec.item_id
        return "ballon"


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
