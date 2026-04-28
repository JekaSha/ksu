from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ksusha_game.infrastructure.sprite_sheet_loader import ScaledAnimationCache, SpriteSheetLoader


@dataclass(frozen=True)
class SkinAsset:
    name: str
    path: Path


class SkinLibrary:
    def __init__(self, textures_dir: Path, preferred_skin: Path) -> None:
        self._textures_dir = textures_dir
        self._preferred_skin = preferred_skin

    def discover(self) -> list[SkinAsset]:
        assets = [
            SkinAsset(name=path.stem, path=path)
            for path in sorted(self._textures_dir.glob("*.png"))
        ]
        if not assets:
            return []

        preferred_abs = self._preferred_skin.resolve()
        assets.sort(key=lambda asset: asset.path.resolve() != preferred_abs)
        return assets


class SkinRuntime:
    def __init__(self, skins: list[SkinAsset], loader: SpriteSheetLoader) -> None:
        if not skins:
            raise ValueError("SkinRuntime requires at least one skin")

        self._skins = skins
        self._loader = loader
        self._current_index = 0
        self._animation_cache_by_path: dict[Path, ScaledAnimationCache] = {}

    @property
    def current_skin(self) -> SkinAsset:
        return self._skins[self._current_index]

    def set_next(self) -> None:
        self._current_index = (self._current_index + 1) % len(self._skins)

    def set_previous(self) -> None:
        self._current_index = (self._current_index - 1) % len(self._skins)

    def current_animation_cache(self) -> ScaledAnimationCache:
        skin_path = self.current_skin.path
        cache = self._animation_cache_by_path.get(skin_path)
        if cache is not None:
            return cache

        raw_frames = self._loader.load_walk_frames(skin_path)
        cache = ScaledAnimationCache(raw_frames)
        self._animation_cache_by_path[skin_path] = cache
        return cache
