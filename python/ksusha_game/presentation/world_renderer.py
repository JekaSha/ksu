from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame

from ksusha_game.config import GameConfig
from ksusha_game.domain.inventory import Inventory
from ksusha_game.domain.world import SprayTag, WorldMap, WorldObject
from ksusha_game.infrastructure.floor_tileset import FloorTileset
from ksusha_game.infrastructure.object_sprites import ObjectSpriteLibrary
from ksusha_game.infrastructure.wall_sprites import WallSpriteLibrary


@dataclass(frozen=True)
class Camera:
    x: float
    y: float
    width: int
    height: int


class WorldRenderer:
    def __init__(self, config: GameConfig) -> None:
        self._config = config
        pygame.font.init()
        self._font = pygame.font.Font(None, 24)
        self._object_label_font = pygame.font.Font(None, 22)
        self._lock_marker_font = pygame.font.Font(None, 16)
        self._wall_scale_cache: dict[tuple[object, ...], pygame.Surface] = {}
        self._floor_shadow_cache: dict[tuple[object, ...], pygame.Surface] = {}
        self._object_tint_cache: dict[tuple[object, ...], pygame.Surface] = {}
        self._door_open_occluder_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        self._spray_scale_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        self._outside_floor_tile_cache: list[pygame.Surface] | None = None
        self._outside_bush_cache: list[pygame.Surface] | None = None
        self._outside_bush_layout_cache: dict[tuple[object, ...], list[tuple[int, int, int]]] = {}

    def render(
        self,
        screen: pygame.Surface,
        world: WorldMap,
        floor_tileset: FloorTileset,
        wall_sprites: WallSpriteLibrary,
        object_sprites: ObjectSpriteLibrary,
        objects: list[WorldObject],
        player_pos: tuple[float, float],
        player_frame: pygame.Surface,
        player_bob: float,
        player_left_facing: bool,
        inventory: Inventory,
        spray_tags: list[SprayTag],
        message: str,
        dragged_object_id: str | None = None,
    ) -> None:
        width, height = screen.get_size()
        camera = self._build_camera(world, width, height, player_pos)
        world_layer = pygame.Surface((width, height), pygame.SRCALPHA)

        world_layer.fill(self._config.window.background_color)
        self._draw_outside_nonwalkable(world_layer, camera, world)
        self._draw_floors(world_layer, camera, world, floor_tileset)
        self._draw_walls(world_layer, camera, world, wall_sprites, objects)
        self._draw_spray_tags(world_layer, camera, world, spray_tags, object_sprites, target_kind="wall_top")
        occluders = self._draw_objects_base_pass(world_layer, camera, objects, object_sprites)
        self._draw_spray_tags(world_layer, camera, world, spray_tags, object_sprites, target_kind="door")
        self._draw_player(world_layer, camera, player_pos, player_frame, player_bob, player_left_facing)
        self._draw_objects_occluder_pass(
            world_layer,
            occluders,
            camera,
            player_pos,
            player_frame,
            player_bob,
        )
        self._draw_top_openings_foreground(
            world_layer,
            camera,
            world,
            wall_sprites,
            objects,
            player_pos,
            player_frame,
            player_bob,
        )
        # Keep wall graffiti strictly behind the character.
        # Re-drawing wall-top spray above player caused inconsistent head overlap
        # on some wall/opening combinations.
        self._draw_dragged_object_foreground(
            screen=world_layer,
            camera=camera,
            world=world,
            objects=objects,
            object_sprites=object_sprites,
            dragged_object_id=dragged_object_id,
            player_pos=player_pos,
        )
        self._draw_bottom_walls_foreground(world_layer, camera, world, wall_sprites)
        if world.show_object_labels:
            self._draw_object_labels(world_layer, camera, objects, object_sprites)

        fog_center = (player_pos[0] - camera.x, player_pos[1] - camera.y)
        world_layer = self._apply_fog(world_layer, world, fog_center)
        screen.blit(world_layer, (0, 0))
        self._draw_inventory(screen, inventory, object_sprites)
        if message:
            self._draw_message(screen, message)

    def _build_camera(
        self,
        world: WorldMap,
        view_w: int,
        view_h: int,
        player_pos: tuple[float, float],
    ) -> Camera:
        x = player_pos[0] - view_w / 2
        y = player_pos[1] - view_h / 2
        x = max(0.0, min(x, world.width - view_w))
        y = max(0.0, min(y, world.height - view_h))
        return Camera(x=x, y=y, width=view_w, height=view_h)

    def _draw_outside_nonwalkable(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
    ) -> None:
        floor_tiles = self._outside_floor_tiles()
        if floor_tiles:
            self._draw_outside_floor_tiles(screen, camera, floor_tiles)
        bush_variants = self._outside_bush_variants()
        if bush_variants:
            self._draw_outside_bushes(screen, camera, world, bush_variants)

    def _outside_floor_tiles(self) -> list[pygame.Surface]:
        if self._outside_floor_tile_cache is not None:
            return self._outside_floor_tile_cache

        base = Path(__file__).resolve().parents[3] / "source/textures/floors/outside"
        candidates = [
            base / "stone_border.png",
        ]
        loaded: list[pygame.Surface] = []
        for p in candidates:
            if not p.exists():
                continue
            loaded.append(pygame.image.load(str(p)).convert_alpha())

        if not loaded:
            self._outside_floor_tile_cache = []
            return self._outside_floor_tile_cache

        target_w = loaded[0].get_width()
        target_h = loaded[0].get_height()
        normalized: list[pygame.Surface] = []
        for tile in loaded:
            if tile.get_width() != target_w or tile.get_height() != target_h:
                tile = pygame.transform.scale(tile, (target_w, target_h))
            normalized.append(tile)

        self._outside_floor_tile_cache = normalized
        return self._outside_floor_tile_cache

    def _draw_outside_floor_tiles(
        self,
        screen: pygame.Surface,
        camera: Camera,
        tiles: list[pygame.Surface],
    ) -> None:
        if not tiles:
            return
        cam_x = int(camera.x)
        cam_y = int(camera.y)
        tw, th = tiles[0].get_size()
        if tw <= 0 or th <= 0:
            return
        start_x = (cam_x // tw) * tw
        start_y = (cam_y // th) * th
        end_x = cam_x + camera.width + tw
        end_y = cam_y + camera.height + th

        for y in range(start_y, end_y, th):
            for x in range(start_x, end_x, tw):
                tile = tiles[0]
                screen.blit(tile, (x - cam_x, y - cam_y))

    def _outside_bush_variants(self) -> list[pygame.Surface]:
        if self._outside_bush_cache is not None:
            return self._outside_bush_cache

        path = Path(__file__).resolve().parents[3] / "source/textures/items/plants/outdoor_bushes_sheet.png"
        if not path.exists():
            self._outside_bush_cache = []
            return self._outside_bush_cache

        sheet = pygame.image.load(str(path)).convert_alpha()
        rgb = pygame.surfarray.pixels3d(sheet)
        alpha = pygame.surfarray.pixels_alpha(sheet)
        r = rgb[:, :, 0].astype(np.int32)
        g = rgb[:, :, 1].astype(np.int32)
        b = rgb[:, :, 2].astype(np.int32)
        magenta = (alpha > 0) & (r >= 170) & (b >= 170) & (g <= 120)
        alpha[magenta] = 0
        rgb[magenta] = 0
        del rgb, alpha

        components = self._extract_components(sheet, alpha_cutoff=20, min_area=3500)
        components = sorted(components, key=lambda r: (r.centery, r.centerx))

        variants: list[pygame.Surface] = []
        for rect in components:
            sprite = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            sprite.blit(sheet, (0, 0), rect)
            tight = sprite.get_bounding_rect(min_alpha=20)
            if tight.width <= 0 or tight.height <= 0:
                continue
            cropped = sprite.subsurface(tight).copy()
            variants.append(self._fit_bottom_aligned(cropped, (112, 112)))

        self._outside_bush_cache = variants
        return self._outside_bush_cache

    def _draw_outside_bushes(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        bush_variants: list[pygame.Surface],
    ) -> None:
        if not bush_variants:
            return
        layout = self._outside_bush_layout(world, len(bush_variants))
        cam_x = int(camera.x)
        cam_y = int(camera.y)
        view = pygame.Rect(0, 0, camera.width, camera.height)

        for x, y, variant_idx in layout:
            sprite = bush_variants[variant_idx % len(bush_variants)]
            draw_x = int(x - cam_x - sprite.get_width() * 0.5)
            draw_y = int(y - cam_y - sprite.get_height())
            rect = pygame.Rect(draw_x, draw_y, sprite.get_width(), sprite.get_height())
            if not rect.colliderect(view):
                continue
            screen.blit(sprite, (draw_x, draw_y))

    def _outside_bush_layout(self, world: WorldMap, variant_count: int) -> list[tuple[int, int, int]]:
        room_sig = tuple((r.x, r.y, r.width, r.height) for r in world.rooms)
        key = (world.width, world.height, room_sig, variant_count)
        cached = self._outside_bush_layout_cache.get(key)
        if cached is not None:
            return cached

        result: list[tuple[int, int, int]] = []
        step_x = 170
        step_y = 156
        for y in range(78, max(79, world.height - 48), step_y):
            for x in range(78, max(79, world.width - 48), step_x):
                h = ((x * 92821) ^ (y * 68917)) & 0xFFFFFFFF
                if h % 5 != 0:
                    continue
                px = x + int((h >> 8) % 41) - 20
                py = y + int((h >> 14) % 33) - 16
                if self._point_in_or_near_any_room(px, py, world, margin=30):
                    continue
                result.append((px, py, h % max(1, variant_count)))

        self._outside_bush_layout_cache[key] = result
        return result

    def _point_in_or_near_any_room(self, x: int, y: int, world: WorldMap, margin: int) -> bool:
        for room in world.rooms:
            if (
                room.x - margin <= x < room.x + room.width + margin
                and room.y - margin <= y < room.y + room.height + margin
            ):
                return True
        return False

    def _extract_components(
        self,
        surface: pygame.Surface,
        alpha_cutoff: int,
        min_area: int,
    ) -> list[pygame.Rect]:
        w, h = surface.get_size()
        alpha_arr = pygame.surfarray.array_alpha(surface)
        solid = alpha_arr >= alpha_cutoff
        visited = np.zeros((w, h), dtype=bool)

        components: list[pygame.Rect] = []
        for pos in np.argwhere(solid):
            x0, y0 = int(pos[0]), int(pos[1])
            if visited[x0, y0]:
                continue
            visited[x0, y0] = True
            q: deque[tuple[int, int]] = deque([(x0, y0)])
            min_x = max_x = x0
            min_y = max_y = y0
            area = 0
            while q:
                x, y = q.popleft()
                area += 1
                if x < min_x:
                    min_x = x
                elif x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                elif y > max_y:
                    max_y = y
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and not visited[nx, ny]:
                        visited[nx, ny] = True
                        if solid[nx, ny]:
                            q.append((nx, ny))
            if area >= min_area:
                components.append(pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))
        return components

    def _fit_bottom_aligned(self, sprite: pygame.Surface, target_size: tuple[int, int]) -> pygame.Surface:
        tw, th = target_size
        sw, sh = sprite.get_size()
        scale = min(tw / max(1, sw), th / max(1, sh))
        out_w = max(1, int(sw * scale))
        out_h = max(1, int(sh * scale))
        scaled = pygame.transform.scale(sprite, (out_w, out_h))
        canvas = pygame.Surface((tw, th), pygame.SRCALPHA)
        canvas.blit(scaled, ((tw - out_w) // 2, th - out_h))
        return canvas

    def _draw_floors(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        floor_tileset: FloorTileset,
    ) -> None:
        cam_x = int(camera.x)
        cam_y = int(camera.y)
        for room in world.rooms:
            tile = floor_tileset.get(room.floor_texture)
            tw, th = tile.get_size()
            start_x = room.x
            end_x = room.x + room.width
            start_y = room.y
            end_y = room.y + room.height
            # World-anchored tiling avoids visible seams where adjacent rooms meet.
            y = (start_y // th) * th
            while y < end_y:
                x = (start_x // tw) * tw
                while x < end_x:
                    clip_l = max(start_x, x)
                    clip_t = max(start_y, y)
                    clip_r = min(end_x, x + tw)
                    clip_b = min(end_y, y + th)
                    if clip_r > clip_l and clip_b > clip_t:
                        src = pygame.Rect(clip_l - x, clip_t - y, clip_r - clip_l, clip_b - clip_t)
                        screen.blit(tile, (clip_l - cam_x, clip_t - cam_y), src)
                    x += tw
                y += th

            # Optional top-left notch carve-out for authored room silhouettes.
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
            notch_w = max(0, min(room.top_left_notch_width, room.width - (t * 2)))
            notch_h = max(0, min(room.top_left_notch_height, room.height // 3))
            if notch_w > t and notch_h > 0:
                carve = pygame.Rect(
                    room.x + t - cam_x,
                    room.y - cam_y,
                    notch_w - t,
                    notch_h,
                )
                pygame.draw.rect(screen, self._config.window.background_color, carve)

            self._draw_side_wall_floor_shadows(
                screen=screen,
                camera=camera,
                room=room,
            )

    def _draw_room_vignette(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        # Warm edge darkening, stronger near borders like the reference room art.
        inset_max = min(42, rect.width // 6, rect.height // 6)
        for i in range(1, inset_max):
            alpha = max(0, int(36 - i * 0.95))
            if alpha <= 0:
                continue
            ring_rect = pygame.Rect(
                rect.x + i,
                rect.y + i,
                max(2, rect.width - i * 2),
                max(2, rect.height - i * 2),
            )
            pygame.draw.rect(screen, (31, 20, 14, alpha), ring_rect, width=1)

    def _draw_side_wall_floor_shadows(
        self,
        screen: pygame.Surface,
        camera: Camera,
        room,
    ) -> None:
        if not room.walls_enabled:
            return
        t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
        top_t = (
            max(t, min(room.top_wall_height, room.height // 2))
            if room.top_wall_height > 0
            else t
        )
        interior = pygame.Rect(
            int(room.x + t - camera.x),
            int(room.y + top_t - camera.y),
            int(room.width - (t * 2)),
            int(room.height - top_t - t),
        )
        if interior.width <= 2 or interior.height <= 2:
            return

        # Keep side wall shadows subtle to avoid visible dark bands.
        left_band = min(max(8, t // 2 + 8), min(28, interior.width // 3))
        right_band = min(max(10, t // 2 + 10), min(34, interior.width // 3))

        if left_band > 1:
            left_shadow = self._side_shadow_gradient(
                width=left_band - 1,
                height=interior.height,
                side="left",
                max_alpha=18,
            )
            # Leave 1px clear at the wall seam to avoid hard dark bands.
            screen.blit(left_shadow, (interior.x + 1, interior.y))
        if right_band > 1:
            right_shadow = self._side_shadow_gradient(
                width=right_band - 1,
                height=interior.height,
                side="right",
                max_alpha=22,
            )
            # Leave 1px clear at the wall seam to avoid hard dark bands.
            screen.blit(right_shadow, (interior.right - right_band, interior.y))

    def _side_shadow_gradient(
        self,
        width: int,
        height: int,
        side: str,
        max_alpha: int,
    ) -> pygame.Surface:
        key = ("side_floor_shadow", side, int(width), int(height), int(max_alpha))
        cached = self._floor_shadow_cache.get(key)
        if cached is not None:
            return cached

        gradient = pygame.Surface((width, height), pygame.SRCALPHA)
        shade_r, shade_g, shade_b = (24, 16, 10)
        denom_x = max(1, width - 1)
        denom_y = max(1, height - 1)
        for x in range(width):
            raw = (1.0 - (x / denom_x)) if side == "left" else (x / denom_x)
            edge_factor = max(0.0, raw) ** 1.65
            alpha_by_x = max_alpha * edge_factor
            for y in range(height):
                # Stronger near top, softer near bottom to mimic wall depth shadow.
                vertical = y / denom_y
                top_boost = 1.0 - min(1.0, vertical * 0.72)
                alpha = int(alpha_by_x * (0.70 + top_boost * 0.30))
                if alpha <= 0:
                    continue
                gradient.set_at((x, y), (shade_r, shade_g, shade_b, alpha))

        self._floor_shadow_cache[key] = gradient
        return gradient

    def _draw_walls(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        wall_sprites: WallSpriteLibrary,
        objects: list[WorldObject],
    ) -> None:
        sprites = wall_sprites.sprites()
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
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
            right_x = room.x + room.width - t
            notch_w = max(0, min(room.top_left_notch_width, room.width - (t * 2)))
            notch_h = max(0, min(room.top_left_notch_height, room.height // 3))

            # Top side
            if top_span is None:
                if notch_w > 0 and notch_h > 0:
                    # Main top segment starts after notch step.
                    self._blit_scaled(
                        screen,
                        sprites.horizontal_wall,
                        room.x + notch_w - camera.x,
                        room.y - camera.y,
                        max(1, room.width - notch_w),
                        top_t,
                        "h",
                    )
                    # Notch shelf segment.
                    self._blit_scaled(
                        screen,
                        sprites.horizontal_wall,
                        room.x - camera.x,
                        room.y + notch_h - camera.y,
                        max(1, notch_w),
                        top_t,
                        "hn",
                    )
                    # Inner notch riser.
                    self._blit_scaled(
                        screen,
                        sprites.vertical_wall,
                        room.x + notch_w - t - camera.x,
                        room.y - camera.y,
                        t,
                        max(t, notch_h + t),
                        "vn",
                    )
                else:
                    self._blit_scaled(
                        screen,
                        sprites.horizontal_wall,
                        room.x - camera.x,
                        room.y - camera.y,
                        room.width,
                        top_t,
                        "h",
                    )
            else:
                l, r = top_span
                opening_door = self._door_for_top_opening(objects, room, l, r, top_t)
                self._blit_scaled(
                    screen,
                    sprites.horizontal_wall,
                    room.x - camera.x,
                    room.y - camera.y,
                    max(1, l - room.x),
                    top_t,
                    "h",
                )
                self._blit_scaled(
                    screen,
                    sprites.horizontal_wall,
                    r - camera.x,
                    room.y - camera.y,
                    max(1, room.x + room.width - r),
                    top_t,
                    "h",
                )
                if room.top_opening_layered:
                    # If a real door object exists in this opening, keep only one floor source
                    # (room floor) to avoid visible floor-substitution seams.
                    if opening_door is None:
                        floor_y, floor_h = self._top_opening_floor_rect(room, top_t)
                        self._blit_scaled(
                            screen,
                            sprites.top_door_floor,
                            l - camera.x,
                            floor_y - camera.y,
                            max(1, r - l),
                            floor_h,
                            "dof",
                        )
                else:
                    self._blit_scaled(
                        screen,
                        sprites.top_door_opening,
                        l - camera.x,
                        room.y - camera.y,
                        max(1, r - l),
                        top_t,
                        "dt",
                    )

            # Bottom side is rendered in a dedicated foreground pass after player draw.

            # Left side
            if left_span is None:
                self._blit_scaled(
                    screen, sprites.vertical_wall, room.x - camera.x, room.y - camera.y, t, room.height, "v"
                )
            else:
                a, b = left_span
                if (b - a) < (side_opening_full_len - 1):
                    self._blit_scaled(
                        screen,
                        sprites.vertical_wall,
                        room.x - camera.x,
                        room.y - camera.y,
                        t,
                        max(1, a - room.y),
                        "v",
                    )
                    self._blit_scaled(
                        screen,
                        sprites.vertical_wall,
                        room.x - camera.x,
                        b - camera.y,
                        t,
                        max(1, room.y + room.height - b),
                        "v",
                    )
                # Keep side transitions clean: no decorative frame inside corridor joints.

            # Right side
            if right_span is None:
                self._blit_scaled(
                    screen,
                    sprites.right_vertical_wall,
                    right_x - camera.x,
                    room.y - camera.y,
                    t,
                    room.height,
                    "vr",
                )
            else:
                a, b = right_span
                if (b - a) < (side_opening_full_len - 1):
                    self._blit_scaled(
                        screen,
                        sprites.right_vertical_wall,
                        right_x - camera.x,
                        room.y - camera.y,
                        t,
                        max(1, a - room.y),
                        "vr",
                    )
                    self._blit_scaled(
                        screen,
                        sprites.right_vertical_wall,
                        right_x - camera.x,
                        b - camera.y,
                        t,
                        max(1, room.y + room.height - b),
                        "vr",
                    )
                # Keep side transitions clean: no decorative frame inside corridor joints.

            left_is_full_open = left_span is not None and (left_span[1] - left_span[0]) >= (side_opening_full_len - 1)
            right_is_full_open = right_span is not None and (right_span[1] - right_span[0]) >= (side_opening_full_len - 1)
            if not left_is_full_open:
                self._blit_scaled(
                    screen,
                    sprites.left_top_wall,
                    room.x - camera.x,
                    room.y - camera.y,
                    t,
                    top_t,
                    "vlt",
                )
            if not right_is_full_open:
                self._blit_scaled(
                    screen,
                    sprites.right_top_wall,
                    right_x - camera.x,
                    room.y - camera.y,
                    t,
                    top_t,
                    "vrt",
                )

            # Optional top partition pillar.
            partition_w = max(0, room.top_partition_width)
            if partition_w > 0:
                px = room.x + (room.width // 2) + room.top_partition_offset - (partition_w // 2)
                ph = min(room.height - t, top_t + 66)
                self._blit_scaled(
                    screen,
                    sprites.vertical_wall,
                    px - camera.x,
                    room.y - camera.y,
                    partition_w,
                    max(1, ph),
                    "pt",
                )

            # Bottom corners are rendered in foreground pass after player draw.

            self._seal_floor_wall_seams(
                screen=screen,
                room=room,
                camera=camera,
                wall_thickness=t,
                top_wall_height=top_t,
            )

    def _draw_bottom_walls_foreground(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        wall_sprites: WallSpriteLibrary,
    ) -> None:
        # Render bottom walls in a foreground pass so player can step visually under them.
        sprites = wall_sprites.sprites()
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
            top_t = (
                max(t, min(room.top_wall_height, room.height // 2))
                if room.top_wall_height > 0
                else t
            )
            bottom_visual_h = self._bottom_wall_visual_height(sprites, t)
            bottom_y = room.y + room.height - t
            # Align by top edge with neighboring room top-wall blocks.
            # Bottom wall must start exactly at the room bottom boundary.
            draw_y = bottom_y + t
            draw_h = bottom_visual_h
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
            left_is_full_open = left_span is not None and (left_span[1] - left_span[0]) >= (side_opening_full_len - 1)
            right_is_full_open = right_span is not None and (right_span[1] - right_span[0]) >= (side_opening_full_len - 1)
            if bottom_span is not None and self._has_direct_bottom_room_transition(world, room, bottom_span):
                # Prevent double-overlay at direct top<->bottom room connections:
                # render either lower wall transition OR upper wall with opening (below room), not both.
                continue
            right_x = room.x + room.width - t

            if bottom_span is None:
                self._blit_scaled(
                    screen,
                    sprites.bottom_wall,
                    room.x - camera.x,
                    draw_y - camera.y,
                    room.width,
                    draw_h,
                    "b",
                )
            else:
                l, r = bottom_span
                self._blit_scaled(
                    screen,
                    sprites.bottom_wall,
                    room.x - camera.x,
                    draw_y - camera.y,
                    max(1, l - room.x),
                    draw_h,
                    "b",
                )
                self._blit_scaled(
                    screen,
                    sprites.bottom_wall,
                    r - camera.x,
                    draw_y - camera.y,
                    max(1, room.x + room.width - r),
                    draw_h,
                    "b",
                )
                self._blit_scaled(
                    screen,
                    sprites.bottom_door_opening,
                    l - camera.x,
                    draw_y - camera.y,
                    max(1, r - l),
                    bottom_visual_h,
                    "db",
                )

            if not left_is_full_open:
                self._blit_scaled(
                    screen,
                    sprites.bottom_left_corner,
                    room.x - camera.x,
                    draw_y - camera.y,
                    t,
                    draw_h,
                    "cbl",
                )
            if not right_is_full_open:
                self._blit_scaled(
                    screen,
                    sprites.bottom_right_corner,
                    right_x - camera.x,
                    draw_y - camera.y,
                    t,
                    draw_h,
                    "cbr",
                )

    def _draw_top_openings_foreground(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        wall_sprites: WallSpriteLibrary,
        objects: list[WorldObject],
        player_pos: tuple[float, float],
        player_frame: pygame.Surface,
        player_bob: float,
    ) -> bool:
        sprites = wall_sprites.sprites()
        player_x = player_pos[0]
        player_bottom = player_pos[1] + player_bob + player_frame.get_height() / 2
        # This overlay exists to hide the player under the lintel.
        # Clip to player area so movable objects (e.g. dragged plants) are not cut.
        player_w = player_frame.get_width()
        player_h = player_frame.get_height()
        player_rect_screen = pygame.Rect(
            int(player_pos[0] - camera.x - player_w / 2),
            int(player_pos[1] - camera.y + player_bob - player_h / 2),
            player_w,
            player_h,
        ).inflate(max(8, int(player_w * 0.16)), max(6, int(player_h * 0.10)))
        view_rect = pygame.Rect(0, 0, camera.width, camera.height)
        clip_rect = player_rect_screen.clip(view_rect)
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return False
        prev_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        drew_overlay = False
        for room in world.rooms:
            if not room.walls_enabled or not room.top_opening_layered:
                continue
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
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
            if top_span is None:
                continue
            l, r = top_span
            opening_door = self._door_for_top_opening(objects, room, l, r, top_t)
            if opening_door is not None:
                # Door object itself handles visual layering/occlusion for this opening.
                continue
            pass_l, pass_r = self._top_opening_pass_span(room, l, r)
            occlude_depth = (
                int(room.top_opening_occlude_depth)
                if room.top_opening_occlude_depth > 0
                else max(44, int(top_t * 0.22))
            )
            in_opening_x = pass_l <= player_x <= pass_r
            in_opening_y = room.y <= player_bottom <= (room.y + top_t + occlude_depth)
            if not (in_opening_x and in_opening_y):
                continue
            self._blit_scaled(
                screen,
                sprites.top_door_opening,
                l - camera.x,
                room.y - camera.y,
                max(1, r - l),
                top_t,
                "dt",
            )
            drew_overlay = True
        screen.set_clip(prev_clip)
        return drew_overlay

    def _door_for_top_opening(
        self,
        objects: list[WorldObject],
        room,
        opening_left: int,
        opening_right: int,
        top_wall_height: int,
    ) -> WorldObject | None:
        center_x = (opening_left + opening_right) / 2.0
        center_y = room.y + top_wall_height * 0.5
        best: tuple[float, WorldObject] | None = None
        for obj in objects:
            if obj.kind != "door":
                continue
            if obj.x < opening_left - 28 or obj.x > opening_right + 28:
                continue
            if obj.y < room.y - 32 or obj.y > room.y + top_wall_height + 56:
                continue
            d = abs(obj.x - center_x) + abs(obj.y - center_y)
            if best is None or d < best[0]:
                best = (d, obj)
        return best[1] if best else None

    def _top_opening_pass_span(self, room, opening_left: int, opening_right: int) -> tuple[int, int]:
        opening_w = max(1, opening_right - opening_left)
        pass_w = int(room.top_opening_pass_width) if room.top_opening_pass_width > 0 else int(opening_w * 0.62)
        pass_w = max(32, min(opening_w, pass_w))
        center = (opening_left + opening_right) // 2 + int(room.top_opening_pass_offset)
        left = max(opening_left, center - (pass_w // 2))
        right = min(opening_right, left + pass_w)
        left = max(opening_left, right - pass_w)
        return left, right

    def _has_direct_bottom_room_transition(
        self,
        world: WorldMap,
        room,
        bottom_span: tuple[int, int],
    ) -> bool:
        boundary_y = room.y + room.height
        open_l, open_r = bottom_span
        open_w = max(1, open_r - open_l)
        min_overlap = max(36, int(open_w * 0.45))

        for other in world.rooms:
            if other.room_id == room.room_id:
                continue
            if not other.walls_enabled:
                continue
            if abs(other.y - boundary_y) > 1:
                continue

            overlap_l = max(room.x, other.x)
            overlap_r = min(room.x + room.width, other.x + other.width)
            if overlap_r - overlap_l < min_overlap:
                continue

            t_other = max(1, min(other.wall_thickness, other.width // 3, other.height // 3))
            top_span_other = self._opening_span(
                start=other.x + t_other + 10,
                length=other.width - (t_other * 2) - 20,
                opening_width=other.top_door_width,
                opening_offset=other.top_door_offset,
            )
            if top_span_other is None:
                continue

            conn_l = max(open_l, top_span_other[0])
            conn_r = min(open_r, top_span_other[1])
            if conn_r - conn_l >= min_overlap:
                return True
        return False

    def _bottom_wall_visual_height(self, sprites, wall_thickness: int) -> int:
        out = wall_thickness
        for corner_sprite in (sprites.bottom_left_corner, sprites.bottom_right_corner):
            cw, ch = corner_sprite.get_size()
            if cw > 0 and ch > 0:
                out = max(out, int(round(ch * (wall_thickness / cw))))
        return out

    def _top_opening_floor_rect(self, room, top_wall_height: int) -> tuple[int, int]:
        floor_offset = max(0, int(room.top_opening_floor_offset))
        floor_y = room.y + floor_offset
        default_h = max(1, top_wall_height - floor_offset)
        floor_h = int(room.top_opening_floor_height) if room.top_opening_floor_height > 0 else default_h
        floor_h = max(1, floor_h)
        max_bottom = room.y + room.height
        if floor_y >= max_bottom:
            floor_y = room.y
        floor_h = min(floor_h, max(1, max_bottom - floor_y))
        return floor_y, floor_h

    def _seal_floor_wall_seams(
        self,
        screen: pygame.Surface,
        room,
        camera: Camera,
        wall_thickness: int,
        top_wall_height: int,
    ) -> None:
        # Cover dark 1-2px seams at wall/floor junctions using sampled floor color.
        seam = 2
        sx = int(room.x + room.width * 0.5 - camera.x)
        sy = int(room.y + min(room.height - wall_thickness - 2, top_wall_height + 8) - camera.y)
        if screen.get_width() <= 0 or screen.get_height() <= 0:
            return
        sx = max(0, min(screen.get_width() - 1, sx))
        sy = max(0, min(screen.get_height() - 1, sy))
        floor_color = screen.get_at((sx, sy))

        interior_y = int(room.y + top_wall_height - camera.y)
        interior_h = max(1, int(room.height - top_wall_height - wall_thickness))
        left_x = int(room.x + wall_thickness - camera.x - seam // 2)
        right_x = int(room.x + room.width - wall_thickness - camera.x - seam // 2)
        bottom_y = int(room.y + room.height - wall_thickness - camera.y - seam // 2)
        interior_x = int(room.x + wall_thickness - camera.x)
        interior_w = max(1, int(room.width - wall_thickness * 2))
        side_opening_full_len = max(1, room.height - (wall_thickness * 2) - 20)
        left_span = self._opening_span(
            start=room.y + wall_thickness + 10,
            length=room.height - (wall_thickness * 2) - 20,
            opening_width=room.left_opening_width,
            opening_offset=room.left_opening_offset,
        )
        right_span = self._opening_span(
            start=room.y + wall_thickness + 10,
            length=room.height - (wall_thickness * 2) - 20,
            opening_width=room.right_opening_width,
            opening_offset=room.right_opening_offset,
        )
        left_is_full_open = left_span is not None and (left_span[1] - left_span[0]) >= (side_opening_full_len - 1)
        right_is_full_open = right_span is not None and (right_span[1] - right_span[0]) >= (side_opening_full_len - 1)
        if not left_is_full_open:
            pygame.draw.rect(screen, floor_color, pygame.Rect(left_x, interior_y, seam, interior_h))
        if not right_is_full_open:
            pygame.draw.rect(screen, floor_color, pygame.Rect(right_x, interior_y, seam, interior_h))
        pygame.draw.rect(screen, floor_color, pygame.Rect(interior_x, bottom_y, interior_w, seam))

    def _blit_scaled(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: float,
        y: float,
        w: int,
        h: int,
        kind: str,
        *,
        flip_x: bool = False,
    ) -> None:
        target_w = max(1, int(w))
        target_h = max(1, int(h))

        # Preserve wall texture proportions and tile instead of non-uniform stretch.
        if kind in {"h", "hn", "b", "db", "dof"}:
            if kind in {"b", "db"}:
                self._blit_tiled_crop_top(
                    screen,
                    sprite,
                    int(x),
                    int(y),
                    target_w,
                    target_h,
                    kind=kind,
                    flip_x=flip_x,
                )
            else:
                self._blit_tiled_preserve_height(
                    screen,
                    sprite,
                    int(x),
                    int(y),
                    target_w,
                    target_h,
                    kind=kind,
                    flip_x=flip_x,
                )
            return
        if kind in {"v", "vn", "vr", "pt"}:
            self._blit_tiled_preserve_width(
                screen,
                sprite,
                int(x),
                int(y),
                target_w,
                target_h,
                kind=kind,
                flip_x=flip_x,
            )
            return
        if kind in {"vlt", "vrt"}:
            self._blit_cover_preserve_aspect(
                screen,
                sprite,
                int(x),
                int(y),
                target_w,
                target_h,
                kind=kind,
                flip_x=flip_x,
            )
            return
        if kind in {"cbl", "cbr"}:
            self._blit_crop_top_preserve_width(
                screen,
                sprite,
                int(x),
                int(y),
                target_w,
                target_h,
                kind=kind,
                flip_x=flip_x,
            )
            return
        if kind == "dt":
            self._blit_cover_preserve_aspect(
                screen,
                sprite,
                int(x),
                int(y),
                target_w,
                target_h,
                kind=kind,
                flip_x=flip_x,
            )
            return

        key = ("scale", kind, target_w, target_h, int(flip_x))
        scaled = self._wall_scale_cache.get(key)
        if scaled is None:
            scaled = pygame.transform.scale(sprite, (target_w, target_h))
            if flip_x:
                scaled = pygame.transform.flip(scaled, True, False)
            self._wall_scale_cache[key] = scaled
        screen.blit(scaled, (x, y))

    def _blit_tiled_preserve_height(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str,
        flip_x: bool,
    ) -> None:
        sw, sh = sprite.get_size()
        if sw <= 0 or sh <= 0:
            return
        tile_w = max(1, int(round(sw * (h / sh))))
        key = ("tile_x", kind, tile_w, h, int(flip_x))
        tile = self._wall_scale_cache.get(key)
        if tile is None:
            tile = pygame.transform.scale(sprite, (tile_w, h))
            if flip_x:
                tile = pygame.transform.flip(tile, True, False)
            self._wall_scale_cache[key] = tile
        for ox in range(0, w, tile_w):
            draw_w = min(tile_w, w - ox)
            screen.blit(tile, (x + ox, y), pygame.Rect(0, 0, draw_w, h))

    def _blit_tiled_crop_top(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str,
        flip_x: bool,
    ) -> None:
        sw, sh = sprite.get_size()
        if sw <= 0 or sh <= 0:
            return
        if sh <= h:
            self._blit_tiled_preserve_height(screen, sprite, x, y, w, h, kind=kind, flip_x=flip_x)
            return

        key = ("tile_crop_top", kind, sw, sh, int(flip_x))
        tile = self._wall_scale_cache.get(key)
        if tile is None:
            tile = pygame.transform.flip(sprite, True, False) if flip_x else sprite
            self._wall_scale_cache[key] = tile
        src_h = min(h, sh)
        for ox in range(0, w, sw):
            draw_w = min(sw, w - ox)
            screen.blit(tile, (x + ox, y), pygame.Rect(0, 0, draw_w, src_h))

    def _blit_tiled_preserve_width(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str,
        flip_x: bool,
    ) -> None:
        sw, sh = sprite.get_size()
        if sw <= 0 or sh <= 0:
            return
        tile_h = max(1, int(round(sh * (w / sw))))
        key = ("tile_y", kind, w, tile_h, int(flip_x))
        tile = self._wall_scale_cache.get(key)
        if tile is None:
            tile = pygame.transform.scale(sprite, (w, tile_h))
            if flip_x:
                tile = pygame.transform.flip(tile, True, False)
            self._wall_scale_cache[key] = tile
        for oy in range(0, h, tile_h):
            draw_h = min(tile_h, h - oy)
            screen.blit(tile, (x, y + oy), pygame.Rect(0, 0, w, draw_h))

    def _blit_crop_top_preserve_width(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str,
        flip_x: bool,
    ) -> None:
        sw, sh = sprite.get_size()
        if sw <= 0 or sh <= 0:
            return
        scale_w = max(1, int(w))
        scaled_h = max(1, int(round(sh * (scale_w / sw))))
        key = ("crop_top_width", kind, scale_w, scaled_h, int(flip_x))
        scaled = self._wall_scale_cache.get(key)
        if scaled is None:
            scaled = pygame.transform.scale(sprite, (scale_w, scaled_h))
            if flip_x:
                scaled = pygame.transform.flip(scaled, True, False)
            self._wall_scale_cache[key] = scaled
        if scaled_h <= h:
            self._blit_scaled(screen, scaled, x, y, w, h, kind=f"{kind}_fallback", flip_x=False)
            return
        screen.blit(scaled, (x, y), pygame.Rect(0, 0, w, h))

    def _blit_cover_preserve_aspect(
        self,
        screen: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str,
        flip_x: bool,
    ) -> None:
        sw, sh = sprite.get_size()
        if sw <= 0 or sh <= 0:
            return
        scale = max(w / sw, h / sh)
        scaled_w = max(1, int(round(sw * scale)))
        scaled_h = max(1, int(round(sh * scale)))
        key = ("cover", kind, w, h, scaled_w, scaled_h, int(flip_x))
        covered = self._wall_scale_cache.get(key)
        if covered is None:
            scaled = pygame.transform.scale(sprite, (scaled_w, scaled_h))
            if flip_x:
                scaled = pygame.transform.flip(scaled, True, False)
            src_x = max(0, (scaled_w - w) // 2)
            src_y = max(0, (scaled_h - h) // 2)
            covered = pygame.Surface((w, h), pygame.SRCALPHA)
            covered.blit(scaled, (0, 0), pygame.Rect(src_x, src_y, w, h))
            self._wall_scale_cache[key] = covered
        screen.blit(covered, (x, y))

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

    def _draw_objects_base_pass(
        self,
        screen: pygame.Surface,
        camera: Camera,
        objects: list[WorldObject],
        object_sprites: ObjectSpriteLibrary,
    ) -> list[tuple[pygame.Surface, float, float, int, bool]]:
        draw_list = sorted(objects, key=lambda obj: obj.y)
        occluders: list[tuple[pygame.Surface, float, float, int, bool]] = []
        for obj in draw_list:
            sprite = self._sprite_for_object(object_sprites, obj)
            occluder_sprite = sprite
            x = obj.x - sprite.get_width() / 2 - camera.x
            y = obj.y - sprite.get_height() / 2 - camera.y
            if obj.occlude_top and obj.occlude_split is not None:
                split_ratio = float(obj.occlude_split)
                if obj.kind == "plant":
                    # Keep foliage over the player for longer while crossing plant sprites.
                    split_ratio = min(0.92, split_ratio + 0.20)
                elif obj.kind == "door":
                    # Door textures are authored as full opaque rectangles.
                    # Clamp occlusion to a narrow top band so entering the opening
                    # hides the head under lintel without swallowing the whole character.
                    if obj.blocking or obj.state <= 0:
                        split_ratio = min(split_ratio, 0.56)
                    else:
                        split_ratio = min(split_ratio, 0.50)
                        if self._normalize_door_orientation(obj.door_orientation) == "top":
                            occluder_sprite = self._open_door_occluder_sprite(sprite)
                split_y = int(sprite.get_height() * split_ratio)
                split_y = max(1, min(sprite.get_height() - 1, split_y))
                # Draw full object in base pass; top overlay is applied conditionally in occluder pass.
                screen.blit(sprite, (x, y))
                occluders.append(
                    (
                        occluder_sprite,
                        x,
                        y,
                        split_y,
                        obj.kind == "door" and self._normalize_door_orientation(obj.door_orientation) == "top",
                    )
                )
            else:
                screen.blit(sprite, (x, y))
            self._draw_object_lock_marker(screen, obj, x, y, sprite)
        return occluders

    def _draw_objects_occluder_pass(
        self,
        screen: pygame.Surface,
        occluders: list[tuple[pygame.Surface, float, float, int, bool]],
        camera: Camera,
        player_pos: tuple[float, float],
        player_frame: pygame.Surface,
        player_bob: float,
    ) -> bool:
        player_bottom_screen = (
            player_pos[1]
            - camera.y
            + player_bob
            + player_frame.get_height() / 2
        )
        player_top_screen = (
            player_pos[1]
            - camera.y
            + player_bob
            - player_frame.get_height() / 2
        )
        # Engine-level stable rule for door lintels: evaluate occlusion almost by the
        # very top of the head so characters never visually "stand" on the lintel.
        player_head_screen = player_top_screen + max(2.0, player_frame.get_height() * 0.03)
        # Occluder pass should affect only the player body, not other world objects.
        player_rect_screen = pygame.Rect(
            int(player_pos[0] - camera.x - player_frame.get_width() / 2),
            int(player_pos[1] - camera.y + player_bob - player_frame.get_height() / 2),
            player_frame.get_width(),
            player_frame.get_height(),
        ).inflate(
            max(8, int(player_frame.get_width() * 0.16)),
            max(6, int(player_frame.get_height() * 0.10)),
        )
        view_rect = pygame.Rect(0, 0, camera.width, camera.height)
        clip_rect = player_rect_screen.clip(view_rect)
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return False
        prev_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        door_margin = -8.0
        drew_door_overlay = False
        for sprite, x, y, split_y, is_door in occluders:
            split_screen_y = y + split_y
            test_y = player_head_screen if is_door else player_bottom_screen
            # Only occlude when player is behind object split line.
            if test_y > (split_screen_y + (door_margin if is_door else 0.0)):
                continue
            upper_src = pygame.Rect(0, 0, sprite.get_width(), split_y)
            screen.blit(sprite, (x, y), upper_src)
            if is_door:
                drew_door_overlay = True
        screen.set_clip(prev_clip)
        return drew_door_overlay

    def _draw_wall_top_spray_occlusion_pass(
        self,
        *,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        spray_tags: list[SprayTag],
        object_sprites: ObjectSpriteLibrary,
        player_pos: tuple[float, float],
        player_frame: pygame.Surface,
        player_bob: float,
    ) -> None:
        if not spray_tags:
            return
        player_rect_screen = pygame.Rect(
            int(player_pos[0] - camera.x - player_frame.get_width() / 2),
            int(player_pos[1] - camera.y + player_bob - player_frame.get_height() / 2),
            player_frame.get_width(),
            player_frame.get_height(),
        ).inflate(
            max(8, int(player_frame.get_width() * 0.16)),
            max(6, int(player_frame.get_height() * 0.10)),
        )
        # Prevent graffiti from covering the whole character: allow restoration
        # only around the upper head/lintel contact area.
        head_h = max(8, int(player_rect_screen.height * 0.28))
        player_rect_screen = pygame.Rect(
            player_rect_screen.x,
            player_rect_screen.y,
            player_rect_screen.width,
            head_h,
        )
        view_rect = pygame.Rect(0, 0, camera.width, camera.height)
        clip_rect = player_rect_screen.clip(view_rect)
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return
        prev_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        self._draw_spray_tags(
            screen=screen,
            camera=camera,
            world=world,
            spray_tags=spray_tags,
            object_sprites=object_sprites,
            target_kind="wall_top",
        )
        screen.set_clip(prev_clip)

    def _draw_dragged_object_foreground(
        self,
        *,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        objects: list[WorldObject],
        object_sprites: ObjectSpriteLibrary,
        dragged_object_id: str | None,
        player_pos: tuple[float, float],
    ) -> None:
        if not dragged_object_id:
            return
        obj = next((o for o in objects if o.object_id == dragged_object_id), None)
        if obj is None or obj.kind == "door":
            return
        # Base pass already draws dragged objects with normal Y-sorting.
        # Foreground redraw is needed only when dragged object should be in front
        # of the player; otherwise it incorrectly covers the head.
        if obj.y <= player_pos[1] + 2:
            return
        sprite = self._sprite_for_object(object_sprites, obj)
        if self._dragged_object_hits_top_opening_lintel(obj, sprite, world):
            # Do not force dragged object to foreground while it crosses a top opening.
            # This prevents plants from visually climbing on doorway lintels.
            return
        x = obj.x - sprite.get_width() / 2 - camera.x
        y = obj.y - sprite.get_height() / 2 - camera.y
        screen.blit(sprite, (x, y))
        self._draw_object_lock_marker(screen, obj, x, y, sprite)

    def _dragged_object_hits_top_opening_lintel(
        self,
        obj: WorldObject,
        sprite: pygame.Surface,
        world: WorldMap,
    ) -> bool:
        obj_rect = pygame.Rect(
            int(obj.x - sprite.get_width() / 2),
            int(obj.y - sprite.get_height() / 2),
            int(sprite.get_width()),
            int(sprite.get_height()),
        )
        if obj_rect.width <= 0 or obj_rect.height <= 0:
            return False
        for room in world.rooms:
            if not room.walls_enabled:
                continue
            t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
            top_t = max(t, min(room.top_wall_height, room.height // 2)) if room.top_wall_height > 0 else t
            top_span = self._opening_span(
                start=room.x + t + 10,
                length=room.width - (t * 2) - 20,
                opening_width=room.top_door_width,
                opening_offset=room.top_door_offset,
            )
            if top_span is None:
                continue
            l, r = top_span
            lintel_rect = pygame.Rect(l, room.y, max(1, r - l), top_t)
            if obj_rect.colliderect(lintel_rect):
                return True
        return False

    def _draw_player(
        self,
        screen: pygame.Surface,
        camera: Camera,
        player_pos: tuple[float, float],
        player_frame: pygame.Surface,
        player_bob: float,
        player_left_facing: bool,
    ) -> None:
        sprite_w = player_frame.get_width()
        sprite_h = player_frame.get_height()
        player_x = player_pos[0] - sprite_w / 2
        player_y = player_pos[1] - sprite_h / 2

        stretch = 1.06 if player_left_facing else 0.92
        shadow_w = int(sprite_w * 0.42 * stretch)
        shadow_h = self._config.shadow.height
        shadow_y_offset = -6  # Move shadow closer to the character feet.
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, self._config.shadow.color, shadow.get_rect())

        # Anchor shadow to the visible sprite body, not full frame size:
        # some sheets have large transparent side padding.
        alpha_cutoff = max(1, self._config.sprite_sheet.alpha_component_cutoff)
        visible = player_frame.get_bounding_rect(min_alpha=alpha_cutoff)
        if visible.width <= 0 or visible.height <= 0:
            visible = player_frame.get_rect()
        shadow_anchor_x = player_x + visible.centerx
        shadow_anchor_y = player_y + visible.bottom

        screen.blit(
            shadow,
            (
                shadow_anchor_x - shadow_w // 2 - camera.x,
                shadow_anchor_y - shadow_h // 2 + shadow_y_offset - camera.y,
            ),
        )
        screen.blit(player_frame, (player_x - camera.x, player_y + player_bob - camera.y))

    def _draw_object_labels(
        self,
        screen: pygame.Surface,
        camera: Camera,
        objects: list[WorldObject],
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        for obj in objects:
            if not obj.label:
                continue
            sprite = self._sprite_for_object(object_sprites, obj)
            x = int(obj.x - camera.x)
            y = int(obj.y - sprite.get_height() / 2 - camera.y - 14)
            text = self._object_label_font.render(obj.label.upper(), True, (240, 227, 153))
            pad_x = 10
            pad_y = 4
            label_rect = pygame.Rect(
                x - (text.get_width() + pad_x * 2) // 2,
                y - text.get_height() - pad_y * 2,
                text.get_width() + pad_x * 2,
                text.get_height() + pad_y * 2,
            )
            pygame.draw.rect(screen, (16, 22, 28), label_rect, border_radius=4)
            pygame.draw.rect(screen, (180, 160, 86), label_rect, width=2, border_radius=4)
            screen.blit(text, (label_rect.x + pad_x, label_rect.y + pad_y))

    def _draw_inventory(
        self,
        screen: pygame.Surface,
        inventory: Inventory,
        object_sprites: ObjectSpriteLibrary,
    ) -> None:
        width, height = screen.get_size()
        slot_size = 56
        spacing = 10
        bar_width = inventory.capacity * slot_size + (inventory.capacity - 1) * spacing
        start_x = (width - bar_width) // 2
        y = height - slot_size - 20

        for i in range(inventory.capacity):
            x = start_x + i * (slot_size + spacing)
            rect = pygame.Rect(x, y, slot_size, slot_size)
            pygame.draw.rect(screen, (20, 24, 34), rect)
            border_color = (255, 208, 92) if i == inventory.active_index else (92, 98, 120)
            pygame.draw.rect(screen, border_color, rect, width=3)

            item = inventory.slots[i]
            if item is not None:
                icon = object_sprites.cached_icon_for_item(item)
                if icon is None:
                    continue
                ix = x + (slot_size - icon.get_width()) // 2
                iy = y + (slot_size - icon.get_height()) // 2
                screen.blit(icon, (ix, iy))

    def _draw_spray_tags(
        self,
        screen: pygame.Surface,
        camera: Camera,
        world: WorldMap,
        spray_tags: list[SprayTag],
        object_sprites: ObjectSpriteLibrary,
        target_kind: str,
    ) -> None:
        if not spray_tags:
            return
        for tag in spray_tags:
            if tag.target_kind != target_kind:
                continue
            sequence_paths = world.spray_profiles.get(tag.profile_id) or world.spray_profiles.get("default") or [
                "source/textures/items/ballon/spray_reveal_sheet.png"
            ]
            sequence = object_sprites.spray_reveal_sequence(sequence_paths)
            seq_idx = max(0, min(len(sequence) - 1, int(tag.sequence_index)))
            frames = sequence[seq_idx].variants
            if not frames:
                continue
            frame = frames[max(0, min(len(frames) - 1, int(tag.frame_index)))]
            draw_w = max(1, int(tag.width))
            draw_h = max(1, int(tag.height))
            scaled = self._scaled_spray_frame(frame, draw_w, draw_h)
            gx = int(tag.x - camera.x)
            gy = int(tag.y - camera.y)
            screen.blit(scaled, (gx, gy))

    def _scaled_spray_frame(
        self,
        frame: pygame.Surface,
        draw_w: int,
        draw_h: int,
    ) -> pygame.Surface:
        key = (id(frame), int(draw_w), int(draw_h))
        cached = self._spray_scale_cache.get(key)
        if cached is not None:
            return cached
        if frame.get_width() == draw_w and frame.get_height() == draw_h:
            scaled = frame
        else:
            # Graffiti sheets are high-detail art; smooth scaling keeps curves readable.
            scaled = pygame.transform.smoothscale(frame, (draw_w, draw_h))
        self._spray_scale_cache[key] = scaled
        return scaled

    def _draw_message(self, screen: pygame.Surface, message: str) -> None:
        label = self._font.render(message, True, (255, 240, 190))
        bg = pygame.Surface((label.get_width() + 16, label.get_height() + 10), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 150))
        screen.blit(bg, (16, 14))
        screen.blit(label, (24, 20))

    def _apply_fog(
        self,
        world_layer: pygame.Surface,
        world: WorldMap,
        center: tuple[float, float],
    ) -> pygame.Surface:
        fog = world.fog
        if not fog.enabled:
            return world_layer

        out = world_layer.copy()
        vision_multiplier = world.player_stats.vision_multiplier()
        near, mid, far, dark = fog.scaled_radii(vision_multiplier)
        cx = int(center[0])
        cy = int(center[1])

        medium_blur = self._blur_surface(world_layer, fog.medium_blur_scale)
        strong_blur = self._blur_surface(world_layer, fog.far_blur_scale)
        grayscale_far = self._grayscale_surface(strong_blur)
        transition = max(0, int(fog.transition))

        self._blit_square_band(out, medium_blur, (cx, cy), near, mid, transition)
        self._blit_square_band(out, strong_blur, (cx, cy), mid, dark, transition)
        self._blit_square_band(out, grayscale_far, (cx, cy), far, dark, transition)
        fog_overlay = self._build_fog_overlay(
            size=out.get_size(),
            center=(cx, cy),
            near=near,
            mid=mid,
            far=far,
            dark=dark,
            fog_color=fog.color,
            mid_alpha=fog.mid_dark_alpha,
            far_alpha=fog.far_dark_alpha,
            outer_alpha=fog.outer_dark_alpha,
            transition=transition,
        )
        out.blit(fog_overlay, (0, 0))
        return out

    def _blur_surface(self, source: pygame.Surface, scale: float) -> pygame.Surface:
        sw, sh = source.get_size()
        safe = max(0.05, min(scale, 1.0))
        down_w = max(1, int(sw * safe))
        down_h = max(1, int(sh * safe))
        reduced = pygame.transform.scale(source, (down_w, down_h))
        return pygame.transform.scale(reduced, (sw, sh))

    def _grayscale_surface(self, source: pygame.Surface) -> pygame.Surface:
        transform = getattr(pygame.transform, "grayscale", None)
        if callable(transform):
            return transform(source)

        # Fallback path for pygame builds without transform.grayscale:
        # blend towards neutral gray to emulate desaturation.
        gray = source.copy()
        tint = pygame.Surface(source.get_size(), pygame.SRCALPHA)
        tint.fill((128, 128, 128, 160))
        gray.blit(tint, (0, 0))
        return gray

    def _blit_square_band(
        self,
        target: pygame.Surface,
        layer: pygame.Surface,
        center: tuple[int, int],
        inner_radius: int,
        outer_radius: int,
        transition: int,
    ) -> None:
        if outer_radius <= inner_radius:
            return
        mask = self._square_band_mask(target.get_size(), center, inner_radius, outer_radius, transition)
        masked = layer.copy()
        masked.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(masked, (0, 0))

    def _build_fog_overlay(
        self,
        size: tuple[int, int],
        center: tuple[int, int],
        near: int,
        mid: int,
        far: int,
        dark: int,
        fog_color: tuple[int, int, int],
        mid_alpha: int,
        far_alpha: int,
        outer_alpha: int,
        transition: int,
    ) -> pygame.Surface:
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.fill((*fog_color, self._clamp_alpha(outer_alpha)))

        self._fill_square(surface=overlay, center=center, radius=dark, color=fog_color, alpha=far_alpha)
        self._fill_square(surface=overlay, center=center, radius=far, color=fog_color, alpha=mid_alpha)
        self._fill_square(surface=overlay, center=center, radius=near, color=fog_color, alpha=0)

        if transition > 0:
            overlay = self._soften_alpha_surface(overlay, transition)
            clear_core = max(8, near - transition // 3)
            self._fill_square(surface=overlay, center=center, radius=clear_core, color=fog_color, alpha=0)
        return overlay

    def _square_band_mask(
        self,
        size: tuple[int, int],
        center: tuple[int, int],
        inner_radius: int,
        outer_radius: int,
        transition: int,
    ) -> pygame.Surface:
        mask = pygame.Surface(size, pygame.SRCALPHA)
        outer_rect = self._square_rect(center, outer_radius, size)
        inner_rect = self._square_rect(center, inner_radius, size)
        pygame.draw.rect(mask, (255, 255, 255, 255), outer_rect)
        pygame.draw.rect(mask, (0, 0, 0, 0), inner_rect)
        if transition > 0:
            return self._soften_alpha_surface(mask, transition)
        return mask

    def _fill_square(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        color: tuple[int, int, int],
        alpha: int,
    ) -> None:
        rect = self._square_rect(center, radius, surface.get_size())
        if rect.width <= 0 or rect.height <= 0:
            return
        pygame.draw.rect(surface, (*color, self._clamp_alpha(alpha)), rect)

    def _square_rect(
        self,
        center: tuple[int, int],
        radius: int,
        bounds: tuple[int, int],
    ) -> pygame.Rect:
        x = center[0] - radius
        y = center[1] - radius
        size = max(2, radius * 2)
        rect = pygame.Rect(x, y, size, size)
        return rect.clip(pygame.Rect(0, 0, bounds[0], bounds[1]))

    def _soften_alpha_surface(self, source: pygame.Surface, transition: int) -> pygame.Surface:
        w, h = source.get_size()
        if w <= 0 or h <= 0:
            return source
        strength = max(2, min(120, transition))
        factor = max(0.16, 1.0 - (strength / 170.0))
        down_w = max(1, int(w * factor))
        down_h = max(1, int(h * factor))
        reduced = pygame.transform.scale(source, (down_w, down_h))
        return pygame.transform.scale(reduced, (w, h))

    def _clamp_alpha(self, value: int) -> int:
        return max(0, min(255, int(value)))

    def _sprite_for_object(self, object_sprites: ObjectSpriteLibrary, obj: WorldObject) -> pygame.Surface:
        base: pygame.Surface
        if obj.kind == "backpack":
            base = object_sprites.backpack_set().get(0)
        elif obj.kind == "sofa":
            base = object_sprites.sofa_set().get(obj.state)
        elif obj.kind == "plant":
            base = object_sprites.plant_set().get(obj.state)
        elif obj.kind == "ballon":
            base = object_sprites.ballon_sprite_for_object(obj)
        elif obj.kind == "key":
            base = object_sprites.key_set().get(obj.state)
        elif obj.kind == "door":
            base = object_sprites.door_set(obj.door_orientation).get(obj.state)
        else:
            raise KeyError(f"Unknown world object kind: {obj.kind}")

        tint = obj.tint_rgb
        strength = max(0.0, min(1.0, float(obj.tint_strength)))
        if tint is None or strength <= 0.001:
            return base
        return self._tinted_object_sprite(base, obj.kind, obj.state, tint, strength)

    def _draw_object_lock_marker(
        self,
        screen: pygame.Surface,
        obj: WorldObject,
        x: float,
        y: float,
        sprite: pygame.Surface,
    ) -> None:
        # Door lock marker (colored circle + letter) is disabled by request.
        return

    def _resolve_lock_marker_text(self, obj: WorldObject) -> str | None:
        if obj.lock_marker_text:
            return obj.lock_marker_text
        key_id = self._first_required_key_id(obj)
        if not key_id:
            return None
        short = key_id.strip().upper()
        if "_" in short:
            parts = [p for p in short.split("_") if p]
            if parts:
                short = parts[-1]
        return short[:2]

    def _resolve_lock_marker_color(self, obj: WorldObject) -> tuple[int, int, int] | None:
        if obj.lock_marker_rgb is not None:
            return obj.lock_marker_rgb
        key_id = self._first_required_key_id(obj)
        if not key_id:
            return None
        return self._key_color_from_item_id(key_id)

    def _first_required_key_id(self, obj: WorldObject) -> str | None:
        if obj.lock_key_sets:
            for key_set in obj.lock_key_sets:
                if key_set:
                    return str(key_set[0])
        if obj.required_item_id:
            return str(obj.required_item_id)
        return None

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
        return (220, 64, 62)

    def _normalize_door_orientation(self, value: str | None) -> str:
        token = str(value).strip().lower() if value is not None else "top"
        if token in {"top", "left", "right", "bottom"}:
            return token
        return "top"

    def _open_door_occluder_sprite(self, sprite: pygame.Surface) -> pygame.Surface:
        key = ("door_open_occ", id(sprite), sprite.get_width(), sprite.get_height())
        cached = self._door_open_occluder_cache.get(key)
        if cached is not None:
            return cached

        out = sprite.copy()
        w, h = out.get_size()
        # Normalized doorway aperture in the authored 296x316 open-door layout.
        # Keep lintel + posts + leaf in base draw, but clear aperture for occluder
        # so entering the opening does not hide the whole character.
        aperture_top = max(1, int(h * 0.30))
        aperture_right = min(w - 1, int(w * 0.84))
        aperture_bottom = max(aperture_top + 1, int(h * 0.985))
        clear_h = max(1, aperture_bottom - aperture_top)
        # Slanted left edge follows opened leaf perspective and removes the
        # residual floor strip that can appear near character head.
        for row in range(clear_h):
            t = row / max(1, clear_h - 1)
            dyn_left = int(w * (0.36 + 0.20 * t))
            dyn_left = max(1, min(aperture_right - 1, dyn_left))
            clear_w = max(1, aperture_right - dyn_left)
            out.fill((0, 0, 0, 0), pygame.Rect(dyn_left, aperture_top + row, clear_w, 1))

        self._door_open_occluder_cache[key] = out
        return out

    def _tinted_object_sprite(
        self,
        base: pygame.Surface,
        kind: str,
        state: int,
        tint_rgb: tuple[int, int, int],
        strength: float,
    ) -> pygame.Surface:
        sr = round(strength, 3)
        key = (
            "obj_tint",
            id(base),
            kind,
            int(state),
            int(tint_rgb[0]),
            int(tint_rgb[1]),
            int(tint_rgb[2]),
            sr,
            base.get_width(),
            base.get_height(),
        )
        cached = self._object_tint_cache.get(key)
        if cached is not None:
            return cached

        out = base.copy()
        target = pygame.Color(int(tint_rgb[0]), int(tint_rgb[1]), int(tint_rgb[2]), 255)
        target_h, target_s, _target_v, _ = target.hsva
        w, h = out.get_size()
        for y in range(h):
            for x in range(w):
                src = out.get_at((x, y))
                if src.a <= 0:
                    continue
                if src.r == src.g == src.b:
                    continue
                src_color = pygame.Color(src.r, src.g, src.b, src.a)
                h0, s0, v0, _a0 = src_color.hsva
                if s0 < 8.0:
                    continue
                recolor = pygame.Color(src.r, src.g, src.b, src.a)
                # Keep value (brightness) from source for shading, but force target hue.
                new_s = s0 + (max(float(target_s), s0) - s0) * sr
                # pygame Color.hsva expects H in [0, 360), S/V/A in [0, 100].
                hue = max(0.0, min(359.999, float(target_h)))
                sat = max(0.0, min(100.0, float(new_s)))
                val = max(0.0, min(100.0, float(v0)))
                alpha = max(0.0, min(100.0, float(_a0)))
                recolor.hsva = (hue, sat, val, alpha)
                nr = int(src.r + (recolor.r - src.r) * sr)
                ng = int(src.g + (recolor.g - src.g) * sr)
                nb = int(src.b + (recolor.b - src.b) * sr)
                out.set_at((x, y), pygame.Color(nr, ng, nb, src.a))

        self._object_tint_cache[key] = out
        return out
