from __future__ import annotations

import random

from ksusha_game.application.math_tasks import MathTaskEngineState


def test_select_task_one_starts_round_and_requests_digits() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    state.open_menu("p1")
    outcome = state.select_task(player_id="p1", task_no=1, now_ts=100.0)
    assert state.active is True
    assert state.selected_task == 1
    assert state.current_round is not None
    assert state.current_round.stage == "pick_first"
    assert outcome.spawn_digits is True
    assert outcome.clear_digits is True
    assert outcome.clear_answers is True


def test_pick_second_digit_spawns_answers() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    state.open_menu("p1")
    state.select_task(player_id="p1", task_no=1, now_ts=100.0)
    rng = random.Random(7)
    out1 = state.pick_digit(player_id="p1", digit=4, rng=rng)
    assert out1.spawn_answers is False
    assert state.current_round is not None
    assert state.current_round.stage == "pick_second"
    out2 = state.pick_digit(player_id="p1", digit=3, rng=rng)
    assert out2.spawn_answers is True
    assert out2.clear_digits is True
    assert state.current_round is not None
    assert state.current_round.stage == "pick_answer"
    assert state.current_round.correct_answer == 7
    assert len(state.current_round.answer_options) == 10
    assert 7 in state.current_round.answer_options


def test_wrong_answer_then_correct_answer_updates_global_score() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    state.open_menu("p1")
    state.select_task(player_id="p1", task_no=1, now_ts=100.0)
    rng = random.Random(1)
    state.pick_digit(player_id="p1", digit=2, rng=rng)
    state.pick_digit(player_id="p1", digit=5, rng=rng)
    assert state.current_round is not None
    correct = int(state.current_round.correct_answer or 0)
    wrong = correct + 1
    if wrong == correct:
        wrong += 2
    out_wrong = state.pick_answer(player_id="p1", answer_value=wrong)
    assert "Неверный" in (out_wrong.message or "")
    assert state.total_solved == 0
    out_ok = state.pick_answer(player_id="p1", answer_value=correct)
    assert "Верно" in (out_ok.message or "")
    assert state.total_solved == 1
    assert state.total_attempts == 2
    assert out_ok.spawn_digits is True
    assert out_ok.clear_answers is True


def test_payload_roundtrip_preserves_state() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    state.open_menu("p2")
    state.select_task(player_id="p2", task_no=1, now_ts=55.0)
    payload = state.to_payload()
    restored = MathTaskEngineState.from_payload(payload)
    assert restored.menu_open == state.menu_open
    assert restored.menu_owner_player_id == state.menu_owner_player_id
    assert restored.selected_task == state.selected_task
    assert restored.active == state.active
    assert restored.round_index == state.round_index
    assert restored.current_round is not None
    assert restored.current_round.stage == "pick_first"
    assert restored.has_math_quest is True


def test_select_task_requires_math_quest_unlock() -> None:
    state = MathTaskEngineState()
    outcome = state.select_task(player_id="p1", task_no=1, now_ts=10.0)
    assert state.active is False
    assert state.current_round is None
    assert "книгу математики" in (outcome.message or "").lower()
