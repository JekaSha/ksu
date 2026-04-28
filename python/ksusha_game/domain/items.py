from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemDefinition:
    item_id: str
    name: str
    kind: str


BACKPACK_ITEM = ItemDefinition(
    item_id="backpack",
    name="Pink Backpack",
    kind="equipment",
)

KEY_ITEM = ItemDefinition(
    item_id="key",
    name="Keys",
    kind="quest",
)

ITEMS_BY_ID: dict[str, ItemDefinition] = {
    BACKPACK_ITEM.item_id: BACKPACK_ITEM,
    KEY_ITEM.item_id: KEY_ITEM,
}
