from __future__ import annotations

import pygame


class KeyboardInputController:
    def read_direction(self) -> tuple[int, int]:
        keys = pygame.key.get_pressed()
        move_right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        move_left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        move_down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        move_up = keys[pygame.K_UP] or keys[pygame.K_w]
        dx = int(move_right) - int(move_left)
        dy = int(move_down) - int(move_up)
        return dx, dy
