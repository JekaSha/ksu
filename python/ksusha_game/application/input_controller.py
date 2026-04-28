from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class InputProfile:
    move_right: tuple[int, ...]
    move_left: tuple[int, ...]
    move_down: tuple[int, ...]
    move_up: tuple[int, ...]
    actions: dict[str, tuple[int, ...]]


class KeyboardInputController:
    _DOUBLE_TAP_WINDOW_SEC = 0.28
    _DOUBLE_TAP_BOOST_SEC = 0.30

    _PROFILES: dict[str, InputProfile] = {
        "p1": InputProfile(
            move_right=(pygame.K_RIGHT,),
            move_left=(pygame.K_LEFT,),
            move_down=(pygame.K_DOWN,),
            move_up=(pygame.K_UP,),
            actions={
                "select_prev": (pygame.K_a,),
                "select_next": (pygame.K_d,),
                "inventory_left": (pygame.K_a,),
                "inventory_right": (pygame.K_d,),
                "inventory_up": (pygame.K_w,),
                "inventory_down": (pygame.K_s,),
                "inventory_move": (pygame.K_q,),
                "pickup": (pygame.K_e,),
                "drop": (pygame.K_g,),
                "use": (pygame.K_r,),
                "jump": (pygame.K_SPACE,),
                "reload": (pygame.K_F5,),
            },
        ),
        "p2": InputProfile(
            move_right=(pygame.K_l,),
            move_left=(pygame.K_j,),
            move_down=(pygame.K_k,),
            move_up=(pygame.K_i,),
            actions={
                "select_prev": (pygame.K_f,),
                "select_next": (pygame.K_h,),
                "inventory_left": (pygame.K_f,),
                "inventory_right": (pygame.K_h,),
                "inventory_up": (pygame.K_t,),
                "inventory_down": (pygame.K_g,),
                "inventory_move": (pygame.K_r,),
                "pickup": (pygame.K_y,),
                "drop": (pygame.K_v,),
                "use": (pygame.K_u,),
                "jump": (pygame.K_b,),
            },
        ),
        "p3": InputProfile(
            move_right=(pygame.K_KP6,),
            move_left=(pygame.K_KP4,),
            move_down=(pygame.K_KP2,),
            move_up=(pygame.K_KP8,),
            actions={
                "select_prev": (pygame.K_KP7,),
                "select_next": (pygame.K_KP9,),
                "inventory_left": (pygame.K_KP7,),
                "inventory_right": (pygame.K_KP9,),
                "inventory_up": (pygame.K_KP8,),
                "inventory_down": (pygame.K_KP2,),
                "inventory_move": (pygame.K_KP0,),
                "pickup": (pygame.K_KP1,),
                "drop": (pygame.K_KP3,),
                "use": (pygame.K_KP5,),
                "jump": (pygame.K_KP_ENTER,),
            },
        ),
        "p4": InputProfile(
            move_right=(pygame.K_6,),
            move_left=(pygame.K_4,),
            move_down=(pygame.K_5,),
            move_up=(pygame.K_8,),
            actions={
                "select_prev": (pygame.K_1,),
                "select_next": (pygame.K_3,),
                "inventory_left": (pygame.K_1,),
                "inventory_right": (pygame.K_3,),
                "inventory_up": (pygame.K_8,),
                "inventory_down": (pygame.K_5,),
                "inventory_move": (pygame.K_2,),
                "pickup": (pygame.K_9,),
                "drop": (pygame.K_7,),
                "use": (pygame.K_0,),
                "jump": (pygame.K_BACKQUOTE,),
            },
        ),
        "p5": InputProfile(
            move_right=(pygame.K_p,),
            move_left=(pygame.K_o,),
            move_down=(pygame.K_SEMICOLON,),
            move_up=(pygame.K_LEFTBRACKET,),
            actions={
                "select_prev": (pygame.K_PERIOD,),
                "select_next": (pygame.K_SLASH,),
                "inventory_left": (pygame.K_PERIOD,),
                "inventory_right": (pygame.K_SLASH,),
                "inventory_up": (pygame.K_QUOTE,),
                "inventory_down": (pygame.K_RIGHTBRACKET,),
                "inventory_move": (pygame.K_COMMA,),
                "pickup": (pygame.K_MINUS,),
                "drop": (pygame.K_EQUALS,),
                "use": (pygame.K_BACKSLASH,),
                "jump": (pygame.K_RSHIFT,),
            },
        ),
    }
    _HINT_ACTIONS: tuple[tuple[str, str], ...] = (
        ("pickup", "pickup"),
        ("drop", "drop"),
        ("use", "use"),
        ("jump", "jump"),
        ("inventory_move", "move-slot"),
    )

    def __init__(self, profile_name: str = "p1") -> None:
        self._profile_name = profile_name if profile_name in self._PROFILES else "p1"
        profile = self._PROFILES[self._profile_name]
        self._move_right_codes = profile.move_right
        self._move_left_codes = profile.move_left
        self._move_down_codes = profile.move_down
        self._move_up_codes = profile.move_up
        self._action_by_name = profile.actions
        self._last_tap_at: dict[str, float] = {}
        self._boost_until: dict[str, float] = {}
        self._pressed_scancodes: set[int] = set()
        self._pressed_keys: set[int] = set()

    @classmethod
    def profile_control_hints(cls, profile_names: list[str]) -> list[str]:
        lines: list[str] = []
        for profile_name in profile_names:
            profile = cls._PROFILES.get(profile_name)
            if profile is None:
                continue
            move = cls._codes_label(profile.move_left + profile.move_right + profile.move_up + profile.move_down)
            parts = [f"{profile_name.upper()} move:{move}"]
            for action_name, short_label in cls._HINT_ACTIONS:
                codes = profile.actions.get(action_name, ())
                if not codes:
                    continue
                parts.append(f"{short_label}:{cls._codes_label(codes)}")
            lines.append(" | ".join(parts))
        return lines

    @staticmethod
    def _codes_label(codes: tuple[int, ...]) -> str:
        if not codes:
            return "-"
        labels: list[str] = []
        seen: set[str] = set()
        for code in codes:
            try:
                name = pygame.key.name(int(code))
            except Exception:
                name = str(int(code))
            label = name.upper()
            if label in seen:
                continue
            seen.add(label)
            labels.append(label)
        return "/".join(labels)

    def read_direction(self, keys: pygame.key.ScancodeWrapper | None = None) -> tuple[int, int]:
        pressed = pygame.key.get_pressed() if keys is None else keys
        move_right = self._is_pressed(pressed, self._move_right_codes)
        move_left = self._is_pressed(pressed, self._move_left_codes)
        move_down = self._is_pressed(pressed, self._move_down_codes)
        move_up = self._is_pressed(pressed, self._move_up_codes)
        dx = int(move_right) - int(move_left)
        dy = int(move_down) - int(move_up)
        return dx, dy

    def is_action(self, event: pygame.event.Event, action_name: str) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        mapped = self._action_by_name.get(action_name, ())
        return int(event.key) in mapped

    def is_action_pressed(self, keys: pygame.key.ScancodeWrapper, action_name: str) -> bool:
        mapped = self._action_by_name.get(action_name, ())
        if any(code in self._pressed_keys for code in mapped):
            return True
        return bool(any(self._is_pressed_index(keys, code) for code in mapped))

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
        if int(event.key) in self._move_right_codes:
            return "right"
        if int(event.key) in self._move_left_codes:
            return "left"
        if int(event.key) in self._move_up_codes:
            return "up"
        if int(event.key) in self._move_down_codes:
            return "down"
        return None

    def _is_pressed(self, keys: pygame.key.ScancodeWrapper, codes: tuple[int, ...]) -> bool:
        return bool(any(self._is_pressed_index(keys, code) for code in codes))

    def _is_pressed_index(self, keys: pygame.key.ScancodeWrapper, index: int) -> bool:
        try:
            return bool(keys[index])
        except Exception:
            return False
