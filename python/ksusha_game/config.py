from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ksusha_game.domain.direction import Direction


@dataclass(frozen=True)
class WindowConfig:
    size: tuple[int, int] = (1280, 720)
    fps: int = 60
    background_color: tuple[int, int, int] = (12, 14, 22)


@dataclass(frozen=True)
class SpriteSheetConfig:
    columns: int = 6
    rows: int = 3
    row_by_direction: dict[Direction, int] = field(
        default_factory=lambda: {
            Direction.DOWN: 0,
            Direction.UP: 1,
            Direction.RIGHT: 2,
        }
    )
    anim_fps: float = 10.0
    target_height_ratio: float = 0.10
    move_speed_ratio: float = 0.35
    alpha_component_cutoff: int = 20
    crop_padding: int = 8
    bg_model_stable_tol: int = 10
    bg_model_match_tol: int = 28
    bg_model_alpha_tol: int = 28


@dataclass(frozen=True)
class ShadowConfig:
    color: tuple[int, int, int, int] = (10, 10, 14, 120)
    height: int = 28


@dataclass(frozen=True)
class GameConfig:
    window: WindowConfig = field(default_factory=WindowConfig)
    sprite_sheet: SpriteSheetConfig = field(default_factory=SpriteSheetConfig)
    shadow: ShadowConfig = field(default_factory=ShadowConfig)
    sprite_path: Path = Path("source/textures/ksusha.png")


DEFAULT_GAME_CONFIG = GameConfig()
