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

    def to_payload(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "operation": self.operation,
            "first_digit": self.first_digit,
            "assignments": dict(self.assignments),
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
        return cls(
            stage=stage,
            operation=operation,
            first_digit=first_digit,
            assignments=assignments,
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
        solved = bool(payload.get("solved", False))
        return cls(
            answer_id=answer_id,
            operation=operation,
            first_digit=first_digit,
            second_digit=second_digit,
            correct_answer=correct_answer,
            answer_options=options,
            assigned_player_id=assigned_player_id,
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

    def task_operation(self) -> str:
        if self.selected_task == 2:
            return "-"
        return "+"

    def select_task(self, *, player_id: str, task_no: int, now_ts: float) -> MathTaskOutcome:
        if not self.has_math_quest:
            return MathTaskOutcome(message="Сначала найди книгу математики")
        if task_no < 1 or task_no > 9:
            return MathTaskOutcome(message="Номер задачи: 1..9")
        if self.menu_open and self.menu_owner_player_id not in {None, player_id}:
            return MathTaskOutcome(message="Эту задачу выбирает другой игрок")
        self.selected_task = int(task_no)
        self.close_menu()
        if task_no not in {1, 2}:
            self.active = False
            self.current_round = None
            self.pending_answers = []
            self.active_answer_id = None
            return MathTaskOutcome(message=f"Задача {task_no}: пока не реализована")
        self.active = True
        if self.session_started_at_ts is None:
            self.session_started_at_ts = float(now_ts)
        operation = "+" if task_no == 1 else "-"
        self.round_index = 0
        self.produced_count = 0
        self.solved_count = 0
        self.pending_answers = []
        self.active_answer_id = None
        self.next_answer_id = 1
        self.current_round = MathRoundState(stage="pick_first", operation=operation, first_digit=None)
        self.iterations_target = 10
        return MathTaskOutcome(
            message=f"Задача {task_no}: {self.iterations_target} итераций. Найди первое число",
            clear_digits=True,
            clear_answers=True,
            spawn_digits=True,
        )

    def can_player_pick_stage(self, *, player_id: str, stage: str) -> bool:
        if self.current_round is None:
            return False
        owner = self.current_round.assignments.get(stage)
        if owner is None:
            return True
        return owner == player_id

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
        if round_state.stage == "pick_first":
            if not self.can_player_pick_stage(player_id=player_id, stage="pick_first"):
                return MathTaskOutcome(message="Это число назначено другому игроку")
            round_state.first_digit = value
            round_state.stage = "pick_second"
            op = round_state.operation
            return MathTaskOutcome(message=f"Операция: {op}. Найди второе число")
        if round_state.stage == "pick_second":
            if not self.can_player_pick_stage(player_id=player_id, stage="pick_second"):
                return MathTaskOutcome(message="Это число назначено другому игроку")
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
            )
            self.next_answer_id += 1
            self.produced_count += 1
            self.round_index += 1
            self.pending_answers.append(answer)
            round_state.first_digit = None
            round_state.stage = "pick_first"

            out = MathTaskOutcome(message="Пример поставлен в очередь", spawn_digits=True)
            if self.active_answer_id is None:
                self.active_answer_id = answer.answer_id
                out.clear_answers = True
                out.spawn_answers = True
            assigned = answer.assigned_player_id
            if assigned is not None and assigned != player_id:
                out.message = f"Ответ делегирован игроку {assigned}. Ищи следующее число"
            else:
                out.message = "Ответ у тебя. Можно брать следующий пример"
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

    def _pending_by_id(self, answer_id: int) -> MathPendingAnswer | None:
        for item in self.pending_answers:
            if item.answer_id == answer_id and not item.solved:
                return item
        return None

    def _activate_next_pending(self) -> None:
        for item in self.pending_answers:
            if not item.solved:
                self.active_answer_id = item.answer_id
                return
        self.active_answer_id = None

    def _resolve_answer_assignee(self, *, producer_player_id: str, online_player_ids: list[str]) -> str:
        candidates = [pid for pid in online_player_ids if pid and pid != producer_player_id]
        if candidates:
            candidates.sort()
            return candidates[0]
        return producer_player_id

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
