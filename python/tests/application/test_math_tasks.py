from __future__ import annotations

import random

from ksusha_game.application.math_tasks import MathTaskEngineState


def _start_task(state: MathTaskEngineState, task_no: int = 1) -> None:
    state.unlock_math_quest()
    state.open_menu("p1")
    outcome = state.select_task(player_id="p1", task_no=task_no, now_ts=100.0)
    assert outcome.spawn_digits is True
    assert state.active is True


def test_select_task_requires_math_quest_unlock() -> None:
    state = MathTaskEngineState()
    outcome = state.select_task(player_id="p1", task_no=1, now_ts=10.0)
    assert state.active is False
    assert state.current_round is None
    assert "книгу математики" in (outcome.message or "").lower()


def test_task1_starts_as_addition_with_ten_iterations() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    assert state.selected_task == 1
    assert state.iterations_target == 10
    assert state.current_round is not None
    assert state.current_round.operation == "+"
    assert state.current_round.stage == "pick_first"
    assert state.pending_count() == 0


def test_task2_starts_as_subtraction() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=2)
    assert state.selected_task == 2
    assert state.current_round is not None
    assert state.current_round.operation == "-"
    assert state.current_round.stage == "pick_first"


def test_second_digit_creates_pending_answer_and_spawns_answers() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(7)
    out1 = state.pick_digit(player_id="p1", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    assert "второе число" in (out1.message or "")
    out2 = state.pick_digit(player_id="p1", digit=3, rng=rng, online_player_ids=["p1", "p2"])
    assert out2.spawn_answers is True
    assert out2.clear_answers is True
    assert state.produced_count == 1
    assert state.pending_count() == 1
    pending = state.active_pending_answer()
    assert pending is not None
    assert pending.correct_answer == 7
    assert pending.assigned_player_id in {"p1", "p2"}
    assert len(pending.answer_options) == 10
    assert 7 in pending.answer_options
    assert state.current_round is not None
    assert state.current_round.stage == "pick_first"


def test_assigned_player_must_solve_answer() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(3)
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=5, rng=rng, online_player_ids=["p1", "p2"])
    pending = state.active_pending_answer()
    assert pending is not None
    assignee = pending.assigned_player_id or "p1"
    wrong_assignee = "p2" if assignee == "p1" else "p1"
    wrong_player = state.pick_answer(player_id=wrong_assignee, answer_value=pending.correct_answer)
    assert "назначен" in (wrong_player.message or "")
    right_player = state.pick_answer(player_id=assignee, answer_value=pending.correct_answer)
    assert "Верно" in (right_player.message or "")
    assert state.solved_count == 1
    assert state.total_solved == 1


def test_payload_roundtrip_preserves_queue_state() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(1)
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    payload = state.to_payload()
    restored = MathTaskEngineState.from_payload(payload)
    assert restored.selected_task == 1
    assert restored.active is True
    assert restored.produced_count == 1
    assert restored.pending_count() == 1
    pending = restored.active_pending_answer()
    assert pending is not None
    assert pending.correct_answer == 3
    assert pending.assigned_player_id in {"p1", "p2"}


def test_assignee_rotates_between_online_players() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(17)
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    assert len(state.pending_answers) == 2
    assignments = [item.assigned_player_id for item in state.pending_answers]
    assert assignments == ["p1", "p2"]


def test_task2_accepts_negative_numbers_for_operands() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=2)
    rng = random.Random(13)
    out1 = state.pick_digit(player_id="p1", digit=-5, rng=rng, online_player_ids=["p1"])
    assert "второе число" in (out1.message or "")
    out2 = state.pick_digit(player_id="p1", digit=3, rng=rng, online_player_ids=["p1"])
    assert out2.spawn_answers is True
    pending = state.active_pending_answer()
    assert pending is not None
    assert pending.operation == "-"
    assert pending.first_digit == -5
    assert pending.second_digit == 3
    assert pending.correct_answer == -8
