from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
import pygame


@dataclass(frozen=True)
class FrameProcessingConfig:
    alpha_component_cutoff: int
    crop_padding: int
    bg_model_stable_tol: int
    bg_model_match_tol: int
    bg_model_alpha_tol: int


class FramePreprocessor:
    def __init__(self, config: FrameProcessingConfig) -> None:
        self._cfg = config

    def remove_static_row_background(self, frames_raw: list[pygame.Surface]) -> list[pygame.Surface]:
        if not frames_raw:
            return frames_raw

        w, h = frames_raw[0].get_size()

        rgb_stack = np.stack([pygame.surfarray.array3d(f) for f in frames_raw])     # (n, w, h, 3)
        alpha_stack = np.stack([pygame.surfarray.array_alpha(f) for f in frames_raw])  # (n, w, h)

        model_rgb = np.median(rgb_stack, axis=0).astype(np.uint8)   # (w, h, 3)
        model_a = np.median(alpha_stack, axis=0).astype(np.uint8)   # (w, h)

        diffs = rgb_stack.astype(np.int32) - model_rgb[np.newaxis]  # (n, w, h, 3)
        max_dev_sq = np.max(np.sum(diffs ** 2, axis=-1), axis=0)    # (w, h)
        stable = (
            (model_a >= self._cfg.alpha_component_cutoff)
            & (max_dev_sq <= self._cfg.bg_model_stable_tol ** 2)
        )

        # Flood-fill from edges to find the connected background region.
        bg_mask = np.zeros((w, h), dtype=bool)
        queue: deque[int] = deque()

        def seed(x: int, y: int) -> None:
            if stable[x, y] and not bg_mask[x, y]:
                bg_mask[x, y] = True
                queue.append(y * w + x)

        for x in range(w):
            seed(x, 0)
            seed(x, h - 1)
        for y in range(1, h - 1):
            seed(0, y)
            seed(w - 1, y)

        while queue:
            cur = queue.popleft()
            x, y = cur % w, cur // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and stable[nx, ny] and not bg_mask[nx, ny]:
                    bg_mask[nx, ny] = True
                    queue.append(ny * w + nx)

        match_tol_sq = self._cfg.bg_model_match_tol ** 2
        alpha_tol = self._cfg.bg_model_alpha_tol

        cleaned_frames: list[pygame.Surface] = []
        for i, frame in enumerate(frames_raw):
            diff_a = np.abs(alpha_stack[i].astype(np.int32) - model_a.astype(np.int32)) <= alpha_tol
            diff_rgb_sq = np.sum(
                (rgb_stack[i].astype(np.int32) - model_rgb.astype(np.int32)) ** 2, axis=-1
            )
            remove = bg_mask & diff_a & (diff_rgb_sq <= match_tol_sq)

            cleaned = frame.copy()
            alpha_px = pygame.surfarray.pixels_alpha(cleaned)
            alpha_px[remove] = 0
            del alpha_px
            cleaned_frames.append(cleaned)

        return cleaned_frames

    def detect_main_rect(self, frame: pygame.Surface) -> pygame.Rect:
        w, h = frame.get_size()
        alpha_arr = pygame.surfarray.array_alpha(frame)  # (w, h)
        solid = alpha_arr >= self._cfg.alpha_component_cutoff

        if not np.any(solid):
            return frame.get_bounding_rect(min_alpha=1)

        # Fast numpy bounding box: find min/max x and y of solid pixels.
        solid_cols = np.any(solid, axis=1)  # (w,) — True for x columns with content
        solid_rows = np.any(solid, axis=0)  # (h,) — True for y rows with content
        min_x = int(np.argmax(solid_cols))
        max_x = int(w - 1 - np.argmax(solid_cols[::-1]))
        min_y = int(np.argmax(solid_rows))
        max_y = int(h - 1 - np.argmax(solid_rows[::-1]))

        pad = self._cfg.crop_padding
        x1 = max(0, min_x - pad)
        y1 = max(0, min_y - pad)
        x2 = min(w - 1, max_x + pad)
        y2 = min(h - 1, max_y + pad)
        return pygame.Rect(x1, y1, x2 - x1 + 1, y2 - y1 + 1)
