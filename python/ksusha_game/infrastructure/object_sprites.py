from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np
import pygame

from ksusha_game.domain.world import BalloonObject, BalloonSpec, WorldObject
from ksusha_game.infrastructure.asset_cache import SpriteCache


@dataclass(frozen=True)
class ObjectSpriteSet:
    variants: list[pygame.Surface]

    def get(self, index: int) -> pygame.Surface:
        return self.variants[index % len(self.variants)]


class ObjectSpriteLibrary:
    def __init__(
        self,
        project_root: Path,
        *,
        balloon_specs: dict[str, BalloonSpec] | None = None,
        balloon_item_ids: dict[str, str] | None = None,
        disk_cache: SpriteCache | None = None,
    ) -> None:
        self._project_root = project_root
        self._cache: dict[str, ObjectSpriteSet] = {}
        self._icon_cache: dict[str, pygame.Surface] = {}
        self._balloon_specs = dict(balloon_specs or {})
        self._balloon_item_ids = dict(balloon_item_ids or {})
        self._disk_cache = disk_cache
        self._kind_size_cache: dict[str, tuple[int, int] | None] = {}

    # ------------------------------------------------------------------ #
    #  Sprite set accessors                                                #
    # ------------------------------------------------------------------ #

    def backpack_set(self) -> ObjectSpriteSet:
        key = "backpack"
        if key in self._cache:
            return self._cache[key]
        sheet_path = self._project_root / "source/textures/items/backpack/backpack_sheet.png"
        if self._disk_cache is not None:
            cached = self._disk_cache.load_sprite_set(sheet_path, key)
            if cached is not None:
                result = ObjectSpriteSet(variants=cached)
                self._cache[key] = result
                return result
        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        target_size = self._load_kind_world_size("backpack") or (84, 84)
        variants = self._extract_top_row_variants(sheet, variant_count=4, target_size=target_size, min_area=1200)
        if self._disk_cache is not None:
            self._disk_cache.save_sprite_set(sheet_path, key, variants)
        result = ObjectSpriteSet(variants=variants)
        self._cache[key] = result
        return result

    def sofa_set(self) -> ObjectSpriteSet:
        key = "sofa"
        if key in self._cache:
            return self._cache[key]
        sheet_path = self._project_root / "source/textures/items/sofa/sofa_sheet.png"
        if self._disk_cache is not None:
            cached = self._disk_cache.load_sprite_set(sheet_path, key)
            if cached is not None:
                result = ObjectSpriteSet(variants=cached)
                self._cache[key] = result
                return result
        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        target_size = self._load_kind_world_size("sofa") or (200, 200)
        variants = self._extract_all_variants(sheet, target_size=target_size, min_area=2000)
        if not variants:
            raise ValueError("Sofa sheet parsing failed: no components detected")
        if self._disk_cache is not None:
            self._disk_cache.save_sprite_set(sheet_path, key, variants)
        result = ObjectSpriteSet(variants=variants)
        self._cache[key] = result
        return result

    def plant_set(self) -> ObjectSpriteSet:
        key = "plant"
        if key in self._cache:
            return self._cache[key]
        sheet_path = self._project_root / "source/textures/items/plants/plants_sheet.png"
        if self._disk_cache is not None:
            cached = self._disk_cache.load_sprite_set(sheet_path, key)
            if cached is not None:
                result = ObjectSpriteSet(variants=cached)
                self._cache[key] = result
                return result
        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        target_size = self._load_kind_world_size("plant") or (180, 218)
        variants = self._extract_all_variants(sheet, target_size=target_size, min_area=900)
        if not variants:
            raise ValueError("Plant sheet parsing failed: no components detected")
        if self._disk_cache is not None:
            self._disk_cache.save_sprite_set(sheet_path, key, variants)
        result = ObjectSpriteSet(variants=variants)
        self._cache[key] = result
        return result

    def key_set(self) -> ObjectSpriteSet:
        key = "key"
        if key in self._cache:
            return self._cache[key]
        sheet_path = self._project_root / "source/textures/items/keys/keys_sheet.png"
        if self._disk_cache is not None:
            cached = self._disk_cache.load_sprite_set(sheet_path, key)
            if cached is not None:
                result = ObjectSpriteSet(variants=cached)
                self._cache[key] = result
                return result
        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        target_size = self._load_kind_world_size("key") or (58, 42)
        variants = self._extract_all_variants(sheet, target_size=target_size, min_area=240)
        if not variants:
            raise ValueError("Key sheet parsing failed: no components detected")
        if self._disk_cache is not None:
            self._disk_cache.save_sprite_set(sheet_path, key, variants)
        result = ObjectSpriteSet(variants=variants)
        self._cache[key] = result
        return result

    def ballon_set(self) -> ObjectSpriteSet:
        key = "ballon"
        if key in self._cache:
            return self._cache[key]

        specs = self._resolved_balloon_specs()
        ordered_ids = self._ordered_balloon_ids(specs)
        variants: list[pygame.Surface] = []
        for balloon_id in ordered_ids:
            spec = specs.get(balloon_id)
            if spec is None:
                continue
            sprite = self._load_single_sprite_with_chroma(
                path=self._resolve_path(spec.sprite_path),
                target_size=spec.world_size,
                green_delta=spec.chroma_green_delta,
                green_min=spec.chroma_green_min,
            )
            variants.append(sprite)

        if not variants:
            legacy = self._project_root / "source/textures/items/ballon/ballon.png"
            variants = [
                self._load_single_sprite_with_chroma(
                    path=legacy,
                    target_size=(78, 110),
                    green_delta=34,
                    green_min=92,
                )
            ]
        result = ObjectSpriteSet(variants=variants)
        self._cache[key] = result
        return result

    def ballon_sprite_for_item(self, item_id: str | None) -> pygame.Surface:
        specs = self._resolved_balloon_specs()
        balloon_id = self._balloon_id_for_item_id(item_id, specs)
        spec = specs.get(balloon_id) if balloon_id else None
        if spec is None:
            return self.ballon_set().get(0)
        key = f"ballon_id:{spec.balloon_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached.get(0)
        sprite = self._load_single_sprite_with_chroma(
            path=self._resolve_path(spec.sprite_path),
            target_size=spec.world_size,
            green_delta=spec.chroma_green_delta,
            green_min=spec.chroma_green_min,
        )
        self._cache[key] = ObjectSpriteSet(variants=[sprite])
        return sprite

    def ballon_sprite_for_object(self, obj: WorldObject) -> pygame.Surface:
        balloon_id = ""
        if isinstance(obj, BalloonObject) and obj.balloon_id:
            balloon_id = str(obj.balloon_id).strip()
        if balloon_id:
            specs = self._resolved_balloon_specs()
            spec = specs.get(balloon_id)
            if spec is not None:
                return self.ballon_sprite_for_item(spec.item_id)
        return self.ballon_sprite_for_item(obj.pickup_item_id)

    def spray_reveal_set(self) -> ObjectSpriteSet:
        default_rel = "source/textures/items/ballon/spray_reveal_sheet.png"
        return self._spray_reveal_set_by_path(default_rel)

    def spray_reveal_sequence(self, sheet_paths: list[str]) -> list[ObjectSpriteSet]:
        if not sheet_paths:
            return [self.spray_reveal_set()]
        out: list[ObjectSpriteSet] = []
        for path in sheet_paths:
            token = str(path).strip()
            if not token:
                continue
            out.append(self._spray_reveal_set_by_path(token))
        return out if out else [self.spray_reveal_set()]

    def _spray_reveal_set_by_path(self, sheet_path: str) -> ObjectSpriteSet:
        p = Path(sheet_path)
        abs_path = p if p.is_absolute() else self._project_root / p
        mtime_ns = 0
        try:
            if abs_path.exists():
                mtime_ns = int(abs_path.stat().st_mtime_ns)
        except OSError:
            mtime_ns = 0

        key = f"spray_reveal:{abs_path}:{mtime_ns}"
        if key in self._cache:
            return self._cache[key]

        cache_path: Path | None = None
        if self._disk_cache is not None:
            cache_path = abs_path
            if cache_path.exists():
                cached = self._disk_cache.load_sprite_set(cache_path, "spray_reveal")
                if cached is not None:
                    result = ObjectSpriteSet(variants=cached)
                    self._cache[key] = result
                    return result

        result = self._load_spray_reveal_sheet(sheet_path)

        if self._disk_cache is not None and cache_path is not None and cache_path.exists():
            self._disk_cache.save_sprite_set(cache_path, "spray_reveal", result.variants)

        self._cache[key] = result
        return result

    def door_set(self, orientation: str = "top") -> ObjectSpriteSet:
        orientation = self._normalize_door_orientation(orientation)
        key = f"door:{orientation}"
        if key in self._cache:
            return self._cache[key]

        wall_dir = self._project_root / "source/textures/walls"
        if orientation == "top":
            pair = self._load_door_pair_from_candidates(
                wall_dir=wall_dir,
                closed_candidates=["door_closed.png", "top_door_closed.png"],
                open_candidates=[
                    "top_open_door_alpha.png",
                    "top_open_door.png",
                    "door_opening_outward_alpha.png",
                    "door_opening_outward.png",
                    "door_opening.png",
                    "door_open.png",
                    "top_opening_frame.png",
                ],
            )
            if pair is not None:
                closed, opened = pair
                result = ObjectSpriteSet(variants=[closed, opened])
                self._cache[key] = result
                return result
        elif orientation == "left":
            pair = self._load_door_pair_from_candidates(
                wall_dir=wall_dir,
                closed_candidates=["left_door_closed.png", "left_door.png"],
                open_candidates=[
                    "left_open_door_alpha.png",
                    "left_open_door.png",
                    "left_door_open.png",
                ],
            )
            if pair is not None:
                closed, opened = pair
                result = ObjectSpriteSet(variants=[closed, opened])
                self._cache[key] = result
                return result
            right_pair = self._load_door_pair_from_candidates(
                wall_dir=wall_dir,
                closed_candidates=["right_door_closed.png", "right_door.png"],
                open_candidates=[
                    "right_open_door_alpha.png",
                    "right_open_door.png",
                    "right_door_open.png",
                ],
            )
            if right_pair is not None:
                rc, ro = right_pair
                result = ObjectSpriteSet(
                    variants=[pygame.transform.flip(rc, True, False), pygame.transform.flip(ro, True, False)]
                )
                self._cache[key] = result
                return result
        elif orientation == "right":
            pair = self._load_door_pair_from_candidates(
                wall_dir=wall_dir,
                closed_candidates=["right_door_closed.png", "right_door.png"],
                open_candidates=[
                    "right_open_door_alpha.png",
                    "right_open_door.png",
                    "right_door_open.png",
                ],
            )
            if pair is not None:
                closed, opened = pair
                result = ObjectSpriteSet(variants=[closed, opened])
                self._cache[key] = result
                return result
            left_pair = self._load_door_pair_from_candidates(
                wall_dir=wall_dir,
                closed_candidates=["left_door_closed.png", "left_door.png"],
                open_candidates=[
                    "left_open_door_alpha.png",
                    "left_open_door.png",
                    "left_door_open.png",
                ],
            )
            if left_pair is not None:
                lc, lo = left_pair
                result = ObjectSpriteSet(
                    variants=[pygame.transform.flip(lc, True, False), pygame.transform.flip(lo, True, False)]
                )
                self._cache[key] = result
                return result

        if orientation != "top":
            result = self.door_set("top")
            self._cache[key] = result
            return result

        sheet = pygame.image.load(
            str(self._project_root / "source/textures/walls/walls_sheet.png")
        ).convert_alpha()
        components = self._extract_components(sheet, alpha_cutoff=20, min_area=1200)
        components = self._filter_components(components, min_area=1200)
        rows = self._cluster_rows(components, tolerance=52)
        if len(rows) < 4:
            raise ValueError("Door sheet parsing failed: expected door row")
        door_row = sorted(rows[3], key=lambda r: r.centerx)
        if len(door_row) < 3:
            raise ValueError("Door sheet parsing failed: missing door variants")

        closed = self._sprite_from_rect(sheet, door_row[1])
        opened = self._sprite_from_rect(sheet, door_row[2])
        result = ObjectSpriteSet(variants=[closed, opened])
        self._cache[key] = result
        return result

    def icon_for_item(self, item_id: str) -> pygame.Surface:
        cached = self._icon_cache.get(item_id)
        if cached is not None:
            return cached
        balloon_specs = self._resolved_balloon_specs()
        known_balloon_items = {spec.item_id for spec in balloon_specs.values() if spec.item_id}
        known_balloon_items.update(self._balloon_item_ids.keys())

        if item_id == "backpack":
            icon = pygame.transform.scale(self.backpack_set().get(0), (42, 42))
            self._icon_cache[item_id] = icon
            return icon
        if item_id in known_balloon_items:
            balloon_id = self._balloon_id_for_item_id(item_id, balloon_specs)
            spec = balloon_specs.get(balloon_id) if balloon_id else None
            target_size = spec.icon_size if spec is not None else (30, 42)
            icon = pygame.transform.scale(self.ballon_sprite_for_item(item_id), target_size)
            self._icon_cache[item_id] = icon
            return icon
        if item_id == "key" or item_id.startswith("key_"):
            base = pygame.transform.scale(self.key_set().get(0), (34, 24))
            key_color = self._key_color_from_item_id(item_id)
            icon = base if key_color is None else self._tint_icon(base, key_color, strength=1.0)
            self._icon_cache[item_id] = icon
            return icon
        raise KeyError(f"Unknown item icon: {item_id}")

    def cached_icon_for_item(self, item_id: str) -> pygame.Surface | None:
        return self._icon_cache.get(item_id)

    def variant_count(self, object_kind: str) -> int:
        if object_kind == "backpack":
            return len(self.backpack_set().variants)
        if object_kind == "sofa":
            return len(self.sofa_set().variants)
        if object_kind == "plant":
            return len(self.plant_set().variants)
        if object_kind == "key":
            return len(self.key_set().variants)
        if object_kind == "ballon":
            return len(self.ballon_set().variants)
        if object_kind == "door":
            return len(self.door_set("top").variants)
        return 1

    def nominal_world_size(self, kind: str, obj: WorldObject | None = None) -> tuple[int, int]:
        if kind == "ballon":
            specs = self._resolved_balloon_specs()
            if isinstance(obj, BalloonObject) and obj.balloon_id:
                spec = specs.get(obj.balloon_id)
                if spec is not None:
                    return (int(spec.world_size[0]), int(spec.world_size[1]))
            if specs:
                first_id = self._ordered_balloon_ids(specs)[0]
                spec = specs.get(first_id)
                if spec is not None:
                    return (int(spec.world_size[0]), int(spec.world_size[1]))
            return (78, 110)
        size = self._load_kind_world_size(kind)
        if size is not None:
            return size
        if obj is not None:
            return (max(32, int(obj.width)), max(32, int(obj.height)))
        return (64, 64)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _load_kind_world_size(self, kind: str) -> tuple[int, int] | None:
        if kind in self._kind_size_cache:
            return self._kind_size_cache[kind]
        items_root = self._project_root / "source/textures/items"
        candidates = [
            items_root / kind / "settings.json",
            items_root / (kind + "s") / "settings.json",
            items_root / (kind + "es") / "settings.json",
        ]
        result: tuple[int, int] | None = None
        for path in candidates:
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(raw, dict):
                continue
            ws = raw.get("world_size")
            if isinstance(ws, list) and len(ws) == 2:
                try:
                    result = (int(ws[0]), int(ws[1]))
                    break
                except (TypeError, ValueError):
                    pass
        self._kind_size_cache[kind] = result
        return result

    def _normalize_door_orientation(self, orientation: str) -> str:
        token = str(orientation).strip().lower()
        if token in {"left", "right", "top", "bottom"}:
            return token
        return "top"

    def _resolved_balloon_specs(self) -> dict[str, BalloonSpec]:
        if self._balloon_specs:
            return self._balloon_specs
        legacy = self._project_root / "source/textures/items/ballon/ballon.png"
        if legacy.exists():
            self._balloon_specs = {
                "default": BalloonSpec(
                    balloon_id="default",
                    item_id="ballon",
                    sprite_path=str(legacy.relative_to(self._project_root)),
                )
            }
            self._balloon_item_ids = {"ballon": "default"}
        return self._balloon_specs

    def _ordered_balloon_ids(self, specs: dict[str, BalloonSpec]) -> list[str]:
        ids = list(specs.keys())
        if "default" in ids:
            ids.remove("default")
            ids.sort()
            return ["default", *ids]
        ids.sort()
        return ids

    def _balloon_id_for_item_id(
        self,
        item_id: str | None,
        specs: dict[str, BalloonSpec],
    ) -> str:
        if item_id is not None:
            token = str(item_id).strip()
            if token:
                mapped = self._balloon_item_ids.get(token)
                if mapped:
                    return mapped
                for spec in specs.values():
                    if spec.item_id == token:
                        return spec.balloon_id
        if "default" in specs:
            return "default"
        if specs:
            return next(iter(specs.keys()))
        return ""

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return self._project_root / candidate

    def _load_door_pair_from_candidates(
        self,
        wall_dir: Path,
        closed_candidates: list[str],
        open_candidates: list[str],
    ) -> tuple[pygame.Surface, pygame.Surface] | None:
        closed_path = next((wall_dir / name for name in closed_candidates if (wall_dir / name).exists()), None)
        open_path = next((wall_dir / name for name in open_candidates if (wall_dir / name).exists()), None)
        if closed_path is None or open_path is None:
            return None
        return (
            pygame.image.load(str(closed_path)).convert_alpha(),
            pygame.image.load(str(open_path)).convert_alpha(),
        )

    def _load_single_sprite_with_chroma(
        self,
        path: Path,
        target_size: tuple[int, int],
        green_delta: int,
        green_min: int,
    ) -> pygame.Surface:
        if not path.exists():
            raise FileNotFoundError(f"Sprite not found: {path}")
        src = pygame.image.load(str(path)).convert_alpha()
        out = src.copy()
        self._chroma_to_alpha(out, green_delta=green_delta, green_min=green_min)
        trimmed = self._trim_sparse_edges(out, alpha_cutoff=18)
        self._sanitize_alpha_edges(trimmed, alpha_cutoff=18)
        return self._fit_to_target(trimmed, target_size)

    def _load_spray_reveal_sheet(self, sheet_path: str) -> ObjectSpriteSet:
        path = Path(sheet_path)
        abs_path = path if path.is_absolute() else self._project_root / path
        if not abs_path.exists():
            raise FileNotFoundError(f"Spray reveal sheet not found: {abs_path}")
        sheet = pygame.image.load(str(abs_path)).convert_alpha()
        sheet_alpha = pygame.surfarray.array_alpha(sheet)
        # If the sheet already has transparent background, do not apply green chroma key:
        # it can remove legitimate green colors from graffiti (e.g. "lisa").
        has_precomputed_alpha = bool(np.any(sheet_alpha < 250))
        del sheet_alpha
        cell_rects = self._sheet_cell_rects(sheet)
        if not cell_rects:
            cols, rows = self._infer_spray_grid(sheet)
            cell_rects = self._sheet_grid_cells(sheet.get_width(), sheet.get_height(), cols=cols, rows=rows)

        frames: list[pygame.Surface] = []
        for rect in cell_rects:
            cell = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            cell.blit(sheet, (0, 0), rect)
            trim_cutoff = 18
            sanitize_cutoff = 18
            if not has_precomputed_alpha:
                self._chroma_to_alpha(cell, green_delta=30, green_min=84)

                border = max(2, min(4, min(rect.width, rect.height) // 32))
                if border > 0:
                    cell.fill((0, 0, 0, 0), pygame.Rect(0, 0, rect.width, border))
                    cell.fill((0, 0, 0, 0), pygame.Rect(0, rect.height - border, rect.width, border))
                    cell.fill((0, 0, 0, 0), pygame.Rect(0, 0, border, rect.height))
                    cell.fill((0, 0, 0, 0), pygame.Rect(rect.width - border, 0, border, rect.height))
                stamp_w = min(rect.width // 3, 48)
                stamp_h = min(rect.height // 5, 40)
                cell.fill((0, 0, 0, 0), pygame.Rect(0, 0, stamp_w, stamp_h))
                cell = self._keep_relevant_spray_components(cell, alpha_cutoff=18)
            else:
                # Pre-matted PNG sheets already have clean alpha; keep thin details and antialiasing.
                trim_cutoff = 2
                sanitize_cutoff = 2

            trimmed = self._trim_sparse_edges(cell, alpha_cutoff=trim_cutoff)
            self._sanitize_alpha_edges(trimmed, alpha_cutoff=sanitize_cutoff)
            bounds = trimmed.get_bounding_rect(min_alpha=18)
            if bounds.width < 8 or bounds.height < 8:
                continue
            # Keep original graffiti colors from the source sheet.
            frames.append(trimmed)

        if not frames:
            raise ValueError(f"Spray reveal sheet parsing failed: no frames detected ({abs_path})")
        return ObjectSpriteSet(variants=frames)

    def _infer_spray_grid(self, sheet: pygame.Surface) -> tuple[int, int]:
        w, h = sheet.get_size()
        cols = max(1, len(self._ranges_between_separator_runs(self._find_separator_runs(sheet, "x"), w)))
        rows = max(1, len(self._ranges_between_separator_runs(self._find_separator_runs(sheet, "y"), h)))

        if cols < 3 or rows < 3 or cols > 16 or rows > 16:
            if abs((w / max(1, h)) - (10.0 / 5.0)) < 0.18:
                return (10, 5)
            if abs((w / max(1, h)) - 1.0) < 0.20:
                return (7, 7)
            return (10, 5)
        return (cols, rows)

    def _sheet_cell_rects(self, sheet: pygame.Surface) -> list[pygame.Rect]:
        w, h = sheet.get_size()
        x_ranges = self._ranges_between_separator_runs(self._find_separator_runs(sheet, "x"), w)
        y_ranges = self._ranges_between_separator_runs(self._find_separator_runs(sheet, "y"), h)
        if not x_ranges or not y_ranges:
            return []
        out: list[pygame.Rect] = []
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                cw = max(1, x1 - x0)
                ch = max(1, y1 - y0)
                if cw < 8 or ch < 8:
                    continue
                out.append(pygame.Rect(x0, y0, cw, ch))
        return out

    def _find_separator_runs(self, sheet: pygame.Surface, axis: str) -> list[tuple[int, int]]:
        w, h = sheet.get_size()
        white_threshold = 220
        alpha_threshold = 180
        ratio_threshold = 0.55

        rgb = pygame.surfarray.array3d(sheet)      # (w, h, 3)
        alpha = pygame.surfarray.array_alpha(sheet)  # (w, h)

        bright = (
            (alpha >= alpha_threshold)
            & (rgb[:, :, 0] >= white_threshold)
            & (rgb[:, :, 1] >= white_threshold)
            & (rgb[:, :, 2] >= white_threshold)
        )  # (w, h) bool

        if axis == "x":
            counts = np.sum(bright, axis=1)  # (w,)  — sum over y
            denom = max(1, h)
            positions = [int(x) for x in range(w) if (int(counts[x]) / denom) >= ratio_threshold]
        else:
            counts = np.sum(bright, axis=0)  # (h,)  — sum over x
            denom = max(1, w)
            positions = [int(y) for y in range(h) if (int(counts[y]) / denom) >= ratio_threshold]

        if not positions:
            return []

        runs: list[tuple[int, int]] = []
        run_start = positions[0]
        prev = positions[0]
        for pos in positions[1:]:
            if pos <= prev + 2:
                prev = pos
                continue
            runs.append((run_start, prev))
            run_start = pos
            prev = pos
        runs.append((run_start, prev))
        return runs

    def _ranges_between_separator_runs(
        self,
        runs: list[tuple[int, int]],
        limit: int,
    ) -> list[tuple[int, int]]:
        if not runs:
            return [(0, limit)]
        out: list[tuple[int, int]] = []
        cursor = 0
        for start, end in sorted(runs, key=lambda it: it[0]):
            if start > cursor + 2:
                out.append((cursor, start))
            cursor = max(cursor, end + 1)
        if limit > cursor + 2:
            out.append((cursor, limit))
        return out

    def _keep_relevant_spray_components(self, sprite: pygame.Surface, alpha_cutoff: int) -> pygame.Surface:
        components = self._extract_components(sprite, alpha_cutoff=alpha_cutoff, min_area=8)
        if not components:
            return sprite
        largest = max(components, key=lambda r: r.width * r.height)
        largest_area = largest.width * largest.height
        keep: list[pygame.Rect] = []
        for rect in components:
            area = rect.width * rect.height
            if area < max(10, int(largest_area * 0.025)):
                continue
            dx = abs(rect.centerx - largest.centerx)
            dy = abs(rect.centery - largest.centery)
            if dy > max(20, int(largest.height * 0.95)) and area < int(largest_area * 0.45):
                continue
            if dx > max(26, int(largest.width * 1.35)) and area < int(largest_area * 0.45):
                continue
            keep.append(rect)
        if not keep:
            keep = [largest]
        out = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
        for rect in keep:
            out.blit(sprite, (rect.x, rect.y), rect)
        return out

    def _sheet_grid_cells(self, width: int, height: int, cols: int, rows: int) -> list[pygame.Rect]:
        out: list[pygame.Rect] = []
        for row in range(rows):
            y0 = int(round((row * height) / rows))
            y1 = int(round(((row + 1) * height) / rows))
            for col in range(cols):
                x0 = int(round((col * width) / cols))
                x1 = int(round(((col + 1) * width) / cols))
                w = max(1, x1 - x0)
                h = max(1, y1 - y0)
                out.append(pygame.Rect(x0, y0, w, h))
        return out

    def _chroma_to_alpha(self, surface: pygame.Surface, green_delta: int, green_min: int) -> None:
        rgb = pygame.surfarray.pixels3d(surface)      # (w, h, 3) — locked
        alpha = pygame.surfarray.pixels_alpha(surface)  # (w, h) — locked
        r = rgb[:, :, 0].astype(np.int32)
        g = rgb[:, :, 1].astype(np.int32)
        b = rgb[:, :, 2].astype(np.int32)
        chroma = (
            (alpha > 0)
            & (g >= green_min)
            & (g >= r + green_delta)
            & (g >= b + green_delta)
        )
        alpha[chroma] = 0
        rgb[chroma] = 0
        del rgb, alpha

    def _sprite_from_rect(self, sheet: pygame.Surface, rect: pygame.Rect) -> pygame.Surface:
        base = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        base.blit(sheet, (0, 0), rect)
        base = self._trim_sparse_edges(base, alpha_cutoff=20)
        self._sanitize_alpha_edges(base, alpha_cutoff=20)
        return base

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

    def _extract_top_row_variants(
        self,
        sheet: pygame.Surface,
        variant_count: int,
        target_size: tuple[int, int],
        min_area: int,
    ) -> list[pygame.Surface]:
        components = self._extract_components(sheet, alpha_cutoff=20, min_area=min_area)
        components = self._filter_components(components, min_area=min_area)
        if len(components) < variant_count:
            raise ValueError(f"Sprite sheet parsing failed: less than {variant_count} components")

        top_row = self._pick_top_row_components(components, variant_count)
        variants: list[pygame.Surface] = []

        for rect in top_row:
            base = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            base.blit(sheet, (0, 0), rect)
            base = self._trim_sparse_edges(base, alpha_cutoff=20)
            self._sanitize_alpha_edges(base, alpha_cutoff=20)
            variants.append(self._fit_to_target(base, target_size))

        return variants

    def _extract_all_variants(
        self,
        sheet: pygame.Surface,
        target_size: tuple[int, int],
        min_area: int,
    ) -> list[pygame.Surface]:
        components = self._extract_components(sheet, alpha_cutoff=20, min_area=min_area)
        components = self._filter_components(components, min_area=min_area)
        components = sorted(components, key=lambda r: (r.centery, r.centerx))

        variants: list[pygame.Surface] = []
        for rect in components:
            base = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            base.blit(sheet, (0, 0), rect)
            base = self._trim_sparse_edges(base, alpha_cutoff=20)
            self._sanitize_alpha_edges(base, alpha_cutoff=20)
            variants.append(self._fit_to_target(base, target_size))
        return variants

    def _extract_components(
        self,
        surface: pygame.Surface,
        alpha_cutoff: int,
        min_area: int,
    ) -> list[pygame.Rect]:
        w, h = surface.get_size()
        alpha_arr = pygame.surfarray.array_alpha(surface)  # (w, h)
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

    def _trim_sparse_edges(self, sprite: pygame.Surface, alpha_cutoff: int) -> pygame.Surface:
        rect = sprite.get_bounding_rect(min_alpha=alpha_cutoff)
        if rect.width <= 0 or rect.height <= 0:
            return sprite

        left = rect.left
        right = rect.right - 1
        top = rect.top
        bottom = rect.bottom - 1
        min_col = max(4, rect.height // 140)
        min_row = max(4, rect.width // 140)

        alpha_arr = pygame.surfarray.array_alpha(sprite)  # (w, h)
        opaque = alpha_arr >= alpha_cutoff

        while left < right and int(np.sum(opaque[left, top : bottom + 1])) < min_col:
            left += 1
        while right > left and int(np.sum(opaque[right, top : bottom + 1])) < min_col:
            right -= 1
        while top < bottom and int(np.sum(opaque[left : right + 1, top])) < min_row:
            top += 1
        while bottom > top and int(np.sum(opaque[left : right + 1, bottom])) < min_row:
            bottom -= 1

        return sprite.subsurface(
            pygame.Rect(left, top, max(1, right - left + 1), max(1, bottom - top + 1))
        ).copy()

    def _sanitize_alpha_edges(self, sprite: pygame.Surface, alpha_cutoff: int) -> None:
        rgb = pygame.surfarray.pixels3d(sprite)      # (w, h, 3) — locked
        alpha = pygame.surfarray.pixels_alpha(sprite)  # (w, h) — locked

        low = alpha < alpha_cutoff
        semi = (~low) & (alpha < 255)

        alpha[low] = 0
        rgb[low] = 0

        if np.any(semi):
            r = rgb[:, :, 0].astype(np.int32)
            g = rgb[:, :, 1].astype(np.int32)
            b = rgb[:, :, 2].astype(np.int32)
            g_limit = np.maximum(r, b) + 14
            spill = semi & (g > g_limit)
            if np.any(spill):
                rgb[:, :, 1] = np.where(spill, np.minimum(g, g_limit), g).astype(np.uint8)

        del rgb, alpha

    def _filter_components(self, components: list[pygame.Rect], min_area: int) -> list[pygame.Rect]:
        if not components:
            return components

        areas = [rect.width * rect.height for rect in components]
        widths = [rect.width for rect in components]
        heights = [rect.height for rect in components]
        med_area = median(areas)
        med_w = median(widths)
        med_h = median(heights)

        filtered: list[pygame.Rect] = []
        for rect in components:
            area = rect.width * rect.height
            aspect = rect.width / max(1, rect.height)
            if area < max(min_area, int(med_area * 0.45)):
                continue
            if rect.width < max(10, int(med_w * 0.35)):
                continue
            if rect.height < max(10, int(med_h * 0.35)):
                continue
            if aspect < 0.28 or aspect > 3.5:
                continue
            filtered.append(rect)

        return filtered if len(filtered) >= 4 else components

    def _pick_top_row_components(
        self,
        components: list[pygame.Rect],
        variant_count: int,
    ) -> list[pygame.Rect]:
        if len(components) <= variant_count:
            return sorted(components, key=lambda r: r.centerx)

        row_tol = int(median(rect.height for rect in components) * 0.55)
        sorted_by_y = sorted(components, key=lambda r: r.centery)
        clusters: list[list[pygame.Rect]] = []
        for rect in sorted_by_y:
            placed = False
            for cluster in clusters:
                cy = int(sum(r.centery for r in cluster) / len(cluster))
                if abs(rect.centery - cy) <= row_tol:
                    cluster.append(rect)
                    placed = True
                    break
            if not placed:
                clusters.append([rect])

        clusters.sort(key=lambda c: (-len(c), min(r.centery for r in c)))
        row = sorted(clusters[0], key=lambda r: r.centerx)
        if len(row) > variant_count:
            row = row[:variant_count]
        return row

    def _fit_to_target(self, sprite: pygame.Surface, target_size: tuple[int, int]) -> pygame.Surface:
        tw, th = target_size
        sw, sh = sprite.get_size()
        scale = min(tw / max(1, sw), th / max(1, sh))
        out_w = max(1, int(sw * scale))
        out_h = max(1, int(sh * scale))
        # For very large downscales (e.g. AI-generated high-res cans), nearest scaling
        # creates noisy holes. Use smooth scaling only in that case.
        downscale_ratio = max(sw / max(1, out_w), sh / max(1, out_h))
        if downscale_ratio >= 3.0:
            scaled = pygame.transform.smoothscale(sprite, (out_w, out_h))
        else:
            scaled = pygame.transform.scale(sprite, (out_w, out_h))

        canvas = pygame.Surface((tw, th), pygame.SRCALPHA)
        dst_x = (tw - out_w) // 2
        dst_y = th - out_h
        canvas.blit(scaled, (dst_x, dst_y))
        return canvas

    def _key_color_from_item_id(self, item_id: str) -> tuple[int, int, int] | None:
        token = item_id.lower()
        if token == "key":
            return None
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

    def _tint_icon(
        self,
        base: pygame.Surface,
        tint_rgb: tuple[int, int, int],
        strength: float,
    ) -> pygame.Surface:
        out = base.copy()
        sr = max(0.0, min(1.0, float(strength)))

        # Compute target hue/saturation in [0,1] scale
        tr, tg, tb = tint_rgb[0] / 255.0, tint_rgb[1] / 255.0, tint_rgb[2] / 255.0
        t_max = max(tr, tg, tb)
        t_delta = t_max - min(tr, tg, tb)
        target_s = t_delta / t_max if t_max > 1e-9 else 0.0
        if t_delta < 1e-9:
            target_h = 0.0
        elif t_max == tr:
            target_h = 60.0 * ((tg - tb) / t_delta % 6.0)
        elif t_max == tg:
            target_h = 60.0 * ((tb - tr) / t_delta + 2.0)
        else:
            target_h = 60.0 * ((tr - tg) / t_delta + 4.0)
        target_h %= 360.0

        alpha = pygame.surfarray.array_alpha(out)   # (w, h)
        rgb_arr = pygame.surfarray.array3d(out)     # (w, h, 3)

        r = rgb_arr[:, :, 0].astype(np.float32) / 255.0
        g = rgb_arr[:, :, 1].astype(np.float32) / 255.0
        b = rgb_arr[:, :, 2].astype(np.float32) / 255.0

        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        delta = max_c - min_c

        # saturation in [0,1]; if max_c==0 or r==g==b → s0==0 → inactive
        s0 = np.where(max_c > 1e-9, delta / np.maximum(max_c, 1e-9), 0.0)
        active = (alpha > 0) & (s0 >= 0.08)  # 8.0/100 threshold from original

        if not np.any(active):
            return out

        eps = 1e-9
        safe_d = np.where(delta > eps, delta, 1.0)
        is_r = (max_c == r) & (delta > eps)
        is_g = (max_c == g) & (delta > eps) & ~is_r
        is_b = ~is_r & ~is_g & (delta > eps)

        h0 = np.zeros_like(r)
        h0 = np.where(is_r, 60.0 * ((g - b) / safe_d % 6.0), h0)
        h0 = np.where(is_g, 60.0 * ((b - r) / safe_d + 2.0), h0)
        h0 = np.where(is_b, 60.0 * ((r - g) / safe_d + 4.0), h0)
        h0 %= 360.0

        new_h = np.where(active, target_h, h0)
        new_s = np.where(active, s0 + (np.maximum(target_s, s0) - s0) * sr, s0)
        new_v = max_c  # value unchanged

        # HSV → RGB
        C_val = new_v * new_s
        H_sec = new_h / 60.0
        X_val = C_val * (1.0 - np.abs(H_sec % 2.0 - 1.0))
        m_val = new_v - C_val
        sec = np.floor(H_sec).astype(np.int32) % 6

        zero = np.zeros_like(C_val)
        lut = [
            (C_val, X_val, zero),
            (X_val, C_val, zero),
            (zero,  C_val, X_val),
            (zero,  X_val, C_val),
            (X_val, zero,  C_val),
            (C_val, zero,  X_val),
        ]
        nr = np.zeros_like(r)
        ng = np.zeros_like(r)
        nb = np.zeros_like(r)
        for i, (cr, cg, cb) in enumerate(lut):
            mask = sec == i
            nr = np.where(mask, cr, nr)
            ng = np.where(mask, cg, ng)
            nb = np.where(mask, cb, nb)

        new_r = np.clip((nr + m_val) * 255.0, 0, 255)
        new_g = np.clip((ng + m_val) * 255.0, 0, 255)
        new_b = np.clip((nb + m_val) * 255.0, 0, 255)

        orig_r = r * 255.0
        orig_g = g * 255.0
        orig_b = b * 255.0

        final_r = np.where(active, orig_r + (new_r - orig_r) * sr, orig_r)
        final_g = np.where(active, orig_g + (new_g - orig_g) * sr, orig_g)
        final_b = np.where(active, orig_b + (new_b - orig_b) * sr, orig_b)

        px = pygame.surfarray.pixels3d(out)
        px[:, :, 0] = final_r.astype(np.uint8)
        px[:, :, 1] = final_g.astype(np.uint8)
        px[:, :, 2] = final_b.astype(np.uint8)
        del px
        return out
