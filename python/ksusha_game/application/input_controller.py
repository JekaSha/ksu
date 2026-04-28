from __future__ import annotations

import pygame


class KeyboardInputController:
    _DOUBLE_TAP_WINDOW_SEC = 0.28
    _DOUBLE_TAP_BOOST_SEC = 0.30

    _MOVE_RIGHT_SCANCODES = (pygame.K_RIGHT, pygame.K_RIGHT)
    _MOVE_LEFT_SCANCODES = (pygame.K_LEFT, pygame.K_LEFT)
    _MOVE_DOWN_SCANCODES = (pygame.K_DOWN, pygame.K_DOWN)
    _MOVE_UP_SCANCODES = (pygame.K_UP, pygame.K_UP)

    _ACTION_BY_NAME: dict[str, tuple[int, int]] = {
        "select_prev": (pygame.KSCAN_A, pygame.K_a),
        "select_next": (pygame.KSCAN_D, pygame.K_d),
        "inventory_left": (pygame.KSCAN_A, pygame.K_a),
        "inventory_right": (pygame.KSCAN_D, pygame.K_d),
        "inventory_up": (pygame.KSCAN_W, pygame.K_w),
        "inventory_down": (pygame.KSCAN_S, pygame.K_s),
        "inventory_move": (pygame.KSCAN_Q, pygame.K_q),
        "pickup": (pygame.KSCAN_E, pygame.K_e),
        "drop": (pygame.KSCAN_G, pygame.K_g),
        "use": (pygame.KSCAN_R, pygame.K_r),
        "jump": (pygame.KSCAN_SPACE, pygame.K_SPACE),
        "reload": (pygame.KSCAN_F5, pygame.K_F5),
    }

    def __init__(self) -> None:
        self._last_tap_at: dict[str, float] = {}
        self._boost_until: dict[str, float] = {}
        self._pressed_scancodes: set[int] = set()
        self._pressed_keys: set[int] = set()

    def read_direction(self) -> tuple[int, int]:
        keys = pygame.key.get_pressed()
        move_right = self._is_pressed(keys, self._MOVE_RIGHT_SCANCODES)
        move_left = self._is_pressed(keys, self._MOVE_LEFT_SCANCODES)
        move_down = self._is_pressed(keys, self._MOVE_DOWN_SCANCODES)
        move_up = self._is_pressed(keys, self._MOVE_UP_SCANCODES)
        dx = int(move_right) - int(move_left)
        dy = int(move_down) - int(move_up)
        return dx, dy

    def is_action(self, event: pygame.event.Event, action_name: str) -> bool:
        scancode, fallback_key = self._ACTION_BY_NAME[action_name]
        event_scancode = getattr(event, "scancode", None)
        return event_scancode == scancode or event.key == fallback_key

    def is_action_pressed(self, keys: pygame.key.ScancodeWrapper, action_name: str) -> bool:
        scancode, fallback_key = self._ACTION_BY_NAME[action_name]
        if scancode in self._pressed_scancodes or fallback_key in self._pressed_keys:
            return True
        return bool(self._is_pressed_index(keys, scancode) or self._is_pressed_index(keys, fallback_key))

    def on_keydown(self, event: pygame.event.Event, now_sec: float) -> None:
        event_scancode = getattr(event, "scancode", None)
        if isinstance(event_scancode, int):
            self._pressed_scancodes.add(event_scancode)
        self._pressed_keys.add(int(event.key))
        direction = self._direction_from_event(event)
        if direction is None:
            return
        last_tap = self._last_tap_at.get(direction)
        if last_tap is not None and (now_sec - last_tap) <= self._DOUBLE_TAP_WINDOW_SEC:
            self._boost_until[direction] = now_sec + self._DOUBLE_TAP_BOOST_SEC
        self._last_tap_at[direction] = now_sec

    def on_keyup(self, event: pygame.event.Event) -> None:
        event_scancode = getattr(event, "scancode", None)
        if isinstance(event_scancode, int):
            self._pressed_scancodes.discard(event_scancode)
        self._pressed_keys.discard(int(event.key))

    def clear_pressed(self) -> None:
        self._pressed_scancodes.clear()
        self._pressed_keys.clear()

    def speed_multiplier(self, now_sec: float, dx: int, dy: int) -> float:
        if dx == 0 and dy == 0:
            return 1.0
        active_dirs: list[str] = []
        if dx > 0:
            active_dirs.append("right")
        elif dx < 0:
            active_dirs.append("left")
        if dy > 0:
            active_dirs.append("down")
        elif dy < 0:
            active_dirs.append("up")
        for direction in active_dirs:
            if self._boost_until.get(direction, 0.0) > now_sec:
                return 2.0
        return 1.0

    def _direction_from_event(self, event: pygame.event.Event) -> str | None:
        event_scancode = getattr(event, "scancode", None)
        if event.key == pygame.K_RIGHT or event_scancode == pygame.KSCAN_RIGHT:
            return "right"
        if event.key == pygame.K_LEFT or event_scancode == pygame.KSCAN_LEFT:
            return "left"
        if event.key == pygame.K_UP or event_scancode == pygame.KSCAN_UP:
            return "up"
        if event.key == pygame.K_DOWN or event_scancode == pygame.KSCAN_DOWN:
            return "down"
        return None

    def _is_pressed(self, keys: pygame.key.ScancodeWrapper, codes: tuple[int, int]) -> bool:
        primary, secondary = codes
        return bool(self._is_pressed_index(keys, primary) or self._is_pressed_index(keys, secondary))

    def _is_pressed_index(self, keys: pygame.key.ScancodeWrapper, index: int) -> bool:
        try:
            return bool(keys[index])
        except Exception:
            return False
