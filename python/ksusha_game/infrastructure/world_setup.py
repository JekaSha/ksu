from __future__ import annotations

import pygame

from ksusha_game.domain.world import RoomArea, WorldMap, WorldObject
from ksusha_game.infrastructure.object_sprites import ObjectSpriteLibrary


def apply_interior_physics(world: WorldMap, object_sprites: ObjectSpriteLibrary) -> None:
    """Clamp interior objects inside room walls and resolve initial overlaps between blockers."""
    interior_kinds = {"sofa", "plant", "backpack", "key", "ballon"}
    for obj in world.objects:
        if obj.kind not in interior_kinds:
            continue
        room = _room_for_point(world, obj.x, obj.y)
        if room is None or not room.walls_enabled:
            continue
        _clamp_inside_room(obj, room, world, object_sprites)

    for room in world.rooms:
        if not room.walls_enabled:
            continue
        blockers = [
            obj
            for obj in world.objects
            if obj.kind in interior_kinds
            and obj.blocking
            and _room_for_point(world, obj.x, obj.y) is room
        ]
        if len(blockers) < 2:
            continue
        for _ in range(8):
            moved = False
            for obj in blockers:
                if obj.kind == "sofa":
                    continue
                rect = _nominal_collider_rect(obj, object_sprites)
                for other in blockers:
                    if other.object_id == obj.object_id:
                        continue
                    other_rect = _nominal_collider_rect(other, object_sprites)
                    if not rect.colliderect(other_rect):
                        continue
                    overlap_x = min(rect.right, other_rect.right) - max(rect.left, other_rect.left)
                    overlap_y = min(rect.bottom, other_rect.bottom) - max(rect.top, other_rect.top)
                    if overlap_x <= 0 or overlap_y <= 0:
                        continue
                    if overlap_x <= overlap_y:
                        dir_x = -1.0 if rect.centerx < other_rect.centerx else 1.0
                        obj.x += dir_x * float(overlap_x + 1)
                    else:
                        dir_y = -1.0 if rect.centery < other_rect.centery else 1.0
                        obj.y += dir_y * float(overlap_y + 1)
                    _clamp_inside_room(obj, room, world, object_sprites)
                    rect = _nominal_collider_rect(obj, object_sprites)
                    moved = True
            if not moved:
                break


def object_collider_metrics(obj: WorldObject, sprite_w: int, sprite_h: int) -> tuple[int, int, float]:
    """Return (collider_w, collider_h, y_anchor) for an object given its sprite dimensions."""
    collider_w = int(obj.collider_w) if obj.collider_w is not None else int(sprite_w * 0.72)
    collider_h = int(obj.collider_h) if obj.collider_h is not None else int(sprite_h * 0.32)
    y_anchor = float(sprite_h) * 0.32

    if obj.kind == "plant":
        extra_up = max(12, int(sprite_h * 0.08))
        collider_h += extra_up
        y_anchor -= extra_up * 0.5
    elif obj.kind == "door":
        if obj.blocking and obj.state <= 0:
            collider_w = max(collider_w, int(sprite_w * 0.66))
            collider_h = max(collider_h, int(sprite_h * 0.64))
            y_anchor = float(sprite_h) * 0.18
        else:
            collider_w = max(collider_w, int(sprite_w * 0.54))
            collider_h = max(collider_h, int(sprite_h * 0.48))
            y_anchor = float(sprite_h) * 0.08
    elif obj.kind == "sofa":
        side_guard = max(14, int(sprite_w * 0.07))
        collider_w = max(collider_w, int(sprite_w * 0.96) + side_guard * 2)
        collider_h = max(collider_h, int(sprite_h * 0.56))
        y_anchor = min(y_anchor, float(sprite_h) * 0.30)
        extra_up = max(12, int(sprite_h * 0.07))
        collider_h += extra_up
        y_anchor -= extra_up * 0.55

    return max(8, collider_w), max(8, collider_h), float(y_anchor)


def _room_for_point(world: WorldMap, x: float, y: float) -> RoomArea | None:
    for room in world.rooms:
        if room.x <= x <= room.x + room.width and room.y <= y <= room.y + room.height:
            return room
    return None


def _clamp_inside_room(
    obj: WorldObject,
    room: RoomArea,
    world: WorldMap,
    object_sprites: ObjectSpriteLibrary,
) -> None:
    t = max(1, min(room.wall_thickness, room.width // 3, room.height // 3))
    top_t = (
        max(t, min(room.top_wall_height, room.height // 2))
        if room.top_wall_height > 0
        else t
    )
    interior_left = room.x + t + 4
    interior_right = room.x + room.width - t - 4
    interior_top = room.y + top_t + 4
    interior_bottom = room.y + room.height - t - 4
    if interior_left >= interior_right or interior_top >= interior_bottom:
        return

    nominal_w, nominal_h = object_sprites.nominal_world_size(obj.kind, obj)
    collider_w, collider_h, y_anchor = object_collider_metrics(obj, nominal_w, nominal_h)

    min_x = interior_left + collider_w / 2
    max_x = interior_right - collider_w / 2
    if min_x <= max_x:
        obj.x = max(min_x, min(max_x, obj.x))

    min_y = interior_top - y_anchor + collider_h / 2
    max_y = interior_bottom - y_anchor - collider_h / 2
    if min_y <= max_y:
        obj.y = max(min_y, min(max_y, obj.y))


def _nominal_collider_rect(obj: WorldObject, object_sprites: ObjectSpriteLibrary) -> pygame.Rect:
    nominal_w, nominal_h = object_sprites.nominal_world_size(obj.kind, obj)
    collider_w, collider_h, y_anchor = object_collider_metrics(obj, nominal_w, nominal_h)
    return pygame.Rect(
        int(obj.x - collider_w / 2),
        int(obj.y + y_anchor - collider_h / 2),
        max(8, int(collider_w)),
        max(8, int(collider_h)),
    )
