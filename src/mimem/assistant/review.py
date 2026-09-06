"""Remembering what you answered, so that tomorrow's session is not today's.

This is the first piece of Part 2, and it deliberately crosses a Part 1 non-goal ("no
cross-session scheduling"). The reason is simple: spacing is the largest effect in the knowledge
base and the whole justification for the project, and a study session that forgets you is not a
study session.

Two commitments, both about being able to change my mind later.

**The log is append-only and richer than the scheduler.** One JSON line per answer, in a file you
can open in a text editor. State is *derived* by replaying it, so a better scheduler can be
fitted to real answers later instead of guessed at now — and switching schedulers costs nothing,
because nothing was ever overwritten.

**The scheduler is deliberately dull.** Get it right and the interval grows by the profile's
ratio; get it wrong and it goes back to a day. It is not SM-2, does not model difficulty, does
not pretend to. Rule ``SPC-02``'s geometric intervals are the same idea at document scale, and
using the same shape across sessions is the least surprising thing to do until there is data
saying otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

#: The first interval after a correct answer, and the floor after a wrong one.
FIRST_INTERVAL_DAYS = 1.0

#: What a correct answer multiplies the interval by. The same ratio rule SPC-02 uses inside a
#: document, for the same reason: the forgetting between exposures is what makes the next one
#: work, so each gap should be longer than the last.
DEFAULT_RATIO = 2.5

#: No interval grows past this. Beyond a year, a review is a new introduction anyway.
MAX_INTERVAL_DAYS = 365.0


@dataclass(frozen=True)
class Answer:
    """One recorded attempt. This is the line that goes in the file."""

    card_id: str
    programme_id: str
    correct: bool
    at: datetime
    interval_days: float  # the interval this answer *earned*, for the next time
    concept_id: str | None = None
    note: str = ""

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "card_id": self.card_id,
            "programme_id": self.programme_id,
            "concept_id": self.concept_id,
            "correct": self.correct,
            "at": self.at.isoformat(timespec="seconds"),
            "interval_days": round(self.interval_days, 3),
            "note": self.note,
        }
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Answer:
        return cls(
            card_id=str(raw["card_id"]),
            programme_id=str(raw.get("programme_id", "")),
            concept_id=raw.get("concept_id"),
            correct=bool(raw.get("correct")),
            at=datetime.fromisoformat(str(raw["at"])),
            interval_days=float(raw.get("interval_days", FIRST_INTERVAL_DAYS)),
            note=str(raw.get("note", "")),
        )


@dataclass(frozen=True)
class CardState:
    """Where one card stands, derived from its answers."""

    card_id: str
    reviews: int
    correct: int
    last_at: datetime
    interval_days: float

    @property
    def due_at(self) -> datetime:
        return self.last_at + timedelta(days=self.interval_days)

    def is_due(self, now: datetime) -> bool:
        return now >= self.due_at


def next_interval(previous_days: float, correct: bool, ratio: float = DEFAULT_RATIO) -> float:
    """How long to wait before asking again."""
    if not correct:
        return FIRST_INTERVAL_DAYS
    if previous_days <= 0:
        return FIRST_INTERVAL_DAYS
    return min(previous_days * ratio, MAX_INTERVAL_DAYS)


@dataclass
class ReviewLog:
    """The append-only record of every answer, and the state derived from it."""

    path: Path
    _answers: list[Answer] = field(default_factory=list)
    _loaded: bool = False

    @classmethod
    def open(cls, root: Path) -> ReviewLog:
        return cls(path=root / "reviews.jsonl")

    def _load(self) -> list[Answer]:
        if self._loaded:
            return self._answers
        answers: list[Answer] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    answers.append(Answer.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, ValueError):
                    # A corrupt line loses one answer, not the history. Skipping beats
                    # refusing to start.
                    continue
        answers.sort(key=lambda a: a.at)
        self._answers, self._loaded = answers, True
        return answers

    def record(
        self,
        card_id: str,
        programme_id: str,
        correct: bool,
        *,
        concept_id: str | None = None,
        note: str = "",
        ratio: float = DEFAULT_RATIO,
        now: datetime | None = None,
    ) -> Answer:
        """Append one answer and return it, with the interval it earned."""
        now = now or datetime.now(UTC)
        state = self.state().get(card_id)
        interval = next_interval(state.interval_days if state else 0.0, correct, ratio)
        answer = Answer(
            card_id=card_id,
            programme_id=programme_id,
            concept_id=concept_id,
            correct=correct,
            at=now,
            interval_days=interval,
            note=note,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(answer.to_json() + "\n")
        self._load().append(answer)
        return answer

    def state(self) -> dict[str, CardState]:
        """Replay the log. Never stored, so the scheduler can change without a migration."""
        out: dict[str, CardState] = {}
        for answer in self._load():
            previous = out.get(answer.card_id)
            out[answer.card_id] = CardState(
                card_id=answer.card_id,
                reviews=(previous.reviews if previous else 0) + 1,
                correct=(previous.correct if previous else 0) + int(answer.correct),
                last_at=answer.at,
                interval_days=answer.interval_days,
            )
        return out

    def answers(self) -> list[Answer]:
        return list(self._load())


def select(
    cards: list[dict[str, Any]],
    state: dict[str, CardState],
    *,
    count: int = 10,
    now: datetime | None = None,
    max_new: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """What to ask next: everything overdue, then a few new ones.

    Due cards come first because a card you are about to forget is worth more than a card you
    have never seen — and ``max_new`` exists because a freshly built programme has sixty cards
    and starting all of them at once produces sixty cards all due tomorrow.
    """
    now = now or datetime.now(UTC)
    due: list[dict[str, Any]] = []
    fresh: list[dict[str, Any]] = []

    for card in cards:
        card_state = state.get(str(card.get("id")))
        if card_state is None:
            fresh.append(card)
        elif card_state.is_due(now):
            due.append(card)

    due.sort(key=lambda c: state[str(c["id"])].due_at)
    fresh.sort(key=lambda c: -float(c.get("difficulty") or 0.0))

    chosen = due[:count]
    chosen += fresh[: max(0, min(max_new, count - len(chosen)))]
    return chosen, {"due": len(due), "new": len(fresh), "returned": len(chosen)}
