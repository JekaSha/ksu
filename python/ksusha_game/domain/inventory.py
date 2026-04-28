from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Inventory:
    base_capacity: int = 5
    capacity: int = 5
    slots: list[str | None] = field(default_factory=list)
    active_index: int = 0
    open: bool = True
    move_mode: bool = False
    move_source_index: int | None = None
    bonus_capacity: int = 0
    bonus_weight_limit_kg: float = 0.0

    def __post_init__(self) -> None:
        if self.base_capacity <= 0:
            self.base_capacity = 5
        if self.capacity <= 0:
            self.capacity = self.base_capacity
        self.capacity = max(self.base_capacity, self.capacity)
        if not self.slots:
            self.slots = [None for _ in range(self.capacity)]
        if len(self.slots) < self.capacity:
            self.slots.extend([None for _ in range(self.capacity - len(self.slots))])
        self.active_index = max(0, min(self.active_index, self.capacity - 1))

    def toggle_open(self) -> None:
        self.open = not self.open

    def ensure_storage(self, total_slots: int) -> None:
        if total_slots <= len(self.slots):
            return
        self.slots.extend([None for _ in range(total_slots - len(self.slots))])

    def set_extension(self, bonus_slots: int, bonus_weight_limit_kg: float = 0.0) -> bool:
        bonus = max(0, int(bonus_slots))
        limit = max(0.0, float(bonus_weight_limit_kg))
        new_capacity = self.base_capacity + bonus
        changed = (bonus != self.bonus_capacity) or (new_capacity != self.capacity) or (
            abs(limit - self.bonus_weight_limit_kg) > 1e-6
        )
        self.bonus_capacity = bonus
        self.bonus_weight_limit_kg = limit
        self.capacity = max(self.base_capacity, new_capacity)
        self.ensure_storage(self.capacity)
        self.active_index = max(0, min(self.active_index, self.capacity - 1))
        if self.move_source_index is not None and self.move_source_index >= self.capacity:
            self.cancel_move_mode()
        return changed

    def select_previous(self) -> None:
        if self.capacity <= 0:
            return
        self.active_index = (self.active_index - 1) % self.capacity

    def select_next(self) -> None:
        if self.capacity <= 0:
            return
        self.active_index = (self.active_index + 1) % self.capacity

    def extra_indices(self) -> range:
        return range(self.base_capacity, self.capacity)

    def is_extra_slot(self, index: int) -> bool:
        return self.base_capacity <= int(index) < self.capacity

    def _bottom_row_indices(self) -> list[int]:
        return [i for i in range(0, min(self.base_capacity, self.capacity))]

    def _top_row_indices(self) -> list[int]:
        return [i for i in range(self.base_capacity, self.capacity)]

    def _slot_column(self, slot_index: int) -> float:
        bottom = self._bottom_row_indices()
        top = self._top_row_indices()
        if slot_index in bottom:
            return float(bottom.index(slot_index))
        if slot_index in top:
            offset = (len(bottom) - len(top)) * 0.5
            return float(offset + top.index(slot_index))
        return 0.0

    def move_cursor_left(self) -> None:
        row = self._top_row_indices() if self.is_extra_slot(self.active_index) else self._bottom_row_indices()
        if not row:
            return
        idx = row.index(self.active_index) if self.active_index in row else 0
        self.active_index = row[(idx - 1) % len(row)]

    def move_cursor_right(self) -> None:
        row = self._top_row_indices() if self.is_extra_slot(self.active_index) else self._bottom_row_indices()
        if not row:
            return
        idx = row.index(self.active_index) if self.active_index in row else 0
        self.active_index = row[(idx + 1) % len(row)]

    def move_cursor_up(self) -> None:
        top = self._top_row_indices()
        if not top:
            return
        if self.active_index in top:
            return
        current_col = self._slot_column(self.active_index)
        self.active_index = min(top, key=lambda i: abs(self._slot_column(i) - current_col))

    def move_cursor_down(self) -> None:
        bottom = self._bottom_row_indices()
        if self.active_index in bottom:
            return
        if not bottom:
            return
        current_col = self._slot_column(self.active_index)
        self.active_index = min(bottom, key=lambda i: abs(self._slot_column(i) - current_col))

    def begin_move_mode(self) -> bool:
        if self.capacity <= 0:
            return False
        if self.slots[self.active_index] is None:
            return False
        self.move_mode = True
        self.move_source_index = int(self.active_index)
        return True

    def cancel_move_mode(self) -> None:
        self.move_mode = False
        self.move_source_index = None

    def commit_move(self, target_index: int) -> tuple[int, int] | None:
        if not self.move_mode or self.move_source_index is None:
            return None
        src = int(self.move_source_index)
        dst = max(0, min(int(target_index), self.capacity - 1))
        if src == dst:
            self.cancel_move_mode()
            return (src, dst)
        self.slots[src], self.slots[dst] = self.slots[dst], self.slots[src]
        self.active_index = dst
        self.cancel_move_mode()
        return (src, dst)

    def selected_item(self) -> str | None:
        return self.slots[self.active_index]

    def add_item(self, item_id: str) -> bool:
        for i in range(self.capacity):
            slot = self.slots[i]
            if slot is None:
                self.slots[i] = item_id
                return True
        return False

    def remove_selected(self) -> str | None:
        item = self.selected_item()
        if item is None:
            return None
        self.slots[self.active_index] = None
        return item
