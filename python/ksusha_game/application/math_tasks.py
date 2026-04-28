from __future__ import annotations

from dataclasses import dataclass, field
import random


@dataclass
class MathRoundState:
    stage: str = "pick_first"
    operation: str = "+"
    first_digit: int | None = None
    second_digit: int | None = None
    correct_answer: int | None = None
    answer_options: list[int] = field(default_factory=list)
    assignments: dict[str, str | None] = field(
        default_factory=lambda: {
            "pick_first": None,
            "pick_second": None,
            "pick_answer": None,
        }
    )

    def to_payload(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "operation": self.operation,
            "first_digit": self.first_digit,
            "second_digit": self.second_digit,
            "correct_answer": self.correct_answer,
            "answer_options": list(self.answer_options),
            "assignments": dict(self.assignments),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> MathRoundState | None:
        if not isinstance(payload, dict):
            return None
        stage = str(payload.get("stage", "")).strip()
        if stage not in {"pick_first", "pick_second", "pick_answer"}:
            return None
        operation = str(payload.get("operation", "+")).strip() or "+"
        first = payload.get("first_digit")
        second = payload.get("second_digit")
        correct = payload.get("correct_answer")
        first_digit = int(first) if isinstance(first, int) else None
        second_digit = int(second) if isinstance(second, int) else None
        correct_answer = int(correct) if isinstance(correct, int) else None
        options_raw = payload.get("answer_options", [])
        answer_options: list[int] = []
        if isinstance(options_raw, list):
            for item in options_raw:
                if isinstance(item, int):
                    answer_options.append(item)
        assignments_raw = payload.get("assignments", {})
        assignments = {"pick_first": None, "pick_second": None, "pick_answer": None}
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
            second_digit=second_digit,
            correct_answer=correct_answer,
            answer_options=answer_options,
            assignments=assignments,
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

    def select_task(self, *, player_id: str, task_no: int, now_ts: float) -> MathTaskOutcome:
        if not self.has_math_quest:
            return MathTaskOutcome(message="Сначала найди книгу математики")
        if task_no < 1 or task_no > 9:
            return MathTaskOutcome(message="Номер задачи: 1..9")
        if self.menu_open and self.menu_owner_player_id not in {None, player_id}:
            return MathTaskOutcome(message="Эту задачу выбирает другой игрок")
        self.selected_task = int(task_no)
        self.close_menu()
        if task_no != 1:
            self.active = False
            self.current_round = None
            return MathTaskOutcome(message=f"Задача {task_no}: пока не реализована")
        self.active = True
        if self.session_started_at_ts is None:
            self.session_started_at_ts = float(now_ts)
        return self._start_new_round()

    def can_player_pick_stage(self, *, player_id: str, stage: str) -> bool:
        if self.current_round is None:
            return False
        owner = self.current_round.assignments.get(stage)
        if owner is None:
            return True
        return owner == player_id

    def pick_digit(self, *, player_id: str, digit: int, rng: random.Random) -> MathTaskOutcome:
        if not self.active or self.selected_task != 1 or self.current_round is None:
            return MathTaskOutcome(message=None)
        round_state = self.current_round
        value = max(0, min(9, int(digit)))
        if round_state.stage == "pick_first":
            if not self.can_player_pick_stage(player_id=player_id, stage="pick_first"):
                return MathTaskOutcome(message="Это число назначено другому игроку")
            round_state.first_digit = value
            round_state.stage = "pick_second"
            return MathTaskOutcome(message="Операция: +. Найди второе число")
        if round_state.stage == "pick_second":
            if not self.can_player_pick_stage(player_id=player_id, stage="pick_second"):
                return MathTaskOutcome(message="Это число назначено другому игроку")
            round_state.second_digit = value
            round_state.correct_answer = int(round_state.first_digit or 0) + int(round_state.second_digit or 0)
            round_state.answer_options = self._generate_answer_options(round_state.correct_answer, rng)
            round_state.stage = "pick_answer"
            return MathTaskOutcome(
                message="Найди правильный ответ",
                clear_digits=True,
                spawn_answers=True,
            )
        return MathTaskOutcome(message=None)

    def pick_answer(self, *, player_id: str, answer_value: int) -> MathTaskOutcome:
        if not self.active or self.selected_task != 1 or self.current_round is None:
            return MathTaskOutcome(message=None)
        round_state = self.current_round
        if round_state.stage != "pick_answer":
            return MathTaskOutcome(message=None)
        if not self.can_player_pick_stage(player_id=player_id, stage="pick_answer"):
            return MathTaskOutcome(message="Ответ назначен другому игроку")
        self.total_attempts += 1
        if round_state.correct_answer is not None and int(answer_value) == int(round_state.correct_answer):
            self.total_solved += 1
            out = self._start_new_round()
            out.message = f"Верно! Общий счет: {self.total_solved}"
            out.clear_answers = True
            return out
        return MathTaskOutcome(message="Неверный ответ. Попробуй другой")

    def _start_new_round(self) -> MathTaskOutcome:
        self.round_index += 1
        self.current_round = MathRoundState(
            stage="pick_first",
            operation="+",
            first_digit=None,
            second_digit=None,
            correct_answer=None,
            answer_options=[],
        )
        return MathTaskOutcome(
            message="Задача 1: найди первое число",
            clear_digits=True,
            clear_answers=True,
            spawn_digits=True,
        )

    def _generate_answer_options(self, correct: int, rng: random.Random) -> list[int]:
        correct_value = max(0, min(99, int(correct)))
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
