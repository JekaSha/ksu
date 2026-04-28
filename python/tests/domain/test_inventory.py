from __future__ import annotations

import pytest

from ksusha_game.domain.inventory import Inventory


def make(capacity: int = 5) -> Inventory:
    return Inventory(base_capacity=capacity, capacity=capacity)


class TestAddItem:
    def test_adds_to_first_free_slot(self):
        inv = make(3)
        assert inv.add_item("key") is True
        assert inv.slots[0] == "key"

    def test_fills_sequentially(self):
        inv = make(3)
        inv.add_item("a")
        inv.add_item("b")
        assert inv.slots == ["a", "b", None]

    def test_returns_false_when_full(self):
        inv = make(2)
        inv.add_item("a")
        inv.add_item("b")
        assert inv.add_item("c") is False

    def test_skips_occupied_slots(self):
        inv = make(3)
        inv.slots[0] = "existing"
        inv.add_item("new")
        assert inv.slots[1] == "new"


class TestRemoveSelected:
    def test_removes_active_slot(self):
        inv = make(3)
        inv.add_item("key")
        result = inv.remove_selected()
        assert result == "key"
        assert inv.slots[0] is None

    def test_returns_none_when_empty(self):
        inv = make(3)
        assert inv.remove_selected() is None

    def test_only_removes_active_index(self):
        inv = make(3)
        inv.slots = ["a", "b", "c"]
        inv.active_index = 1
        inv.remove_selected()
        assert inv.slots == ["a", None, "c"]


class TestNavigation:
    def test_select_next_wraps(self):
        inv = make(3)
        inv.active_index = 2
        inv.select_next()
        assert inv.active_index == 0

    def test_select_previous_wraps(self):
        inv = make(3)
        inv.active_index = 0
        inv.select_previous()
        assert inv.active_index == 2

    def test_cursor_right_stays_in_row(self):
        inv = make(5)
        inv.active_index = 3
        inv.move_cursor_right()
        assert inv.active_index == 4

    def test_cursor_right_wraps_in_row(self):
        inv = make(5)
        inv.active_index = 4
        inv.move_cursor_right()
        assert inv.active_index == 0

    def test_cursor_left_stays_in_row(self):
        inv = make(5)
        inv.active_index = 2
        inv.move_cursor_left()
        assert inv.active_index == 1

    def test_cursor_left_wraps_in_row(self):
        inv = make(5)
        inv.active_index = 0
        inv.move_cursor_left()
        assert inv.active_index == 4

    def test_cursor_up_moves_to_extra_row(self):
        inv = make(5)
        inv.set_extension(bonus_slots=3)
        inv.active_index = 2
        inv.move_cursor_up()
        assert inv.is_extra_slot(inv.active_index)

    def test_cursor_down_returns_to_base_row(self):
        inv = make(5)
        inv.set_extension(bonus_slots=3)
        inv.active_index = inv.base_capacity  # first extra slot
        inv.move_cursor_down()
        assert not inv.is_extra_slot(inv.active_index)

    def test_cursor_up_no_op_when_no_extra_slots(self):
        inv = make(5)
        prev = inv.active_index
        inv.move_cursor_up()
        assert inv.active_index == prev


class TestSetExtension:
    def test_increases_capacity(self):
        inv = make(5)
        inv.set_extension(bonus_slots=3)
        assert inv.capacity == 8

    def test_adds_slots(self):
        inv = make(5)
        inv.set_extension(bonus_slots=2)
        assert len(inv.slots) == 7

    def test_removing_extension_doesnt_shrink_below_base(self):
        inv = make(5)
        inv.set_extension(bonus_slots=3)
        inv.set_extension(bonus_slots=0)
        assert inv.capacity == 5

    def test_returns_true_when_changed(self):
        inv = make(5)
        assert inv.set_extension(bonus_slots=2) is True

    def test_returns_false_when_unchanged(self):
        inv = make(5)
        inv.set_extension(bonus_slots=2)
        assert inv.set_extension(bonus_slots=2) is False

    def test_clamps_active_index_after_shrink(self):
        inv = make(5)
        inv.set_extension(bonus_slots=5)
        inv.active_index = 9
        inv.set_extension(bonus_slots=0)
        assert inv.active_index < inv.capacity


class TestMoveMode:
    def test_begin_requires_non_empty_slot(self):
        inv = make(3)
        assert inv.begin_move_mode() is False

    def test_begin_sets_source(self):
        inv = make(3)
        inv.slots[0] = "item"
        inv.begin_move_mode()
        assert inv.move_mode is True
        assert inv.move_source_index == 0

    def test_commit_swaps_slots(self):
        inv = make(3)
        inv.slots = ["a", None, "b"]
        inv.active_index = 0
        inv.begin_move_mode()
        result = inv.commit_move(2)
        assert result == (0, 2)
        assert inv.slots[0] == "b"
        assert inv.slots[2] == "a"

    def test_commit_same_index_cancels(self):
        inv = make(3)
        inv.slots[0] = "item"
        inv.begin_move_mode()
        result = inv.commit_move(0)
        assert result == (0, 0)
        assert inv.move_mode is False

    def test_cancel_clears_state(self):
        inv = make(3)
        inv.slots[0] = "item"
        inv.begin_move_mode()
        inv.cancel_move_mode()
        assert inv.move_mode is False
        assert inv.move_source_index is None

    def test_commit_without_begin_returns_none(self):
        inv = make(3)
        assert inv.commit_move(1) is None


class TestSelectedItem:
    def test_returns_active_slot(self):
        inv = make(3)
        inv.slots = ["a", "b", "c"]
        inv.active_index = 1
        assert inv.selected_item() == "b"

    def test_returns_none_for_empty_slot(self):
        inv = make(3)
        assert inv.selected_item() is None


class TestExtraIndices:
    def test_empty_when_no_extension(self):
        inv = make(5)
        assert list(inv.extra_indices()) == []

    def test_correct_range_with_extension(self):
        inv = make(5)
        inv.set_extension(bonus_slots=3)
        assert list(inv.extra_indices()) == [5, 6, 7]

    def test_is_extra_slot(self):
        inv = make(5)
        inv.set_extension(bonus_slots=2)
        assert inv.is_extra_slot(5) is True
        assert inv.is_extra_slot(4) is False
