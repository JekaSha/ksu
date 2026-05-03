from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ksusha_game.domain.direction import Direction

_DEFAULT_CHARACTER_ID = "ksu"
_USER_SETTINGS_PATH = Path(".ksusha_game_settings.json")
_CHARACTER_REGISTRY_PATH = Path("source/textures/characters/characters.json")


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


def _load_character_registry(characters_root: Path = Path("source/textures/characters")) -> dict[str, dict]:
    root = Path(characters_root)
    registry_path = root / _CHARACTER_REGISTRY_PATH.name
    if not registry_path.exists():
        return {}
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    manifests: list[dict] = []
    if isinstance(raw, dict):
        chars_raw = raw.get("characters")
        if isinstance(chars_raw, list):
            manifests = [item for item in chars_raw if isinstance(item, dict)]
        elif raw and all(isinstance(v, dict) for v in raw.values()):
            # Alternative format: {"ksu": {...}, "jekas": {...}}
            for char_id, payload in raw.items():
                item = dict(payload)
                item.setdefault("id", str(char_id))
                manifests.append(item)

    out: dict[str, dict] = {}
    for manifest in manifests:
        payload = manifest.get("character") if isinstance(manifest.get("character"), dict) else manifest
        if not isinstance(payload, dict):
            continue
        char_id = str(payload.get("id", "")).strip()
        if not char_id:
            continue
        out[char_id] = payload
    return out


def _merge_character_manifests(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in {"sheets", "skills", "stats"}
            and isinstance(merged.get(key), dict)
            and isinstance(value, dict)
        ):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
            continue
        merged[key] = value
    return merged


def _resolve_character_manifest(character: str, characters_root: Path) -> dict | None:
    registry = _load_character_registry(characters_root)
    registry_manifest = registry.get(character)
    local_manifest = _load_character_manifest(characters_root / character)
    if registry_manifest is None:
        return local_manifest
    if local_manifest is None:
        return registry_manifest
    # Registry provides discoverability/listing, local file provides per-character runtime overrides.
    return _merge_character_manifests(registry_manifest, local_manifest)


def list_available_characters(characters_root: Path = Path("source/textures/characters")) -> list[dict[str, str]]:
    root = Path(characters_root)
    out: list[dict[str, str]] = []
    registry = _load_character_registry(root)
    if registry:
        for char_id, manifest in registry.items():
            display_name = str(manifest.get("name", char_id.capitalize())).strip() or char_id
            out.append({"id": char_id, "name": display_name})
        return out
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
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        fallback_character_dir = characters_root / _DEFAULT_CHARACTER_ID
        fallback_skin_pool_dir = fallback_character_dir / "walk"
        return (
            fallback_skin_pool_dir,
            fallback_skin_pool_dir / "ksu.png",
            fallback_character_dir / "backpack/ksu_with_bag.png",
            _DEFAULT_CHARACTER_ID,
        )
    resolved_character = str(manifest.get("id", character)).strip() or character
    character_dir = characters_root / resolved_character

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

    return skin_pool_dir, sprite_path, backpack_path, resolved_character


def resolve_character_physical_stats(character_id: str | None = None) -> tuple[float | None, float | None]:
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        return None, None

    stats_raw = manifest.get("stats")
    stats = stats_raw if isinstance(stats_raw, dict) else {}

    def _read_float(*values: object) -> float | None:
        for raw in values:
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
        return None

    weight_kg = _read_float(
        stats.get("weight_kg"),
        stats.get("weight"),
        manifest.get("weight_kg"),
        manifest.get("weight"),
    )
    height_cm = _read_float(
        stats.get("height_cm"),
        stats.get("height"),
        manifest.get("height_cm"),
        manifest.get("height"),
    )
    return weight_kg, height_cm


def resolve_character_skill(character_id: str | None, skill_id: str) -> bool:
    token = str(skill_id or "").strip().lower()
    if not token:
        return False
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        return False
    skills_raw = manifest.get("skills")
    if isinstance(skills_raw, dict):
        value = skills_raw.get(token)
        if value is None:
            return False
        return bool(value)
    if isinstance(skills_raw, list):
        return token in {str(item).strip().lower() for item in skills_raw if str(item).strip()}
    return False


def resolve_character_sheet_path(character_id: str | None, sheet_id: str) -> Path | None:
    sheet_token = str(sheet_id or "").strip()
    if not sheet_token:
        return None
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        return None
    resolved_character = str(manifest.get("id", character)).strip() or character
    character_dir = characters_root / resolved_character
    sheets_raw = manifest.get("sheets")
    sheets = sheets_raw if isinstance(sheets_raw, dict) else {}
    rel = str(sheets.get(sheet_token, "")).strip()
    if not rel:
        return None
    path = character_dir / rel
    if not path.exists():
        return None
    return path


def resolve_character_sheet_bundle(
    character_id: str | None,
) -> tuple[str, dict[str, Path], str, str]:
    """Return (resolved_character_id, sheet_paths, default_sheet_id, backpack_sheet_id)."""
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        fallback_dir = characters_root / _DEFAULT_CHARACTER_ID
        fallback_sheet = fallback_dir / "walk/ksu.png"
        return (
            _DEFAULT_CHARACTER_ID,
            {"walk": fallback_sheet, "backpack": fallback_dir / "backpack/ksu_with_bag.png"},
            "walk",
            "backpack",
        )

    resolved_character = str(manifest.get("id", character)).strip() or character
    character_dir = characters_root / resolved_character
    sheets_raw = manifest.get("sheets")
    sheets = sheets_raw if isinstance(sheets_raw, dict) else {}
    default_sheet_id = str(manifest.get("default_sheet", "walk")).strip() or "walk"
    backpack_sheet_id = str(manifest.get("backpack_sheet", default_sheet_id)).strip() or default_sheet_id

    out: dict[str, Path] = {}
    for key, rel in sheets.items():
        sheet_id = str(key).strip()
        rel_token = str(rel).strip()
        if not sheet_id or not rel_token:
            continue
        path = character_dir / rel_token
        if path.exists():
            out[sheet_id] = path

    # Keep compatibility fallbacks when manifest is incomplete.
    if default_sheet_id not in out:
        fallback = character_dir / "walk/ksu.png"
        if fallback.exists():
            out[default_sheet_id] = fallback
    if backpack_sheet_id not in out:
        fallback_backpack = character_dir / "backpack/ksu_with_bag.png"
        if fallback_backpack.exists():
            out[backpack_sheet_id] = fallback_backpack

    return resolved_character, out, default_sheet_id, backpack_sheet_id


def resolve_character_sheet_scale(character_id: str | None, sheet_id: str, default: float = 1.0) -> float:
    token = str(sheet_id or "").strip()
    if not token:
        return float(default)
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        return float(default)

    # Preferred: explicit per-sheet scale map.
    map_raw = manifest.get("sheet_scales")
    sheet_scales = map_raw if isinstance(map_raw, dict) else {}
    raw = sheet_scales.get(token)
    if raw is None:
        # Backward compatibility with old global keys.
        if token in {"skate", "skateboard"}:
            raw = manifest.get("render_scale_with_ride")
        else:
            raw = manifest.get("render_scale_without_ride")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if value <= 0:
        return float(default)
    return value


def resolve_character_render_scale(character_id: str | None, scale_key: str, default: float = 1.0) -> float:
    key = str(scale_key or "").strip()
    if not key:
        return float(default)
    characters_root = Path("source/textures/characters")
    character = str(character_id or "").strip() or _resolve_character_id()
    manifest = _resolve_character_manifest(character, characters_root)
    if manifest is None:
        return float(default)
    raw = manifest.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if value <= 0:
        return float(default)
    return value


def get_default_config() -> GameConfig:
    skin_pool_dir, sprite_path, backpack_path, character_id = resolve_character_config()
    return GameConfig(
        skin_pool_dir=skin_pool_dir,
        sprite_path=sprite_path,
        backpack_sprite_path=backpack_path,
        character_id=character_id,
    )
