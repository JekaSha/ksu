from __future__ import annotations

import math
from pathlib import Path

import pygame

from ksusha_game.application.input_controller import KeyboardInputController
from ksusha_game.config import GameConfig
from ksusha_game.domain.player import Player
from ksusha_game.infrastructure.frame_processing import FramePreprocessor, FrameProcessingConfig
from ksusha_game.infrastructure.sprite_sheet_loader import ScaledAnimationCache, SpriteSheetLoader
from ksusha_game.presentation.renderer import GameRenderer


class KsushaGame:
    def __init__(self, config: GameConfig) -> None:
        self._config = config

    def run(self) -> int:
        project_root = Path(__file__).resolve().parents[3]
        sheet_path = project_root / self._config.sprite_path

        if not sheet_path.exists():
            print(f"Не найден спрайт: {sheet_path}")
            return 1

        pygame.init()
        pygame.display.set_caption("Ksusha Walk")
        screen = pygame.display.set_mode(self._config.window.size, pygame.RESIZABLE)
        clock = pygame.time.Clock()

        frame_cfg = FrameProcessingConfig(
            alpha_component_cutoff=self._config.sprite_sheet.alpha_component_cutoff,
            crop_padding=self._config.sprite_sheet.crop_padding,
            bg_model_stable_tol=self._config.sprite_sheet.bg_model_stable_tol,
            bg_model_match_tol=self._config.sprite_sheet.bg_model_match_tol,
            bg_model_alpha_tol=self._config.sprite_sheet.bg_model_alpha_tol,
        )
        preprocessor = FramePreprocessor(frame_cfg)
        loader = SpriteSheetLoader(self._config.sprite_sheet, preprocessor)
        raw_frames = loader.load_walk_frames(sheet_path)
        scaled_frames = ScaledAnimationCache(raw_frames)

        input_controller = KeyboardInputController()
        renderer = GameRenderer(self._config)
        player = Player(
            x=self._config.window.size[0] * 0.5,
            y=self._config.window.size[1] * 0.5,
        )

        running = True
        while running:
            dt = clock.tick(self._config.window.fps) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

            width, height = screen.get_size()
            target_h = max(18, int(height * self._config.sprite_sheet.target_height_ratio))
            frames_by_dir = scaled_frames.frames_for_height(target_h)

            dx, dy = input_controller.read_direction()
            speed = min(width, height) * self._config.sprite_sheet.move_speed_ratio
            moving = player.apply_input(
                dx=dx,
                dy=dy,
                speed=speed,
                dt=dt,
                anim_fps=self._config.sprite_sheet.anim_fps,
            )

            current_frames = frames_by_dir[player.facing]
            sprite_w = current_frames[0].get_width()
            sprite_h = current_frames[0].get_height()
            player.clamp_to_bounds(max_x=width - sprite_w, max_y=height - sprite_h)

            current_frames = frames_by_dir[player.facing]
            frame_index = int(player.walk_time) % len(current_frames)
            current_frame = current_frames[frame_index]
            bob = math.sin(player.walk_time * 2.0 * math.pi / len(current_frames)) * (2 if moving else 0)

            renderer.render(screen, player, current_frame, bob)
            pygame.display.flip()

        pygame.quit()
        return 0
