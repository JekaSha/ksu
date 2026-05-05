from __future__ import annotations

import sys

from ksusha_game.config import get_default_config


def _enable_image_load_fallback(pygame_module) -> None:
    """Install a Pillow-based fallback for PNG/WebP when pygame lacks codecs."""
    original_load = pygame_module.image.load
    if getattr(original_load, "_ksu_fallback_wrapped", False):
        return

    def _wrapped_load(source, *args, **kwargs):
        try:
            return original_load(source, *args, **kwargs)
        except pygame_module.error as exc:
            message = str(exc).lower()
            needs_fallback = (
                "windows bmp" in message
                or "unsupported image format" in message
                or "unknown image type" in message
            )
            if not needs_fallback:
                raise
            try:
                from PIL import Image
            except Exception as pil_exc:
                raise pygame_module.error(
                    f"{exc}. This pygame build has no PNG/WebP decoder. "
                    "Install Pillow: python -m pip install Pillow"
                ) from pil_exc
            with Image.open(source) as img:
                rgba = img.convert("RGBA")
                surface = pygame_module.image.frombuffer(
                    rgba.tobytes(),
                    rgba.size,
                    "RGBA",
                )
                # frombuffer keeps a view into source bytes; copy for safe lifetime.
                return surface.copy()

    setattr(_wrapped_load, "_ksu_fallback_wrapped", True)
    pygame_module.image.load = _wrapped_load


def main() -> int:
    if sys.version_info < (3, 14):
        current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"Требуется Python 3.14+ (сейчас: {current})")
        print("Используй интерпретатор python3.14 и пересоздай venv.")
        return 1
    try:
        import pygame
    except ImportError:
        print("Не найден pygame. Установи зависимости:")
        print("  python3.14 -m pip install -r python/requirements.txt")
        return 1
    _enable_image_load_fallback(pygame)

    from ksusha_game.application.game import KsushaGame

    game = KsushaGame(get_default_config())
    return game.run()


if __name__ == "__main__":
    raise SystemExit(main())
