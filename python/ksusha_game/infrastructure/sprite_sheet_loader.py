from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame

from ksusha_game.config import SpriteSheetConfig
from ksusha_game.domain.direction import Direction
from ksusha_game.infrastructure.asset_cache import SpriteCache
from ksusha_game.infrastructure.frame_processing import FramePreprocessor


@dataclass(frozen=True)
class SpriteSheetRuntimeSettings:
    columns: int
    rows: int
    row_by_direction: dict[Direction, int]
    detect_content_rect: bool
    offset_x: int
    offset_y: int
    cell_width: int | None
    cell_height: int | None
    spacing_x: int
    spacing_y: int
    alignment_mode: str
    frame_columns: list[int] | None
    normalize_canvas: bool
    component_pick: str
    output_width: int | None
    output_height: int | None
    step_x: int | None
    step_y: int | None
    bbox_padding: int
    body_height: int | None
    body_scale_min: float
    body_scale_max: float
    foot_margin: int
    mirror_directions: dict[Direction, Direction]
    chroma_key: bool
    chroma_green_delta: int
    chroma_green_min: int
    chroma_soften_spill: bool
    chroma_spill_green_delta: int
    chroma_spill_green_min: int


class SpriteSheetLoader:
    def __init__(
        self,
        config: SpriteSheetConfig,
        preprocessor: FramePreprocessor,
        cache: SpriteCache | None = None,
    ) -> None:
        self._config = config
        self._preprocessor = preprocessor
        self._cache = cache

    def load_walk_frames(self, sheet_path: Path) -> dict[Direction, list[pygame.Surface]]:
        cache_variant = self._cache_variant_token(sheet_path)
        if self._cache is not None:
            cached = self._cache.load(sheet_path, variant=cache_variant)
            if cached is not None:
                return cached

        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        runtime = self._resolve_runtime_settings(sheet_path, sheet)
        if runtime.chroma_key:
            self._chroma_to_alpha(
                sheet,
                green_delta=runtime.chroma_green_delta,
                green_min=runtime.chroma_green_min,
            )
            if runtime.chroma_soften_spill:
                self._soften_green_spill(
                    sheet,
                    green_delta=runtime.chroma_spill_green_delta,
                    green_min=runtime.chroma_spill_green_min,
                )
        content_rect = sheet.get_rect()
        if runtime.detect_content_rect:
            content_rect = self._detect_content_rect(sheet)
            if content_rect.width <= 0 or content_rect.height <= 0:
                content_rect = sheet.get_rect()
        result: dict[Direction, list[pygame.Surface]] = {}
        for direction, row in runtime.row_by_direction.items():
            result[direction] = self._load_row_frames(sheet, row, content_rect, runtime)
        for target, source in runtime.mirror_directions.items():
            source_frames = result.get(source)
            if not source_frames:
                continue
            result[target] = [pygame.transform.flip(frame, True, False) for frame in source_frames]
        if runtime.normalize_canvas:
            result = self._normalize_direction_canvas(result, runtime)
        if runtime.body_height is not None:
            result = self._normalize_body_height(
                result,
                target_height=runtime.body_height,
                scale_min=runtime.body_scale_min,
                scale_max=runtime.body_scale_max,
                foot_margin=runtime.foot_margin,
            )

        if self._cache is not None:
            self._cache.save(sheet_path, result, variant=cache_variant)

        return result

    def _load_row_frames(
        self,
        sheet: pygame.Surface,
        row: int,
        content_rect: pygame.Rect,
        runtime: SpriteSheetRuntimeSettings,
    ) -> list[pygame.Surface]:
        frames_raw: list[pygame.Surface] = []
        frame_columns = runtime.frame_columns if runtime.frame_columns is not None else list(range(runtime.columns))
        for col in frame_columns:
            src = self._grid_cell_rect(
                content_rect,
                row=row,
                col=col,
                columns=runtime.columns,
                rows=runtime.rows,
                runtime=runtime,
                sheet=sheet,
            )
            frame = pygame.Surface((src.width, src.height), pygame.SRCALPHA)
            frame.blit(sheet, (0, 0), src)
            frames_raw.append(frame)

        if not self._has_transparency(frames_raw):
            frames_raw = self._preprocessor.remove_static_row_background(frames_raw)
        if runtime.component_pick != "none":
            frames_raw = [self._filter_frame_component(frame, runtime.component_pick) for frame in frames_raw]
        frames_raw = [self._trim_top_fringe_noise(frame) for frame in frames_raw]
        if runtime.alignment_mode == "raw_cell":
            return frames_raw

        rects = [self._detect_main_rect(frame, padding=runtime.bbox_padding) for frame in frames_raw]

        if runtime.alignment_mode == "union":
            return self._stabilize_frames_union(frames_raw, rects)
        if runtime.alignment_mode == "rect_center":
            return self._stabilize_frames_rect_center(frames_raw, rects)

        # "body_anchor": keep legacy behavior for compatibility when no per-skin settings exist.
        body_cx = self._stable_body_cx(frames_raw)
        max_h = max(rect.height for rect in rects)
        max_left = max(body_cx - rect.x for rect in rects)
        max_right = max(rect.right - body_cx for rect in rects)
        canvas_body_cx = int(np.ceil(max_left))
        canvas_w = max(1, canvas_body_cx + int(np.ceil(max_right)))

        frames: list[pygame.Surface] = []
        for frame, rect in zip(frames_raw, rects):
            cropped = frame.subsurface(rect).copy()
            canvas = pygame.Surface((canvas_w, max_h), pygame.SRCALPHA)
            dst_x = max(0, canvas_body_cx - int(round(body_cx - rect.x)))
            dst_y = max_h - rect.height
            canvas.blit(cropped, (dst_x, dst_y))
            frames.append(canvas)

        return frames

    def _stabilize_frames_union(
        self,
        frames_raw: list[pygame.Surface],
        rects: list[pygame.Rect],
    ) -> list[pygame.Surface]:
        if not frames_raw:
            return []
        union = rects[0].copy()
        for rect in rects[1:]:
            union.union_ip(rect)
        union_w = max(1, union.width)
        union_h = max(1, union.height)

        frames: list[pygame.Surface] = []
        for frame in frames_raw:
            canvas = pygame.Surface((union_w, union_h), pygame.SRCALPHA)
            canvas.blit(frame, (0, 0), union)
            frames.append(canvas)
        return frames

    def _stabilize_frames_rect_center(
        self,
        frames_raw: list[pygame.Surface],
        rects: list[pygame.Rect],
    ) -> list[pygame.Surface]:
        if not frames_raw:
            return []
        max_w = max(1, max(rect.width for rect in rects))
        max_h = max(1, max(rect.height for rect in rects))

        frames: list[pygame.Surface] = []
        for frame, rect in zip(frames_raw, rects):
            cropped = frame.subsurface(rect).copy()
            canvas = pygame.Surface((max_w, max_h), pygame.SRCALPHA)
            x = (max_w - rect.width) // 2
            y = max_h - rect.height
            canvas.blit(cropped, (x, y))
            frames.append(canvas)
        return frames

    def _stable_body_cx(self, frames: list[pygame.Surface]) -> float:
        alpha_cutoff = self._config.alpha_component_cutoff
        centroids: list[float] = []
        for frame in frames:
            alpha = pygame.surfarray.array_alpha(frame)
            col_weights = (alpha >= alpha_cutoff).astype(np.float64).sum(axis=1)  # (w,)
            total = col_weights.sum()
            if total < 1.0:
                centroids.append(float(frame.get_width()) / 2.0)
            else:
                xs = np.arange(len(col_weights), dtype=np.float64)
                centroids.append(float((xs * col_weights).sum() / total))
        centroids.sort()
        return centroids[len(centroids) // 2]

    def _grid_cell_rect(
        self,
        content_rect: pygame.Rect,
        row: int,
        col: int,
        *,
        columns: int,
        rows: int,
        runtime: SpriteSheetRuntimeSettings,
        sheet: pygame.Surface,
    ) -> pygame.Rect:
        if runtime.cell_width is not None and runtime.cell_height is not None:
            step_x = runtime.step_x if runtime.step_x is not None else (runtime.cell_width + runtime.spacing_x)
            step_y = runtime.step_y if runtime.step_y is not None else (runtime.cell_height + runtime.spacing_y)
            x0 = runtime.offset_x + col * step_x
            y0 = runtime.offset_y + row * step_y
            rect = pygame.Rect(x0, y0, runtime.cell_width, runtime.cell_height)
        else:
            x0 = content_rect.x + (col * content_rect.width) // columns
            x1 = content_rect.x + ((col + 1) * content_rect.width) // columns
            y0 = content_rect.y + (row * content_rect.height) // rows
            y1 = content_rect.y + ((row + 1) * content_rect.height) // rows
            rect = pygame.Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))

        clipped = rect.clip(sheet.get_rect())
        if clipped.width <= 0 or clipped.height <= 0:
            raise ValueError(f"Sprite cell is outside sheet bounds: row={row}, col={col}, rect={rect}")
        return clipped

    def _resolve_runtime_settings(
        self,
        sheet_path: Path,
        sheet: pygame.Surface,
    ) -> SpriteSheetRuntimeSettings:
        row_by_direction = dict(self._config.row_by_direction)
        runtime = SpriteSheetRuntimeSettings(
            columns=self._config.columns,
            rows=self._config.rows,
            row_by_direction=row_by_direction,
            detect_content_rect=True,
            offset_x=0,
            offset_y=0,
            cell_width=None,
            cell_height=None,
            spacing_x=0,
            spacing_y=0,
            alignment_mode="body_anchor",
            frame_columns=None,
            normalize_canvas=False,
            component_pick="none",
            output_width=None,
            output_height=None,
            step_x=None,
            step_y=None,
            bbox_padding=self._config.crop_padding,
            body_height=None,
            body_scale_min=0.72,
            body_scale_max=1.28,
            foot_margin=0,
            mirror_directions={},
            chroma_key=False,
            chroma_green_delta=24,
            chroma_green_min=86,
            chroma_soften_spill=False,
            chroma_spill_green_delta=10,
            chroma_spill_green_min=74,
        )
        raw = self._load_sheet_settings_for_file(sheet_path)
        if raw is None:
            return runtime

        columns = self._safe_positive_int(raw.get("columns"), runtime.columns)
        rows = self._safe_positive_int(raw.get("rows"), runtime.rows)
        row_map = self._parse_direction_rows(raw.get("row_by_direction"), fallback=row_by_direction)

        detect_content_rect = bool(raw.get("detect_content_rect", False))
        alignment_mode = str(raw.get("alignment_mode", "union")).strip().lower()
        if alignment_mode not in {"union", "body_anchor", "rect_center", "raw_cell"}:
            alignment_mode = "union"

        offset_x = self._safe_int(raw.get("offset_x"), 0)
        offset_y = self._safe_int(raw.get("offset_y"), 0)
        spacing_x = self._safe_int(raw.get("spacing_x"), 0)
        spacing_y = self._safe_int(raw.get("spacing_y"), 0)
        step_x = self._safe_positive_int(raw.get("step_x"), -1)
        step_y = self._safe_positive_int(raw.get("step_y"), -1)

        offset_pair = raw.get("offset")
        if isinstance(offset_pair, list) and len(offset_pair) == 2:
            offset_x = self._safe_int(offset_pair[0], offset_x)
            offset_y = self._safe_int(offset_pair[1], offset_y)

        spacing_pair = raw.get("spacing")
        if isinstance(spacing_pair, list) and len(spacing_pair) == 2:
            spacing_x = self._safe_int(spacing_pair[0], spacing_x)
            spacing_y = self._safe_int(spacing_pair[1], spacing_y)
        step_pair = raw.get("step")
        if isinstance(step_pair, list) and len(step_pair) == 2:
            step_x = self._safe_positive_int(step_pair[0], step_x)
            step_y = self._safe_positive_int(step_pair[1], step_y)

        cell_width = raw.get("cell_width")
        cell_height = raw.get("cell_height")
        cell_pair = raw.get("cell_size")
        if isinstance(cell_pair, list) and len(cell_pair) == 2:
            cell_width = cell_pair[0]
            cell_height = cell_pair[1]
        parsed_cell_w = self._safe_positive_int(cell_width, -1)
        parsed_cell_h = self._safe_positive_int(cell_height, -1)
        use_explicit_cells = parsed_cell_w > 0 and parsed_cell_h > 0

        if use_explicit_cells:
            eff_step_x = step_x if step_x > 0 else (parsed_cell_w + spacing_x)
            eff_step_y = step_y if step_y > 0 else (parsed_cell_h + spacing_y)
            max_w = offset_x + (max(0, columns - 1) * eff_step_x) + parsed_cell_w
            max_h = offset_y + (max(0, rows - 1) * eff_step_y) + parsed_cell_h
            sheet_w, sheet_h = sheet.get_size()
            if max_w > sheet_w or max_h > sheet_h:
                raise ValueError(
                    f"Character settings exceed sheet bounds for {sheet_path.name}: "
                    f"need {max_w}x{max_h}, got {sheet_w}x{sheet_h}"
                )
            detect_content_rect = False
        else:
            parsed_cell_w = None
            parsed_cell_h = None

        frame_columns = self._parse_frame_columns(raw.get("frame_columns"), columns=columns)
        normalize_canvas = bool(raw.get("normalize_canvas", True))
        component_pick = str(raw.get("component_pick", "none")).strip().lower()
        if component_pick not in {"none", "leftmost", "rightmost", "largest"}:
            component_pick = "none"
        output_w = raw.get("output_width")
        output_h = raw.get("output_height")
        output_pair = raw.get("output_size")
        if isinstance(output_pair, list) and len(output_pair) == 2:
            output_w = output_pair[0]
            output_h = output_pair[1]
        parsed_output_w = self._safe_positive_int(output_w, -1)
        parsed_output_h = self._safe_positive_int(output_h, -1)
        if parsed_output_w <= 0 or parsed_output_h <= 0:
            parsed_output_w = None
            parsed_output_h = None
        bbox_padding = self._safe_non_negative_int(raw.get("bbox_padding"), runtime.bbox_padding)
        parsed_body_height = self._safe_positive_int(raw.get("body_height"), -1)
        if parsed_body_height <= 0:
            parsed_body_height = None
        body_scale_min = self._safe_float(raw.get("body_scale_min"), runtime.body_scale_min)
        body_scale_max = self._safe_float(raw.get("body_scale_max"), runtime.body_scale_max)
        if body_scale_min <= 0.0:
            body_scale_min = runtime.body_scale_min
        if body_scale_max < body_scale_min:
            body_scale_max = body_scale_min
        foot_margin = self._safe_non_negative_int(raw.get("foot_margin"), 0)
        mirror_directions = self._parse_mirror_directions(raw.get("mirror_directions"))
        chroma_key = bool(raw.get("chroma_key", runtime.chroma_key))
        chroma_green_delta = self._safe_non_negative_int(
            raw.get("chroma_green_delta"),
            runtime.chroma_green_delta,
        )
        chroma_green_min = self._safe_non_negative_int(
            raw.get("chroma_green_min"),
            runtime.chroma_green_min,
        )
        chroma_soften_spill = bool(raw.get("chroma_soften_spill", runtime.chroma_soften_spill))
        chroma_spill_green_delta = self._safe_non_negative_int(
            raw.get("chroma_spill_green_delta"),
            runtime.chroma_spill_green_delta,
        )
        chroma_spill_green_min = self._safe_non_negative_int(
            raw.get("chroma_spill_green_min"),
            runtime.chroma_spill_green_min,
        )

        return SpriteSheetRuntimeSettings(
            columns=columns,
            rows=rows,
            row_by_direction=row_map,
            detect_content_rect=detect_content_rect,
            offset_x=offset_x,
            offset_y=offset_y,
            cell_width=parsed_cell_w,
            cell_height=parsed_cell_h,
            spacing_x=spacing_x,
            spacing_y=spacing_y,
            alignment_mode=alignment_mode,
            frame_columns=frame_columns,
            normalize_canvas=normalize_canvas,
            component_pick=component_pick,
            output_width=parsed_output_w,
            output_height=parsed_output_h,
            step_x=(step_x if step_x > 0 else None),
            step_y=(step_y if step_y > 0 else None),
            bbox_padding=bbox_padding,
            body_height=parsed_body_height,
            body_scale_min=body_scale_min,
            body_scale_max=body_scale_max,
            foot_margin=foot_margin,
            mirror_directions=mirror_directions,
            chroma_key=chroma_key,
            chroma_green_delta=chroma_green_delta,
            chroma_green_min=chroma_green_min,
            chroma_soften_spill=chroma_soften_spill,
            chroma_spill_green_delta=chroma_spill_green_delta,
            chroma_spill_green_min=chroma_spill_green_min,
        )

    def _load_sheet_settings_for_file(self, sheet_path: Path) -> dict[str, object] | None:
        for path in self._settings_candidate_paths(sheet_path):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            selected = self._select_settings_for_sheet(raw, sheet_path, path.parent)
            if selected is not None:
                return selected
        return None

    def _settings_candidate_paths(self, sheet_path: Path) -> list[Path]:
        character_root = self._find_character_root(sheet_path)
        if character_root is not None:
            preferred = character_root / "settings.json"
            legacy = character_root / "sheet_settings.json"
            if preferred.exists() and preferred.is_file():
                return [preferred, legacy] if legacy.exists() and legacy.is_file() else [preferred]
            if legacy.exists() and legacy.is_file():
                return [legacy]
            return []

        # Strict standard is preferred, but keep a single fallback for non-character assets.
        fallback_preferred = sheet_path.parent / "settings.json"
        fallback_legacy = sheet_path.parent / "sheet_settings.json"
        if fallback_preferred.exists() and fallback_preferred.is_file():
            return [fallback_preferred, fallback_legacy] if fallback_legacy.exists() and fallback_legacy.is_file() else [fallback_preferred]
        if fallback_legacy.exists() and fallback_legacy.is_file():
            return [fallback_legacy]
        return []

    def _find_character_root(self, sheet_path: Path) -> Path | None:
        current = sheet_path.parent
        while True:
            marker = current / "character.json"
            if marker.exists() and marker.is_file():
                return current
            settings_marker = current / "settings.json"
            if settings_marker.exists() and settings_marker.is_file():
                return current
            if current.parent.name == "characters":
                return current
            if current.name == "characters":
                return None
            if current.parent == current:
                return None
            current = current.parent

    def _select_settings_for_sheet(
        self,
        raw: object,
        sheet_path: Path,
        root_dir: Path,
    ) -> dict[str, object] | None:
        if not isinstance(raw, dict):
            return None

        mapping_raw = raw.get("files", raw.get("sheets"))
        defaults_raw = raw.get("defaults")
        profiles_raw = raw.get("profiles")
        mapping = mapping_raw if isinstance(mapping_raw, dict) else None
        defaults = defaults_raw if isinstance(defaults_raw, dict) else None
        profiles = profiles_raw if isinstance(profiles_raw, dict) else None

        merged: dict[str, object] = {}
        if defaults is not None:
            merged.update(defaults)

        selected_spec: object | None = None
        if mapping is not None:
            keys = [sheet_path.name]
            try:
                rel = sheet_path.relative_to(root_dir).as_posix()
                keys.insert(0, rel)
                keys.append(f"./{rel}")
            except ValueError:
                pass
            for key in keys:
                if key in mapping:
                    selected_spec = mapping[key]
                    break
        if isinstance(selected_spec, str) and profiles is not None:
            selected_spec = profiles.get(selected_spec)
        if isinstance(selected_spec, dict):
            merged.update(selected_spec)

        if merged:
            return merged

        # Backward compatibility: single-file settings payload.
        if any(
            key in raw
            for key in (
                "columns",
                "rows",
                "row_by_direction",
                "cell_size",
                "cell_width",
                "cell_height",
                "frame_columns",
            )
        ):
            return raw
        return None

    def _cache_variant_token(self, sheet_path: Path) -> str:
        token_parts = ["walk_v9"]
        try:
            stat = sheet_path.stat()
            token_parts.append(f"sheet:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            token_parts.append("sheet:err")
        candidates = self._settings_candidate_paths(sheet_path)
        if not candidates:
            token_parts.append("no_settings")
            return "_".join(token_parts)

        for path in candidates:
            try:
                token_parts.append(f"{path.name}:{path.stat().st_mtime_ns}")
            except OSError:
                token_parts.append(f"{path.name}:err")
        return "_".join(token_parts)

    def _parse_direction_rows(
        self,
        raw: object,
        *,
        fallback: dict[Direction, int],
    ) -> dict[Direction, int]:
        out = dict(fallback)
        if not isinstance(raw, dict):
            return out
        for key, value in raw.items():
            direction = self._direction_from_token(key)
            if direction is None:
                continue
            out[direction] = self._safe_non_negative_int(value, out[direction])
        return out

    def _trim_top_fringe_noise(self, frame: pygame.Surface) -> pygame.Surface:
        alpha_cutoff = self._config.alpha_component_cutoff
        alpha = pygame.surfarray.array_alpha(frame)
        if alpha.size == 0:
            return frame
        solid = alpha >= alpha_cutoff
        if not np.any(solid):
            return frame

        # Count opaque pixels per scanline.
        row_counts = np.sum(solid, axis=0).astype(np.int32)  # (h,)
        max_row = int(row_counts.max())
        if max_row <= 0:
            return frame

        dense_threshold = max(10, int(max_row * 0.20))
        first_dense = -1
        for y, count in enumerate(row_counts):
            if int(count) >= dense_threshold:
                first_dense = y
                break
        if first_dense <= 0:
            return frame

        # Remove only very sparse rows above the first dense row.
        thin_threshold = max(2, int(max_row * 0.12))
        rows_to_clear = [y for y in range(first_dense) if int(row_counts[y]) <= thin_threshold]
        if not rows_to_clear:
            return frame

        out = frame.copy()
        alpha_px = pygame.surfarray.pixels_alpha(out)
        for y in rows_to_clear:
            alpha_px[:, y] = 0
        del alpha_px
        return out

    def _parse_frame_columns(self, raw: object, *, columns: int) -> list[int] | None:
        if not isinstance(raw, list):
            return None
        out: list[int] = []
        for value in raw:
            idx = self._safe_non_negative_int(value, -1)
            if idx < 0 or idx >= columns:
                continue
            out.append(idx)
        return out if out else None

    def _parse_mirror_directions(self, raw: object) -> dict[Direction, Direction]:
        if not isinstance(raw, dict):
            return {}
        out: dict[Direction, Direction] = {}
        for target_raw, source_raw in raw.items():
            target = self._direction_from_token(target_raw)
            source = self._direction_from_token(source_raw)
            if target is None or source is None or target == source:
                continue
            out[target] = source
        return out

    def _filter_frame_component(self, frame: pygame.Surface, mode: str) -> pygame.Surface:
        alpha_cutoff = self._config.alpha_component_cutoff
        # Keep low threshold here so tiny detached artifacts (often 1-3 px tall strips
        # above diagonal rows) are still detected and can be removed.
        components = self._extract_components(frame, alpha_cutoff=alpha_cutoff, min_area=8)
        if len(components) <= 1:
            return frame

        largest_area = max(rect.width * rect.height for rect in components)
        meaningful = [r for r in components if (r.width * r.height) >= max(40, int(largest_area * 0.12))]
        if not meaningful:
            meaningful = components

        if mode == "leftmost":
            selected = min(meaningful, key=lambda r: (r.centerx, -r.width * r.height))
        elif mode == "rightmost":
            selected = max(meaningful, key=lambda r: (r.centerx, r.width * r.height))
        elif mode == "largest":
            selected = max(meaningful, key=lambda r: r.width * r.height)
        else:
            return frame

        pad = 6
        keep_zone = selected.inflate(pad * 2, pad * 2)
        down_allow = max(14, int(selected.height * 0.32))
        out = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
        for rect in components:
            if rect == selected or keep_zone.colliderect(rect):
                out.blit(frame, (rect.x, rect.y), rect)
                continue
            # Keep detached footwear-like islands: below the body and horizontally close.
            below_body = rect.top >= (selected.centery - 4) and rect.top <= (selected.bottom + down_allow)
            x_overlap = min(rect.right, selected.right) - max(rect.x, selected.x)
            near_x = x_overlap > 0 or abs(rect.centerx - selected.centerx) <= max(10, selected.width // 3)
            if below_body and near_x:
                out.blit(frame, (rect.x, rect.y), rect)
        return out

    def _extract_components(
        self,
        surface: pygame.Surface,
        *,
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

    def _normalize_direction_canvas(
        self,
        frames_by_direction: dict[Direction, list[pygame.Surface]],
        runtime: SpriteSheetRuntimeSettings,
    ) -> dict[Direction, list[pygame.Surface]]:
        if runtime.output_width is not None and runtime.output_height is not None:
            max_w = runtime.output_width
            max_h = runtime.output_height
        else:
            max_w = 1
            max_h = 1
            for frames in frames_by_direction.values():
                for frame in frames:
                    max_w = max(max_w, frame.get_width())
                    max_h = max(max_h, frame.get_height())

        normalized: dict[Direction, list[pygame.Surface]] = {}
        for direction, frames in frames_by_direction.items():
            out: list[pygame.Surface] = []
            for frame in frames:
                canvas = pygame.Surface((max_w, max_h), pygame.SRCALPHA)
                sw, sh = frame.get_size()
                draw = frame
                if sw > max_w or sh > max_h:
                    scale = min(max_w / max(1, sw), max_h / max(1, sh))
                    out_w = max(1, int(round(sw * scale)))
                    out_h = max(1, int(round(sh * scale)))
                    draw = pygame.transform.scale(frame, (out_w, out_h))
                    sw, sh = out_w, out_h
                x = (max_w - sw) // 2
                y = max(0, max_h - sh - runtime.foot_margin)
                canvas.blit(draw, (x, y))
                out.append(canvas)
            normalized[direction] = out
        return normalized

    def _normalize_body_height(
        self,
        frames_by_direction: dict[Direction, list[pygame.Surface]],
        *,
        target_height: int,
        scale_min: float,
        scale_max: float,
        foot_margin: int,
    ) -> dict[Direction, list[pygame.Surface]]:
        if target_height <= 0:
            return frames_by_direction

        normalized: dict[Direction, list[pygame.Surface]] = {}
        for direction, frames in frames_by_direction.items():
            out: list[pygame.Surface] = []
            for frame in frames:
                canvas_w, canvas_h = frame.get_size()
                body = frame.get_bounding_rect(min_alpha=self._config.alpha_component_cutoff)
                if body.height <= 0:
                    out.append(frame)
                    continue
                target_h = min(target_height, max(1, canvas_h - foot_margin))
                scale = target_h / max(1.0, float(body.height))
                # Keep scaling safe; this is stabilization, not stylization.
                scale = max(scale_min, min(scale_max, scale))
                if abs(scale - 1.0) < 0.01:
                    out.append(frame)
                    continue

                body_sprite = frame.subsurface(body).copy()
                bw, bh = body_sprite.get_size()
                scaled_w = max(1, int(round(bw * scale)))
                scaled_h = max(1, int(round(bh * scale)))
                scaled = pygame.transform.scale(body_sprite, (scaled_w, scaled_h))

                new_canvas = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA)
                # Anchor by body center horizontally to avoid side-to-side jitter.
                body_center_x = body.x + body.width / 2.0
                dx = int(round(body_center_x - scaled_w / 2.0))
                dx = max(min(dx, canvas_w - scaled_w), 0)
                dy = max(0, canvas_h - scaled_h - foot_margin)
                new_canvas.blit(scaled, (dx, dy))
                out.append(new_canvas)
            normalized[direction] = out
        return normalized

    def _direction_from_token(self, value: object) -> Direction | None:
        token = str(value).strip().lower()
        aliases: dict[str, Direction] = {
            "down": Direction.DOWN,
            "up": Direction.UP,
            "left": Direction.LEFT,
            "right": Direction.RIGHT,
            "up_right": Direction.UP_RIGHT,
            "upright": Direction.UP_RIGHT,
            "up-right": Direction.UP_RIGHT,
            "up_left": Direction.UP_LEFT,
            "upleft": Direction.UP_LEFT,
            "up-left": Direction.UP_LEFT,
            "down_left": Direction.DOWN_LEFT,
            "downleft": Direction.DOWN_LEFT,
            "down-left": Direction.DOWN_LEFT,
            "down_right": Direction.DOWN_RIGHT,
            "downright": Direction.DOWN_RIGHT,
            "down-right": Direction.DOWN_RIGHT,
        }
        return aliases.get(token)

    def _safe_int(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_non_negative_int(self, value: object, default: int) -> int:
        parsed = self._safe_int(value, default)
        return max(0, parsed)

    def _safe_positive_int(self, value: object, default: int) -> int:
        parsed = self._safe_int(value, default)
        return parsed if parsed > 0 else default

    def _safe_float(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _detect_main_rect(self, frame: pygame.Surface, *, padding: int) -> pygame.Rect:
        alpha_cutoff = self._config.alpha_component_cutoff
        w, h = frame.get_size()
        alpha_arr = pygame.surfarray.array_alpha(frame)
        solid = alpha_arr >= alpha_cutoff
        if not np.any(solid):
            return frame.get_bounding_rect(min_alpha=1)

        solid_cols = np.any(solid, axis=1)
        solid_rows = np.any(solid, axis=0)
        min_x = int(np.argmax(solid_cols))
        max_x = int(w - 1 - np.argmax(solid_cols[::-1]))
        min_y = int(np.argmax(solid_rows))
        max_y = int(h - 1 - np.argmax(solid_rows[::-1]))

        pad = max(0, int(padding))
        x1 = max(0, min_x - pad)
        y1 = max(0, min_y - pad)
        x2 = min(w - 1, max_x + pad)
        y2 = min(h - 1, max_y + pad)
        return pygame.Rect(x1, y1, x2 - x1 + 1, y2 - y1 + 1)

    def _detect_content_rect(self, sheet: pygame.Surface) -> pygame.Rect:
        alpha_cutoff = self._config.alpha_component_cutoff
        alpha_arr = pygame.surfarray.array_alpha(sheet)  # (w, h)
        opaque = alpha_arr >= alpha_cutoff

        col_counts = np.sum(opaque, axis=1)  # (w,) solid pixels per x-column
        row_counts = np.sum(opaque, axis=0)  # (h,) solid pixels per y-row

        if not np.any(col_counts > 0):
            return sheet.get_rect()

        # Require each boundary column/row to hold at least 0.5% of the peak
        # column/row density, so lone stray pixels don't corrupt the content rect.
        col_threshold = max(2, int(col_counts.max() * 0.005))
        row_threshold = max(2, int(row_counts.max() * 0.005))
        significant_cols = col_counts >= col_threshold
        significant_rows = row_counts >= row_threshold

        if not np.any(significant_cols):
            return sheet.get_rect()

        w, h = sheet.get_size()
        min_x = int(np.argmax(significant_cols))
        max_x = int(w - 1 - np.argmax(significant_cols[::-1]))
        min_y = int(np.argmax(significant_rows))
        max_y = int(h - 1 - np.argmax(significant_rows[::-1]))

        return pygame.Rect(min_x, min_y, max(1, max_x - min_x + 1), max(1, max_y - min_y + 1))

    def _has_transparency(self, frames: list[pygame.Surface]) -> bool:
        alpha_cutoff = self._config.alpha_component_cutoff
        for frame in frames:
            alpha = pygame.surfarray.array_alpha(frame)
            if np.any(alpha < alpha_cutoff):
                return True
        return False

    def _sanitize_alpha_edges(self, frame: pygame.Surface) -> None:
        alpha_cutoff = self._config.alpha_component_cutoff
        rgb = pygame.surfarray.pixels3d(frame)      # (w, h, 3) — locked view
        alpha = pygame.surfarray.pixels_alpha(frame)  # (w, h) — locked view

        low = alpha < alpha_cutoff
        semi = (~low) & (alpha < 255)

        alpha[low] = 0
        rgb[low] = 0

        if np.any(semi):
            r = rgb[:, :, 0].astype(np.int32)
            g = rgb[:, :, 1].astype(np.int32)
            b = rgb[:, :, 2].astype(np.int32)
            g_limit = np.maximum(r, b) + 20
            spill = semi & (g > g_limit)
            if np.any(spill):
                rgb[:, :, 1] = np.where(spill, np.minimum(g, g_limit), g).astype(np.uint8)

        del rgb, alpha  # release surface pixel lock

    def _chroma_to_alpha(self, surface: pygame.Surface, *, green_delta: int, green_min: int) -> None:
        rgb = pygame.surfarray.pixels3d(surface)
        alpha = pygame.surfarray.pixels_alpha(surface)
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

    def _soften_green_spill(self, surface: pygame.Surface, *, green_delta: int, green_min: int) -> None:
        rgb = pygame.surfarray.pixels3d(surface)
        alpha = pygame.surfarray.pixels_alpha(surface)
        r = rgb[:, :, 0].astype(np.int32)
        g = rgb[:, :, 1].astype(np.int32)
        b = rgb[:, :, 2].astype(np.int32)
        spill = (
            (alpha > 0)
            & (g >= green_min)
            & (g >= r + green_delta)
            & (g >= b + green_delta)
        )
        if np.any(spill):
            # Keep contour antialiasing but suppress green halo.
            reduced_alpha = (alpha.astype(np.float32) * 0.35).astype(np.uint8)
            alpha[:, :] = np.where(spill, reduced_alpha, alpha)
            rgb[:, :, 1] = np.where(spill, np.minimum(g, np.maximum(r, b) + 8), g).astype(np.uint8)
        del rgb, alpha


class ScaledAnimationCache:
    def __init__(self, base_frames: dict[Direction, list[pygame.Surface]]) -> None:
        self._base_frames = base_frames
        self._cache: dict[int, dict[Direction, list[pygame.Surface]]] = {}

    def frames_for_height(self, target_height: int) -> dict[Direction, list[pygame.Surface]]:
        if target_height in self._cache:
            return self._cache[target_height]

        scaled: dict[Direction, list[pygame.Surface]] = {}
        for direction, frames in self._base_frames.items():
            source_h = frames[0].get_height()
            scale = max(0.05, target_height / source_h)
            scaled_size = (
                max(1, int(frames[0].get_width() * scale)),
                max(1, int(source_h * scale)),
            )
            scaled[direction] = [pygame.transform.scale(frame, scaled_size) for frame in frames]

        self._cache[target_height] = scaled
        return scaled
