from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame


@dataclass(frozen=True)
class WallSpriteSet:
    horizontal_wall: pygame.Surface
    vertical_wall: pygame.Surface
    right_vertical_wall: pygame.Surface
    left_top_wall: pygame.Surface
    right_top_wall: pygame.Surface
    bottom_wall: pygame.Surface
    bottom_left_corner: pygame.Surface
    bottom_right_corner: pygame.Surface
    bottom_left_down_transition: pygame.Surface
    bottom_right_down_transition: pygame.Surface
    top_door_opening: pygame.Surface
    top_door_floor: pygame.Surface
    vertical_door_opening: pygame.Surface
    bottom_door_opening: pygame.Surface
    horizontal_door_closed: pygame.Surface
    horizontal_door_open: pygame.Surface


class WallSpriteLibrary:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._cache: WallSpriteSet | None = None

    def sprites(self) -> WallSpriteSet:
        if self._cache is not None:
            return self._cache

        style_dir = self._project_root / "source/textures/walls"
        top_opening_frame = style_dir / "top_opening_frame.png"
        top_opening_fallback = style_dir / "top_opening.png"
        named_assets = {
            "horizontal_wall": style_dir / "top_wall.png",
            "vertical_wall": style_dir / "side_wall.png",
            "right_vertical_wall": style_dir / "right_wall.png",
            "left_top_wall": style_dir / "left_top_wall.png",
            "right_top_wall": style_dir / "right_top_wall.png",
            "bottom_wall": style_dir / "bottom_wall.png",
            "bottom_left_corner": style_dir / "bottom_left_corner.png",
            "bottom_right_corner": style_dir / "bottom_right_corner.png",
            "bottom_left_down_transition": style_dir / "bottom_left_down_transition.png",
            "bottom_right_down_transition": style_dir / "bottom_right_down_transition.png",
            "top_door_opening": top_opening_frame if top_opening_frame.exists() else top_opening_fallback,
            "top_door_floor": style_dir / "top_opening_floor.png",
            "vertical_door_opening": style_dir / "side_opening.png",
            "bottom_door_opening": style_dir / "bottom_opening.png",
            "horizontal_door_closed": style_dir / "door_closed.png",
            "horizontal_door_open": style_dir / "door_open.png",
        }
        required_keys = (
            "horizontal_wall",
            "vertical_wall",
            "bottom_wall",
            "top_door_opening",
        )
        if all(named_assets[k].exists() for k in required_keys):
            top_door_floor_path = named_assets["top_door_floor"]
            top_door_floor_sprite = (
                self._soften_near_black(self._load_sprite(top_door_floor_path))
                if top_door_floor_path.exists()
                else self._soften_near_black(self._load_sprite(named_assets["horizontal_wall"]))
            )
            vertical_door_opening_path = named_assets["vertical_door_opening"]
            vertical_door_opening_sprite = (
                self._soften_near_black(self._load_sprite(vertical_door_opening_path))
                if vertical_door_opening_path.exists()
                else self._soften_near_black(self._load_sprite(named_assets["vertical_wall"]))
            )
            bottom_door_opening_path = named_assets["bottom_door_opening"]
            bottom_door_opening_sprite = (
                self._soften_near_black(self._load_sprite(bottom_door_opening_path))
                if bottom_door_opening_path.exists()
                else self._soften_near_black(self._load_sprite(named_assets["bottom_wall"]))
            )
            horizontal_door_closed_path = named_assets["horizontal_door_closed"]
            horizontal_door_open_path = named_assets["horizontal_door_open"]
            right_path = named_assets["right_vertical_wall"]
            right_sprite = (
                self._soften_near_black(self._load_sprite(right_path))
                if right_path.exists()
                else pygame.transform.flip(
                    self._soften_near_black(self._load_sprite(named_assets["vertical_wall"])),
                    True,
                    False,
                )
            )
            left_top_path = named_assets["left_top_wall"]
            left_top_sprite = (
                self._soften_near_black(self._load_sprite(left_top_path))
                if left_top_path.exists()
                else self._soften_near_black(self._load_sprite(named_assets["vertical_wall"]))
            )
            right_top_path = named_assets["right_top_wall"]
            right_top_sprite = (
                self._soften_near_black(self._load_sprite(right_top_path))
                if right_top_path.exists()
                else pygame.transform.flip(left_top_sprite, True, False)
            )
            bottom_left_path = named_assets["bottom_left_corner"]
            bottom_left_corner = (
                self._soften_near_black(self._load_sprite(bottom_left_path))
                if bottom_left_path.exists()
                else None
            )
            if bottom_left_corner is None:
                side = self._soften_near_black(self._load_sprite(named_assets["vertical_wall"]))
                bottom = self._soften_near_black(self._load_sprite(named_assets["bottom_wall"]))
                t = min(side.get_width(), bottom.get_height())
                bottom_left_corner = pygame.Surface((t, t), pygame.SRCALPHA)
                bottom_left_corner.blit(
                    pygame.transform.scale(side, (t, t)),
                    (0, 0),
                )
                bottom_left_corner.blit(
                    pygame.transform.scale(bottom, (t, t)),
                    (0, 0),
                    special_flags=pygame.BLEND_RGBA_MAX,
                )
            bottom_right_path = named_assets["bottom_right_corner"]
            bottom_right_corner = (
                self._soften_near_black(self._load_sprite(bottom_right_path))
                if bottom_right_path.exists()
                else pygame.transform.flip(bottom_left_corner, True, False)
            )
            bottom_left_down_path = named_assets["bottom_left_down_transition"]
            bottom_left_down_transition = (
                self._soften_near_black(self._load_sprite(bottom_left_down_path))
                if bottom_left_down_path.exists()
                else self._soften_near_black(self._load_sprite(named_assets["vertical_wall"]))
            )
            bottom_right_down_path = named_assets["bottom_right_down_transition"]
            bottom_right_down_transition = (
                self._soften_near_black(self._load_sprite(bottom_right_down_path))
                if bottom_right_down_path.exists()
                else pygame.transform.flip(bottom_left_down_transition, True, False)
            )
            result = WallSpriteSet(
                horizontal_wall=self._soften_near_black(self._load_sprite(named_assets["horizontal_wall"])),
                vertical_wall=self._soften_near_black(self._load_sprite(named_assets["vertical_wall"])),
                right_vertical_wall=right_sprite,
                left_top_wall=left_top_sprite,
                right_top_wall=right_top_sprite,
                bottom_wall=self._soften_near_black(self._load_sprite(named_assets["bottom_wall"])),
                bottom_left_corner=bottom_left_corner,
                bottom_right_corner=bottom_right_corner,
                bottom_left_down_transition=bottom_left_down_transition,
                bottom_right_down_transition=bottom_right_down_transition,
                top_door_opening=self._soften_near_black(self._load_sprite(named_assets["top_door_opening"])),
                top_door_floor=top_door_floor_sprite,
                vertical_door_opening=vertical_door_opening_sprite,
                bottom_door_opening=bottom_door_opening_sprite,
                horizontal_door_closed=(
                    self._load_sprite(horizontal_door_closed_path)
                    if horizontal_door_closed_path.exists()
                    else self._load_sprite(named_assets["top_door_opening"])
                ),
                horizontal_door_open=(
                    self._load_sprite(horizontal_door_open_path)
                    if horizontal_door_open_path.exists()
                    else self._load_sprite(named_assets["top_door_opening"])
                ),
            )
            self._cache = result
            return result

        sheet = pygame.image.load(
            str(self._project_root / "source/textures/walls/walls_sheet.png")
        ).convert_alpha()
        components = self._extract_components(sheet, alpha_cutoff=22, min_area=1600)
        rows = self._cluster_rows(components, tolerance=54)

        horizontal_rect: pygame.Rect | None = None
        vertical_rect: pygame.Rect | None = None
        door_rect: pygame.Rect | None = None

        if rows and len(rows[0]) >= 2:
            row0 = sorted(rows[0], key=lambda r: r.centerx)
            horizontal_rect = row0[0]
            vertical_rect = row0[1]

        horizontal_door_closed_rect: pygame.Rect | None = None
        horizontal_door_open_rect: pygame.Rect | None = None
        vertical_door_opening_rect: pygame.Rect | None = None
        if len(rows) >= 4 and rows[3]:
            row3 = sorted(rows[3], key=lambda r: r.centerx)
            door_rect = row3[0]
            if len(row3) >= 4:
                horizontal_door_closed_rect = row3[1]
                horizontal_door_open_rect = row3[2]
                vertical_door_opening_rect = row3[3]

        if horizontal_rect is None:
            horizontal_rect = max(components, key=lambda r: r.width)
        if vertical_rect is None:
            vertical_rect = max(components, key=lambda r: r.height)
        if door_rect is None:
            door_rect = horizontal_rect
        if horizontal_door_closed_rect is None:
            horizontal_door_closed_rect = door_rect
        if horizontal_door_open_rect is None:
            horizontal_door_open_rect = door_rect
        if vertical_door_opening_rect is None:
            vertical_door_opening_rect = vertical_rect

        result = WallSpriteSet(
            horizontal_wall=self._soften_near_black(self._extract(sheet, horizontal_rect)),
            vertical_wall=self._soften_near_black(self._extract(sheet, vertical_rect)),
            right_vertical_wall=self._soften_near_black(
                pygame.transform.flip(self._extract(sheet, vertical_rect), True, False)
            ),
            left_top_wall=self._soften_near_black(self._extract(sheet, vertical_rect)),
            right_top_wall=self._soften_near_black(
                pygame.transform.flip(self._extract(sheet, vertical_rect), True, False)
            ),
            bottom_wall=self._soften_near_black(self._extract(sheet, horizontal_rect)),
            bottom_left_corner=self._soften_near_black(self._extract(sheet, vertical_rect)),
            bottom_right_corner=self._soften_near_black(
                pygame.transform.flip(self._extract(sheet, vertical_rect), True, False)
            ),
            bottom_left_down_transition=self._soften_near_black(self._extract(sheet, vertical_rect)),
            bottom_right_down_transition=self._soften_near_black(
                pygame.transform.flip(self._extract(sheet, vertical_rect), True, False)
            ),
            top_door_opening=self._soften_near_black(self._extract(sheet, door_rect)),
            top_door_floor=self._soften_near_black(self._extract(sheet, horizontal_rect)),
            vertical_door_opening=self._soften_near_black(self._extract(sheet, vertical_door_opening_rect)),
            bottom_door_opening=self._soften_near_black(self._extract(sheet, horizontal_rect)),
            horizontal_door_closed=self._extract(sheet, horizontal_door_closed_rect),
            horizontal_door_open=self._extract(sheet, horizontal_door_open_rect),
        )
        self._cache = result
        return result

    def _load_sprite(self, path: Path) -> pygame.Surface:
        return pygame.image.load(str(path)).convert_alpha()

    def _soften_near_black(self, sprite: pygame.Surface) -> pygame.Surface:
        # Replace hard black seam pixels with an average of their non-black neighbours.
        out = sprite.copy()
        rgb = pygame.surfarray.array3d(out).astype(np.float32)   # (w, h, 3)
        alpha = pygame.surfarray.array_alpha(out)                  # (w, h)

        near_black = (
            (alpha >= 220)
            & (rgb[:, :, 0] < 26)
            & (rgb[:, :, 1] < 26)
            & (rgb[:, :, 2] < 26)
        )

        if not np.any(near_black):
            return out

        eligible = (alpha >= 220) & ~near_black  # non-black opaque neighbours
        w_s, h_s = rgb.shape[:2]

        rgb_sum = np.zeros_like(rgb)
        count = np.zeros((w_s, h_s), dtype=np.float32)

        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sx = slice(max(0, -dx), w_s + min(0, -dx) or None)
            sy = slice(max(0, -dy), h_s + min(0, -dy) or None)
            tx = slice(max(0, dx), w_s + min(0, dx) or None)
            ty = slice(max(0, dy), h_s + min(0, dy) or None)
            mask = eligible[sx, sy].astype(np.float32)
            count[tx, ty] += mask
            for c in range(3):
                rgb_sum[:, :, c][tx, ty] += rgb[:, :, c][sx, sy] * mask

        has_eligible = count > 0
        result = rgb.copy()
        for c in range(3):
            fallback = np.array([52.0, 32.0, 20.0])[c]
            avg = np.where(has_eligible, rgb_sum[:, :, c] / np.maximum(count, 1.0), fallback)
            result[:, :, c] = np.where(near_black, avg, rgb[:, :, c])

        out_px = pygame.surfarray.pixels3d(out)
        out_px[:] = result.astype(np.uint8)
        del out_px
        return out

    def _extract(self, sheet: pygame.Surface, rect: pygame.Rect) -> pygame.Surface:
        sprite = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        sprite.blit(sheet, (0, 0), rect)
        return sprite

    def _cluster_rows(self, rects: list[pygame.Rect], tolerance: int) -> list[list[pygame.Rect]]:
        rows: list[list[pygame.Rect]] = []
        for rect in sorted(rects, key=lambda r: r.centery):
            placed = False
            for row in rows:
                mean_y = sum(r.centery for r in row) / len(row)
                if abs(rect.centery - mean_y) <= tolerance:
                    row.append(rect)
                    placed = True
                    break
            if not placed:
                rows.append([rect])
        return rows

    def _extract_components(
        self,
        surface: pygame.Surface,
        alpha_cutoff: int,
        min_area: int,
    ) -> list[pygame.Rect]:
        w, h = surface.get_size()
        visited = bytearray(w * h)
        components: list[pygame.Rect] = []

        def idx(x: int, y: int) -> int:
            return y * w + x

        for y0 in range(h):
            for x0 in range(w):
                i0 = idx(x0, y0)
                if visited[i0]:
                    continue
                visited[i0] = 1
                if surface.get_at((x0, y0)).a < alpha_cutoff:
                    continue

                q: deque[tuple[int, int]] = deque([(x0, y0)])
                min_x = max_x = x0
                min_y = max_y = y0
                area = 0
                while q:
                    x, y = q.popleft()
                    area += 1
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if nx < 0 or ny < 0 or nx >= w or ny >= h:
                            continue
                        ii = idx(nx, ny)
                        if visited[ii]:
                            continue
                        visited[ii] = 1
                        if surface.get_at((nx, ny)).a >= alpha_cutoff:
                            q.append((nx, ny))

                if area >= min_area:
                    components.append(
                        pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
                    )

        if not components:
            raise ValueError("Walls sheet parsing failed: no components detected")
        return components
