from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ksusha_game.domain.player import PlayerStats
from ksusha_game.domain.world import (
    BalloonObject,
    BalloonSpec,
    FogSettings,
    GraffitiSpec,
    ItemObject,
    ObjectTransition,
    RoomArea,
    WorldMap,
    WorldObject,
)


@dataclass(frozen=True)
class FloorAtlasConfig:
    atlas_path: Path
    columns: int
    rows: int
    textures: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class LoadedMap:
    world: WorldMap
    floor_atlas: FloorAtlasConfig


class MapLoader:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def load(self, map_path: Path) -> LoadedMap:
        abs_map = self._project_root / map_path
        raw = json.loads(abs_map.read_text(encoding="utf-8"))

        world_cfg = raw["world"]
        player_stats_cfg = world_cfg.get("player_stats", {})
        fog_cfg = world_cfg.get("fog", {})
        fog_color_raw = fog_cfg.get("color", [8, 10, 16])
        fog_color = (
            int(fog_color_raw[0]) if isinstance(fog_color_raw, list) and len(fog_color_raw) == 3 else 8,
            int(fog_color_raw[1]) if isinstance(fog_color_raw, list) and len(fog_color_raw) == 3 else 10,
            int(fog_color_raw[2]) if isinstance(fog_color_raw, list) and len(fog_color_raw) == 3 else 16,
        )

        player_stats = PlayerStats(
            speed=float(player_stats_cfg.get("speed", 1.0)),
            vision=float(player_stats_cfg.get("vision", 1.0)),
            jump_power=float(player_stats_cfg.get("jump_power", 1.0)),
            weight_kg=float(player_stats_cfg.get("weight_kg", player_stats_cfg.get("weight", 25.0))),
            height_cm=float(player_stats_cfg.get("height_cm", player_stats_cfg.get("height", 150.0))),
        )
        fog_settings = FogSettings(
            enabled=bool(fog_cfg.get("enabled", False)),
            near_radius=float(fog_cfg.get("near_radius", 170.0)),
            mid_radius=float(fog_cfg.get("mid_radius", 300.0)),
            far_radius=float(fog_cfg.get("far_radius", 460.0)),
            dark_radius=float(fog_cfg.get("dark_radius", 640.0)),
            medium_blur_scale=float(fog_cfg.get("medium_blur_scale", 0.42)),
            far_blur_scale=float(fog_cfg.get("far_blur_scale", 0.20)),
            mid_dark_alpha=int(fog_cfg.get("mid_dark_alpha", 36)),
            far_dark_alpha=int(fog_cfg.get("far_dark_alpha", 110)),
            outer_dark_alpha=int(fog_cfg.get("outer_dark_alpha", 220)),
            color=fog_color,
            transition=float(fog_cfg.get("transition", 56.0)),
        )

        rooms = [
            RoomArea(
                room_id=item["id"],
                x=int(item["x"]),
                y=int(item["y"]),
                width=int(item["width"]),
                height=int(item["height"]),
                floor_texture=item["floor_texture"],
                walls_enabled=bool(item.get("walls_enabled", True)),
                wall_thickness=int(item.get("wall_thickness", 52)),
                top_wall_height=int(item.get("top_wall_height", 0)),
                top_door_width=int(item.get("top_door_width", 180)),
                top_door_offset=int(item.get("top_door_offset", 0)),
                left_opening_width=int(item.get("left_opening_width", 0)),
                left_opening_offset=int(item.get("left_opening_offset", 0)),
                right_opening_width=int(item.get("right_opening_width", 0)),
                right_opening_offset=int(item.get("right_opening_offset", 0)),
                bottom_opening_width=int(item.get("bottom_opening_width", 0)),
                bottom_opening_offset=int(item.get("bottom_opening_offset", 0)),
                top_left_notch_width=int(item.get("top_left_notch_width", 0)),
                top_left_notch_height=int(item.get("top_left_notch_height", 0)),
                top_partition_offset=int(item.get("top_partition_offset", 0)),
                top_partition_width=int(item.get("top_partition_width", 0)),
                top_opening_layered=bool(item.get("top_opening_layered", False)),
                top_opening_floor_offset=int(item.get("top_opening_floor_offset", 0)),
                top_opening_floor_height=int(item.get("top_opening_floor_height", 0)),
                top_opening_pass_width=int(item.get("top_opening_pass_width", 0)),
                top_opening_pass_offset=int(item.get("top_opening_pass_offset", 0)),
                top_opening_hard_height=int(item.get("top_opening_hard_height", 0)),
                top_opening_occlude_depth=int(item.get("top_opening_occlude_depth", 0)),
            )
            for item in raw["rooms"]
        ]

        asset_settings = raw.get("asset_settings", {})
        balloons_root_raw = (
            asset_settings.get("balloons_root", "source/textures/items/balons")
            if isinstance(asset_settings, dict)
            else "source/textures/items/balons"
        )
        graffity_root_raw = (
            asset_settings.get("graffity_root", "source/textures/graffity")
            if isinstance(asset_settings, dict)
            else "source/textures/graffity"
        )
        balloon_specs, balloon_item_ids = self._load_balloon_specs(Path(str(balloons_root_raw)))
        graffiti_specs = self._load_graffiti_specs(Path(str(graffity_root_raw)))
        item_settings = self._load_item_settings(Path("source/textures/items"))

        object_kinds: dict[str, dict] = raw.get("object_kinds", {})
        raw_item_weights = raw.get("item_weights", {})
        item_weights: dict[str, float] = {}
        if isinstance(raw_item_weights, dict):
            for key, value in raw_item_weights.items():
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                item_weights[str(key)] = max(0.0, parsed)
        for item_id, spec in item_settings.items():
            raw_weight = spec.get("weight_kg", spec.get("weight"))
            if raw_weight is None:
                continue
            try:
                parsed = float(raw_weight)
            except (TypeError, ValueError):
                continue
            item_weights.setdefault(item_id, max(0.0, parsed))

        item_inventory_bonus_slots: dict[str, int] = {}
        item_inventory_bonus_weight_limit_kg: dict[str, float] = {}
        item_backpack_storable: dict[str, bool] = {}
        for item_id, spec in item_settings.items():
            raw_bonus = spec.get("inventory_slots_bonus", spec.get("inventory_bonus_slots", 0))
            try:
                parsed_bonus = max(0, int(raw_bonus))
            except (TypeError, ValueError):
                parsed_bonus = 0
            if parsed_bonus > 0:
                item_inventory_bonus_slots[item_id] = parsed_bonus

            raw_limit = spec.get(
                "inventory_bonus_max_weight_kg",
                spec.get("inventory_bonus_weight_limit_kg", 0.0),
            )
            try:
                parsed_limit = max(0.0, float(raw_limit))
            except (TypeError, ValueError):
                parsed_limit = 0.0
            if parsed_limit > 0.0:
                item_inventory_bonus_weight_limit_kg[item_id] = parsed_limit

            if "can_store_in_backpack" in spec:
                item_backpack_storable[item_id] = bool(spec.get("can_store_in_backpack"))

        raw_item_bonus_slots = raw.get("item_inventory_bonus_slots", {})
        if isinstance(raw_item_bonus_slots, dict):
            for key, value in raw_item_bonus_slots.items():
                try:
                    item_inventory_bonus_slots[str(key)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue
        raw_item_bonus_weight_limits = raw.get("item_inventory_bonus_weight_limits", {})
        if isinstance(raw_item_bonus_weight_limits, dict):
            for key, value in raw_item_bonus_weight_limits.items():
                try:
                    item_inventory_bonus_weight_limit_kg[str(key)] = max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
        raw_item_backpack_storable = raw.get("item_backpack_storable", {})
        if isinstance(raw_item_backpack_storable, dict):
            for key, value in raw_item_backpack_storable.items():
                item_backpack_storable[str(key)] = bool(value)
        raw_default_balloon_weight = object_kinds.get("ballon", {}).get(
            "weight_kg",
            object_kinds.get("ballon", {}).get("weight", 0.0),
        )
        try:
            default_balloon_weight = max(0.0, float(raw_default_balloon_weight))
        except (TypeError, ValueError):
            default_balloon_weight = 0.0
        for spec in balloon_specs.values():
            if spec.item_id and spec.item_id not in item_weights:
                item_weights[spec.item_id] = default_balloon_weight

        raw_item_room_use_limits = raw.get("item_room_use_limits", {})
        item_room_use_limits: dict[str, int] = {}
        if isinstance(raw_item_room_use_limits, dict):
            for key, value in raw_item_room_use_limits.items():
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                item_room_use_limits[str(key)] = max(0, parsed)

        spray_profiles: dict[str, list[str]] = {
            profile_id: list(spec.sheet_paths)
            for profile_id, spec in graffiti_specs.items()
            if spec.sheet_paths
        }
        raw_spray_profiles = raw.get("spray_profiles", {})
        if isinstance(raw_spray_profiles, dict):
            for key, value in raw_spray_profiles.items():
                profile_id = str(key).strip()
                if not profile_id:
                    continue
                paths: list[str] = []
                if isinstance(value, list):
                    for entry in value:
                        token = str(entry).strip()
                        if token:
                            paths.append(token)
                else:
                    token = str(value).strip()
                    if token:
                        paths.append(token)
                if paths:
                    spray_profiles[profile_id] = paths

        item_spray_profiles: dict[str, str] = {}
        for spec in balloon_specs.values():
            if spec.item_id and spec.default_graffiti_id:
                item_spray_profiles[spec.item_id] = spec.default_graffiti_id
        for profile_map_key in ("balloon_graffiti_profiles", "item_spray_profiles"):
            raw_item_spray_profiles = raw.get(profile_map_key, {})
            if not isinstance(raw_item_spray_profiles, dict):
                continue
            for item_id, profile_id in raw_item_spray_profiles.items():
                item_key = str(item_id).strip()
                profile_key = str(profile_id).strip()
                if not item_key or not profile_key:
                    continue
                if item_key in balloon_specs:
                    resolved_item_key = balloon_specs[item_key].item_id
                else:
                    resolved_item_key = item_key
                if resolved_item_key:
                    item_spray_profiles[resolved_item_key] = profile_key

        objects: list[WorldObject] = []

        def _clamp_rgb_channel(value: object) -> int:
            return max(0, min(255, int(value)))

        def _parse_rgb(value: object) -> tuple[int, int, int] | None:
            if value is None:
                return None
            if isinstance(value, list) and len(value) == 3:
                try:
                    return (
                        _clamp_rgb_channel(value[0]),
                        _clamp_rgb_channel(value[1]),
                        _clamp_rgb_channel(value[2]),
                    )
                except (TypeError, ValueError):
                    return None
            if isinstance(value, str):
                raw_hex = value.strip().lstrip("#")
                if len(raw_hex) != 6:
                    return None
                try:
                    return (
                        int(raw_hex[0:2], 16),
                        int(raw_hex[2:4], 16),
                        int(raw_hex[4:6], 16),
                    )
                except ValueError:
                    return None
            return None

        def _normalize_door_orientation(value: object) -> str:
            token = str(value).strip().lower() if value is not None else "top"
            if token in {"left", "right", "top", "bottom"}:
                return token
            return "top"

        for item in raw["objects"]:
            kind = item["kind"]
            kind_defaults = object_kinds.get(kind, {})
            merged = {**kind_defaults, **item}

            collider = merged.get("collider")
            collider_w = (
                float(collider[0]) if isinstance(collider, list) and len(collider) == 2 else None
            )
            collider_h = (
                float(collider[1]) if isinstance(collider, list) and len(collider) == 2 else None
            )
            jump_platform = merged.get("jump_platform")
            jump_platform_w = (
                float(jump_platform[0])
                if isinstance(jump_platform, list) and len(jump_platform) == 3
                else None
            )
            jump_platform_h = (
                float(jump_platform[1])
                if isinstance(jump_platform, list) and len(jump_platform) == 3
                else None
            )
            jump_platform_offset_y = (
                float(jump_platform[2])
                if isinstance(jump_platform, list) and len(jump_platform) == 3
                else 0.0
            )
            raw_lock_sets = merged.get("lock_key_sets")
            lock_key_sets: list[list[str]] = []
            if isinstance(raw_lock_sets, list):
                for raw_set in raw_lock_sets:
                    if isinstance(raw_set, list):
                        keys = [str(k) for k in raw_set if str(k)]
                    else:
                        keys = [str(raw_set)] if str(raw_set) else []
                    if keys:
                        lock_key_sets.append(keys)
            required_item_id = merged.get("required_item_id")
            if not lock_key_sets and required_item_id is not None:
                lock_key_sets = [[str(required_item_id)]]

            raw_lock_flags = merged.get("lock_open_flags")
            lock_open_flags: list[bool] = []
            if isinstance(raw_lock_flags, list):
                lock_open_flags = [bool(v) for v in raw_lock_flags]

            transitions: dict[str, ObjectTransition] = {}
            raw_transitions = merged.get("transitions")
            if isinstance(raw_transitions, dict):
                for event_name, event_cfg in raw_transitions.items():
                    if not event_name:
                        continue
                    key = str(event_name).strip()
                    if not key:
                        continue
                    state: int | None = None
                    blocking: bool | None = None
                    if isinstance(event_cfg, dict):
                        if event_cfg.get("state") is not None:
                            try:
                                state = int(event_cfg["state"])
                            except (TypeError, ValueError):
                                state = None
                        if event_cfg.get("blocking") is not None:
                            blocking = bool(event_cfg["blocking"])
                    elif event_cfg is not None:
                        try:
                            state = int(event_cfg)
                        except (TypeError, ValueError):
                            state = None
                    transitions[key] = ObjectTransition(state=state, blocking=blocking)

            if "unlock" not in transitions:
                legacy_state = merged.get("use_set_state")
                legacy_blocking = merged.get("use_set_blocking")
                parsed_legacy_state: int | None
                try:
                    parsed_legacy_state = int(legacy_state) if legacy_state is not None else None
                except (TypeError, ValueError):
                    parsed_legacy_state = None
                if legacy_state is not None or legacy_blocking is not None:
                    transitions["unlock"] = ObjectTransition(
                        state=parsed_legacy_state,
                        blocking=(bool(legacy_blocking) if legacy_blocking is not None else None),
                    )

            raw_weight = merged.get("weight_kg", merged.get("weight", 0.0))
            try:
                parsed_weight = max(0.0, float(raw_weight))
            except (TypeError, ValueError):
                parsed_weight = 0.0
            raw_spray_zoom = merged.get("spray_zoom_coef", merged.get("graffiti_zoom_coef", 1.0))
            try:
                spray_zoom_coef = max(0.35, min(float(raw_spray_zoom), 3.5))
            except (TypeError, ValueError):
                spray_zoom_coef = 1.0
            tint_rgb = _parse_rgb(merged.get("tint_rgb", merged.get("tint")))
            raw_tint_strength = merged.get("tint_strength", 1.0)
            try:
                tint_strength = max(0.0, min(1.0, float(raw_tint_strength)))
            except (TypeError, ValueError):
                tint_strength = 1.0
            lock_marker_rgb = _parse_rgb(
                merged.get(
                    "lock_marker_rgb",
                    merged.get("lock_indicator_rgb", merged.get("key_marker_rgb")),
                )
            )
            raw_lock_marker_text = merged.get(
                "lock_marker_text",
                merged.get("lock_indicator_text", merged.get("lock_id")),
            )
            lock_marker_text = None
            if raw_lock_marker_text is not None:
                text = str(raw_lock_marker_text).strip()
                if text:
                    lock_marker_text = text[:3].upper()

            object_has_own_pickup = "pickup_item_id" in item and item.get("pickup_item_id") is not None
            raw_pickup_item = merged.get("pickup_item_id")
            pickup_item_id = None
            if raw_pickup_item is not None:
                token = str(raw_pickup_item).strip()
                if token:
                    pickup_item_id = token

            balloon_id = ""
            if kind == "ballon":
                raw_balloon_id = merged.get("balloon_id")
                if raw_balloon_id is not None:
                    balloon_id = str(raw_balloon_id).strip()
                if not balloon_id and pickup_item_id:
                    balloon_id = balloon_item_ids.get(pickup_item_id, "")
                if not balloon_id:
                    balloon_id = "default" if "default" in balloon_specs else ""
                spec = balloon_specs.get(balloon_id)
                if spec is not None and (not pickup_item_id or not object_has_own_pickup):
                    pickup_item_id = spec.item_id
                if pickup_item_id and pickup_item_id not in balloon_item_ids:
                    balloon_item_ids[pickup_item_id] = balloon_id or "default"

            base_kwargs = dict(
                object_id=merged["id"],
                kind=kind,
                x=float(merged["x"]),
                y=float(merged["y"]),
                door_orientation=_normalize_door_orientation(
                    merged.get("door_orientation", merged.get("orientation", "top"))
                ),
                state=int(merged.get("state", 0)),
                blocking=bool(merged.get("blocking", False)),
                cycle_sprites=bool(merged.get("cycle_sprites", False)),
                occlude_top=bool(merged.get("occlude_top", False)),
                occlude_split=(
                    float(merged["occlude_split"])
                    if merged.get("occlude_split") is not None
                    else None
                ),
                jump_platform_w=jump_platform_w,
                jump_platform_h=jump_platform_h,
                jump_platform_offset_y=jump_platform_offset_y,
                collider_w=collider_w,
                collider_h=collider_h,
                label=merged.get("label"),
                pickup_item_id=pickup_item_id,
                required_item_id=(str(required_item_id) if required_item_id is not None else None),
                lock_key_sets=lock_key_sets,
                lock_open_flags=lock_open_flags,
                consume_required_item=bool(merged.get("consume_required_item", False)),
                use_set_state=(
                    int(merged["use_set_state"])
                    if merged.get("use_set_state") is not None
                    else None
                ),
                use_set_blocking=(
                    bool(merged["use_set_blocking"])
                    if merged.get("use_set_blocking") is not None
                    else None
                ),
                transitions=transitions,
                tint_rgb=tint_rgb,
                tint_strength=tint_strength,
                lock_marker_rgb=lock_marker_rgb,
                lock_marker_text=lock_marker_text,
                weight_kg=parsed_weight,
                spray_zoom_coef=spray_zoom_coef,
                width=int(merged.get("width", 64)),
                height=int(merged.get("height", 64)),
            )

            if kind == "ballon":
                resolved_item_id = pickup_item_id or "ballon"
                resolved_profile = item_spray_profiles.get(resolved_item_id, "")
                if not resolved_profile:
                    spec = balloon_specs.get(balloon_id)
                    if spec is not None:
                        resolved_profile = spec.default_graffiti_id
                objects.append(
                    BalloonObject(
                        **base_kwargs,
                        item_id=resolved_item_id,
                        balloon_id=balloon_id or "default",
                        graffiti_profile_id=resolved_profile,
                    )
                )
            elif pickup_item_id is not None:
                objects.append(
                    ItemObject(
                        **base_kwargs,
                        item_id=pickup_item_id,
                    )
                )
            else:
                objects.append(WorldObject(**base_kwargs))

        world = WorldMap(
            width=int(world_cfg["width"]),
            height=int(world_cfg["height"]),
            spawn_x=int(world_cfg["spawn"][0]),
            spawn_y=int(world_cfg["spawn"][1]),
            show_object_labels=bool(world_cfg.get("show_object_labels", False)),
            player_stats=player_stats,
            item_weights=item_weights,
            item_inventory_bonus_slots=item_inventory_bonus_slots,
            item_inventory_bonus_weight_limit_kg=item_inventory_bonus_weight_limit_kg,
            item_backpack_storable=item_backpack_storable,
            item_room_use_limits=item_room_use_limits,
            spray_profiles=spray_profiles,
            item_spray_profiles=item_spray_profiles,
            balloon_specs=balloon_specs,
            balloon_item_ids=balloon_item_ids,
            graffiti_specs=graffiti_specs,
            fog=fog_settings,
            rooms=rooms,
            objects=objects,
        )

        floor_cfg = raw["floors"]
        textures = {
            key: (int(value[0]), int(value[1]))
            for key, value in floor_cfg["textures"].items()
        }

        floor_atlas = FloorAtlasConfig(
            atlas_path=Path(floor_cfg["atlas_path"]),
            columns=int(floor_cfg["columns"]),
            rows=int(floor_cfg["rows"]),
            textures=textures,
        )

        return LoadedMap(world=world, floor_atlas=floor_atlas)

    def _load_balloon_specs(self, settings_root: Path) -> tuple[dict[str, BalloonSpec], dict[str, str]]:
        specs: dict[str, BalloonSpec] = {}
        item_to_balloon: dict[str, str] = {}
        root = settings_root if settings_root.is_absolute() else self._project_root / settings_root
        settings_paths: list[Path] = []
        if root.exists():
            for candidate in sorted(root.glob("*/settings.json")):
                settings_paths.append(candidate)
            for candidate in sorted(root.glob("*/setting.json")):
                if candidate not in settings_paths:
                    settings_paths.append(candidate)

        for settings_path in settings_paths:
            try:
                raw = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            balloon_id = str(raw.get("id", settings_path.parent.name)).strip().lower()
            if not balloon_id:
                continue
            item_id = str(
                raw.get(
                    "item_id",
                    "ballon" if balloon_id == "default" else f"ballon_{balloon_id}",
                )
            ).strip()
            if not item_id:
                item_id = "ballon"

            sprite_rel = str(raw.get("sprite_path", "")).strip()
            if sprite_rel:
                sprite_path = self._resolve_asset_path(settings_path.parent, sprite_rel)
            else:
                local_png = settings_path.parent / "ballon.png"
                if local_png.exists():
                    sprite_path = self._to_project_rel_path(local_png)
                else:
                    legacy = self._project_root / "source/textures/items/ballon/ballon.png"
                    if not legacy.exists():
                        continue
                    sprite_path = self._to_project_rel_path(legacy)

            world_size = self._parse_size(raw.get("world_size"), default=(78, 110))
            icon_size = self._parse_size(raw.get("icon_size"), default=(30, 42))
            try:
                green_delta = int(raw.get("chroma_green_delta", 34))
            except (TypeError, ValueError):
                green_delta = 34
            try:
                green_min = int(raw.get("chroma_green_min", 92))
            except (TypeError, ValueError):
                green_min = 92
            default_graffiti_id = str(raw.get("default_graffiti_id", "default")).strip() or "default"

            spec = BalloonSpec(
                balloon_id=balloon_id,
                item_id=item_id,
                sprite_path=sprite_path,
                world_size=world_size,
                icon_size=icon_size,
                chroma_green_delta=green_delta,
                chroma_green_min=green_min,
                default_graffiti_id=default_graffiti_id,
            )
            specs[balloon_id] = spec
            item_to_balloon[item_id] = balloon_id

        if not specs:
            legacy_sprite = self._project_root / "source/textures/items/ballon/ballon.png"
            if legacy_sprite.exists():
                default_spec = BalloonSpec(
                    balloon_id="default",
                    item_id="ballon",
                    sprite_path=self._to_project_rel_path(legacy_sprite),
                )
                specs["default"] = default_spec
                item_to_balloon["ballon"] = "default"

        return specs, item_to_balloon

    def _load_graffiti_specs(self, settings_root: Path) -> dict[str, GraffitiSpec]:
        specs: dict[str, GraffitiSpec] = {}
        root = settings_root if settings_root.is_absolute() else self._project_root / settings_root
        settings_paths: list[Path] = []
        if root.exists():
            for candidate in sorted(root.glob("*/settings.json")):
                settings_paths.append(candidate)
            for candidate in sorted(root.glob("*/setting.json")):
                if candidate not in settings_paths:
                    settings_paths.append(candidate)

        for settings_path in settings_paths:
            try:
                raw = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            profile_id = str(raw.get("id", settings_path.parent.name)).strip().lower()
            if not profile_id:
                continue

            raw_paths = raw.get("sheet_paths", raw.get("sheet_path", []))
            paths: list[str] = []
            if isinstance(raw_paths, list):
                iterable = raw_paths
            else:
                iterable = [raw_paths]
            for entry in iterable:
                token = str(entry).strip()
                if not token:
                    continue
                paths.append(self._resolve_asset_path(settings_path.parent, token))
            if not paths:
                local_sheet = settings_path.parent / "spray_reveal_sheet.png"
                if local_sheet.exists():
                    paths.append(self._to_project_rel_path(local_sheet))
            if not paths:
                continue
            render_raw = raw.get("render")
            render = render_raw if isinstance(render_raw, dict) else {}
            preserve_aspect = bool(render.get("preserve_aspect", raw.get("preserve_aspect", True)))
            try:
                char_width_mult = float(render.get("char_width_mult", raw.get("char_width_mult", 3.0)))
            except (TypeError, ValueError):
                char_width_mult = 3.0
            try:
                size_mul = float(render.get("size_mul", raw.get("size_mul", 1.0)))
            except (TypeError, ValueError):
                size_mul = 1.0
            char_width_mult = max(0.45, min(char_width_mult, 8.0))
            size_mul = max(0.20, min(size_mul, 4.0))
            specs[profile_id] = GraffitiSpec(
                profile_id=profile_id,
                sheet_paths=paths,
                preserve_aspect=preserve_aspect,
                char_width_mult=char_width_mult,
                size_mul=size_mul,
            )

        if "default" not in specs:
            legacy_default = self._project_root / "source/textures/items/ballon/spray_reveal_sheet.png"
            if legacy_default.exists():
                specs["default"] = GraffitiSpec(
                    profile_id="default",
                    sheet_paths=[self._to_project_rel_path(legacy_default)],
                    preserve_aspect=True,
                    char_width_mult=3.0,
                    size_mul=1.0,
                )
        return specs

    def _parse_size(self, raw_size: object, default: tuple[int, int]) -> tuple[int, int]:
        if isinstance(raw_size, list) and len(raw_size) == 2:
            try:
                w = max(8, int(raw_size[0]))
                h = max(8, int(raw_size[1]))
                return (w, h)
            except (TypeError, ValueError):
                pass
        return default

    def _resolve_asset_path(self, base_dir: Path, raw_path: str) -> str:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return str(candidate)
        local = base_dir / candidate
        if local.exists():
            return self._to_project_rel_path(local)
        project_path = self._project_root / candidate
        if project_path.exists():
            return self._to_project_rel_path(project_path)
        return raw_path

    def _to_project_rel_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._project_root.resolve()))
        except ValueError:
            return str(path.resolve())

    def _load_item_settings(self, items_root: Path) -> dict[str, dict]:
        root = items_root if items_root.is_absolute() else self._project_root / items_root
        out: dict[str, dict] = {}
        if not root.exists():
            return out
        settings_paths: list[Path] = []
        for candidate in sorted(root.rglob("settings.json")):
            settings_paths.append(candidate)
        for candidate in sorted(root.rglob("setting.json")):
            if candidate not in settings_paths:
                settings_paths.append(candidate)
        for path in settings_paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            raw_item_id = raw.get("item_id", raw.get("id", ""))
            item_id = str(raw_item_id).strip()
            if not item_id:
                continue
            out[item_id] = raw
        return out
