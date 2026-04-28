from __future__ import annotations

from ksusha_game.config import get_default_config


def main() -> int:
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("Не найден pygame. Установи зависимости:")
        print("  python3 -m pip install -r python/requirements.txt")
        return 1

    from ksusha_game.application.game import KsushaGame

    game = KsushaGame(get_default_config())
    return game.run()


if __name__ == "__main__":
    raise SystemExit(main())
