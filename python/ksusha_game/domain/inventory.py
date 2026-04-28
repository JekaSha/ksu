from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Inventory:
    capacity: int = 5
    slots: list[str | None] = field(default_factory=list)
    active_index: int = 0
    open: bool = True

    def __post_init__(self) -> None:
        if not self.slots:
            self.slots = [None for _ in range(self.capacity)]

    def toggle_open(self) -> None:
        self.open = not self.open

    def select_previous(self) -> None:
        self.active_index = (self.active_index - 1) % self.capacity

    def select_next(self) -> None:
        self.active_index = (self.active_index + 1) % self.capacity

    def selected_item(self) -> str | None:
        return self.slots[self.active_index]

    def add_item(self, item_id: str) -> bool:
        for i, slot in enumerate(self.slots):
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
