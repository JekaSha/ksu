from __future__ import annotations

from dataclasses import dataclass, field
import random


@dataclass
class MathRoundState:
    stage: str = "pick_first"
    operation: str = "+"
    first_digit: int | None = None
    assignments: dict[str, str | None] = field(
        default_factory=lambda: {
            "pick_first": None,
            "pick_second": None,
        }
    )
    assignment_accepted: dict[str, bool] = field(
        default_factory=lambda: {
            "pick_first": True,
            "pick_second": True,
        }
    )
    assignment_assigned_by: dict[str, str | None] = field(
        default_factory=lambda: {
            "pick_first": None,
            "pick_second": None,
        }
    )

    def to_payload(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "operation": self.operation,
            "first_digit": self.first_digit,
            "assignments": dict(self.assignments),
            "assignment_accepted": dict(self.assignment_accepted),
            "assignment_assigned_by": dict(self.assignment_assigned_by),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> MathRoundState | None:
        if not isinstance(payload, dict):
            return None
        stage = str(payload.get("stage", "")).strip()
        if stage not in {"pick_first", "pick_second"}:
            return None
        operation = str(payload.get("operation", "+")).strip() or "+"
        if operation not in {"+", "-"}:
            operation = "+"
        first = payload.get("first_digit")
        first_digit = int(first) if isinstance(first, int) else None
        assignments_raw = payload.get("assignments", {})
        assignments = {"pick_first": None, "pick_second": None}
        if isinstance(assignments_raw, dict):
            for key in assignments.keys():
                raw = assignments_raw.get(key)
                if raw is None:
                    assignments[key] = None
                else:
                    token = str(raw).strip()
                    assignments[key] = token if token else None
        accepted_raw = payload.get("assignment_accepted", {})
        assignment_accepted = {"pick_first": True, "pick_second": True}
        if isinstance(accepted_raw, dict):
            for key in assignment_accepted.keys():
                assignment_accepted[key] = bool(accepted_raw.get(key, True))
        assigned_by_raw = payload.get("assignment_assigned_by", {})
        assignment_assigned_by = {"pick_first": None, "pick_second": None}
        if isinstance(assigned_by_raw, dict):
            for key in assignment_assigned_by.keys():
                raw = assigned_by_raw.get(key)
                token = str(raw).strip() if raw is not None else ""
                assignment_assigned_by[key] = token if token else None
        return cls(
            stage=stage,
            operation=operation,
            first_digit=first_digit,
            assignments=assignments,
            assignment_accepted=assignment_accepted,
            assignment_assigned_by=assignment_assigned_by,
        )


@dataclass
class MathPendingAnswer:
    answer_id: int
    operation: str
    first_digit: int
    second_digit: int
    correct_answer: int
    answer_options: list[int] = field(default_factory=list)
    assigned_player_id: str | None = None
    assigned_by_player_id: str | None = None
    brief: str | None = None
    details: str | None = None
    accepted: bool = True
    solved: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "answer_id": self.answer_id,
            "operation": self.operation,
            "first_digit": self.first_digit,
            "second_digit": self.second_digit,
            "correct_answer": self.correct_answer,
            "answer_options": list(self.answer_options),
            "assigned_player_id": self.assigned_player_id,
            "assigned_by_player_id": self.assigned_by_player_id,
            "brief": self.brief,
            "details": self.details,
            "accepted": self.accepted,
            "solved": self.solved,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> MathPendingAnswer | None:
        if not isinstance(payload, dict):
            return None
        try:
            answer_id = int(payload.get("answer_id", 0))
            first_digit = int(payload.get("first_digit", 0))
            second_digit = int(payload.get("second_digit", 0))
            correct_answer = int(payload.get("correct_answer", 0))
        except (TypeError, ValueError):
            return None
        operation = str(payload.get("operation", "+")).strip()
        if operation not in {"+", "-"}:
            operation = "+"
        options_raw = payload.get("answer_options", [])
        options: list[int] = []
        if isinstance(options_raw, list):
            for item in options_raw:
                if isinstance(item, int):
                    options.append(item)
        assigned_raw = payload.get("assigned_player_id")
        assigned_player_id = str(assigned_raw).strip() if assigned_raw is not None and str(assigned_raw).strip() else None
        assigned_by_raw = payload.get("assigned_by_player_id")
        assigned_by_player_id = (
            str(assigned_by_raw).strip() if assigned_by_raw is not None and str(assigned_by_raw).strip() else None
        )
        brief_raw = payload.get("brief")
        brief = str(brief_raw).strip() if brief_raw is not None and str(brief_raw).strip() else None
        details_raw = payload.get("details")
        details = str(details_raw).strip() if details_raw is not None and str(details_raw).strip() else None
        accepted = bool(payload.get("accepted", True))
        solved = bool(payload.get("solved", False))
        return cls(
            answer_id=answer_id,
            operation=operation,
            first_digit=first_digit,
            second_digit=second_digit,
            correct_answer=correct_answer,
            answer_options=options,
            assigned_player_id=assigned_player_id,
            assigned_by_player_id=assigned_by_player_id,
            brief=brief,
            details=details,
            accepted=accepted,
            solved=solved,
        )


@dataclass
class MathTaskOutcome:
    message: str | None = None
    clear_digits: bool = False
    clear_answers: bool = False
    spawn_digits: bool = False
    spawn_answers: bool = False


@dataclass
class MathTaskEngineState:
    has_math_quest: bool = False
    menu_open: bool = False
    menu_owner_player_id: str | None = None
    selected_task: int | None = None
    active: bool = False
    total_solved: int = 0
    total_attempts: int = 0
    session_started_at_ts: float | None = None
    round_index: int = 0
    current_round: MathRoundState | None = None
    iterations_target: int = 10
    produced_count: int = 0
    solved_count: int = 0
    pending_answers: list[MathPendingAnswer] = field(default_factory=list)
    active_answer_id: int | None = None
    next_answer_id: int = 1
    dispatcher_player_id: str | None = None
    dispatcher_team_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "has_math_quest": self.has_math_quest,
            "menu_open": self.menu_open,
            "menu_owner_player_id": self.menu_owner_player_id,
            "selected_task": self.selected_task,
            "active": self.active,
            "total_solved": self.total_solved,
            "total_attempts": self.total_attempts,
            "session_started_at_ts": self.session_started_at_ts,
            "round_index": self.round_index,
            "current_round": self.current_round.to_payload() if self.current_round is not None else None,
            "iterations_target": self.iterations_target,
            "produced_count": self.produced_count,
            "solved_count": self.solved_count,
            "pending_answers": [item.to_payload() for item in self.pending_answers],
            "active_answer_id": self.active_answer_id,
            "next_answer_id": self.next_answer_id,
            "dispatcher_player_id": self.dispatcher_player_id,
            "dispatcher_team_id": self.dispatcher_team_id,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> MathTaskEngineState:
        if not isinstance(payload, dict):
            return cls()
        out = cls()
        out.has_math_quest = bool(payload.get("has_math_quest", False))
        out.menu_open = bool(payload.get("menu_open", False))
        owner = payload.get("menu_owner_player_id")
        out.menu_owner_player_id = str(owner).strip() if owner is not None and str(owner).strip() else None
        raw_selected = payload.get("selected_task")
        out.selected_task = int(raw_selected) if isinstance(raw_selected, int) else None
        out.active = bool(payload.get("active", False))
        out.total_solved = max(0, int(payload.get("total_solved", 0) or 0))
        out.total_attempts = max(0, int(payload.get("total_attempts", 0) or 0))
        raw_started = payload.get("session_started_at_ts")
        out.session_started_at_ts = float(raw_started) if isinstance(raw_started, (int, float)) else None
        out.round_index = max(0, int(payload.get("round_index", 0) or 0))
        round_payload = payload.get("current_round")
        if isinstance(round_payload, dict):
            out.current_round = MathRoundState.from_payload(round_payload)
        out.iterations_target = max(1, int(payload.get("iterations_target", 10) or 10))
        out.produced_count = max(0, int(payload.get("produced_count", 0) or 0))
        out.solved_count = max(0, int(payload.get("solved_count", 0) or 0))
        out.active_answer_id = int(payload.get("active_answer_id")) if isinstance(payload.get("active_answer_id"), int) else None
        out.next_answer_id = max(1, int(payload.get("next_answer_id", 1) or 1))
        raw_dispatcher = payload.get("dispatcher_player_id")
        out.dispatcher_player_id = (
            str(raw_dispatcher).strip() if raw_dispatcher is not None and str(raw_dispatcher).strip() else None
        )
        raw_team = payload.get("dispatcher_team_id")
        out.dispatcher_team_id = str(raw_team).strip() if raw_team is not None and str(raw_team).strip() else None
        pending_raw = payload.get("pending_answers", [])
        if isinstance(pending_raw, list):
            for item in pending_raw:
                pending = MathPendingAnswer.from_payload(item) if isinstance(item, dict) else None
                if pending is not None:
                    out.pending_answers.append(pending)
        if out.active_answer_id is not None and out._pending_by_id(out.active_answer_id) is None:
            out.active_answer_id = None
        if out.active_answer_id is None:
            out._activate_next_pending()
        return out

    def unlock_math_quest(self) -> MathTaskOutcome:
        if self.has_math_quest:
            return MathTaskOutcome(message="Книга математики уже найдена")
        self.has_math_quest = True
        return MathTaskOutcome(message="Открыт раздел: Математика")

    def open_menu(self, player_id: str) -> MathTaskOutcome:
        self.menu_open = True
        self.menu_owner_player_id = player_id
        return MathTaskOutcome(message="Задачи 1-9: выбери номер")

    def close_menu(self) -> None:
        self.menu_open = False
        self.menu_owner_player_id = None

    def session_duration_sec(self, now_ts: float) -> float:
        if self.session_started_at_ts is None:
            return 0.0
        return max(0.0, float(now_ts) - float(self.session_started_at_ts))

    def pending_count(self) -> int:
        return len([item for item in self.pending_answers if not item.solved])

    def active_pending_answer(self) -> MathPendingAnswer | None:
        if self.active_answer_id is None:
            return None
        return self._pending_by_id(self.active_answer_id)

    def active_answer_options(self) -> list[int]:
        pending = self.active_pending_answer()
        if pending is None:
            return []
        return list(pending.answer_options)

    def unresolved_pending_answers(self) -> list[MathPendingAnswer]:
        return [item for item in self.pending_answers if not item.solved]

    def _is_dispatcher(self, player_id: str) -> bool:
        requester = str(player_id).strip()
        dispatcher = str(self.dispatcher_player_id).strip() if self.dispatcher_player_id is not None else ""
        if not requester:
            return False
        if not dispatcher:
            return True
        return requester == dispatcher

    def task_operation(self) -> str:
        if self.selected_task == 2:
            return "-"
        return "+"

    def _activate_supported_task(
        self,
        *,
        player_id: str,
        task_no: int,
        now_ts: float,
        team_id: str | None = None,
    ) -> MathTaskOutcome:
        self.active = True
        self.dispatcher_player_id = str(player_id).strip() or None
        self.dispatcher_team_id = str(team_id).strip() if team_id is not None and str(team_id).strip() else None
        if self.session_started_at_ts is None:
            self.session_started_at_ts = float(now_ts)
        operation = "+" if task_no == 1 else "-"
        self.round_index = 0
        self.produced_count = 0
        self.solved_count = 0
        self.pending_answers = []
        self.active_answer_id = None
        self.next_answer_id = 1
        leader_id = str(player_id).strip() or "p1"
        self.current_round = MathRoundState(
            stage="pick_first",
            operation=operation,
            first_digit=None,
            assignments={
                "pick_first": leader_id,
                "pick_second": leader_id,
            },
            assignment_accepted={
                "pick_first": True,
                "pick_second": True,
            },
            assignment_assigned_by={
                "pick_first": leader_id,
                "pick_second": leader_id,
            },
        )
        self.iterations_target = 10
        return MathTaskOutcome(
            message=f"Задача {task_no}: {self.iterations_target} итераций. Найди первое число",
            clear_digits=True,
            clear_answers=True,
            spawn_digits=True,
        )

    def select_task(
        self,
        *,
        player_id: str,
        task_no: int,
        now_ts: float,
        team_id: str | None = None,
    ) -> MathTaskOutcome:
        if not self.has_math_quest:
            return MathTaskOutcome(message="Сначала найди книгу математики")
        if task_no < 1 or task_no > 9:
            return MathTaskOutcome(message="Номер задачи: 1..9")
        if self.menu_open and self.menu_owner_player_id not in {None, player_id}:
            return MathTaskOutcome(message="Эту задачу выбирает другой игрок")
        if self.active and self.selected_task == int(task_no) and task_no in {1, 2}:
            return MathTaskOutcome(message=f"Задача {task_no} уже идет. Удерживай Q 5 сек для сброса")
        self.selected_task = int(task_no)
        self.close_menu()
        if task_no not in {1, 2}:
            self.active = False
            self.current_round = None
            self.pending_answers = []
            self.active_answer_id = None
            return MathTaskOutcome(message=f"Задача {task_no}: пока не реализована")
        return self._activate_supported_task(
            player_id=player_id,
            task_no=task_no,
            now_ts=now_ts,
            team_id=team_id,
        )

    def restart_task(
        self,
        *,
        player_id: str,
        task_no: int,
        now_ts: float,
        team_id: str | None = None,
    ) -> MathTaskOutcome:
        if not self.has_math_quest:
            return MathTaskOutcome(message="Сначала найди книгу математики")
        if task_no < 1 or task_no > 9:
            return MathTaskOutcome(message="Номер задачи: 1..9")
        if task_no not in {1, 2}:
            return MathTaskOutcome(message=f"Задача {task_no}: пока не реализована")
        if not self.active or self.selected_task != int(task_no):
            return self.select_task(
                player_id=player_id,
                task_no=task_no,
                now_ts=now_ts,
                team_id=team_id,
            )
        if not self._is_dispatcher(player_id):
            return MathTaskOutcome(message="Сброс доступен только ведущему")
        self.selected_task = int(task_no)
        self.close_menu()
        return self._activate_supported_task(
            player_id=player_id,
            task_no=task_no,
            now_ts=now_ts,
            team_id=team_id,
        )

    def pick_digit(
        self,
        *,
        player_id: str,
        digit: int,
        rng: random.Random,
        online_player_ids: list[str] | None = None,
    ) -> MathTaskOutcome:
        if not self.active or self.selected_task not in {1, 2} or self.current_round is None:
            return MathTaskOutcome(message=None)
        if self.produced_count >= self.iterations_target:
            return MathTaskOutcome(message="Все примеры собраны. Закройте очередь ответов")
        round_state = self.current_round
        if self.selected_task == 2:
            value = max(-9, min(9, int(digit)))
        else:
            value = max(0, min(9, int(digit)))
        if self._player_has_assigned_pending_answer(player_id=player_id):
            return MathTaskOutcome(message="Сначала реши назначенный тебе результат")
        if round_state.stage == "pick_first":
            owner = round_state.assignments.get("pick_first")
            if owner not in {None, player_id}:
                return MathTaskOutcome(message="Это число назначено другому игроку")
            if owner == player_id and not round_state.assignment_accepted.get("pick_first", True):
                return MathTaskOutcome(message="Сначала прими задачу: найти первое число")
            round_state.first_digit = value
            round_state.stage = "pick_second"
            op = round_state.operation
            return MathTaskOutcome(message=f"Операция: {op}. Найди второе число")
        if round_state.stage == "pick_second":
            owner = round_state.assignments.get("pick_second")
            if owner not in {None, player_id}:
                return MathTaskOutcome(message="Это число назначено другому игроку")
            if owner == player_id and not round_state.assignment_accepted.get("pick_second", True):
                return MathTaskOutcome(message="Сначала прими задачу: найти второе число")
            first = int(round_state.first_digit or 0)
            second = value
            operation = round_state.operation if round_state.operation in {"+", "-"} else "+"
            correct = (first + second) if operation == "+" else (first - second)
            answer = MathPendingAnswer(
                answer_id=self.next_answer_id,
                operation=operation,
                first_digit=first,
                second_digit=second,
                correct_answer=correct,
                answer_options=self._generate_answer_options(correct, operation=operation, rng=rng),
                assigned_player_id=self._resolve_answer_assignee(
                    producer_player_id=player_id,
                    online_player_ids=online_player_ids or [],
                ),
                assigned_by_player_id=player_id,
                brief="Найти результат выражения",
                details=f"Найди правильный результат для {first} {operation} {second}",
                accepted=False,
            )
            self.next_answer_id += 1
            self.produced_count += 1
            self.round_index += 1
            self.pending_answers.append(answer)
            round_state.first_digit = None
            round_state.stage = "pick_first"
            next_owner = self._resolve_next_stage_owner(
                producer_player_id=player_id,
                online_player_ids=online_player_ids or [],
            )
            leader_id = str(player_id).strip() or "p1"
            assigned_by = leader_id
            round_state.assignments["pick_first"] = next_owner
            round_state.assignment_accepted["pick_first"] = next_owner in {None, assigned_by}
            round_state.assignment_assigned_by["pick_first"] = assigned_by if next_owner is not None else None
            round_state.assignments["pick_second"] = next_owner
            round_state.assignment_accepted["pick_second"] = next_owner in {None, assigned_by}
            round_state.assignment_assigned_by["pick_second"] = assigned_by if next_owner is not None else None

            out = MathTaskOutcome(message="Пример поставлен в очередь", spawn_digits=True)
            if self.active_answer_id is None:
                self.active_answer_id = answer.answer_id
                out.clear_answers = True
                out.spawn_answers = True
            assigned = answer.assigned_player_id
            if assigned is not None and assigned != player_id:
                out.message = f"Ответ делегирован игроку {assigned}. Ищи следующее число"
            elif assigned == player_id:
                answer.accepted = True
                out.message = "Ответ у тебя. Можно брать следующий пример"
            else:
                out.message = "Ответ в очереди без исполнителя. Назначь игрока или реши позже"
            return out
        return MathTaskOutcome(message=None)

    def pick_answer(self, *, player_id: str, answer_value: int) -> MathTaskOutcome:
        if not self.active or self.selected_task not in {1, 2}:
            return MathTaskOutcome(message=None)
        pending = self.active_pending_answer()
        if pending is None:
            return MathTaskOutcome(message="Сейчас нет активного ответа")
        assigned = pending.assigned_player_id
        if assigned is not None and assigned != player_id:
            return MathTaskOutcome(message=f"Этот ответ назначен игроку {assigned}")
        if assigned is not None and assigned == player_id and not pending.accepted:
            return MathTaskOutcome(message="Сначала прими задачу на ответ")
        self.total_attempts += 1
        if int(answer_value) == int(pending.correct_answer):
            pending.solved = True
            self.solved_count += 1
            self.total_solved += 1
            out = MathTaskOutcome(clear_answers=True)
            self._activate_next_pending()
            if self.active_answer_id is not None:
                out.spawn_answers = True
                out.message = f"Верно! Осталось: {max(0, self.iterations_target - self.solved_count)}"
                return out
            if self.solved_count >= self.iterations_target and self.produced_count >= self.iterations_target:
                self.active = False
                self.current_round = None
                out.clear_digits = True
                out.message = f"Серия завершена! Решено {self.solved_count}/{self.iterations_target}"
                return out
            out.message = "Верно! Очередь ответов пока пуста"
            return out
        return MathTaskOutcome(message="Неверный ответ. Попробуй другой")

    def reassign_pending_answer(
        self,
        *,
        answer_id: int,
        assignee_player_id: str,
        requested_by_player_id: str,
        online_player_ids: list[str] | None = None,
    ) -> str:
        if not self._is_dispatcher(requested_by_player_id):
            return "Только диспетчер может перераспределять задачи"
        pending = self._pending_by_id(int(answer_id))
        if pending is None:
            return "Эта задача уже решена или не найдена"
        assignee = str(assignee_player_id).strip()
        if not assignee:
            return "Исполнитель не указан"
        roster: set[str] = set()
        for pid in online_player_ids or []:
            token = str(pid).strip()
            if token:
                roster.add(token)
        requester = str(requested_by_player_id).strip()
        if requester:
            roster.add(requester)
        if assignee not in roster:
            return "Исполнитель не в текущей сессии"
        if self._is_player_busy(player_id=assignee, exclude_answer_id=pending.answer_id):
            return f"Игрок {assignee} уже занят другой задачей"
        pending.assigned_player_id = assignee
        pending.assigned_by_player_id = requester
        pending.accepted = assignee == requester
        return f"Задача #{pending.answer_id}: ответ назначен игроку {assignee}"

    def reassign_round_stage(
        self,
        *,
        stage: str,
        assignee_player_id: str,
        requested_by_player_id: str,
        online_player_ids: list[str] | None = None,
    ) -> str:
        if not self._is_dispatcher(requested_by_player_id):
            return "Только диспетчер может перераспределять задачи"
        if self.current_round is None or not self.active:
            return "Нет активной задачи"
        stage_key = str(stage).strip().lower()
        if stage_key not in {"pick_first", "pick_second"}:
            return "Неизвестный этап"
        assignee = str(assignee_player_id).strip()
        if not assignee:
            return "Исполнитель не указан"
        roster: set[str] = set()
        for pid in online_player_ids or []:
            token = str(pid).strip()
            if token:
                roster.add(token)
        requester = str(requested_by_player_id).strip()
        if requester:
            roster.add(requester)
        if assignee not in roster:
            return "Исполнитель не в текущей команде"
        if self._is_player_busy(player_id=assignee, exclude_stage=stage_key):
            return f"Игрок {assignee} уже занят другой задачей"
        self.current_round.assignments[stage_key] = assignee
        self.current_round.assignment_accepted[stage_key] = assignee == requester
        self.current_round.assignment_assigned_by[stage_key] = requester
        stage_label = "первое число" if stage_key == "pick_first" else "второе число"
        return f"Этап '{stage_label}' назначен игроку {assignee}"

    def accept_round_stage(self, *, stage: str, player_id: str) -> str:
        if self.current_round is None or not self.active:
            return "Нет активной задачи"
        stage_key = str(stage).strip().lower()
        if stage_key not in {"pick_first", "pick_second"}:
            return "Неизвестный этап"
        owner = self.current_round.assignments.get(stage_key)
        if owner is None:
            return "Этот этап не назначен явно"
        if owner != player_id:
            return "Этот этап назначен другому игроку"
        self.current_round.assignment_accepted[stage_key] = True
        stage_label = "первое число" if stage_key == "pick_first" else "второе число"
        return f"Принято: этап '{stage_label}'"

    def accept_pending_answer(self, *, answer_id: int, player_id: str) -> str:
        pending = self._pending_by_id(int(answer_id))
        if pending is None:
            return "Эта задача уже решена или не найдена"
        owner = pending.assigned_player_id
        if owner is None:
            return f"Ответ #{pending.answer_id} без назначения: принятие не требуется"
        if owner != player_id:
            return "Этот ответ назначен другому игроку"
        pending.accepted = True
        return f"Принято: ответ #{pending.answer_id}"

    def _pending_by_id(self, answer_id: int) -> MathPendingAnswer | None:
        for item in self.pending_answers:
            if item.answer_id == answer_id and not item.solved:
                return item
        return None

    def _active_stage_key(self) -> str | None:
        if self.current_round is None or not self.active:
            return None
        stage = str(self.current_round.stage).strip().lower()
        if stage not in {"pick_first", "pick_second"}:
            return None
        return stage

    def _player_has_assigned_pending_answer(
        self,
        *,
        player_id: str,
        exclude_answer_id: int | None = None,
    ) -> bool:
        owner = str(player_id).strip()
        if not owner:
            return False
        for item in self.pending_answers:
            if item.solved:
                continue
            if exclude_answer_id is not None and int(item.answer_id) == int(exclude_answer_id):
                continue
            assigned = str(item.assigned_player_id).strip() if item.assigned_player_id is not None else ""
            if assigned and assigned == owner:
                return True
        return False

    def _player_has_active_stage_assignment(
        self,
        *,
        player_id: str,
        exclude_stage: str | None = None,
    ) -> bool:
        owner = str(player_id).strip()
        if not owner:
            return False
        stage_key = self._active_stage_key()
        if stage_key is None:
            return False
        if exclude_stage is not None and stage_key == str(exclude_stage).strip().lower():
            return False
        if self.current_round is None:
            return False
        stage_owner = self.current_round.assignments.get(stage_key)
        return str(stage_owner).strip() == owner if stage_owner is not None else False

    def _is_player_busy(
        self,
        *,
        player_id: str,
        exclude_answer_id: int | None = None,
        exclude_stage: str | None = None,
    ) -> bool:
        return self._player_has_assigned_pending_answer(
            player_id=player_id,
            exclude_answer_id=exclude_answer_id,
        ) or self._player_has_active_stage_assignment(
            player_id=player_id,
            exclude_stage=exclude_stage,
        )

    def _activate_next_pending(self) -> None:
        for item in self.pending_answers:
            if not item.solved:
                self.active_answer_id = item.answer_id
                return
        self.active_answer_id = None

    def _resolve_answer_assignee(self, *, producer_player_id: str, online_player_ids: list[str]) -> str | None:
        roster: list[str] = []
        seen: set[str] = set()
        for pid in online_player_ids:
            token = str(pid).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            roster.append(token)
        producer = str(producer_player_id).strip()
        if producer and producer not in seen:
            roster.append(producer)
            seen.add(producer)
        if not producer:
            producer = roster[0] if roster else "p1"
        if not roster:
            return producer or None
        free_candidates = [
            pid
            for pid in roster
            if pid != producer and not self._player_has_assigned_pending_answer(player_id=pid)
        ]
        if free_candidates:
            free_candidates.sort()
            idx = max(0, int(self.next_answer_id) - 1) % len(free_candidates)
            return free_candidates[idx]
        if producer and not self._player_has_assigned_pending_answer(player_id=producer):
            return producer
        return None

    def _resolve_next_stage_owner(
        self,
        *,
        producer_player_id: str,
        online_player_ids: list[str],
    ) -> str | None:
        roster: list[str] = []
        seen: set[str] = set()
        for pid in online_player_ids:
            token = str(pid).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            roster.append(token)
        producer = str(producer_player_id).strip()
        if producer and producer not in seen:
            seen.add(producer)
            roster.append(producer)
        if producer and not self._player_has_assigned_pending_answer(player_id=producer):
            return producer
        free_candidates = [pid for pid in roster if not self._player_has_assigned_pending_answer(player_id=pid)]
        if free_candidates:
            free_candidates.sort()
            return free_candidates[0]
        return None

    def _generate_answer_options(self, correct: int, *, operation: str, rng: random.Random) -> list[int]:
        correct_value = int(correct)
        if operation == "-":
            start = max(-20, correct_value - 15)
            end = min(20, correct_value + 15)
            pool = list(range(start, end + 1))
        else:
            if correct_value <= 18:
                pool = list(range(0, 19))
            else:
                start = max(0, correct_value - 20)
                pool = list(range(start, correct_value + 21))
        wrong = [v for v in pool if v != correct_value]
        rng.shuffle(wrong)
        options = [correct_value, *wrong[:9]]
        rng.shuffle(options)
        return options

    def on_player_left(
        self,
        *,
        player_id: str,
        online_player_ids: list[str],
        online_team_player_ids: list[str] | None = None,
    ) -> None:
        left = str(player_id).strip()
        if not left:
            return
        online: list[str] = []
        seen: set[str] = set()
        for pid in online_player_ids:
            token = str(pid).strip()
            if not token or token == left or token in seen:
                continue
            seen.add(token)
            online.append(token)
        team_online: list[str] = []
        team_seen: set[str] = set()
        for pid in online_team_player_ids or []:
            token = str(pid).strip()
            if not token or token == left or token in team_seen:
                continue
            team_seen.add(token)
            team_online.append(token)
        if self.dispatcher_player_id == left:
            if team_online:
                self.dispatcher_player_id = sorted(team_online)[0]
            elif online:
                self.dispatcher_player_id = sorted(online)[0]
            else:
                self.dispatcher_player_id = None

        if self.current_round is not None:
            for stage in ("pick_first", "pick_second"):
                owner = self.current_round.assignments.get(stage)
                if owner == left:
                    self.current_round.assignments[stage] = None
                    self.current_round.assignment_accepted[stage] = True
                    self.current_round.assignment_assigned_by[stage] = None
                elif self.current_round.assignment_assigned_by.get(stage) == left:
                    self.current_round.assignment_assigned_by[stage] = None

        for pending in self.pending_answers:
            if pending.assigned_player_id == left:
                pending.assigned_player_id = None
                pending.accepted = True
            if pending.assigned_by_player_id == left:
                pending.assigned_by_player_id = None

    def remap_player_ids(self, id_map: dict[str, str]) -> None:
        if not id_map:
            return

        def _remap(value: str | None) -> str | None:
            if value is None:
                return None
            token = str(value).strip()
            if not token:
                return None
            return id_map.get(token, token)

        self.menu_owner_player_id = _remap(self.menu_owner_player_id)
        self.dispatcher_player_id = _remap(self.dispatcher_player_id)

        if self.current_round is not None:
            for stage, owner in list(self.current_round.assignments.items()):
                self.current_round.assignments[stage] = _remap(owner)
            for stage, owner in list(self.current_round.assignment_assigned_by.items()):
                self.current_round.assignment_assigned_by[stage] = _remap(owner)

        for pending in self.pending_answers:
            pending.assigned_player_id = _remap(pending.assigned_player_id)
            pending.assigned_by_player_id = _remap(pending.assigned_by_player_id)
