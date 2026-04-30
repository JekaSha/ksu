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


def test_only_leader_can_collect_expression_digits() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(5)
    blocked_first = state.pick_digit(player_id="p2", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    assert "другому игроку" in (blocked_first.message or "")
    leader_first = state.pick_digit(player_id="p1", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    assert "второе число" in (leader_first.message or "")
    blocked_second = state.pick_digit(player_id="p2", digit=3, rng=rng, online_player_ids=["p1", "p2"])
    assert "другому игроку" in (blocked_second.message or "")


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
    assert pending.assigned_player_id == "p2"
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
    if assignee == "p2":
        not_accepted = state.pick_answer(player_id=assignee, answer_value=pending.correct_answer)
        assert "прими задачу" in (not_accepted.message or "").lower()
        accept_msg = state.accept_pending_answer(answer_id=pending.answer_id, player_id=assignee)
        assert "Принято" in accept_msg
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
    assert pending.assigned_player_id == "p2"


def test_assignee_prefers_free_player_then_falls_back_to_producer() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(17)
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    assert len(state.pending_answers) == 2
    assignments = [item.assigned_player_id for item in state.pending_answers]
    assert assignments == ["p2", "p1"]


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


def test_can_reassign_pending_answer_to_another_online_player() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(21)
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    pending = state.active_pending_answer()
    assert pending is not None
    assert pending.assigned_player_id == "p2"
    msg = state.reassign_pending_answer(
        answer_id=pending.answer_id,
        assignee_player_id="p1",
        requested_by_player_id="p1",
        online_player_ids=["p1", "p2"],
    )
    assert "назначен игроку p1" in msg
    assert pending.assigned_player_id == "p1"
    assert pending.accepted is True


def test_non_dispatcher_cannot_reassign_pending_answer() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(21)
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=2, rng=rng, online_player_ids=["p1", "p2"])
    pending = state.active_pending_answer()
    assert pending is not None
    msg = state.reassign_pending_answer(
        answer_id=pending.answer_id,
        assignee_player_id="p1",
        requested_by_player_id="p2",
        online_player_ids=["p1", "p2"],
    )
    assert "только диспетчер" in msg.lower()
    assert pending.assigned_player_id == "p2"


def test_select_task_persists_dispatcher_team() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    out = state.select_task(player_id="p1", task_no=1, now_ts=10.0, team_id="blue")
    assert out.spawn_digits is True
    assert state.dispatcher_player_id == "p1"
    assert state.dispatcher_team_id == "blue"


def test_can_reassign_round_stage() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    msg = state.reassign_round_stage(
        stage="pick_first",
        assignee_player_id="p2",
        requested_by_player_id="p1",
        online_player_ids=["p1", "p2"],
    )
    assert "первое число" in msg
    assert state.current_round is not None
    assert state.current_round.assignments["pick_first"] == "p2"
    assert state.current_round.assignment_accepted["pick_first"] is False


def test_non_dispatcher_cannot_reassign_round_stage() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    msg = state.reassign_round_stage(
        stage="pick_first",
        assignee_player_id="p2",
        requested_by_player_id="p2",
        online_player_ids=["p1", "p2"],
    )
    assert "только диспетчер" in msg.lower()
    assert state.current_round is not None
    assert state.current_round.assignments["pick_first"] == "p1"


def test_assigned_stage_requires_accept_before_pick() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(33)
    state.reassign_round_stage(
        stage="pick_first",
        assignee_player_id="p2",
        requested_by_player_id="p1",
        online_player_ids=["p1", "p2"],
    )
    blocked = state.pick_digit(player_id="p2", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    assert "прими задачу" in (blocked.message or "").lower()
    accept_msg = state.accept_round_stage(stage="pick_first", player_id="p2")
    assert "Принято" in accept_msg
    ok = state.pick_digit(player_id="p2", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    assert "второе число" in (ok.message or "")


def test_dispatcher_is_reelected_when_current_dispatcher_leaves() -> None:
    state = MathTaskEngineState()
    state.unlock_math_quest()
    state.select_task(player_id="p2", task_no=1, now_ts=1.0, team_id="A")
    assert state.dispatcher_player_id == "p2"
    state.on_player_left(
        player_id="p2",
        online_player_ids=["p1", "p3"],
        online_team_player_ids=["p1"],
    )
    assert state.dispatcher_player_id == "p1"
    msg = state.reassign_round_stage(
        stage="pick_first",
        assignee_player_id="p1",
        requested_by_player_id="p1",
        online_player_ids=["p1"],
    )
    assert "назначен игроку p1" in msg


def test_player_leave_releases_stage_and_pending_answer_assignment() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(99)
    state.pick_digit(player_id="p1", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=1, rng=rng, online_player_ids=["p1", "p2"])
    state.reassign_round_stage(
        stage="pick_first",
        assignee_player_id="p2",
        requested_by_player_id="p1",
        online_player_ids=["p1", "p2"],
    )
    pending = state.active_pending_answer()
    assert pending is not None
    assert pending.assigned_player_id == "p2"
    state.on_player_left(
        player_id="p2",
        online_player_ids=["p1"],
        online_team_player_ids=["p1"],
    )
    assert state.current_round is not None
    assert state.current_round.assignments["pick_first"] is None
    assert pending.assigned_player_id is None
    assert pending.accepted is True
    solved = state.pick_answer(player_id="p1", answer_value=pending.correct_answer)
    assert "Верно" in (solved.message or "")


def test_accept_pending_answer_reports_no_need_when_unassigned() -> None:
    state = MathTaskEngineState()
    _start_task(state, task_no=1)
    rng = random.Random(7)
    state.pick_digit(player_id="p1", digit=3, rng=rng, online_player_ids=["p1", "p2"])
    state.pick_digit(player_id="p1", digit=4, rng=rng, online_player_ids=["p1", "p2"])
    pending = state.active_pending_answer()
    assert pending is not None
    state.on_player_left(
        player_id="p2",
        online_player_ids=["p1"],
        online_team_player_ids=["p1"],
    )
    assert pending.assigned_player_id is None
    msg = state.accept_pending_answer(answer_id=pending.answer_id, player_id="p1")
    assert "не требуется" in msg.lower()
