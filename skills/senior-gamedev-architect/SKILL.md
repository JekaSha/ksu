---
name: senior-gamedev-architect
description: Use when building or refactoring Python game projects where maintainable OOP architecture, clean patterns, and explicit separation of responsibilities are required.
---

# Senior GameDev Architect (Python)

Use this skill for Python game projects (pygame, arcade, custom engines) when the user wants production-grade structure.

## Contract

- Build maintainable, modular OOP architecture.
- No spaghetti code, no hidden side effects, no god objects.
- Prefer clarity over cleverness.
- Preserve gameplay behavior while improving architecture.

## Architecture Rules

1. Split by responsibility:
- `domain`: entities, value objects, game state invariants.
- `application`: orchestration/use-cases/game loop coordination.
- `infrastructure`: IO, assets, serialization, framework adapters.
- `presentation`: rendering, UI, scene drawing.

2. Follow SOLID:
- Single responsibility per class/module.
- Depend on abstractions where practical.
- Keep interfaces small and explicit.

3. Prefer explicit patterns where they reduce complexity:
- State pattern for game states/scenes.
- Strategy for interchangeable behaviors.
- Factory for controlled object creation.
- Repository for persistence/asset access abstractions.

4. Keep config centralized:
- Dataclasses or typed config objects.
- Avoid magic constants in gameplay code.

5. Keep gameplay deterministic where possible:
- Isolate randomness.
- Support fixed seeds for generation systems.

## Coding Standards

- Type hints required for public APIs.
- Short methods with clear names.
- Comments only for non-obvious decisions.
- Avoid tight coupling between input, update, and render.
- Handle missing assets/dependencies with explicit error messages.

## Refactor Workflow

1. Read current behavior and invariants.
2. Define target module boundaries.
3. Move code without changing behavior first.
4. Introduce abstractions and patterns incrementally.
5. Validate by running the game/tests.
6. Document final architecture and entrypoints.

## Output Checklist

- Project tree is understandable at a glance.
- Main loop is orchestration-only, not business-logic-heavy.
- Asset pipeline is isolated from domain logic.
- Domain objects are testable without renderer.
- README includes run instructions and architecture map.
