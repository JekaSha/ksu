from __future__ import annotations

from collections import deque
from pathlib import Path

import pygame

from ksusha_game.infrastructure.map_loader import FloorAtlasConfig


class FloorTileset:
    def __init__(self, atlas_cfg: FloorAtlasConfig, project_root: Path) -> None:
        atlas = pygame.image.load(str(project_root / atlas_cfg.atlas_path)).convert_alpha()
        self._tiles: dict[str, pygame.Surface] = {}
        grid = self._build_grid(atlas, atlas_cfg.rows, atlas_cfg.columns)

        for texture_key, (row, col) in atlas_cfg.textures.items():
            src = grid[row][col]
            if src is None:
                raise ValueError(f"Floor tile not found for key={texture_key} at ({row},{col})")
            tile = pygame.Surface((src.width, src.height), pygame.SRCALPHA)
            tile.blit(atlas, (0, 0), src)
            self._tiles[texture_key] = tile

    def get(self, texture_key: str) -> pygame.Surface:
        return self._tiles[texture_key]

    def _extract_components(self, atlas: pygame.Surface, alpha_cutoff: int) -> list[pygame.Rect]:
        w, h = atlas.get_size()
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
                if atlas.get_at((x0, y0)).a < alpha_cutoff:
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
                        if atlas.get_at((nx, ny)).a >= alpha_cutoff:
                            q.append((nx, ny))

                if area >= 800:
                    components.append(
                        pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
                    )

        return components

    def _components_to_grid(
        self,
        components: list[pygame.Rect],
        atlas_w: int,
        atlas_h: int,
        rows: int,
        cols: int,
    ) -> list[list[pygame.Rect | None]]:
        grid: list[list[pygame.Rect | None]] = [[None for _ in range(cols)] for _ in range(rows)]
        area_grid: list[list[int]] = [[-1 for _ in range(cols)] for _ in range(rows)]

        for rect in components:
            cx = rect.centerx
            cy = rect.centery
            row = min(rows - 1, max(0, int(cy * rows / atlas_h)))
            col = min(cols - 1, max(0, int(cx * cols / atlas_w)))
            area = rect.width * rect.height
            if area > area_grid[row][col]:
                area_grid[row][col] = area
                grid[row][col] = rect

        return grid

    def _build_grid(
        self,
        atlas: pygame.Surface,
        rows: int,
        cols: int,
    ) -> list[list[pygame.Rect | None]]:
        # First try strict grid slicing. This works for dense atlases with no transparent gaps.
        cell_w = atlas.get_width() // cols
        cell_h = atlas.get_height() // rows
        if cell_w > 0 and cell_h > 0:
            grid: list[list[pygame.Rect | None]] = [[None for _ in range(cols)] for _ in range(rows)]
            found_dense_cells = 0
            for row in range(rows):
                for col in range(cols):
                    cell = pygame.Rect(col * cell_w, row * cell_h, cell_w, cell_h)
                    sub = atlas.subsurface(cell)
                    bounds = sub.get_bounding_rect(min_alpha=20)
                    if bounds.width <= 0 or bounds.height <= 0:
                        continue
                    grid[row][col] = pygame.Rect(
                        cell.x + bounds.x,
                        cell.y + bounds.y,
                        bounds.width,
                        bounds.height,
                    )
                    found_dense_cells += 1
            if found_dense_cells > 0:
                return grid

        # Fallback for older atlases where tiles are separated as alpha components.
        components = self._extract_components(atlas, alpha_cutoff=20)
        return self._components_to_grid(
            components=components,
            atlas_w=atlas.get_width(),
            atlas_h=atlas.get_height(),
            rows=rows,
            cols=cols,
        )
