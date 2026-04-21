from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class FrameProcessingConfig:
    alpha_component_cutoff: int
    crop_padding: int
    bg_model_stable_tol: int
    bg_model_match_tol: int
    bg_model_alpha_tol: int


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


class FramePreprocessor:
    def __init__(self, config: FrameProcessingConfig) -> None:
        self._cfg = config

    def remove_static_row_background(self, frames_raw: list[pygame.Surface]) -> list[pygame.Surface]:
        if not frames_raw:
            return frames_raw

        w, h = frames_raw[0].get_size()
        total = w * h
        count = len(frames_raw)
        stable_tol2 = self._cfg.bg_model_stable_tol * self._cfg.bg_model_stable_tol
        match_tol2 = self._cfg.bg_model_match_tol * self._cfg.bg_model_match_tol

        frame_pixels: list[list[pygame.Color]] = []
        for frame in frames_raw:
            frame_pixels.append([frame.get_at((x, y)) for y in range(h) for x in range(w)])

        model: list[tuple[int, int, int, int]] = [(0, 0, 0, 0)] * total
        stable = bytearray(total)

        for idx in range(total):
            r_vals = [int(frame_pixels[i][idx].r) for i in range(count)]
            g_vals = [int(frame_pixels[i][idx].g) for i in range(count)]
            b_vals = [int(frame_pixels[i][idx].b) for i in range(count)]
            a_vals = [int(frame_pixels[i][idx].a) for i in range(count)]
            mr = _median(r_vals)
            mg = _median(g_vals)
            mb = _median(b_vals)
            ma = _median(a_vals)
            model[idx] = (mr, mg, mb, ma)

            max_dev = 0
            for i in range(count):
                dr = r_vals[i] - mr
                dg = g_vals[i] - mg
                db = b_vals[i] - mb
                dev = dr * dr + dg * dg + db * db
                if dev > max_dev:
                    max_dev = dev
            if ma >= self._cfg.alpha_component_cutoff and max_dev <= stable_tol2:
                stable[idx] = 1

        bg_mask = bytearray(total)
        queue: deque[int] = deque()

        def seed(x: int, y: int) -> None:
            idx = y * w + x
            if stable[idx] and not bg_mask[idx]:
                bg_mask[idx] = 1
                queue.append(idx)

        for x in range(w):
            seed(x, 0)
            seed(x, h - 1)
        for y in range(1, h - 1):
            seed(0, y)
            seed(w - 1, y)

        while queue:
            cur = queue.popleft()
            x = cur % w
            y = cur // w
            if x > 0:
                left = cur - 1
                if stable[left] and not bg_mask[left]:
                    bg_mask[left] = 1
                    queue.append(left)
            if x < w - 1:
                right = cur + 1
                if stable[right] and not bg_mask[right]:
                    bg_mask[right] = 1
                    queue.append(right)
            if y > 0:
                up = cur - w
                if stable[up] and not bg_mask[up]:
                    bg_mask[up] = 1
                    queue.append(up)
            if y < h - 1:
                down = cur + w
                if stable[down] and not bg_mask[down]:
                    bg_mask[down] = 1
                    queue.append(down)

        cleaned_frames: list[pygame.Surface] = []
        for frame in frames_raw:
            cleaned = frame.copy()
            for idx in range(total):
                if not bg_mask[idx]:
                    continue
                c = frame.get_at((idx % w, idx // w))
                mr, mg, mb, ma = model[idx]
                if abs(int(c.a) - ma) > self._cfg.bg_model_alpha_tol:
                    continue
                dr = int(c.r) - mr
                dg = int(c.g) - mg
                db = int(c.b) - mb
                if dr * dr + dg * dg + db * db <= match_tol2:
                    cleaned.set_at((idx % w, idx // w), pygame.Color(0, 0, 0, 0))
            cleaned_frames.append(cleaned)

        return cleaned_frames

    def detect_main_rect(self, frame: pygame.Surface) -> pygame.Rect:
        w, h = frame.get_size()
        total = w * h
        solid = bytearray(total)
        visited = bytearray(total)

        for y in range(h):
            for x in range(w):
                idx = y * w + x
                if frame.get_at((x, y)).a >= self._cfg.alpha_component_cutoff:
                    solid[idx] = 1
                else:
                    visited[idx] = 1

        best_area = 0
        best_rect = frame.get_bounding_rect(min_alpha=1)

        def component_rect(seed: int) -> tuple[int, pygame.Rect]:
            visited[seed] = 1
            stack = [seed]
            area = 0
            x0 = seed % w
            y0 = seed // w
            min_x = max_x = x0
            min_y = max_y = y0

            while stack:
                cur = stack.pop()
                x = cur % w
                y = cur // w
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

                if x > 0:
                    left = cur - 1
                    if not visited[left] and solid[left]:
                        visited[left] = 1
                        stack.append(left)
                    else:
                        visited[left] = visited[left] or 1
                if x < w - 1:
                    right = cur + 1
                    if not visited[right] and solid[right]:
                        visited[right] = 1
                        stack.append(right)
                    else:
                        visited[right] = visited[right] or 1
                if y > 0:
                    up = cur - w
                    if not visited[up] and solid[up]:
                        visited[up] = 1
                        stack.append(up)
                    else:
                        visited[up] = visited[up] or 1
                if y < h - 1:
                    down = cur + w
                    if not visited[down] and solid[down]:
                        visited[down] = 1
                        stack.append(down)
                    else:
                        visited[down] = visited[down] or 1

            x1 = max(0, min_x - self._cfg.crop_padding)
            y1 = max(0, min_y - self._cfg.crop_padding)
            x2 = min(w - 1, max_x + self._cfg.crop_padding)
            y2 = min(h - 1, max_y + self._cfg.crop_padding)
            return area, pygame.Rect(x1, y1, x2 - x1 + 1, y2 - y1 + 1)

        center = (h // 2) * w + (w // 2)
        if solid[center]:
            best_area, best_rect = component_rect(center)
        else:
            for radius in range(1, max(w, h)):
                found = False
                min_x = max(0, w // 2 - radius)
                max_x = min(w - 1, w // 2 + radius)
                min_y = max(0, h // 2 - radius)
                max_y = min(h - 1, h // 2 + radius)
                for y in range(min_y, max_y + 1):
                    for x in range(min_x, max_x + 1):
                        idx = y * w + x
                        if solid[idx]:
                            best_area, best_rect = component_rect(idx)
                            found = True
                            break
                    if found:
                        break
                if found:
                    break

        for idx in range(total):
            if visited[idx] or not solid[idx]:
                continue

            area, rect = component_rect(idx)
            if area > best_area:
                best_area = area
                best_rect = rect

        return best_rect
