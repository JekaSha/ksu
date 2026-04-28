from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pygame

from ksusha_game.domain.direction import Direction


class SpriteCache:
    """Disk cache for processed walk-frame sprites, keyed by source file mtime."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def load(self, source: Path, variant: str = "") -> dict[Direction, list[pygame.Surface]] | None:
        path = self._cache_path(source, variant=variant)
        if not path.exists():
            return None
        try:
            with path.open("rb") as f:
                data: dict[int, list[np.ndarray]] = pickle.load(f)
            return {
                Direction(dir_val): [_rgba_to_surface(arr) for arr in frames]
                for dir_val, frames in data.items()
            }
        except Exception:
            return None

    def save(self, source: Path, frames: dict[Direction, list[pygame.Surface]], variant: str = "") -> None:
        path = self._cache_path(source, variant=variant)
        self._evict_stale(source, keep=path)
        data = {
            direction.value: [_surface_to_rgba(surf) for surf in surfs]
            for direction, surfs in frames.items()
        }
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)

    def _cache_path(self, source: Path, *, variant: str = "") -> Path:
        mtime = source.stat().st_mtime_ns
        suffix = f"_{self._sanitize_token(variant)}" if variant else ""
        return self._dir / f"{source.stem}_{mtime}{suffix}.pkl"

    def _evict_stale(self, source: Path, keep: Path) -> None:
        for old in self._dir.glob(f"{source.stem}_*.pkl"):
            if old != keep:
                try:
                    old.unlink()
                except OSError:
                    pass

    def _sanitize_token(self, token: str) -> str:
        clean = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "_" for ch in token)
        return clean[:72] if clean else "v"


    def load_sprite_set(self, source: Path, key: str) -> list[pygame.Surface] | None:
        path = self._obj_cache_path(source, key)
        if not path.exists():
            return None
        try:
            with path.open("rb") as f:
                data: list[np.ndarray] = pickle.load(f)
            return [_rgba_to_surface(arr) for arr in data]
        except Exception:
            return None

    def save_sprite_set(self, source: Path, key: str, variants: list[pygame.Surface]) -> None:
        path = self._obj_cache_path(source, key)
        self._evict_stale(source, keep=path)
        data = [_surface_to_rgba(surf) for surf in variants]
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)

    def _obj_cache_path(self, source: Path, key: str) -> Path:
        mtime = source.stat().st_mtime_ns
        return self._dir / f"{source.stem}_{mtime}_{key}.pkl"


def _surface_to_rgba(surf: pygame.Surface) -> np.ndarray:
    rgb = pygame.surfarray.array3d(surf)       # (w, h, 3) uint8
    alpha = pygame.surfarray.array_alpha(surf)  # (w, h) uint8
    return np.dstack([rgb, alpha])              # (w, h, 4) uint8


def _rgba_to_surface(arr: np.ndarray) -> pygame.Surface:
    surf = pygame.Surface((arr.shape[0], arr.shape[1]), pygame.SRCALPHA)
    pygame.surfarray.blit_array(surf, arr[:, :, :3])
    alpha_px = pygame.surfarray.pixels_alpha(surf)
    alpha_px[:] = arr[:, :, 3]
    del alpha_px
    return surf
