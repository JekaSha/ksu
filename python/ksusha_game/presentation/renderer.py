from __future__ import annotations

import pygame

from ksusha_game.config import GameConfig
from ksusha_game.domain.direction import Direction
from ksusha_game.domain.player import Player


class GameRenderer:
    def __init__(self, config: GameConfig) -> None:
        self._config = config

    def render(self, screen: pygame.Surface, player: Player, frame: pygame.Surface, bob: float) -> None:
        screen.fill(self._config.window.background_color)
        left_dirs = {Direction.LEFT, Direction.UP_LEFT, Direction.DOWN_LEFT}
        direction = -1 if player.facing in left_dirs else 1
        self._draw_shadow(
            screen=screen,
            x_center=player.x + frame.get_width() / 2,
            y_bottom=player.y + frame.get_height(),
            sprite_w=frame.get_width(),
            direction=direction,
        )
        screen.blit(frame, (player.x, player.y + bob))

    def _draw_shadow(
        self,
        screen: pygame.Surface,
        x_center: float,
        y_bottom: float,
        sprite_w: int,
        direction: int,
    ) -> None:
        stretch = 0.92 if direction > 0 else 1.06
        shadow_w = int(sprite_w * 0.42 * stretch)
        shadow = pygame.Surface((shadow_w, self._config.shadow.height), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, self._config.shadow.color, shadow.get_rect())
        screen.blit(
            shadow,
            (x_center - shadow_w // 2, y_bottom - self._config.shadow.height // 2 + 10),
        )
