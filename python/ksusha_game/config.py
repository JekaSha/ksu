from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ksusha_game.domain.direction import Direction

_DEFAULT_CHARACTER_ID = "ksu"
_USER_SETTINGS_PATH = Path(".ksusha_game_settings.json")


@dataclass(frozen=True)
class WindowConfig:
    size: tuple[int, int] = (1280, 720)
    fps: int = 60
    background_color: tuple[int, int, int] = (12, 14, 22)


@dataclass(frozen=True)
class SpriteSheetConfig:
    columns: int = 5
    rows: int = 8
    row_by_direction: dict[Direction, int] = field(
        default_factory=lambda: {
            Direction.DOWN: 0,
            Direction.UP: 1,
            Direction.LEFT: 2,
            Direction.RIGHT: 3,
            Direction.UP_RIGHT: 5,
            Direction.UP_LEFT: 4,
            Direction.DOWN_LEFT: 7,
            Direction.DOWN_RIGHT: 6,
        }
    )
    anim_fps: float = 10.0
    target_height_ratio: float = 0.20
    move_speed_ratio: float = 0.43
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
    map_path: Path = Path("source/maps/main_map.json")
    skin_pool_dir: Path = Path("source/textures/characters/ksu/walk")
    sprite_path: Path = Path("source/textures/characters/ksu/walk/ksu.png")
    backpack_sprite_path: Path = Path("source/textures/characters/ksu/backpack/ksu_with_bag.png")
    interaction_distance: float = 140.0
    character_id: str = _DEFAULT_CHARACTER_ID


def load_user_settings(settings_path: Path | None = None) -> dict[str, object]:
    path = _USER_SETTINGS_PATH if settings_path is None else Path(settings_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_user_settings(settings: dict[str, object], settings_path: Path | None = None) -> None:
    path = _USER_SETTINGS_PATH if settings_path is None else Path(settings_path)
    payload = settings if isinstance(settings, dict) else {}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_character_id() -> str:
    env_character = os.getenv("KSU_CHARACTER", "").strip()
    if env_character:
        return env_character
    settings = load_user_settings()
    selected = str(settings.get("character_id", "")).strip()
    if selected:
        return selected
    return _DEFAULT_CHARACTER_ID


def _resolve_skin_pool_dir(character_id: str | None = None) -> Path:
    character = str(character_id or "").strip() or _resolve_character_id()
    state = os.getenv("KSU_STATE", "walk").strip() or "walk"
    return Path("source/textures/characters") / character / state


def _resolve_default_skin(skin_pool_dir: Path) -> Path:
    skin = os.getenv("KSU_SKIN", "ksu.png").strip() or "ksu.png"
    return skin_pool_dir / skin


def _load_character_manifest(character_dir: Path) -> dict | None:
    candidates = [character_dir / "settings.json", character_dir / "character.json"]
    for manifest_path in candidates:
        if not manifest_path.exists():
            continue
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        # Allow settings.json to wrap character manifest under "character".
        if "character" in raw and isinstance(raw.get("character"), dict):
            payload = raw["character"]
        else:
            payload = raw
        if isinstance(payload, dict):
            return payload
    return None


def list_available_characters(characters_root: Path = Path("source/textures/characters")) -> list[dict[str, str]]:
    root = Path(characters_root)
    out: list[dict[str, str]] = []
    if not root.exists():
        return out
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if entry.name.upper().endswith("_TEMPLATE"):
            continue
        manifest = _load_character_manifest(entry)
        if manifest is None:
            continue
        char_id = str(manifest.get("id", entry.name)).strip() or entry.name
        display_name = str(manifest.get("name", char_id.capitalize())).strip() or char_id
        out.append({"id": char_id, "name": display_name})
    return out


def resolve_character_config(character_id: str | None = None) -> tuple[Path, Path, Path, str]:
    character = str(character_id or "").strip() or _resolve_character_id()
    character_dir = Path("source/textures/characters") / character
    manifest = _load_character_manifest(character_dir)
    if manifest is None:
        fallback_character_dir = Path("source/textures/characters") / _DEFAULT_CHARACTER_ID
        fallback_skin_pool_dir = fallback_character_dir / "walk"
        return (
            fallback_skin_pool_dir,
            fallback_skin_pool_dir / "ksu.png",
            fallback_character_dir / "backpack/ksu_with_bag.png",
            _DEFAULT_CHARACTER_ID,
        )

    sheets_raw = manifest.get("sheets", {})
    sheets = sheets_raw if isinstance(sheets_raw, dict) else {}
    default_sheet_id = os.getenv("KSU_SHEET", "").strip() or str(manifest.get("default_sheet", "walk")).strip() or "walk"
    backpack_sheet_id = (
        os.getenv("KSU_BACKPACK_SHEET", "").strip()
        or str(manifest.get("backpack_sheet", "backpack")).strip()
        or default_sheet_id
    )

    def _sheet_path(sheet_id: str, fallback: Path) -> Path:
        token = str(sheets.get(sheet_id, "")).strip()
        if not token:
            return fallback
        path = character_dir / token
        return path if path.exists() else fallback

    fallback_skin_name = os.getenv("KSU_SKIN", "ksu.png").strip() or "ksu.png"
    fallback_walk = character_dir / "walk" / fallback_skin_name
    fallback_backpack = character_dir / "backpack/ksu_with_bag.png"
    sprite_path = _sheet_path(default_sheet_id, fallback_walk)
    backpack_path = _sheet_path(backpack_sheet_id, fallback_backpack if fallback_backpack.exists() else sprite_path)
    skin_pool_subdir = str(manifest.get("skin_pool_subdir", "")).strip()
    if skin_pool_subdir:
        skin_pool_dir = character_dir / skin_pool_subdir
    else:
        skin_pool_dir = sprite_path.parent

    return skin_pool_dir, sprite_path, backpack_path, character


def get_default_config() -> GameConfig:
    skin_pool_dir, sprite_path, backpack_path, character_id = resolve_character_config()
    return GameConfig(
        skin_pool_dir=skin_pool_dir,
        sprite_path=sprite_path,
        backpack_sprite_path=backpack_path,
        character_id=character_id,
    )
