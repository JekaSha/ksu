from __future__ import annotations

from pathlib import Path

import pygame

from ksusha_game.config import SpriteSheetConfig
from ksusha_game.domain.direction import Direction
from ksusha_game.infrastructure.frame_processing import FramePreprocessor


class SpriteSheetLoader:
    def __init__(self, config: SpriteSheetConfig, preprocessor: FramePreprocessor) -> None:
        self._config = config
        self._preprocessor = preprocessor

    def load_walk_frames(self, sheet_path: Path) -> dict[Direction, list[pygame.Surface]]:
        sheet = pygame.image.load(str(sheet_path)).convert_alpha()
        result: dict[Direction, list[pygame.Surface]] = {}
        for direction, row in self._config.row_by_direction.items():
            result[direction] = self._load_row_frames(sheet, row)
        result[Direction.LEFT] = [
            pygame.transform.flip(frame, True, False) for frame in result[Direction.RIGHT]
        ]
        return result

    def _load_row_frames(self, sheet: pygame.Surface, row: int) -> list[pygame.Surface]:
        frame_w = sheet.get_width() // self._config.columns
        frame_h = sheet.get_height() // self._config.rows

        frames_raw: list[pygame.Surface] = []
        for col in range(self._config.columns):
            src = pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)
            frame = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
            frame.blit(sheet, (0, 0), src)
            frames_raw.append(frame)

        frames_raw = self._preprocessor.remove_static_row_background(frames_raw)
        rects = [self._preprocessor.detect_main_rect(frame) for frame in frames_raw]

        max_w = max(rect.width for rect in rects)
        max_h = max(rect.height for rect in rects)

        frames: list[pygame.Surface] = []
        for frame, rect in zip(frames_raw, rects):
            cropped = frame.subsurface(rect).copy()
            canvas = pygame.Surface((max_w, max_h), pygame.SRCALPHA)
            dst_x = (max_w - rect.width) // 2
            dst_y = max_h - rect.height
            canvas.blit(cropped, (dst_x, dst_y))
            frames.append(canvas)

        return frames


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
            scaled[direction] = [pygame.transform.smoothscale(frame, scaled_size) for frame in frames]

        self._cache[target_height] = scaled
        return scaled
