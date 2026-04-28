# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the game

```bash
# Setup (once)
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt

# Run
python python/ksusha_walk.py

# Hot-reload mode (auto-reloads source/ on file changes)
KSU_DEV_HOT=1 python python/ksusha_walk.py
```

There are no automated tests. Validation is done by running the game and exercising the feature manually. Press `F5` in-game to hot-reload the map and assets without restarting.

## Skin / character selection via env

```bash
KSU_CHARACTER=ksu KSU_STATE=walk KSU_SKIN=ksu.png python python/ksusha_walk.py
```

Skins are discovered from `source/textures/characters/<character>/<state>/`. Multiple `.png` files in that directory are treated as a skin pool — switch between them in-game with `Q`/`W` (inventory prev/next, which also cycles skins in the current implementation).

## Architecture

The project follows a strict 4-layer architecture enforced by the `skills/senior-gamedev-architect/SKILL.md` skill:

```
domain/         — pure data: Player, WorldMap, WorldObject, Inventory, Direction
application/    — game loop & orchestration: KsushaGame, KeyboardInputController
infrastructure/ — asset I/O: MapLoader, SpriteSheetLoader, SkinLibrary,
                  FloorTileset, WallSpriteLibrary, ObjectSpriteLibrary, FramePreprocessor
presentation/   — drawing: WorldRenderer, renderer.py (inventory/HUD)
```

**Key data flow:**
1. `MapLoader.load()` reads `source/maps/main_map.json` → returns `LoadedMap` (contains `WorldMap` + `FloorAtlasConfig`)
2. `KsushaGame.run()` owns the pygame loop; it holds `Player`, `Inventory`, `WorldMap`, and all infrastructure instances
3. `WorldRenderer.render()` takes everything as arguments (stateless draw pass) — no game state lives inside the renderer
4. `FramePreprocessor` strips chroma-green backgrounds from sprite sheets and builds per-frame alpha masks

**`WorldObject` state machine:** objects have an integer `state` field; `cycle_sprites`, `pickup_item_id`, `required_item_id`, `lock_key_sets`, and `transitions` drive all interactive behavior inside `KsushaGame`. No separate state-machine class — logic lives in `game.py`.

**Rendering layers (in order):** floor tiles → walls → spray tags (wall_top layer) → objects base pass → player → objects occluder pass → inventory HUD → fog → on-screen message.

## Map format

The single map file is `source/maps/main_map.json`. Top-level keys:

- `world` — dimensions, spawn point, `player_stats`, `fog`, `show_object_labels`
- `floors` — atlas PNG path, grid dimensions, named texture coords
- `rooms` — list of rectangular areas with `floor_texture` and optional wall/door parameters
- `object_kinds` — type-level defaults for objects (sprites, collider, layer flags)
- `objects` — per-instance placement, overrides, and interactive properties
- `balloon_specs` / `graffiti_specs` — spray-paint item definitions

The complete field reference is in `README.md`.

## Asset conventions

- Sprite sheets use **chroma-green** (`#00FF00`-ish) backgrounds — `FramePreprocessor` removes them at load time. Chroma-green variants of sheets are stored as `*_chroma_green.png` alongside originals.
- Object sprite sheets are parsed by `ObjectSpriteLibrary` using connected-component detection (not fixed grid slicing) to extract individual sprites from arbitrarily-laid-out sheets.
- Wall sprites live in `source/textures/walls/` (individual PNGs per wall segment type). Floor atlas is a single PNG referenced by the map.
- Graffiti / spray profiles are configured in `source/textures/graffity/<profile_id>/settings.json` and `source/textures/items/balons/<profile_id>/settings.json`.

## Config

`python/ksusha_game/config.py` — all tunable constants are frozen dataclasses (`WindowConfig`, `SpriteSheetConfig`, `ShadowConfig`, `GameConfig`). `DEFAULT_GAME_CONFIG` is the single instance passed into `KsushaGame`. Avoid scattering magic numbers into `game.py`.
