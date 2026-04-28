from __future__ import annotations

from collections import deque
import math
import os
import time
from pathlib import Path

import pygame

from ksusha_game.application.input_controller import KeyboardInputController
from ksusha_game.config import GameConfig
from ksusha_game.domain.direction import Direction
from ksusha_game.domain.inventory import Inventory
from ksusha_game.domain.player import Player
from ksusha_game.domain.world import (
    FACING_VECTOR,
    BalloonObject,
    RoomArea,
    SprayTag,
    WorldMap,
    WorldObject,
)
from ksusha_game.infrastructure.asset_cache import SpriteCache
from ksusha_game.infrastructure.floor_tileset import FloorTileset
from ksusha_game.infrastructure.frame_processing import FramePreprocessor, FrameProcessingConfig
from ksusha_game.infrastructure.map_loader import MapLoader
from ksusha_game.infrastructure.object_sprites import ObjectSpriteLibrary
from ksusha_game.infrastructure.sprite_sheet_loader import ScaledAnimationCache, SpriteSheetLoader
from ksusha_game.infrastructure.wall_sprites import WallSpriteLibrary
from ksusha_game.presentation.world_renderer import WorldRenderer


class KsushaGame:
    _GRAB_MAX_DISTANCE = 104.0
    _DRAG_ACTIVE_DISTANCE = 118.0
    _DRAG_RELEASE_DISTANCE = 176.0
    _PLANT_GRAB_MAX_GAP = 10.0
    _NEAR_INTERACT_GAP = 14.0
    _NEAR_PICKUP_GAP = 18.0

    def __init__(self, config: GameConfig) -> None:
        self._config = config
        self._message = ""
        self._message_until = 0.0
        self._drop_counter = 0
        self._interaction_anchor_offset = (44.0, 58.0)
        self._standing_on_object_id: str | None = None
        self._grabbed_object_id: str | None = None
        self._spray_tags: list[SprayTag] = []
        self._spray_active_target: tuple[str, str] | None = None
        self._spray_active_tag_index: int | None = None
        self._spray_hold_accum = 0.0
        self._spray_frame_interval = 0.055
        # Tracks consumed spray by inventory slot (slot_index -> item_id).
        self._spray_spent_slots: dict[int, str] = {}
        self._door_overlap_ids: set[str] = set()
        self._room_item_use_counts: dict[tuple[str, str], int] = {}
        self._spray_item_ids: set[str] = {"ballon"}
        self._spray_profile_sequences: dict[str, object] = {}
        self._async_preload_queue: deque[tuple[str, str]] = deque()
        self._async_preload_pending: set[tuple[str, str]] = set()
        self._active_area_id: str | None = None
        # Event handlers run before per-frame sprite selection, so keep last known player sprite size.
        self._last_player_sprite_size: tuple[int, int] = (100, 120)

    def run(self) -> int:
        project_root = Path(__file__).resolve().parents[3]
        dev_hot_enabled = os.getenv("KSU_DEV_HOT", "").strip().lower() in {"1", "true", "yes", "on"}

        pygame.init()
        pygame.display.set_caption("Ksusha Rooms")
        screen = pygame.display.set_mode(self._config.window.size, pygame.RESIZABLE)
        clock = pygame.time.Clock()

        frame_cfg = FrameProcessingConfig(
            alpha_component_cutoff=self._config.sprite_sheet.alpha_component_cutoff,
            crop_padding=self._config.sprite_sheet.crop_padding,
            bg_model_stable_tol=self._config.sprite_sheet.bg_model_stable_tol,
            bg_model_match_tol=self._config.sprite_sheet.bg_model_match_tol,
            bg_model_alpha_tol=self._config.sprite_sheet.bg_model_alpha_tol,
        )
        preprocessor = FramePreprocessor(frame_cfg)
        cache = SpriteCache(project_root / ".asset_cache")
        loader = SpriteSheetLoader(self._config.sprite_sheet, preprocessor, cache=cache)
        (
            world,
            floor_tileset,
            wall_sprites,
            object_sprites,
            walk_cache,
            backpack_cache,
        ) = self._load_runtime_resources(project_root, loader, cache)
        input_controller = KeyboardInputController()
        renderer = WorldRenderer(self._config)
        inventory = Inventory(base_capacity=5, capacity=5)

        player = Player(x=float(world.spawn_x), y=float(world.spawn_y), stats=world.player_stats)
        snapshot = self._resource_snapshot(project_root) if dev_hot_enabled else None
        next_hot_check = 0.0

        running = True
        while running:
            dt = clock.tick(self._config.window.fps) / 1000.0
            now = time.monotonic()
            reload_requested = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.KEYUP:
                    input_controller.on_keyup(event)
                elif event.type in {pygame.WINDOWFOCUSLOST, pygame.WINDOWLEAVE}:
                    # Avoid sticky hold-actions (E/drag/spray) after focus or cursor leaves the window.
                    input_controller.clear_pressed()
                elif event.type == pygame.KEYDOWN:
                    input_controller.on_keydown(event, now)
                    if input_controller.is_action(event, "reload"):
                        reload_requested = True
                        continue
                    self._handle_key(
                        event=event,
                        input_controller=input_controller,
                        inventory=inventory,
                        world=world,
                        player=player,
                        object_sprites=object_sprites,
                    )

            self._process_async_preloads(world, object_sprites, budget_ms=1.8, max_jobs=1)

            if dev_hot_enabled and now >= next_hot_check:
                next_hot_check = now + 0.45
                new_snapshot = self._resource_snapshot(project_root)
                if snapshot is None or new_snapshot != snapshot:
                    snapshot = new_snapshot
                    reload_requested = True

            if reload_requested:
                try:
                    self._async_preload_queue.clear()
                    self._async_preload_pending.clear()
                    (
                        world,
                        floor_tileset,
                        wall_sprites,
                        object_sprites,
                        walk_cache,
                        backpack_cache,
                    ) = self._load_runtime_resources(project_root, loader, cache)
                    player.stats = world.player_stats
                    self._grabbed_object_id = None
                    self._spray_tags.clear()
                    self._reset_spray_state()
                    self._door_overlap_ids.clear()
                    self._spray_spent_slots.clear()
                    self._active_area_id = None
                    self._set_message("Hot reload: assets/map reloaded")
                except Exception as exc:
                    self._set_message(f"Hot reload failed: {exc}")

            width, height = screen.get_size()
            target_h = max(28, int(height * self._config.sprite_sheet.target_height_ratio))
            wearing_backpack = self._inventory_has_item(inventory, "backpack")
            animation_cache = backpack_cache if wearing_backpack else walk_cache
            frames_by_dir = animation_cache.frames_for_height(target_h)

            dx, dy = input_controller.read_direction()
            keys = pygame.key.get_pressed()
            holding_pickup = input_controller.is_action_pressed(keys, "pickup")
            self._sync_inventory_extension_from_active_item(inventory, world)
            selected_item = inventory.selected_item()
            selected_slot_index = inventory.active_index
            spray_holding = holding_pickup and self._is_spray_item(selected_item)
            drag_hold = holding_pickup
            pre_frames = frames_by_dir[player.facing]
            pre_sprite_w = pre_frames[0].get_width()
            pre_sprite_h = pre_frames[0].get_height()
            speed = (
                min(width, height)
                * self._config.sprite_sheet.move_speed_ratio
                * player.stats.speed_multiplier()
            )
            run_boost = input_controller.speed_multiplier(now, dx, dy)
            speed *= run_boost
            speed *= self._drag_movement_speed_factor(
                holding_pickup=drag_hold,
                input_dx=dx,
                input_dy=dy,
                player=player,
                sprite_w=pre_sprite_w,
                sprite_h=pre_sprite_h,
                world=world,
                object_sprites=object_sprites,
                inventory=inventory,
            )
            is_running = run_boost > 1.01
            prev_x, prev_y = player.x, player.y
            moving = player.apply_input(
                dx=dx,
                dy=dy,
                speed=speed,
                dt=dt,
                anim_fps=self._config.sprite_sheet.anim_fps,
            )
            was_jumping = player.jump_time_left > 0.0
            player.update_jump(dt)
            landed = was_jumping and player.jump_time_left <= 0.0

            current_frames = frames_by_dir[player.facing]
            sprite_w = current_frames[0].get_width()
            sprite_h = current_frames[0].get_height()
            self._last_player_sprite_size = (sprite_w, sprite_h)
            player.clamp_to_bounds(
                max_x=world.width - sprite_w,
                max_y=world.height - sprite_h,
            )
            self._update_grab_target_state(
                holding_pickup=drag_hold,
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                world=world,
                object_sprites=object_sprites,
                inventory=inventory,
            )
            self._update_standing_platform(player, sprite_w, sprite_h, world, object_sprites)
            if landed:
                self._try_land_on_platform(player, sprite_w, sprite_h, world, object_sprites)
            self._resolve_blocking_collisions(
                player=player,
                prev_x=prev_x,
                prev_y=prev_y,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                world=world,
                object_sprites=object_sprites,
                inventory=inventory,
                is_running=is_running,
            )
            self._resolve_room_wall_collisions(
                player=player,
                prev_x=prev_x,
                prev_y=prev_y,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                world=world,
            )
            self._update_grabbed_object_drag(
                player=player,
                prev_x=prev_x,
                prev_y=prev_y,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                world=world,
                object_sprites=object_sprites,
                inventory=inventory,
                holding_pickup=drag_hold,
            )

            current_frames = frames_by_dir[player.facing]
            frame_index = int(player.walk_time) % len(current_frames)
            current_frame = current_frames[frame_index]
            bob = math.sin(player.walk_time * 2.0 * math.pi / len(current_frames)) * (2 if moving else 0)
            jump_y = player.jump_offset()
            self._update_spray_recharge_by_door_crossing(
                player=player,
                sprite_w=current_frame.get_width(),
                sprite_h=current_frame.get_height(),
                world=world,
                object_sprites=object_sprites,
            )
            spray_area_id = self._area_id_for_player(
                world=world,
                player=player,
                sprite_w=current_frame.get_width(),
                sprite_h=current_frame.get_height(),
            )
            self._sync_interaction_state_on_area_change(spray_area_id)
            self._update_spray_painting(
                holding_spray=spray_holding,
                dt=dt,
                selected_spray_item=selected_item,
                selected_spray_slot_index=selected_slot_index,
                spray_area_id=spray_area_id,
                player=player,
                player_sprite_w=current_frame.get_width(),
                player_sprite_h=current_frame.get_height(),
                world=world,
                object_sprites=object_sprites,
            )

            player_center = (player.x + current_frame.get_width() / 2, player.y + current_frame.get_height() / 2)
            left_facing = player.facing in {Direction.LEFT, Direction.UP_LEFT, Direction.DOWN_LEFT}

            message = self._message if now < self._message_until else ""
            renderer.render(
                screen=screen,
                world=world,
                floor_tileset=floor_tileset,
                wall_sprites=wall_sprites,
                object_sprites=object_sprites,
                objects=world.objects,
                player_pos=player_center,
                player_frame=current_frame,
                player_bob=bob + jump_y,
                player_left_facing=left_facing,
                inventory=inventory,
                spray_tags=self._spray_tags,
                message=message,
                dragged_object_id=self._grabbed_object_id,
            )

            pygame.display.set_caption(
                f"Ksusha Rooms | backpack={'on' if wearing_backpack else 'off'} | Arrows move | E interact | F5 reload"
            )
            pygame.display.flip()

        pygame.quit()
        return 0

    def _load_runtime_resources(
        self,
        project_root: Path,
        loader: SpriteSheetLoader,
        cache: SpriteCache,
    ) -> tuple[
        WorldMap,
        FloorTileset,
        WallSpriteLibrary,
        ObjectSpriteLibrary,
        ScaledAnimationCache,
        ScaledAnimationCache,
    ]:
        loaded_map = MapLoader(project_root).load(self._config.map_path)
        world = loaded_map.world
        floor_tileset = FloorTileset(loaded_map.floor_atlas, project_root)
        wall_sprites = WallSpriteLibrary(project_root)
        object_sprites = ObjectSpriteLibrary(
            project_root,
            balloon_specs=world.balloon_specs,
            balloon_item_ids=world.balloon_item_ids,
            disk_cache=cache,
        )
        spray_items = world.spray_item_ids()
        self._spray_item_ids = spray_items if spray_items else {"ballon"}
        self._spray_profile_sequences.clear()
        # Pre-queue all spray profiles so they load from disk cache on first frame rather than on pickup.
        for profile_id in world.spray_profiles:
            self._queue_async_preload("spray_profile", profile_id)
        if not world.spray_profiles:
            self._queue_async_preload("spray_profile", "")
        self._keep_interior_objects_off_walls(world, object_sprites)
        walk_cache = ScaledAnimationCache(loader.load_walk_frames(project_root / self._config.sprite_path))
        backpack_cache = ScaledAnimationCache(
            loader.load_walk_frames(project_root / self._config.backpack_sprite_path)
        )
        return world, floor_tileset, wall_sprites, object_sprites, walk_cache, backpack_cache

    def _queue_async_preload(self, kind: str, token: str) -> None:
        key = (kind, token)
        if key in self._async_preload_pending:
            return
        self._async_preload_pending.add(key)
        self._async_preload_queue.append(key)

    def _process_async_preloads(
        self,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        *,
        budget_ms: float,
        max_jobs: int,
    ) -> None:
        if not self._async_preload_queue:
            return
        started = time.perf_counter()
        processed = 0
        while self._async_preload_queue and processed < max_jobs:
            kind, token = self._async_preload_queue.popleft()
            self._async_preload_pending.discard((kind, token))
            try:
                if kind == "item_icon":
                    object_sprites.icon_for_item(token)
                elif kind == "spray_profile":
                    if token not in self._spray_profile_sequences:
                        paths = self._spray_profile_paths(token, world)
                        self._spray_profile_sequences[token] = object_sprites.spray_reveal_sequence(paths)
            except Exception:
                if kind == "spray_profile":
                    # Never keep spray logic blocked by one broken profile.
                    try:
                        fallback_paths = self._spray_profile_paths("default", world)
                        self._spray_profile_sequences[token] = object_sprites.spray_reveal_sequence(fallback_paths)
                    except Exception:
                        self._spray_profile_sequences[token] = []
            processed += 1
            if ((time.perf_counter() - started) * 1000.0) >= budget_ms:
                break

    def _sync_interaction_state_on_area_change(self, new_area_id: str | None) -> None:
        if new_area_id == self._active_area_id:
            return
        prev_area = self._active_area_id
        self._active_area_id = new_area_id
        self._reset_spray_state()
        self._grabbed_object_id = None
        # Crossing between corridor/rooms should always recharge spray items.
        if prev_area != new_area_id and (prev_area is not None or new_area_id is not None):
            self._spray_spent_slots.clear()

    def _keep_interior_objects_off_walls(
        self,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        interior_kinds = {"sofa", "plant", "backpack", "key", "ballon"}
        for obj in world.objects:
            if obj.kind not in interior_kinds:
                continue
            room = self._room_for_point(world, obj.x, obj.y)
            if room is None or not room.walls_enabled:
                continue
            self._clamp_object_inside_room_interior(obj, room, world, object_sprites)

        # Resolve authored overlaps between movable interior blockers (mostly plants near sofas).
        # Without this, grabbed plants can appear "stuck" because they start intersecting a sofa.
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            blockers = [
                obj
                for obj in world.objects
                if obj.kind in interior_kinds
                and obj.blocking
                and self._room_for_point(world, obj.x, obj.y) is room
            ]
            if len(blockers) < 2:
                continue
            for _ in range(8):
                moved = False
                for obj in blockers:
                    if obj.kind == "sofa":
                        continue
                    rect = self._nominal_object_collider_rect(obj, world, object_sprites)
                    for other in blockers:
                        if other.object_id == obj.object_id:
                            continue
                        other_rect = self._nominal_object_collider_rect(other, world, object_sprites)
                        if not rect.colliderect(other_rect):
                            continue
                        overlap_x = min(rect.right, other_rect.right) - max(rect.left, other_rect.left)
                        overlap_y = min(rect.bottom, other_rect.bottom) - max(rect.top, other_rect.top)
                        if overlap_x <= 0 or overlap_y <= 0:
                            continue
                        if overlap_x <= overlap_y:
                            dir_x = -1.0 if rect.centerx < other_rect.centerx else 1.0
                            obj.x += dir_x * float(overlap_x + 1)
                        else:
                            dir_y = -1.0 if rect.centery < other_rect.centery else 1.0
                            obj.y += dir_y * float(overlap_y + 1)
                        self._clamp_object_inside_room_interior(obj, room, world, object_sprites)
                        rect = self._nominal_object_collider_rect(obj, world, object_sprites)
                        moved = True
                if not moved:
                    break

    def _clamp_object_inside_room_interior(
        self,
        obj: WorldObject,
        room: RoomArea,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
        top_t = (
            max(t, min(room.top_wall_height, room.height // 2))
            if room.top_wall_height > 0
            else t
        )
        interior_left = room.x + t + 4
        interior_right = room.x + room.width - t - 4
        interior_top = room.y + top_t + 4
        interior_bottom = room.y + room.height - t - 4
        if interior_left >= interior_right or interior_top >= interior_bottom:
            return

        nominal_w, nominal_h = object_sprites.nominal_world_size(obj.kind, obj)
        collider_w, collider_h, y_anchor = self._object_collider_metrics_from_size(
            obj=obj,
            sprite_w=nominal_w,
            sprite_h=nominal_h,
        )

        min_x = interior_left + collider_w / 2
        max_x = interior_right - collider_w / 2
        if min_x <= max_x:
            obj.x = max(min_x, min(max_x, obj.x))

        min_y = interior_top - y_anchor + collider_h / 2
        max_y = interior_bottom - y_anchor - collider_h / 2
        if min_y <= max_y:
            obj.y = max(min_y, min(max_y, obj.y))

    def _nominal_object_collider_rect(self, obj: WorldObject, world: WorldMap, object_sprites: ObjectSpriteLibrary) -> pygame.Rect:
        nominal_w, nominal_h = object_sprites.nominal_world_size(obj.kind, obj)
        collider_w, collider_h, y_anchor = self._object_collider_metrics_from_size(
            obj=obj,
            sprite_w=nominal_w,
            sprite_h=nominal_h,
        )
        return pygame.Rect(
            int(obj.x - collider_w / 2),
            int(obj.y + y_anchor - collider_h / 2),
            max(8, int(collider_w)),
            max(8, int(collider_h)),
        )

    def _room_for_point(self, world: WorldMap, x: float, y: float) -> RoomArea | None:
        for room in world.rooms:
            if room.x <= x <= room.x + room.width and room.y <= y <= room.y + room.height:
                return room
        return None

    def _area_id_for_player(
        self,
        world: WorldMap,
        player: Player,
        sprite_w: int,
        sprite_h: int,
    ) -> str | None:
        cx = player.x + sprite_w * 0.5
        probes = (
            (cx, player.y + sprite_h * 0.62),
            (cx, player.y + sprite_h * 0.74),
            (cx, player.y + sprite_h * 0.84),
        )
        for px, py in probes:
            rid = self._room_id_for_point_half_open(world, px, py)
            if rid is not None:
                return rid
        room = self._room_for_point(world, cx, player.y + sprite_h * 0.84)
        return room.room_id if room is not None else None

    def _room_id_for_point_half_open(self, world: WorldMap, x: float, y: float) -> str | None:
        # Half-open bounds eliminate ambiguity on shared borders between corridor/room.
        for room in reversed(world.rooms):
            if room.x <= x < room.x + room.width and room.y <= y < room.y + room.height:
                return room.room_id
        return None

    def _update_spray_recharge_by_door_crossing(
        self,
        *,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        current_overlap: set[str] = set()
        for obj in world.objects:
            if obj.kind != "door":
                continue
            if not self._is_door_open(obj):
                continue
            sprite = self._object_sprite(obj, object_sprites)
            left = int(obj.x - sprite.get_width() / 2)
            top = int(obj.y - sprite.get_height() / 2)
            rect = pygame.Rect(left, top, sprite.get_width(), sprite.get_height())
            # Crossing the doorway aperture (not posts) triggers recharge.
            aperture = pygame.Rect(
                rect.left + int(rect.width * 0.20),
                rect.top + int(rect.height * 0.20),
                max(10, int(rect.width * 0.60)),
                max(10, int(rect.height * 0.70)),
            )
            if player_rect.colliderect(aperture):
                current_overlap.add(obj.object_id)

        new_entries = current_overlap - self._door_overlap_ids
        if new_entries:
            self._spray_spent_slots.clear()
            self._reset_spray_state()
            self._grabbed_object_id = None
        self._door_overlap_ids = current_overlap

    def _resource_snapshot(self, project_root: Path) -> tuple[tuple[str, int], ...]:
        root = project_root / "source"
        paths = [p for p in root.rglob("*") if p.is_file()]
        result: list[tuple[str, int]] = []
        for p in paths:
            try:
                stat = p.stat()
            except FileNotFoundError:
                continue
            result.append((str(p.relative_to(project_root)), stat.st_mtime_ns))
        result.sort()
        return tuple(result)

    def _handle_key(
        self,
        event: pygame.event.Event,
        input_controller: KeyboardInputController,
        inventory: Inventory,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        if input_controller.is_action(event, "inventory_move"):
            self._toggle_inventory_move_mode(inventory, world)
            return

        if inventory.move_mode:
            if input_controller.is_action(event, "inventory_left"):
                inventory.move_cursor_left()
                return
            if input_controller.is_action(event, "inventory_right"):
                inventory.move_cursor_right()
                return
            if input_controller.is_action(event, "inventory_up"):
                inventory.move_cursor_up()
                return
            if input_controller.is_action(event, "inventory_down"):
                inventory.move_cursor_down()
                return
            # While inventory transfer mode is active, block world interactions.
            return

        if input_controller.is_action(event, "inventory_up"):
            inventory.move_cursor_up()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "inventory_down"):
            inventory.move_cursor_down()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "inventory_left"):
            inventory.move_cursor_left()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "inventory_right"):
            inventory.move_cursor_right()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "select_prev"):
            inventory.select_previous()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "select_next"):
            inventory.select_next()
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "pickup"):
            self._pickup_or_interact(world, player, inventory, object_sprites)
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "drop"):
            self._drop_selected(world, player, inventory)
            self._sync_inventory_extension_from_active_item(inventory, world)
            return

        if input_controller.is_action(event, "use"):
            self._use_or_touch(world, player, inventory, object_sprites)
            return

        if input_controller.is_action(event, "jump"):
            if player.try_start_jump():
                self._set_message("Прыжок")
            return

    def _try_pickup(
        self,
        world: WorldMap,
        player: Player,
        inventory: Inventory,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        target = self._find_pickup_target(world, player, object_sprites)
        if target is None:
            return False

        item_id = self._pickup_item_id_for_target(target, world)
        if item_id is None:
            return False

        if not inventory.add_item(item_id):
            self._set_message("Инвентарь заполнен")
            return False

        if self._grabbed_object_id == target.object_id:
            self._grabbed_object_id = None
        world.remove_object(target.object_id)
        self._queue_async_preload("item_icon", item_id)
        if self._is_spray_item(item_id):
            self._queue_async_preload("spray_profile", self._spray_profile_for_item(item_id, world))
        if item_id == "backpack":
            self._set_message("Рюкзак поднят")
        else:
            self._set_message(f"Предмет поднят: {item_id}")
        return True

    def _pickup_item_id_for_target(self, target: WorldObject, world: WorldMap) -> str | None:
        item_id = target.pickup_item_id
        if item_id is None and target.kind in {"backpack", "key", "ballon"}:
            if target.kind == "key":
                item_id = "key"
            elif target.kind == "ballon":
                item_id = world.default_balloon_item_id()
            else:
                item_id = "backpack"
        return item_id

    def _is_pickable_target(self, obj: WorldObject) -> bool:
        return obj.pickup_item_id is not None or obj.kind in {"backpack", "key", "ballon"}

    def _find_pickup_target(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> WorldObject | None:
        # Priority:
        # 1) Object under/at player feet.
        # 2) Object in front.
        # 3) Nearest pickup object in small close radius.
        under = self._find_pickup_under_player(world, player, object_sprites)
        if under is not None:
            return under

        front = self._find_object_in_front(world, player, object_sprites)
        if front is not None and self._is_pickable_target(front):
            return front

        return self._find_nearby_pickup_target(world, player, object_sprites)

    def _find_pickup_under_player(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> WorldObject | None:
        sprite_w, sprite_h = self._last_player_sprite_size
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h).inflate(8, 10)
        best: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            if not self._is_pickable_target(obj):
                continue
            obj_rect = self._object_collider_rect(obj, object_sprites)
            if not player_rect.colliderect(obj_rect):
                continue
            dist = self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=obj,
                object_sprites=object_sprites,
            )
            if best is None or dist < best[0]:
                best = (dist, obj)
        return best[1] if best else None

    def _find_nearby_pickup_target(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> WorldObject | None:
        sprite_w, sprite_h = self._last_player_sprite_size
        best: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            if not self._is_pickable_target(obj):
                continue
            dist = self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=obj,
                object_sprites=object_sprites,
            )
            if dist > self._NEAR_PICKUP_GAP:
                continue
            if best is None or dist < best[0]:
                best = (dist, obj)
        return best[1] if best else None

    def _pickup_or_interact(
        self,
        world: WorldMap,
        player: Player,
        inventory: Inventory,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        if self._try_pickup(world, player, inventory, object_sprites):
            return

        target = self._find_object_in_front(world, player, object_sprites)
        if target is None:
            target = self._find_nearby_interaction_target(world, player, object_sprites)
        if target is None:
            selected_item = inventory.selected_item()
            if self._is_spray_item(selected_item):
                self._set_message(
                    self._spray_action_hint(
                        selected_item,
                        selected_slot_index=inventory.active_index,
                        world=world,
                        player=player,
                    )
                )
                return
            self._set_message("Перед вами ничего нет")
            return

        selected = inventory.selected_item()
        if self._is_spray_item(selected):
            self._set_message(
                self._spray_action_hint(
                    selected,
                    selected_slot_index=inventory.active_index,
                    world=world,
                    player=player,
                )
            )
            return
        if selected is not None and self._try_assign_open_door_lock(
            target,
            selected,
            player=player,
            world=world,
            object_sprites=object_sprites,
        ):
            return
        if self._try_toggle_door_by_action(
            target,
            selected,
            player=player,
            world=world,
            object_sprites=object_sprites,
        ):
            return

        if target.blocking and target.kind != "door":
            self._set_message("Зажмите E и бегите в обратную сторону, чтобы тянуть объект")
            return

        if selected is not None and self._try_apply_selected_to_target(target, selected, inventory):
            return

        lock_hint = self._required_item_hint(target)
        if lock_hint is not None:
            self._set_message(lock_hint)
            return

        if target.cycle_sprites:
            total = object_sprites.variant_count(target.kind)
            target.state = self._next_cycled_state(target.kind, target.state, total)
            self._set_message("Вариант спрайта переключен")
            return

        self._set_message("Тач выполнен")

    def _find_nearby_interaction_target(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> WorldObject | None:
        sprite_w, sprite_h = self._last_player_sprite_size
        best: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            # Fallback for close-range interaction: for physical blockers/doors only.
            if not obj.blocking and obj.kind != "door":
                continue
            dist = self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=obj,
                object_sprites=object_sprites,
            )
            if dist > self._NEAR_INTERACT_GAP:
                continue
            if best is None or dist < best[0]:
                best = (dist, obj)
        return best[1] if best else None

    def _drop_selected(
        self,
        world: WorldMap,
        player: Player,
        inventory: Inventory,
    ) -> None:
        selected_item = inventory.selected_item()
        if selected_item == "backpack":
            if self._extra_slots_have_items(inventory):
                self._set_message("Сначала выньте предметы из доп. слотов рюкзака")
                return
        item_id = inventory.remove_selected()
        if item_id is None:
            self._set_message("Нечего выбрасывать")
            return
        inventory.cancel_move_mode()
        if self._is_spray_item(item_id):
            # Fresh can in the same slot should not inherit spent state.
            self._spray_spent_slots.pop(inventory.active_index, None)

        drop_x, drop_y = self._front_drop_position(player)

        if item_id == "backpack":
            self._drop_counter += 1
            world.add_object(
                WorldObject(
                    object_id=f"backpack_drop_{self._drop_counter}",
                    kind="backpack",
                    x=drop_x,
                    y=drop_y,
                    state=0,
                )
            )
            self._set_message("Рюкзак выброшен")
            return
        if item_id == "key" or item_id.startswith("key_"):
            self._drop_counter += 1
            key_tint = self._key_color_from_item_id(item_id)
            world.add_object(
                WorldObject(
                    object_id=f"key_drop_{self._drop_counter}",
                    kind="key",
                    x=drop_x,
                    y=drop_y,
                    state=0,
                    pickup_item_id=item_id,
                    tint_rgb=key_tint,
                    tint_strength=(1.0 if key_tint is not None else 0.0),
                )
            )
            self._set_message(f"Предмет выброшен: {item_id}")
            return
        if self._is_spray_item(item_id):
            self._drop_counter += 1
            balloon_id = world.balloon_id_for_item(item_id) or world.default_balloon_id()
            spray_profile_id = world.item_spray_profiles.get(item_id, "")
            world.add_object(
                BalloonObject(
                    object_id=f"ballon_drop_{self._drop_counter}",
                    kind="ballon",
                    x=drop_x,
                    y=drop_y,
                    state=0,
                    pickup_item_id=item_id,
                    item_id=item_id,
                    balloon_id=balloon_id,
                    graffiti_profile_id=spray_profile_id,
                )
            )
            self._set_message("Балон выброшен")
            return

        self._set_message("Предмет выброшен")
        return

    def _use_or_touch(
        self,
        world: WorldMap,
        player: Player,
        inventory: Inventory,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        target = self._find_object_in_front(world, player, object_sprites)
        selected = inventory.selected_item()

        if target is None:
            self._set_message("Нет объекта для взаимодействия")
            return

        if selected is None:
            lock_hint = self._required_item_hint(target)
            if lock_hint is not None:
                self._set_message(lock_hint)
                return
            if target.cycle_sprites:
                total = object_sprites.variant_count(target.kind)
                target.state = self._next_cycled_state(target.kind, target.state, total)
                self._set_message("Вариант спрайта переключен")
                return
            self._set_message("Тач выполнен")
            return

        if self._try_apply_selected_to_target(target, selected, inventory):
            return

        self._set_message(f"{selected} нельзя применить к {target.kind}")

    def _try_apply_selected_to_target(
        self,
        target: WorldObject,
        selected_item: str,
        inventory: Inventory,
    ) -> bool:
        if target.has_locks():
            unlocked = target.try_open_lock_with_key(selected_item)
            if not unlocked:
                return False

            if target.consume_required_item:
                inventory.remove_selected()

            opened = target.opened_locks_count()
            total = target.total_locks_count()
            if target.is_fully_unlocked():
                self._apply_unlock_effects(target)
                self._set_message(f"{selected_item}: замок {opened}/{total}, дверь открыта")
            else:
                self._set_message(f"{selected_item}: замок {opened}/{total}")
            return True

        if target.required_item_id is None:
            return False
        if selected_item != target.required_item_id:
            return False
        self._apply_unlock_effects(target)
        if target.consume_required_item:
            inventory.remove_selected()
        self._set_message(f"{selected_item} применен к {target.kind}")
        return True

    def _apply_unlock_effects(self, target: WorldObject) -> None:
        if self._apply_named_transition(target, "unlock"):
            return
        if target.use_set_state is not None:
            target.state = target.use_set_state
        if target.use_set_blocking is not None:
            target.blocking = target.use_set_blocking

    def _apply_named_transition(self, target: WorldObject, event_name: str) -> bool:
        transition = target.transition_for(event_name)
        if transition is None:
            return False
        if transition.state is not None:
            target.state = transition.state
        if transition.blocking is not None:
            target.blocking = transition.blocking
        return True

    def _try_toggle_door_by_action(
        self,
        target: WorldObject,
        selected_item: str | None,
        *,
        player: Player,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        if target.kind != "door":
            return False
        if selected_item is not None:
            return False

        if self._is_door_open(target):
            self._close_door_by_action(target, player=player, world=world, object_sprites=object_sprites)
            self._set_message("Дверь закрыта")
            return True

        if self._is_door_unlocked(target):
            self._open_door_by_action(target)
            self._set_message("Дверь открыта")
            return True

        return False

    def _is_door_open(self, target: WorldObject) -> bool:
        # Primary source of truth for passability.
        if not target.blocking:
            return True
        # Fallback for authored door states where open state may still be marked blocking.
        return target.state > 0

    def _is_door_unlocked(self, target: WorldObject) -> bool:
        if target.has_locks():
            return target.is_fully_unlocked()
        # Doors without explicit locks are considered operable by action key.
        return True

    def _open_door_by_action(self, target: WorldObject) -> None:
        if self._apply_named_transition(target, "action_open"):
            return
        if self._apply_named_transition(target, "unlock"):
            return
        target.blocking = False
        if target.state <= 0:
            target.state = 1

    def _close_door_by_action(
        self,
        target: WorldObject,
        *,
        player: Player | None = None,
        world: WorldMap | None = None,
        object_sprites: ObjectSpriteLibrary | None = None,
    ) -> None:
        if self._apply_named_transition(target, "action_close"):
            pass
        else:
            target.blocking = True
            target.state = 0

        if player is not None and world is not None and object_sprites is not None:
            self._eject_player_from_closed_door(
                target=target,
                player=player,
                world=world,
                object_sprites=object_sprites,
            )

    def _try_assign_open_door_lock(
        self,
        target: WorldObject,
        selected_item: str,
        *,
        player: Player,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        if target.kind != "door":
            return False
        if not self._is_door_open(target):
            return False
        if not self._is_key_item(selected_item):
            return False

        # Replace previous lock setup with one lock tied to the currently selected key.
        target.lock_key_sets = [[selected_item]]
        target.lock_open_flags = [False]
        target.required_item_id = None
        marker_color = self._key_color_from_item_id(selected_item)
        if marker_color is not None:
            target.lock_marker_rgb = marker_color
        target.lock_marker_text = self._key_marker_text(selected_item)
        self._close_door_by_action(target, player=player, world=world, object_sprites=object_sprites)
        self._set_message(f"Дверь закрыта на {selected_item}")
        return True

    def _eject_player_from_closed_door(
        self,
        *,
        target: WorldObject,
        player: Player,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        if target.kind != "door" or not target.blocking:
            return

        sprite_w, sprite_h = self._last_player_sprite_size
        sprite_w = max(32, int(sprite_w))
        sprite_h = max(32, int(sprite_h))
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        door_rect = self._object_collider_rect(target, object_sprites)
        if not player_rect.colliderect(door_rect):
            return

        margin = 3
        half_w = player_rect.width / 2.0
        half_h = player_rect.height / 2.0
        cx0 = float(player_rect.centerx)
        cy0 = float(player_rect.centery)

        def _clamp(value: float, lo: float, hi: float) -> float:
            if hi < lo:
                return (lo + hi) * 0.5
            return max(lo, min(hi, value))

        x_min = float(door_rect.left) + half_w + 1.0
        x_max = float(door_rect.right) - half_w - 1.0
        y_min = float(door_rect.top) + half_h + 1.0
        y_max = float(door_rect.bottom) - half_h - 1.0

        candidates: list[tuple[str, float, float]] = [
            ("above", _clamp(cx0, x_min, x_max), float(door_rect.top) - half_h - margin),
            ("below", _clamp(cx0, x_min, x_max), float(door_rect.bottom) + half_h + margin),
            ("left", float(door_rect.left) - half_w - margin, _clamp(cy0, y_min, y_max)),
            ("right", float(door_rect.right) + half_w + margin, _clamp(cy0, y_min, y_max)),
        ]
        orientation = self._normalize_door_orientation(target.door_orientation)
        if orientation in {"top", "bottom"}:
            # Keep player on the same side they entered from:
            # center above door center => eject above, else below.
            primary_vertical = "above" if cy0 <= float(door_rect.centery) else "below"
            secondary_vertical = "below" if primary_vertical == "above" else "above"
            pref = (primary_vertical, secondary_vertical, "left", "right")
        else:
            # Side doors: preserve horizontal side.
            primary_horizontal = "left" if cx0 <= float(door_rect.centerx) else "right"
            secondary_horizontal = "right" if primary_horizontal == "left" else "left"
            pref = (primary_horizontal, secondary_horizontal, "below", "above")
        pref_rank = {name: idx for idx, name in enumerate(pref)}
        candidates.sort(
            key=lambda c: (
                pref_rank.get(c[0], 99),
                math.hypot(c[1] - cx0, c[2] - cy0),
            )
        )

        for _, ccx, ccy in candidates:
            if self._try_place_player_collider(
                player=player,
                world=world,
                object_sprites=object_sprites,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                collider_center_x=ccx,
                collider_center_y=ccy,
                ignore_object_id=target.object_id,
            ):
                return

        # Last safety net: keep the player out of closed door by reopening if no valid ejection exists.
        target.blocking = False
        if target.state <= 0:
            target.state = 1

    def _try_place_player_collider(
        self,
        *,
        player: Player,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        sprite_w: int,
        sprite_h: int,
        collider_center_x: float,
        collider_center_y: float,
        ignore_object_id: str | None,
    ) -> bool:
        new_x = float(collider_center_x) - (sprite_w * 0.5)
        new_y = float(collider_center_y) - (sprite_h * 0.86)
        new_x = max(0.0, min(new_x, float(max(0, world.width - sprite_w))))
        new_y = max(0.0, min(new_y, float(max(0, world.height - sprite_h))))
        candidate_rect = self._player_collider_rect(new_x, new_y, sprite_w, sprite_h)
        if self._collides_with_room_walls(candidate_rect, world):
            return False
        collided = self._first_blocking_collision(
            candidate_rect,
            world,
            object_sprites,
            ignore_object_id=ignore_object_id,
        )
        if collided is not None:
            return False
        player.x = new_x
        player.y = new_y
        return True

    def _is_key_item(self, item_id: str) -> bool:
        return item_id == "key" or item_id.startswith("key_")

    def _key_marker_text(self, item_id: str) -> str | None:
        token = item_id.strip()
        if not token:
            return None
        if "_" in token:
            parts = [part for part in token.split("_") if part]
            if parts:
                token = parts[-1]
        return token[:1].upper() or None

    def _key_color_from_item_id(self, item_id: str) -> tuple[int, int, int] | None:
        token = item_id.lower()
        if "red" in token or "крас" in token:
            return (220, 64, 62)
        if "blue" in token or "син" in token:
            return (72, 132, 235)
        if "green" in token or "зел" in token:
            return (64, 176, 86)
        if "yellow" in token or "жел" in token:
            return (226, 188, 66)
        if "purple" in token or "фиол" in token:
            return (154, 92, 214)
        if "orange" in token or "оранж" in token:
            return (236, 142, 62)
        if "white" in token or "бел" in token:
            return (235, 235, 235)
        if "black" in token or "чер" in token:
            return (34, 34, 34)
        return (226, 188, 66)

    def _next_cycled_state(self, kind: str, current_state: int, total_variants: int) -> int:
        total = max(1, int(total_variants))
        if kind != "sofa":
            return (current_state + 1) % total

        # Sofa sheet layout: colors by rows, 4 view angles per color.
        group = 4
        if total < group:
            return (current_state + 1) % total
        group_start = ((current_state % total) // group) * group
        offset = (current_state - group_start + 1) % group
        return group_start + offset

    def _required_item_hint(self, target: WorldObject) -> str | None:
        if target.has_locks():
            target.ensure_lock_flags()
            for idx, key_set in enumerate(target.lock_key_sets):
                if target.lock_open_flags[idx]:
                    continue
                if key_set:
                    keys = ", ".join(key_set)
                    return f"Нужен ключ ({idx + 1}/{target.total_locks_count()}): {keys}"
            return "Замки уже открыты"
        if target.required_item_id is not None:
            return f"Нужен предмет: {target.required_item_id}"
        return None

    def _touch_only(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        target = self._find_object_in_front(world, player, object_sprites)
        if target is None:
            self._set_message("Перед вами ничего нет")
            return
        if target.cycle_sprites:
            total = object_sprites.variant_count(target.kind)
            target.state = self._next_cycled_state(target.kind, target.state, total)
            self._set_message("Вариант спрайта переключен")
            return
        self._set_message("Тач выполнен")

    def _find_object_in_front(
        self,
        world: WorldMap,
        player: Player,
        object_sprites: ObjectSpriteLibrary,
    ) -> WorldObject | None:
        facing = FACING_VECTOR[player.facing]
        px = player.x + self._interaction_anchor_offset[0]
        py = player.y + self._interaction_anchor_offset[1]

        best: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            sprite = self._object_sprite(obj, object_sprites)
            half_w = sprite.get_width() / 2
            half_h = sprite.get_height() / 2
            ox = obj.x
            oy = obj.y

            vx = ox - px
            vy = oy - py
            dist = math.hypot(vx, vy)
            if dist > self._config.interaction_distance:
                continue
            if dist < 1e-6:
                continue

            dot = (vx / dist) * facing[0] + (vy / dist) * facing[1]
            if dot < 0.3:
                continue

            # Small overlap expansion so interaction feels forgiving.
            if abs(vx) > half_w + 110 or abs(vy) > half_h + 110:
                continue

            if best is None or dist < best[0]:
                best = (dist, obj)

        return best[1] if best else None

    def _front_drop_position(self, player: Player) -> tuple[float, float]:
        fx, fy = FACING_VECTOR[player.facing]
        sprite_w, sprite_h = self._last_player_sprite_size
        # Drop from the current body anchor so direction always matches facing.
        px = player.x + sprite_w * 0.50
        py = player.y + sprite_h * 0.86
        return px + fx * 68, py + fy * 68

    def _is_spray_item(self, item_id: str | None) -> bool:
        if item_id is None:
            return False
        return item_id in self._spray_item_ids

    def _spray_action_hint(
        self,
        item_id: str | None,
        *,
        selected_slot_index: int,
        world: WorldMap,
        player: Player,
    ) -> str:
        token = (item_id or "").strip()
        if not token:
            return "Балон: зажмите E и ведите по верхней стене/закрытой двери"
        if not self._is_spray_item_ready(token, selected_slot_index):
            return "Балон пуст: пройдите через дверь/в другую зону для перезарядки"
        sprite_w, sprite_h = self._last_player_sprite_size
        area_id = self._area_id_for_player(world, player, sprite_w, sprite_h) or "__none__"
        if not self._can_use_item_in_room(item_id=token, room_id=area_id, world=world):
            return "Лимит использования предмета в этой комнате исчерпан"
        return "Балон: зажмите E и ведите по верхней стене/закрытой двери"

    def _is_spray_item_ready(self, item_id: str, selected_slot_index: int) -> bool:
        return self._spray_spent_slots.get(int(selected_slot_index)) != item_id

    def _mark_spray_item_spent(self, item_id: str, selected_slot_index: int) -> None:
        self._spray_spent_slots[int(selected_slot_index)] = item_id

    def _reset_spray_state(self) -> None:
        self._spray_active_target = None
        self._spray_active_tag_index = None
        self._spray_hold_accum = 0.0

    def _update_spray_painting(
        self,
        *,
        holding_spray: bool,
        dt: float,
        selected_spray_item: str | None,
        selected_spray_slot_index: int,
        spray_area_id: str | None,
        player: Player,
        player_sprite_w: int,
        player_sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        if not holding_spray:
            self._reset_spray_state()
            return

        profile_id = self._spray_profile_for_item(selected_spray_item, world)
        sequence = self._spray_sequence_for_profile(profile_id, world, object_sprites)
        if not sequence:
            self._set_message("Подгружаю граффити...")
            self._reset_spray_state()
            return
        sprite_height_coef = max(0.82, min(float(player_sprite_h) / 120.0, 1.25))
        # Keep reference at 150cm so 120cm gives noticeably lower/smaller graffiti.
        raw_height_ratio = max(0.45, min(float(player.stats.height_cm) / 150.0, 2.2))
        player_height_coef = max(0.55, min(raw_height_ratio * sprite_height_coef, 1.9))
        spray_extra_down_px = self._spray_extra_down_px(float(player.stats.height_cm))
        preserve_aspect, char_width_mult, size_mul = self._graffiti_render_config(world, profile_id)
        aspect_ratio = self._spray_sequence_aspect_ratio(sequence)
        target = self._spray_target(
            player=player,
            player_sprite_w=player_sprite_w,
            player_sprite_h=player_sprite_h,
            player_height_coef=player_height_coef,
            spray_extra_down_px=spray_extra_down_px,
            preserve_aspect=preserve_aspect,
            char_width_mult=char_width_mult,
            size_mul=size_mul,
            aspect_ratio=aspect_ratio,
            world=world,
            object_sprites=object_sprites,
        )
        if target is None:
            self._reset_spray_state()
            return
        target_kind, target_id, draw_x, draw_y, draw_w, draw_h = target
        target_key = (target_kind, target_id)
        room_id = spray_area_id or "__none__"
        item_id = selected_spray_item or "ballon"
        draw_center = (float(draw_x) + (float(draw_w) * 0.5), float(draw_y) + (float(draw_h) * 0.5))

        if self._spray_active_target != target_key or self._spray_active_tag_index is None:
            reusable_idx = self._find_reusable_spray_tag_index(
                target_kind=target_kind,
                target_id=target_id,
                profile_id=profile_id,
                room_id=room_id,
                draw_center=draw_center,
            )
            if reusable_idx is not None:
                self._spray_active_target = target_key
                self._spray_active_tag_index = reusable_idx
                self._spray_hold_accum = 0.0
            else:
                if not self._is_spray_item_ready(item_id, selected_spray_slot_index):
                    self._set_message("Балон пуст: пройдите через дверь для перезарядки")
                    return
                if not self._can_use_item_in_room(item_id=item_id, room_id=room_id, world=world):
                    self._set_message("Лимит использования предмета в этой комнате исчерпан")
                    return
                self._spray_tags.append(
                    SprayTag(
                        x=float(draw_x),
                        y=float(draw_y),
                        width=int(draw_w),
                        height=int(draw_h),
                        target_kind=target_kind,
                        target_id=target_id,
                        spray_area_id=room_id,
                        profile_id=profile_id,
                        sequence_index=0,
                        frame_index=0,
                    )
                )
                if len(self._spray_tags) > 320:
                    self._spray_tags = self._spray_tags[-320:]
                self._spray_active_target = target_key
                self._spray_active_tag_index = len(self._spray_tags) - 1
                self._spray_hold_accum = 0.0
                self._mark_spray_item_spent(item_id, selected_spray_slot_index)
                self._consume_item_use_in_room(item_id=item_id, room_id=room_id)
            return

        idx = int(self._spray_active_tag_index)
        if idx < 0 or idx >= len(self._spray_tags):
            self._reset_spray_state()
            return

        tag = self._spray_tags[idx]
        if tag.target_kind != target_kind or tag.target_id != target_id:
            self._reset_spray_state()
            return
        if not self._is_near_spray_tag(tag, draw_center):
            self._reset_spray_state()
            return
        if not tag.spray_area_id:
            tag.spray_area_id = room_id
        if tag.profile_id != profile_id:
            tag.profile_id = profile_id
            tag.sequence_index = 0
            tag.frame_index = 0

        self._spray_hold_accum += max(0.0, float(dt))
        advance = int(self._spray_hold_accum / self._spray_frame_interval)
        if advance <= 0:
            return
        self._spray_hold_accum -= advance * self._spray_frame_interval

        while advance > 0:
            seq_idx = max(0, min(len(sequence) - 1, int(tag.sequence_index)))
            frames = sequence[seq_idx].variants
            if not frames:
                break
            max_frame = len(frames) - 1
            room = max_frame - int(tag.frame_index)
            if room > 0:
                step = min(room, advance)
                tag.frame_index += step
                advance -= step
            if advance <= 0:
                break
            if tag.sequence_index >= len(sequence) - 1:
                tag.frame_index = max_frame
                break
            tag.sequence_index += 1
            tag.frame_index = 0
            advance -= 1

    def _find_reusable_spray_tag_index(
        self,
        *,
        target_kind: str,
        target_id: str,
        profile_id: str,
        room_id: str,
        draw_center: tuple[float, float],
    ) -> int | None:
        for idx in range(len(self._spray_tags) - 1, -1, -1):
            tag = self._spray_tags[idx]
            if (
                tag.target_kind == target_kind
                and tag.target_id == target_id
                and tag.profile_id == profile_id
                and tag.spray_area_id == room_id
                and self._is_near_spray_tag(tag, draw_center)
            ):
                return idx
        return None

    def _is_near_spray_tag(self, tag: SprayTag, draw_center: tuple[float, float]) -> bool:
        tag_center_x = float(tag.x) + (float(tag.width) * 0.5)
        tag_center_y = float(tag.y) + (float(tag.height) * 0.5)
        dx = tag_center_x - float(draw_center[0])
        dy = tag_center_y - float(draw_center[1])
        return (dx * dx + dy * dy) <= (72.0 * 72.0)

    def _room_item_use_limit(self, item_id: str, world: WorldMap) -> int:
        # Spray items are not limited per-room: different balloons must work in the same room.
        if self._is_spray_item(item_id):
            return 0
        if item_id in world.item_room_use_limits:
            return max(0, int(world.item_room_use_limits[item_id]))
        if "_" in item_id:
            base = item_id.split("_", 1)[0]
            if base in world.item_room_use_limits:
                return max(0, int(world.item_room_use_limits[base]))
        return 0

    def _can_use_item_in_room(self, *, item_id: str, room_id: str, world: WorldMap) -> bool:
        limit = self._room_item_use_limit(item_id, world)
        if limit <= 0:
            return True
        used = self._room_item_use_counts.get((room_id, item_id), 0)
        return used < limit

    def _consume_item_use_in_room(self, *, item_id: str, room_id: str) -> None:
        key = (room_id, item_id)
        self._room_item_use_counts[key] = self._room_item_use_counts.get(key, 0) + 1

    def _spray_profile_for_item(self, item_id: str | None, world: WorldMap) -> str:
        if item_id:
            direct = world.item_spray_profiles.get(item_id)
            if direct:
                return direct
            balloon_id = world.balloon_id_for_item(item_id)
            if balloon_id:
                spec = world.balloon_specs.get(balloon_id)
                if spec is not None and spec.default_graffiti_id:
                    return spec.default_graffiti_id
        fallback = world.item_spray_profiles.get("ballon")
        if fallback:
            return fallback
        if "default" in world.spray_profiles:
            return "default"
        if world.spray_profiles:
            return next(iter(world.spray_profiles.keys()))
        return "default"

    def _spray_sequence_for_profile(
        self,
        profile_id: str,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ):
        cached = self._spray_profile_sequences.get(profile_id)
        if cached is not None:
            return cached
        self._queue_async_preload("spray_profile", profile_id)
        return []

    def _spray_profile_paths(self, profile_id: str, world: WorldMap) -> list[str]:
        paths = world.spray_profiles.get(profile_id)
        if not paths:
            paths = world.spray_profiles.get("default")
        if not paths:
            default_spec = world.graffiti_specs.get("default")
            if default_spec is not None:
                paths = list(default_spec.sheet_paths)
        if not paths:
            return ["source/textures/items/ballon/spray_reveal_sheet.png"]
        return list(paths)

    def _graffiti_render_config(self, world: WorldMap, profile_id: str) -> tuple[bool, float, float]:
        spec = world.graffiti_specs.get(profile_id) or world.graffiti_specs.get("default")
        if spec is None:
            return (True, 3.0, 1.0)
        return (
            bool(spec.preserve_aspect),
            max(0.45, min(float(spec.char_width_mult), 8.0)),
            max(0.20, min(float(spec.size_mul), 4.0)),
        )

    def _spray_sequence_aspect_ratio(self, sequence) -> float:
        # Use final reveal frame proportions so rendered graffiti matches original art.
        if not sequence:
            return 1.0
        try:
            frames = sequence[-1].variants
        except Exception:
            return 1.0
        if not frames:
            return 1.0
        frame = frames[-1]
        w = max(1, int(frame.get_width()))
        h = max(1, int(frame.get_height()))
        return max(0.15, min(float(w) / float(h), 8.0))

    def _spray_target(
        self,
        *,
        player: Player,
        player_sprite_w: int,
        player_sprite_h: int,
        player_height_coef: float,
        spray_extra_down_px: int,
        preserve_aspect: bool,
        char_width_mult: float,
        size_mul: float,
        aspect_ratio: float,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> tuple[str, str, float, float, int, int] | None:
        fx, fy = FACING_VECTOR[player.facing]
        origin_x = player.x + self._interaction_anchor_offset[0]
        origin_y = player.y + self._interaction_anchor_offset[1]
        probes: list[tuple[float, float]] = []
        probes.append((origin_x + fx * 84.0, origin_y + fy * 84.0))
        # Fallback probe near player's top-center makes painting stable even when
        # facing vector is not perfectly aligned with top wall/door.
        probes.append((player.x + player_sprite_w * 0.50, player.y + player_sprite_h * 0.18))
        # Small side probes to avoid "dead zones" near door frames.
        probes.append((player.x + player_sprite_w * 0.38, player.y + player_sprite_h * 0.22))
        probes.append((player.x + player_sprite_w * 0.62, player.y + player_sprite_h * 0.22))

        for spray_x, spray_y in probes:
            door_hit = self._find_closed_door_spray_target(
                spray_x,
                spray_y,
                player_sprite_w,
                player_sprite_h,
                player_height_coef,
                spray_extra_down_px,
                preserve_aspect,
                char_width_mult,
                size_mul,
                aspect_ratio,
                world,
                object_sprites,
            )
            if door_hit is not None:
                return door_hit

            wall_hit = self._find_top_wall_spray_target(
                spray_x,
                spray_y,
                player_sprite_w,
                player_sprite_h,
                player_height_coef,
                spray_extra_down_px,
                preserve_aspect,
                char_width_mult,
                size_mul,
                aspect_ratio,
                world,
            )
            if wall_hit is not None:
                return wall_hit
        return None

    def _find_closed_door_spray_target(
        self,
        spray_x: float,
        spray_y: float,
        player_sprite_w: int,
        player_sprite_h: int,
        player_height_coef: float,
        spray_extra_down_px: int,
        preserve_aspect: bool,
        char_width_mult: float,
        size_mul: float,
        aspect_ratio: float,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> tuple[str, str, float, float, int, int] | None:
        best: tuple[float, str, float, float, int, int] | None = None
        for obj in world.objects:
            if obj.kind != "door":
                continue
            if not (obj.blocking or obj.state <= 0):
                continue
            sprite = self._object_sprite(obj, object_sprites)
            left = obj.x - sprite.get_width() / 2
            top = obj.y - sprite.get_height() / 2
            rect = pygame.Rect(int(left), int(top), sprite.get_width(), sprite.get_height())
            if not rect.collidepoint(int(spray_x), int(spray_y)):
                continue
            target_height_px = int(obj.height) if int(obj.height) > 0 else rect.height
            zoom_coef, y_bias_coef = self._spray_height_params(
                player_height_coef=player_height_coef,
                target_height_px=target_height_px,
                object_zoom_coef=obj.spray_zoom_coef,
            )
            zoom_coef *= size_mul
            char_body_w = player_sprite_w * 0.58
            draw_w = int(max(84, char_body_w * char_width_mult) * zoom_coef)
            draw_h = int(max(52, player_sprite_h * 0.66) * zoom_coef)
            draw_w, draw_h = self._fit_graffiti_draw_size(
                draw_w=draw_w,
                draw_h=draw_h,
                max_w=max(1, rect.width - 4),
                max_h=max(1, rect.height - 4),
                preserve_aspect=preserve_aspect,
                aspect_ratio=aspect_ratio,
            )
            draw_w = min(max(1, rect.width - 4), draw_w)
            draw_h = min(max(1, rect.height - 4), draw_h)
            draw_x = self._clampf(spray_x - draw_w * 0.5, rect.left + 2, rect.right - draw_w - 2)
            draw_y_base = spray_y - draw_h * 0.55 + y_bias_coef * target_height_px + float(spray_extra_down_px)
            draw_y = self._clampf(draw_y_base, rect.top + 2, rect.bottom - draw_h - 2)
            dist = math.hypot(obj.x - spray_x, obj.y - spray_y)
            if best is None or dist < best[0]:
                best = (
                    dist,
                    obj.object_id,
                    float(draw_x),
                    float(draw_y),
                    int(draw_w),
                    int(draw_h),
                )
        if best is None:
            return None
        return ("door", best[1], best[2], best[3], best[4], best[5])

    def _find_top_wall_spray_target(
        self,
        spray_x: float,
        spray_y: float,
        player_sprite_w: int,
        player_sprite_h: int,
        player_height_coef: float,
        spray_extra_down_px: int,
        preserve_aspect: bool,
        char_width_mult: float,
        size_mul: float,
        aspect_ratio: float,
        world: WorldMap,
    ) -> tuple[str, str, float, float, int, int] | None:
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
            top_t = max(t, min(room.top_wall_height, room.height // 2)) if room.top_wall_height > 0 else t
            wall_rect = pygame.Rect(room.x, room.y, room.width, top_t)
            if not wall_rect.collidepoint(int(spray_x), int(spray_y)):
                continue

            top_span = self._opening_span(
                start=room.x + t + 10,
                length=room.width - (t * 2) - 20,
                opening_width=room.top_door_width,
                opening_offset=room.top_door_offset,
            )
            if top_span is not None:
                l, r = top_span
                if l <= spray_x <= r:
                    continue

            inner_left = room.x + t + 4
            inner_right = room.x + room.width - t - 4
            inner_w = max(1, inner_right - inner_left)
            zoom_coef, y_bias_coef = self._spray_height_params(
                player_height_coef=player_height_coef,
                target_height_px=top_t,
                object_zoom_coef=1.0,
            )
            zoom_coef *= size_mul
            char_body_w = player_sprite_w * 0.58
            draw_w = int(max(110, char_body_w * char_width_mult) * zoom_coef)
            draw_h = int(max(52, player_sprite_h * 0.66) * zoom_coef)
            draw_w, draw_h = self._fit_graffiti_draw_size(
                draw_w=draw_w,
                draw_h=draw_h,
                max_w=inner_w,
                max_h=max(1, top_t - 2),
                preserve_aspect=preserve_aspect,
                aspect_ratio=aspect_ratio,
            )
            draw_w = min(inner_w, draw_w)
            draw_h = min(max(1, top_t - 2), draw_h)
            draw_x = self._clampf(spray_x - draw_w * 0.5, inner_left, inner_right - draw_w)
            draw_y = room.y + max(
                1,
                int((top_t - draw_h) * 0.5 + y_bias_coef * top_t + float(spray_extra_down_px)),
            )
            draw_y = self._clampf(draw_y, room.y + 1, room.y + top_t - draw_h - 1)
            return (
                "wall_top",
                room.room_id,
                float(draw_x),
                float(draw_y),
                int(draw_w),
                int(draw_h),
            )
        return None

    def _fit_graffiti_draw_size(
        self,
        *,
        draw_w: int,
        draw_h: int,
        max_w: int,
        max_h: int,
        preserve_aspect: bool,
        aspect_ratio: float,
    ) -> tuple[int, int]:
        w = max(1, int(draw_w))
        h = max(1, int(draw_h))
        mw = max(1, int(max_w))
        mh = max(1, int(max_h))
        ar = max(0.15, min(float(aspect_ratio), 8.0))
        if preserve_aspect:
            h = max(1, int(round(w / ar)))
        if w > mw:
            w = mw
            if preserve_aspect:
                h = max(1, int(round(w / ar)))
        if h > mh:
            h = mh
            if preserve_aspect:
                w = max(1, int(round(h * ar)))
        w = min(w, mw)
        h = min(h, mh)
        return (max(1, w), max(1, h))

    def _spray_height_params(
        self,
        *,
        player_height_coef: float,
        target_height_px: int,
        object_zoom_coef: float,
    ) -> tuple[float, float]:
        p = max(0.55, min(float(player_height_coef), 1.9))
        target_coef = max(0.80, min(float(target_height_px) / 316.0, 1.35))
        obj_coef = max(0.35, min(float(object_zoom_coef), 3.5))
        zoom_coef = max(0.42, min(p * target_coef * obj_coef, 1.90))
        # Stronger vertical response:
        # small player (p<1) -> clearly lower graffiti, tall player -> higher.
        y_bias_coef = (1.0 - p) * 0.58
        return zoom_coef, y_bias_coef

    def _spray_extra_down_px(self, player_height_cm: float) -> int:
        # Requested: at 120cm graffiti should be ~40px lower; fade to 0px by 150cm.
        h = max(80.0, min(float(player_height_cm), 220.0))
        if h >= 150.0:
            return 0
        if h <= 120.0:
            return 40
        ratio = (150.0 - h) / 30.0
        return int(round(40.0 * ratio))

    def _clampf(self, value: float, low: float, high: float) -> float:
        if high < low:
            return float(low)
        return max(float(low), min(float(high), float(value)))

    def _object_sprite(self, obj: WorldObject, sprites: ObjectSpriteLibrary) -> pygame.Surface:
        if obj.kind == "backpack":
            return sprites.backpack_set().get(0)
        if obj.kind == "sofa":
            return sprites.sofa_set().get(obj.state)
        if obj.kind == "plant":
            return sprites.plant_set().get(obj.state)
        if obj.kind == "ballon":
            return sprites.ballon_sprite_for_object(obj)
        if obj.kind == "key":
            return sprites.key_set().get(obj.state)
        if obj.kind == "door":
            return sprites.door_set(obj.door_orientation).get(obj.state)
        return sprites.backpack_set().get(0)

    def _set_message(self, text: str) -> None:
        self._message = text
        self._message_until = time.monotonic() + 1.6

    def _inventory_has_item(self, inventory: Inventory, item_id: str) -> bool:
        target = item_id.strip().lower()
        for slot in inventory.slots:
            if slot is None:
                continue
            token = str(slot).strip().lower()
            if token == target:
                return True
            if target == "backpack" and (token == "bag" or token.startswith("backpack") or token.startswith("bag_")):
                return True
        return False

    def _sync_inventory_extension_from_active_item(self, inventory: Inventory, world: WorldMap) -> None:
        selected = inventory.selected_item()
        bonus = 0
        bonus_weight_limit = 0.0
        if selected is not None:
            bonus = max(0, int(world.item_inventory_bonus_slots.get(selected, 0)))
            bonus_weight_limit = max(
                0.0,
                float(world.item_inventory_bonus_weight_limit_kg.get(selected, 0.0)),
            )
        # Keep extension only while cursor is currently in extra row.
        # If selected item is not a backpack/extender, inventory should collapse back.
        keep_extended = inventory.is_extra_slot(inventory.active_index)
        if keep_extended and bonus <= 0:
            for slot_item in inventory.slots[: inventory.capacity]:
                if slot_item is None:
                    continue
                slot_bonus = max(0, int(world.item_inventory_bonus_slots.get(slot_item, 0)))
                if slot_bonus <= 0:
                    continue
                slot_limit = max(
                    0.0,
                    float(world.item_inventory_bonus_weight_limit_kg.get(slot_item, 0.0)),
                )
                if slot_bonus > bonus or (slot_bonus == bonus and slot_limit > bonus_weight_limit):
                    bonus = slot_bonus
                    bonus_weight_limit = slot_limit
        # During inventory move mode keep extension available if backpack/extender
        # exists in inventory, otherwise A/S vertical navigation can have no target.
        if inventory.move_mode and bonus <= 0:
            for slot_item in inventory.slots[: inventory.capacity]:
                if slot_item is None:
                    continue
                slot_bonus = max(0, int(world.item_inventory_bonus_slots.get(slot_item, 0)))
                if slot_bonus <= 0:
                    continue
                slot_limit = max(
                    0.0,
                    float(world.item_inventory_bonus_weight_limit_kg.get(slot_item, 0.0)),
                )
                if slot_bonus > bonus or (slot_bonus == bonus and slot_limit > bonus_weight_limit):
                    bonus = slot_bonus
                    bonus_weight_limit = slot_limit
        changed = inventory.set_extension(bonus, bonus_weight_limit)
        if changed:
            self._trim_spray_spent_slots_for_inventory(inventory)
            if inventory.move_mode and inventory.move_source_index is not None:
                if inventory.move_source_index >= inventory.capacity:
                    inventory.cancel_move_mode()

    def _trim_spray_spent_slots_for_inventory(self, inventory: Inventory) -> None:
        if not self._spray_spent_slots:
            return
        valid = {i for i in range(inventory.capacity)}
        stale = [idx for idx in self._spray_spent_slots.keys() if idx not in valid]
        for idx in stale:
            self._spray_spent_slots.pop(idx, None)

    def _extra_slots_have_items(self, inventory: Inventory) -> bool:
        for idx in inventory.extra_indices():
            if idx < len(inventory.slots) and inventory.slots[idx] is not None:
                return True
        return False

    def _toggle_inventory_move_mode(self, inventory: Inventory, world: WorldMap) -> None:
        if not inventory.move_mode:
            if inventory.begin_move_mode():
                self._set_message("Перенос: выберите слот и нажмите D")
            else:
                self._set_message("Выбранный слот пуст")
            return

        src = inventory.move_source_index
        if src is None:
            inventory.cancel_move_mode()
            return
        dst = inventory.active_index
        src_item = inventory.slots[src] if 0 <= src < len(inventory.slots) else None
        dst_item = inventory.slots[dst] if 0 <= dst < len(inventory.slots) else None
        if src_item is None:
            inventory.cancel_move_mode()
            self._set_message("Нечего переносить")
            return
        if not self._can_swap_inventory_slots(
            inventory=inventory,
            world=world,
            src=src,
            dst=dst,
            src_item=src_item,
            dst_item=dst_item,
        ):
            return
        moved = inventory.commit_move(dst)
        if moved is None:
            return
        self._move_spray_slot_marker(moved[0], moved[1])
        self._set_message("Предмет перемещен")

    def _can_swap_inventory_slots(
        self,
        *,
        inventory: Inventory,
        world: WorldMap,
        src: int,
        dst: int,
        src_item: str | None,
        dst_item: str | None,
    ) -> bool:
        if src_item is None:
            return False
        if src == dst:
            return True

        if inventory.is_extra_slot(dst):
            if str(src_item).strip().lower() == "backpack":
                self._set_message("Рюкзак нельзя класть в доп. слот")
                return False
            if not self._can_store_in_backpack(src_item, world):
                self._set_message("Этот предмет нельзя положить в рюкзак")
                return False
        if inventory.is_extra_slot(src) and dst_item is not None:
            if str(dst_item).strip().lower() == "backpack":
                self._set_message("Рюкзак нельзя класть в доп. слот")
                return False
            if not self._can_store_in_backpack(dst_item, world):
                self._set_message("Этот предмет нельзя положить в рюкзак")
                return False

        # Respect backpack extra slots max carry weight.
        max_extra_weight = max(0.0, float(inventory.bonus_weight_limit_kg))
        if max_extra_weight > 0.0:
            proposed = {src: dst_item, dst: src_item}
            total_extra_weight = self._extra_slots_weight_kg_after(inventory, world, proposed)
            if total_extra_weight > (max_extra_weight + 1e-6):
                self._set_message("Слишком тяжело для рюкзака")
                return False
        return True

    def _extra_slots_weight_kg_after(
        self,
        inventory: Inventory,
        world: WorldMap,
        overrides: dict[int, str | None],
    ) -> float:
        total = 0.0
        for idx in inventory.extra_indices():
            if idx >= len(inventory.slots):
                continue
            item_id = overrides.get(idx, inventory.slots[idx])
            if item_id is None:
                continue
            total += self._item_weight_kg(item_id, world.item_weights)
        return total

    def _can_store_in_backpack(self, item_id: str, world: WorldMap) -> bool:
        token = str(item_id).strip().lower()
        if not token:
            return False
        if token == "backpack":
            return False
        if token in world.item_backpack_storable:
            return bool(world.item_backpack_storable[token])
        return True

    def _move_spray_slot_marker(self, src: int, dst: int) -> None:
        if src == dst:
            return
        src_val = self._spray_spent_slots.get(src)
        dst_val = self._spray_spent_slots.get(dst)
        if src_val is None and dst_val is None:
            return
        if src_val is None:
            self._spray_spent_slots.pop(dst, None)
            self._spray_spent_slots[src] = dst_val  # type: ignore[assignment]
            return
        if dst_val is None:
            self._spray_spent_slots.pop(src, None)
            self._spray_spent_slots[dst] = src_val
            return
        self._spray_spent_slots[src], self._spray_spent_slots[dst] = dst_val, src_val

    def _update_grab_target_state(
        self,
        holding_pickup: bool,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
    ) -> None:
        if not holding_pickup:
            self._grabbed_object_id = None
            return

        grabbed_valid = False
        if self._grabbed_object_id is not None:
            obj = next((o for o in world.objects if o.object_id == self._grabbed_object_id), None)
            if obj is None or not obj.blocking or obj.kind == "door":
                self._grabbed_object_id = None
            else:
                if (
                    self._distance_to_object_from_player(
                        player=player,
                        sprite_w=sprite_w,
                        sprite_h=sprite_h,
                        obj=obj,
                        object_sprites=object_sprites,
                    )
                    > self._DRAG_RELEASE_DISTANCE
                ):
                    self._grabbed_object_id = None
                elif not self._can_push_object(player, inventory, world, obj):
                    self._grabbed_object_id = None
                else:
                    grabbed_valid = True

        if grabbed_valid:
            return

        if self._grabbed_object_id is not None and not grabbed_valid:
            # Ensure reacquire path always starts from clean state in the same frame.
            self._grabbed_object_id = None

        target = self._find_grab_candidate(
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            world=world,
            object_sprites=object_sprites,
            inventory=inventory,
        )
        if target is None:
            return
        self._grabbed_object_id = target.object_id

    def _drag_movement_speed_factor(
        self,
        holding_pickup: bool,
        input_dx: float,
        input_dy: float,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
    ) -> float:
        if not holding_pickup:
            return 1.0
        if abs(input_dx) < 0.001 and abs(input_dy) < 0.001:
            return 1.0

        target = self._active_drag_target(
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            world=world,
            object_sprites=object_sprites,
            inventory=inventory,
        )
        if target is None:
            return 1.0
        if not self._is_moving_away_from_object(
            obj=target,
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            move_dx=input_dx,
            move_dy=input_dy,
            object_sprites=object_sprites,
        ):
            return 1.0

        return self._mass_based_drag_factor(player, inventory, world, target)

    def _active_drag_target(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
    ) -> WorldObject | None:
        if self._grabbed_object_id is not None:
            grabbed = next((o for o in world.objects if o.object_id == self._grabbed_object_id), None)
            if (
                grabbed is not None
                and grabbed.blocking
                and grabbed.kind != "door"
                and self._can_push_object(player, inventory, world, grabbed)
                and self._distance_to_object_from_player(
                    player=player,
                    sprite_w=sprite_w,
                    sprite_h=sprite_h,
                    obj=grabbed,
                    object_sprites=object_sprites,
                )
                <= self._DRAG_RELEASE_DISTANCE
            ):
                return grabbed

        return self._find_grab_candidate(
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            world=world,
            object_sprites=object_sprites,
            inventory=inventory,
        )

    def _find_grab_candidate(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
    ) -> WorldObject | None:
        touching = self._find_touching_grab_candidate(
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            world=world,
            object_sprites=object_sprites,
            inventory=inventory,
        )
        if touching is not None:
            return touching

        front = self._find_object_in_front(world, player, object_sprites)
        if (
            front is not None
            and front.blocking
            and front.kind != "door"
            and self._can_push_object(player, inventory, world, front)
            and self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=front,
                object_sprites=object_sprites,
            )
            <= self._grab_max_gap_for_object(front)
        ):
            return front

        nearest: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            if not obj.blocking or obj.kind == "door":
                continue
            if not self._can_push_object(player, inventory, world, obj):
                continue
            dist = self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=obj,
                object_sprites=object_sprites,
            )
            if dist > self._grab_max_gap_for_object(obj):
                continue
            if nearest is None or dist < nearest[0]:
                nearest = (dist, obj)
        return nearest[1] if nearest else None

    def _find_touching_grab_candidate(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
    ) -> WorldObject | None:
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        probe_rect = player_rect.inflate(34, 30)
        best: tuple[float, WorldObject] | None = None

        for obj in world.objects:
            if not obj.blocking or obj.kind == "door":
                continue
            if not self._can_push_object(player, inventory, world, obj):
                continue
            obj_rect = self._object_collider_rect(obj, object_sprites)
            if not probe_rect.colliderect(obj_rect):
                continue
            dist = self._distance_to_object_from_player(
                player=player,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                obj=obj,
                object_sprites=object_sprites,
            )
            if dist > self._grab_max_gap_for_object(obj):
                continue
            if best is None or dist < best[0]:
                best = (dist, obj)
        return best[1] if best else None

    def _grab_max_gap_for_object(self, obj: WorldObject) -> float:
        if obj.kind == "plant":
            return self._PLANT_GRAB_MAX_GAP
        return self._GRAB_MAX_DISTANCE

    def _mass_based_drag_factor(
        self,
        player: Player,
        inventory: Inventory,
        world: WorldMap,
        obj: WorldObject,
    ) -> float:
        player_mass = max(1.0, player.stats.mass_kg() + self._inventory_weight_kg(inventory, world.item_weights))
        max_pull_mass = max(1.0, player_mass / 1.5)
        heaviness_ratio = max(0.0, obj.weight_kg) / max_pull_mass
        heaviness_ratio = min(1.25, heaviness_ratio)
        # Heavier object relative to player means slower dragging movement.
        return max(0.28, 1.0 - heaviness_ratio * 0.72)

    def _is_moving_away_from_object(
        self,
        obj: WorldObject,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        move_dx: float,
        move_dy: float,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        obj_rect = self._object_collider_rect(obj, object_sprites)
        to_obj_x = obj_rect.centerx - player_rect.centerx
        to_obj_y = obj_rect.centery - player_rect.centery
        dot = move_dx * to_obj_x + move_dy * to_obj_y
        return dot < -0.05

    def _distance_to_object_from_player(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        obj: WorldObject,
        object_sprites: ObjectSpriteLibrary,
    ) -> float:
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        obj_rect = self._object_collider_rect(obj, object_sprites).inflate(12, 12)
        return self._rect_gap_distance(player_rect, obj_rect)

    @staticmethod
    def _rect_gap_distance(a: pygame.Rect, b: pygame.Rect) -> float:
        if a.right < b.left:
            dx = float(b.left - a.right)
        elif b.right < a.left:
            dx = float(a.left - b.right)
        else:
            dx = 0.0

        if a.bottom < b.top:
            dy = float(b.top - a.bottom)
        elif b.bottom < a.top:
            dy = float(a.top - b.bottom)
        else:
            dy = 0.0

        return math.hypot(dx, dy)

    def _resolve_blocking_collisions(
        self,
        player: Player,
        prev_x: float,
        prev_y: float,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
        is_running: bool,
    ) -> None:
        is_jumping = player.jump_time_left > 0.0

        current_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        collided = self._first_blocking_collision(current_rect, world, object_sprites)
        if collided is None:
            return
        if is_jumping and collided.kind != "door":
            return
        move_dx = player.x - prev_x
        move_dy = player.y - prev_y
        if (
            not is_jumping
            and is_running
            and self._can_push_object(player, inventory, world, collided)
            and self._is_moving_towards_object(
                obj=collided,
                move_dx=move_dx,
                move_dy=move_dy,
                prev_x=prev_x,
                prev_y=prev_y,
                sprite_w=sprite_w,
                sprite_h=sprite_h,
                object_sprites=object_sprites,
            )
            and self._try_push_object(collided, move_dx, move_dy, world, object_sprites)
        ):
            current_after_push = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
            if self._first_blocking_collision(current_after_push, world, object_sprites) is None:
                return

        x_only_rect = self._player_collider_rect(prev_x, player.y, sprite_w, sprite_h)
        if not self._collides_with_blocking(x_only_rect, world, object_sprites):
            player.x = prev_x
            return

        y_only_rect = self._player_collider_rect(player.x, prev_y, sprite_w, sprite_h)
        if not self._collides_with_blocking(y_only_rect, world, object_sprites):
            player.y = prev_y
            return

        player.x = prev_x
        player.y = prev_y

    def _resolve_room_wall_collisions(
        self,
        player: Player,
        prev_x: float,
        prev_y: float,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
    ) -> None:
        current_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        if not self._collides_with_room_walls(current_rect, world):
            return

        x_only_rect = self._player_collider_rect(prev_x, player.y, sprite_w, sprite_h)
        if not self._collides_with_room_walls(x_only_rect, world):
            player.x = prev_x
            return

        y_only_rect = self._player_collider_rect(player.x, prev_y, sprite_w, sprite_h)
        if not self._collides_with_room_walls(y_only_rect, world):
            player.y = prev_y
            return

        player.x = prev_x
        player.y = prev_y

    def _collides_with_room_walls(self, player_rect: pygame.Rect, world: WorldMap) -> bool:
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            for wall in self._room_wall_rects(room):
                if player_rect.colliderect(wall):
                    return True
        return False

    def _room_wall_rects(self, room: RoomArea) -> list[pygame.Rect]:
        t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
        # Allow player to step slightly under the bottom wall for better depth feel.
        bottom_collision_inset = min(8, max(0, t - 1))
        bottom_collision_y = room.y + room.height - t + bottom_collision_inset
        bottom_collision_h = max(1, t - bottom_collision_inset)
        top_t = (
            max(t, min(room.top_wall_height, room.height // 2))
            if room.top_wall_height > 0
            else t
        )
        top_span = self._opening_span(
            start=room.x + t + 10,
            length=room.width - (t * 2) - 20,
            opening_width=room.top_door_width,
            opening_offset=room.top_door_offset,
        )
        bottom_span = self._opening_span(
            start=room.x + t + 10,
            length=room.width - (t * 2) - 20,
            opening_width=room.bottom_opening_width,
            opening_offset=room.bottom_opening_offset,
        )
        left_span = self._opening_span(
            start=room.y + t + 10,
            length=room.height - (t * 2) - 20,
            opening_width=room.left_opening_width,
            opening_offset=room.left_opening_offset,
        )
        right_span = self._opening_span(
            start=room.y + t + 10,
            length=room.height - (t * 2) - 20,
            opening_width=room.right_opening_width,
            opening_offset=room.right_opening_offset,
        )
        side_opening_full_len = max(1, room.height - (t * 2) - 20)

        rects: list[pygame.Rect] = []
        if top_span is None:
            rects.append(pygame.Rect(room.x, room.y, room.width, top_t))
        else:
            l, r = top_span
            rects.append(pygame.Rect(room.x, room.y, max(1, l - room.x), top_t))
            rects.append(pygame.Rect(r, room.y, max(1, room.x + room.width - r), top_t))
            if room.top_opening_layered:
                pass_l, pass_r = self._top_opening_pass_span(room, l, r)
                hard_h = int(room.top_opening_hard_height) if room.top_opening_hard_height > 0 else top_t
                hard_h = max(1, min(room.height, hard_h))
                if pass_l > l:
                    rects.append(pygame.Rect(l, room.y, pass_l - l, hard_h))
                if r > pass_r:
                    rects.append(pygame.Rect(pass_r, room.y, r - pass_r, hard_h))

        if bottom_span is None:
            rects.append(pygame.Rect(room.x, bottom_collision_y, room.width, bottom_collision_h))
        else:
            l, r = bottom_span
            rects.append(
                pygame.Rect(room.x, bottom_collision_y, max(1, l - room.x), bottom_collision_h)
            )
            rects.append(
                pygame.Rect(r, bottom_collision_y, max(1, room.x + room.width - r), bottom_collision_h)
            )

        if left_span is None:
            rects.append(pygame.Rect(room.x, room.y, t, room.height))
        else:
            a, b = left_span
            if (b - a) < (side_opening_full_len - 1):
                rects.append(pygame.Rect(room.x, room.y, t, max(1, a - room.y)))
                rects.append(pygame.Rect(room.x, b, t, max(1, room.y + room.height - b)))

        if right_span is None:
            rects.append(pygame.Rect(room.x + room.width - t, room.y, t, room.height))
        else:
            a, b = right_span
            x = room.x + room.width - t
            if (b - a) < (side_opening_full_len - 1):
                rects.append(pygame.Rect(x, room.y, t, max(1, a - room.y)))
                rects.append(pygame.Rect(x, b, t, max(1, room.y + room.height - b)))

        return rects

    def _opening_span(
        self,
        start: int,
        length: int,
        opening_width: int,
        opening_offset: int,
    ) -> tuple[int, int] | None:
        if opening_width <= 0 or length <= 0:
            return None
        width = max(1, min(opening_width, length))
        center = start + (length // 2) + int(opening_offset)
        left = max(start, center - (width // 2))
        right = min(start + length, left + width)
        left = max(start, right - width)
        if right <= left:
            return None
        return left, right

    def _top_opening_pass_span(self, room: RoomArea, opening_left: int, opening_right: int) -> tuple[int, int]:
        opening_w = max(1, opening_right - opening_left)
        pass_w = int(room.top_opening_pass_width) if room.top_opening_pass_width > 0 else int(opening_w * 0.62)
        pass_w = max(32, min(opening_w, pass_w))
        center = (opening_left + opening_right) // 2 + int(room.top_opening_pass_offset)
        left = max(opening_left, center - (pass_w // 2))
        right = min(opening_right, left + pass_w)
        left = max(opening_left, right - pass_w)
        return left, right

    def _collides_with_blocking(
        self,
        player_rect: pygame.Rect,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        return self._first_blocking_collision(player_rect, world, object_sprites) is not None

    def _first_blocking_collision(
        self,
        player_rect: pygame.Rect,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        *,
        ignore_object_id: str | None = None,
    ) -> WorldObject | None:
        for obj in world.objects:
            if not obj.blocking and not self._is_open_door_leaf_blocking(obj):
                continue
            if ignore_object_id is not None and obj.object_id == ignore_object_id:
                continue
            if self._standing_on_object_id is not None and obj.object_id == self._standing_on_object_id:
                continue
            obj_rect = self._object_collider_rect(obj, object_sprites)
            if player_rect.colliderect(obj_rect):
                return obj
        return None

    def _player_collider_rect(self, x: float, y: float, sprite_w: int, sprite_h: int) -> pygame.Rect:
        collider_w = max(18, int(sprite_w * 0.42))
        collider_h = max(14, int(sprite_h * 0.24))
        cx = x + sprite_w / 2
        cy = y + sprite_h * 0.86
        return pygame.Rect(
            int(cx - collider_w / 2),
            int(cy - collider_h / 2),
            collider_w,
            collider_h,
        )

    def _object_collider_rect(
        self,
        obj: WorldObject,
        object_sprites: ObjectSpriteLibrary,
    ) -> pygame.Rect:
        return self._object_collider_rect_at(obj, object_sprites, obj.x, obj.y)

    def _object_collider_rect_at(
        self,
        obj: WorldObject,
        object_sprites: ObjectSpriteLibrary,
        x: float,
        y: float,
    ) -> pygame.Rect:
        sprite = self._object_sprite(obj, object_sprites)
        if self._is_open_door_leaf_blocking(obj):
            sw, sh = sprite.get_size()
            left = x - sw / 2
            top = y - sh / 2
            orientation = self._normalize_door_orientation(obj.door_orientation)
            # Opened leaf is hard; pass-through stays in the aperture side.
            if orientation == "right":
                leaf_x = int(left + sw * 0.55)
            else:
                leaf_x = int(left + sw * 0.12)
            leaf_y = int(top + sh * 0.18)
            leaf_w = max(10, int(sw * 0.33))
            leaf_h = max(20, int(sh * 0.80))
            return pygame.Rect(leaf_x, leaf_y, leaf_w, leaf_h)
        collider_w, collider_h, y_anchor = self._object_collider_metrics(obj, sprite)
        return pygame.Rect(
            int(x - collider_w / 2),
            int(y + y_anchor - collider_h / 2),
            collider_w,
            collider_h,
        )

    def _is_open_door_leaf_blocking(self, obj: WorldObject) -> bool:
        return obj.kind == "door" and (not obj.blocking) and obj.state > 0

    def _normalize_door_orientation(self, value: str | None) -> str:
        token = str(value).strip().lower() if value is not None else "top"
        if token in {"top", "left", "right", "bottom"}:
            return token
        return "top"

    def _can_push_object(
        self,
        player: Player,
        inventory: Inventory,
        world: WorldMap,
        obj: WorldObject,
    ) -> bool:
        if not obj.blocking or obj.weight_kg <= 0.0:
            return False
        if obj.kind == "door":
            return False
        player_mass = player.stats.mass_kg() + self._inventory_weight_kg(inventory, world.item_weights)
        return player_mass >= obj.weight_kg * 1.5

    def _is_moving_towards_object(
        self,
        obj: WorldObject,
        move_dx: float,
        move_dy: float,
        prev_x: float,
        prev_y: float,
        sprite_w: int,
        sprite_h: int,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        # Prevent dragging/pulling exploit: only allow push when movement is directed into the object.
        if abs(move_dx) < 0.001 and abs(move_dy) < 0.001:
            return False
        prev_rect = self._player_collider_rect(prev_x, prev_y, sprite_w, sprite_h)
        obj_rect = self._object_collider_rect(obj, object_sprites)
        to_obj_x = obj_rect.centerx - prev_rect.centerx
        to_obj_y = obj_rect.centery - prev_rect.centery
        dot = move_dx * to_obj_x + move_dy * to_obj_y
        return dot > 0.0

    def _update_grabbed_object_drag(
        self,
        player: Player,
        prev_x: float,
        prev_y: float,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        inventory: Inventory,
        holding_pickup: bool,
    ) -> None:
        if self._grabbed_object_id is None:
            return
        if not holding_pickup:
            return
        obj = next((o for o in world.objects if o.object_id == self._grabbed_object_id), None)
        if obj is None or not obj.blocking:
            self._grabbed_object_id = None
            return
        if not self._can_push_object(player, inventory, world, obj):
            return

        move_dx = player.x - prev_x
        move_dy = player.y - prev_y
        if abs(move_dx) < 0.001 and abs(move_dy) < 0.001:
            return

        dist = self._distance_to_object_from_player(
            player=player,
            sprite_w=sprite_w,
            sprite_h=sprite_h,
            obj=obj,
            object_sprites=object_sprites,
        )
        if dist > self._DRAG_RELEASE_DISTANCE:
            self._grabbed_object_id = None
            self._set_message("Слишком далеко: объект отпущен")
            return
        if dist > self._DRAG_ACTIVE_DISTANCE:
            return

        # While E is held, dragged object follows player movement each frame.
        pull_factor = 1.0
        self._try_push_object(
            obj=obj,
            move_dx=move_dx * pull_factor,
            move_dy=move_dy * pull_factor,
            world=world,
            object_sprites=object_sprites,
        )

    def _inventory_weight_kg(self, inventory: Inventory, item_weights: dict[str, float]) -> float:
        total = 0.0
        for item_id in inventory.slots:
            if item_id is None:
                continue
            total += self._item_weight_kg(item_id, item_weights)
        return total

    def _item_weight_kg(self, item_id: str, item_weights: dict[str, float]) -> float:
        if item_id in item_weights:
            return max(0.0, float(item_weights[item_id]))
        if item_id.startswith("key_") and "key" in item_weights:
            return max(0.0, float(item_weights["key"]))
        if item_id.startswith("backpack") and "backpack" in item_weights:
            return max(0.0, float(item_weights["backpack"]))
        if item_id in self._spray_item_ids and "ballon" in item_weights:
            return max(0.0, float(item_weights["ballon"]))
        return 0.0

    def _try_push_object(
        self,
        obj: WorldObject,
        move_dx: float,
        move_dy: float,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> bool:
        if abs(move_dx) < 0.001 and abs(move_dy) < 0.001:
            return False
        start_rect = self._object_collider_rect(obj, object_sprites)
        candidates: list[tuple[float, float]] = [(move_dx, move_dy)]
        if abs(move_dx) >= abs(move_dy):
            candidates.extend([(move_dx, 0.0), (0.0, move_dy)])
        else:
            candidates.extend([(0.0, move_dy), (move_dx, 0.0)])

        old_x, old_y = obj.x, obj.y
        for dx, dy in candidates:
            if abs(dx) < 0.001 and abs(dy) < 0.001:
                continue
            obj.x = old_x + dx
            obj.y = old_y + dy
            if not self._object_position_blocked(
                obj,
                world,
                object_sprites,
                start_rect=start_rect,
            ):
                return True
        obj.x, obj.y = old_x, old_y
        return False

    def _object_position_blocked(
        self,
        obj: WorldObject,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
        *,
        start_rect: pygame.Rect | None = None,
    ) -> bool:
        rect = self._object_collider_rect(obj, object_sprites)
        bounds_penalty = self._out_of_bounds_area(rect, world.width, world.height)
        if bounds_penalty > 0:
            if start_rect is not None:
                old_bounds_penalty = self._out_of_bounds_area(start_rect, world.width, world.height)
                if old_bounds_penalty > 0 and bounds_penalty < old_bounds_penalty:
                    pass
                else:
                    return True
            else:
                return True

        for room in world.rooms:
            if not room.walls_enabled:
                continue
            for wall in self._room_wall_rects(room):
                if rect.colliderect(wall):
                    # If object is already intersecting this wall, allow movement that reduces overlap.
                    if start_rect is not None and start_rect.colliderect(wall):
                        old_overlap = self._rect_overlap_area(start_rect, wall)
                        new_overlap = self._rect_overlap_area(rect, wall)
                        if new_overlap < old_overlap:
                            continue
                    return True

        for other in world.objects:
            if (
                other.object_id == obj.object_id
                or (not other.blocking and not self._is_open_door_leaf_blocking(other))
            ):
                continue
            other_rect = self._object_collider_rect(other, object_sprites)
            if rect.colliderect(other_rect):
                # If objects are already intersecting (e.g. tight interior placement),
                # allow movement that reduces overlap so the object can be pulled out.
                if start_rect is not None and start_rect.colliderect(other_rect):
                    old_overlap = self._rect_overlap_area(start_rect, other_rect)
                    new_overlap = self._rect_overlap_area(rect, other_rect)
                    if new_overlap < old_overlap:
                        continue
                return True
        return False

    @staticmethod
    def _rect_overlap_area(a: pygame.Rect, b: pygame.Rect) -> int:
        ix = min(a.right, b.right) - max(a.left, b.left)
        iy = min(a.bottom, b.bottom) - max(a.top, b.top)
        if ix <= 0 or iy <= 0:
            return 0
        return int(ix * iy)

    @staticmethod
    def _out_of_bounds_area(rect: pygame.Rect, width: int, height: int) -> int:
        left = max(0, -rect.left)
        top = max(0, -rect.top)
        right = max(0, rect.right - width)
        bottom = max(0, rect.bottom - height)
        if left == 0 and top == 0 and right == 0 and bottom == 0:
            return 0
        penalty = 0
        if left > 0:
            penalty += left * max(1, rect.height)
        if right > 0:
            penalty += right * max(1, rect.height)
        if top > 0:
            penalty += top * max(1, rect.width)
        if bottom > 0:
            penalty += bottom * max(1, rect.width)
        return int(penalty)

    def _object_collider_metrics(self, obj: WorldObject, sprite: pygame.Surface) -> tuple[int, int, float]:
        return self._object_collider_metrics_from_size(
            obj=obj,
            sprite_w=sprite.get_width(),
            sprite_h=sprite.get_height(),
        )

    def _object_collider_metrics_from_size(
        self,
        obj: WorldObject,
        sprite_w: int,
        sprite_h: int,
    ) -> tuple[int, int, float]:
        collider_w = int(obj.collider_w) if obj.collider_w is not None else int(sprite_w * 0.72)
        collider_h = int(obj.collider_h) if obj.collider_h is not None else int(sprite_h * 0.32)
        y_anchor = float(sprite_h) * 0.32

        if obj.kind == "plant":
            # Expand plant collider upward a bit so player cannot step too deep into the leaves.
            extra_up = max(12, int(sprite_h * 0.08))
            collider_h += extra_up
            y_anchor -= extra_up * 0.5
        elif obj.kind == "door":
            # Closed top doors: keep pass blocked, but let player approach from corridor side.
            # Shift collider down (instead of full centered slab), and widen it to seal side bypass.
            if obj.blocking and obj.state <= 0:
                collider_w = max(collider_w, int(sprite_w * 0.66))
                collider_h = max(collider_h, int(sprite_h * 0.64))
                y_anchor = float(sprite_h) * 0.18
            else:
                collider_w = max(collider_w, int(sprite_w * 0.54))
                collider_h = max(collider_h, int(sprite_h * 0.48))
                y_anchor = float(sprite_h) * 0.08
        elif obj.kind == "sofa":
            # Make sofa non-passable from sides and earlier from top.
            side_guard = max(14, int(sprite_w * 0.07))
            collider_w = max(collider_w, int(sprite_w * 0.96) + side_guard * 2)
            collider_h = max(collider_h, int(sprite_h * 0.56))
            y_anchor = min(y_anchor, float(sprite_h) * 0.30)
            extra_up = max(12, int(sprite_h * 0.07))
            collider_h += extra_up
            y_anchor -= extra_up * 0.55

        return max(8, collider_w), max(8, collider_h), float(y_anchor)

    def _update_standing_platform(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        if self._standing_on_object_id is None:
            return
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        obj = next((o for o in world.objects if o.object_id == self._standing_on_object_id), None)
        if obj is None:
            self._standing_on_object_id = None
            return
        platform = self._object_platform_rect(obj, object_sprites)
        if platform is None:
            self._standing_on_object_id = None
            return
        if not player_rect.colliderect(platform.inflate(24, 20)):
            self._standing_on_object_id = None

    def _try_land_on_platform(
        self,
        player: Player,
        sprite_w: int,
        sprite_h: int,
        world: WorldMap,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        player_rect = self._player_collider_rect(player.x, player.y, sprite_w, sprite_h)
        best: tuple[float, WorldObject] | None = None
        for obj in world.objects:
            platform = self._object_platform_rect(obj, object_sprites)
            if platform is None:
                continue
            if not player_rect.colliderect(platform):
                continue
            dist = abs(player_rect.centerx - platform.centerx) + abs(player_rect.centery - platform.centery)
            if best is None or dist < best[0]:
                best = (dist, obj)
        self._standing_on_object_id = best[1].object_id if best else None

    def _object_platform_rect(
        self,
        obj: WorldObject,
        object_sprites: ObjectSpriteLibrary,
    ) -> pygame.Rect | None:
        if obj.kind == "sofa":
            # Sofa should not be a jump-landing platform.
            return None
        if obj.jump_platform_w is None or obj.jump_platform_h is None:
            return None
        sprite = self._object_sprite(obj, object_sprites)
        cx = obj.x
        cy = obj.y + obj.jump_platform_offset_y
        return pygame.Rect(
            int(cx - obj.jump_platform_w / 2),
            int(cy - obj.jump_platform_h / 2 - sprite.get_height() * 0.12),
            int(max(8.0, obj.jump_platform_w)),
            int(max(8.0, obj.jump_platform_h)),
        )
