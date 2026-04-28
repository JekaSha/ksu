from __future__ import annotations

from pathlib import Path
import random

import pygame


ROOT = Path(__file__).resolve().parents[1]
WALL_DIR = ROOT / "source" / "textures" / "walls"
FLOOR_DIR = ROOT / "source" / "textures" / "floors"


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def color_lerp(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )


def draw_top_wall(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)

    top_trim_dark = (48, 28, 17)
    top_trim_mid = (86, 52, 31)
    plaster_top = (190, 171, 140)
    plaster_bottom = (177, 157, 127)
    wainscot_top = (88, 53, 31)
    wainscot_bottom = (59, 34, 20)

    split1 = max(8, h // 8)
    split2 = int(h * 0.58)
    split3 = int(h * 0.84)

    for y in range(h):
        if y < split1:
            t = y / max(1, split1 - 1)
            c = color_lerp(top_trim_dark, top_trim_mid, t)
        elif y < split2:
            t = (y - split1) / max(1, split2 - split1 - 1)
            c = color_lerp(plaster_top, plaster_bottom, t)
        elif y < split3:
            t = (y - split2) / max(1, split3 - split2 - 1)
            c = color_lerp(wainscot_top, (70, 42, 25), t)
        else:
            t = (y - split3) / max(1, h - split3 - 1)
            c = color_lerp((52, 30, 19), wainscot_bottom, t)
        pygame.draw.line(surf, c, (0, y), (w, y))

    # Plaster speckles: light and sparse, no visual noise.
    rng = random.Random(17)
    speckle_rect = pygame.Rect(10, split1 + 8, w - 20, max(1, split2 - split1 - 16))
    dots = max(14, (speckle_rect.width * speckle_rect.height) // 1800)
    for _ in range(dots):
        x = rng.randint(speckle_rect.left, speckle_rect.right - 1)
        y = rng.randint(speckle_rect.top, speckle_rect.bottom - 1)
        shade = rng.randint(-10, 8)
        px = surf.get_at((x, y))
        surf.set_at(
            (x, y),
            (
                max(0, min(255, px.r + shade)),
                max(0, min(255, px.g + shade)),
                max(0, min(255, px.b + shade)),
                255,
            ),
        )

    # Vertical panel marks in wood section.
    for x in range(14, w, 54):
        pygame.draw.line(surf, (102, 69, 44, 96), (x, split2 + 2), (x, h - 6))

    pygame.draw.line(surf, (116, 80, 51), (0, split2), (w, split2))
    pygame.draw.line(surf, (39, 23, 14), (0, h - 2), (w, h - 2))
    pygame.draw.rect(surf, (34, 19, 11), pygame.Rect(0, 0, w, h), width=2)
    return surf


def draw_side_wall(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    for x in range(w):
        t = x / max(1, w - 1)
        c = color_lerp((56, 32, 20), (96, 59, 36), t)
        pygame.draw.line(surf, c, (x, 0), (x, h))
    pygame.draw.line(surf, (35, 20, 12), (1, 0), (1, h))
    pygame.draw.line(surf, (120, 78, 48), (w - 3, 0), (w - 3, h))
    pygame.draw.rect(surf, (34, 19, 11), pygame.Rect(0, 0, w, h), width=2)
    return surf


def draw_bottom_wall(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        c = color_lerp((44, 26, 16), (76, 47, 28), t)
        pygame.draw.line(surf, c, (0, y), (w, y))
    pygame.draw.line(surf, (22, 12, 9), (0, 1), (w, 1))
    pygame.draw.line(surf, (108, 70, 43), (0, h - 3), (w, h - 3))
    pygame.draw.rect(surf, (34, 19, 11), pygame.Rect(0, 0, w, h), width=2)
    return surf


def draw_top_opening(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    left_post = max(12, w // 10)
    right_post = left_post
    beam_h = max(16, h // 4)
    surf.blit(draw_side_wall((left_post, h)), (0, 0))
    surf.blit(draw_side_wall((right_post, h)), (w - right_post, 0))
    surf.blit(draw_bottom_wall((w, beam_h)), (0, 0))
    return surf


def draw_vertical_opening(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    cap_h = max(12, h // 10)
    surf.blit(draw_bottom_wall((w, cap_h)), (0, 0))
    surf.blit(draw_bottom_wall((w, cap_h)), (0, h - cap_h))
    return surf


def draw_door(size: tuple[int, int], opened: bool) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    frame = draw_top_opening((w, h))
    surf.blit(frame, (0, 0))

    frame_w = max(12, w // 12)
    door_w = w - frame_w * 2 - 10
    door_h = h - max(18, h // 5) - 6
    door_x = frame_w + 5
    door_y = h - door_h - 4

    if opened:
        leaf_w = max(18, door_w // 2)
        left = pygame.Surface((leaf_w, door_h), pygame.SRCALPHA)
        right = pygame.Surface((leaf_w, door_h), pygame.SRCALPHA)
        draw_door_leaf(left)
        draw_door_leaf(right)
        left = pygame.transform.rotate(left, 20)
        right = pygame.transform.rotate(right, -20)
        surf.blit(left, (door_x - 6, door_y + 4))
        surf.blit(right, (door_x + door_w - leaf_w + 2, door_y + 4))
    else:
        leaf = pygame.Surface((door_w, door_h), pygame.SRCALPHA)
        draw_door_leaf(leaf)
        surf.blit(leaf, (door_x, door_y))
    return surf


def draw_door_leaf(surface: pygame.Surface) -> None:
    w, h = surface.get_size()
    for x in range(w):
        t = x / max(1, w - 1)
        c = color_lerp((69, 40, 22), (96, 59, 35), t)
        pygame.draw.line(surface, c, (x, 0), (x, h))
    pygame.draw.rect(surface, (45, 25, 13), pygame.Rect(0, 0, w, h), width=3)
    inset = pygame.Rect(10, 12, w - 20, h - 24)
    pygame.draw.rect(surface, (61, 35, 18), inset, width=2)
    pygame.draw.rect(surface, (61, 35, 18), inset.inflate(-20, -26), width=2)
    knob_x = max(12, w - 18)
    knob_y = h // 2 + 6
    pygame.draw.circle(surface, (179, 139, 67), (knob_x, knob_y), 4)


def draw_floor_tile(size: tuple[int, int], base1: tuple[int, int, int], base2: tuple[int, int, int], seed: int) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    plank_h = max(14, h // 9)
    rng = random.Random(seed)

    y = 0
    while y < h:
        current_h = min(plank_h + rng.randint(-1, 1), h - y)
        tone_t = y / max(1, h - 1)
        tone = color_lerp(base1, base2, tone_t)
        for yy in range(y, y + current_h):
            pygame.draw.line(surf, tone, (0, yy), (w, yy))

        # Long staggered seams.
        cursor = rng.randint(18, 40)
        while cursor < w - 24:
            seam_h = max(6, current_h - 7)
            pygame.draw.line(surf, (92, 62, 40), (cursor, y + 3), (cursor, y + seam_h))
            cursor += rng.randint(130, 190)

        pygame.draw.line(surf, (110, 76, 49), (0, y), (w, y))
        pygame.draw.line(surf, (86, 58, 37), (0, y + current_h - 1), (w, y + current_h - 1))
        y += current_h

    # Very light grain, avoid noisy shimmer.
    specks = max(20, (w * h) // 1500)
    for _ in range(specks):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        delta = rng.randint(-4, 4)
        px = surf.get_at((x, y))
        surf.set_at(
            (x, y),
            (
                max(0, min(255, px.r + delta)),
                max(0, min(255, px.g + delta)),
                max(0, min(255, px.b + delta)),
                255,
            ),
        )

    return surf


def save(surface: pygame.Surface, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def main() -> None:
    pygame.init()

    save(draw_top_wall((192, 92)), WALL_DIR / "top_wall.png")
    save(draw_side_wall((34, 192)), WALL_DIR / "side_wall.png")
    save(draw_bottom_wall((192, 34)), WALL_DIR / "bottom_wall.png")
    save(draw_top_opening((140, 92)), WALL_DIR / "top_opening.png")
    save(draw_vertical_opening((34, 140)), WALL_DIR / "side_opening.png")
    save(draw_door((126, 148), opened=False), WALL_DIR / "door_closed.png")
    save(draw_door((126, 148), opened=True), WALL_DIR / "door_open.png")

    tile_size = 128
    atlas = pygame.Surface((tile_size * 3, tile_size * 2), pygame.SRCALPHA)
    tiles = [
        ("warm_oak", draw_floor_tile((tile_size, tile_size), (131, 89, 54), (111, 73, 44), 101)),
        ("warm_honey", draw_floor_tile((tile_size, tile_size), (146, 100, 59), (120, 79, 45), 202)),
        ("warm_walnut", draw_floor_tile((tile_size, tile_size), (111, 72, 43), (91, 58, 34), 303)),
        ("warm_ash", draw_floor_tile((tile_size, tile_size), (126, 93, 66), (104, 74, 52), 404)),
        ("warm_redwood", draw_floor_tile((tile_size, tile_size), (130, 79, 49), (104, 59, 35), 505)),
        ("warm_dark", draw_floor_tile((tile_size, tile_size), (95, 61, 36), (75, 46, 29), 606)),
    ]
    for idx, (_, tile) in enumerate(tiles):
        col = idx % 3
        row = idx // 3
        atlas.blit(tile, (col * tile_size, row * tile_size))
    save(atlas, FLOOR_DIR / "room_style_floors.png")


if __name__ == "__main__":
    main()
