from __future__ import annotations

import sys

from ksusha_game.config import get_default_config


def main() -> int:
    if sys.version_info < (3, 14):
        current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"Требуется Python 3.14+ (сейчас: {current})")
        print("Используй интерпретатор python3.14 и пересоздай venv.")
        return 1
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("Не найден pygame. Установи зависимости:")
        print("  python3.14 -m pip install -r python/requirements.txt")
        return 1

    from ksusha_game.application.game import KsushaGame

    game = KsushaGame(get_default_config())
    return game.run()


if __name__ == "__main__":
    raise SystemExit(main())
