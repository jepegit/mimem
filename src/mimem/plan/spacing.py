"""The spacing scheduler: when each concept comes back.

Spacing is the largest effect in the knowledge base (§1.2, g ~= 0.74) and the one a linear audio
programme is worst at: you cannot flip back, so if the programme does not bring an idea back,
nothing does. Rules ``SPC-01`` and ``SPC-02`` say what "brings it back" means -- increasing
intervals measured in narration minutes, a minimum gap of three, roughly geometric, at the
natural boundaries of the document -- and this module is the only place those become real.

The problem: place *n* exposures of *k* concepts on a fixed timeline of boundary slots so that

1. no two exposures of one concept are closer than the minimum gap (``SPC-01``);
2. successive intervals never shrink (``SPC-01``: *increasing*);
3. intervals track a geometric target (``SPC-02``);
4. no boundary is buried under a pile of callbacks;
5. exposures land near their concept's own material where they can.

Greedy, hardest concept first, with the target time driving slot choice -- and, deliberately,
**no relaxation when it does not fit**. A twelve-minute paper cannot hold five exposures three
minutes apart at increasing intervals. The honest outcome is to place what fits, report the rest
as ``unplaced``, and let them become review items and part-two schedule seeds. Quietly shrinking
the gap instead would satisfy the loop and violate the rule the loop exists for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mimem.config import SpacingPolicy

#: How many callbacks one boundary may carry before it stops being a boundary and starts being
#: a list. Two is enough to keep a schedule flexible without turning a segment break into a quiz.
DEFAULT_SLOT_CAPACITY = 2

#: Slots inside the concept's own section are worth a small detour from the ideal time; this is
#: how much, in seconds, one such slot is discounted when choosing.
HOME_SECTION_BONUS = 20.0


@dataclass(frozen=True)
class Slot:
    """A boundary in the programme where a callback can be placed."""

    id: str
    at_seconds: float
    section_id: str | None = None
    capacity: int = DEFAULT_SLOT_CAPACITY


@dataclass(frozen=True)
class Request:
    """A concept that wants ``repetitions`` exposures in total, the first already placed."""

    concept_id: str
    first_at: float
    repetitions: int
    home_section_id: str | None = None
    priority: float = 0.0  # difficulty x importance; ties broken in favour of the harder idea


@dataclass(frozen=True)
class Placement:
    """One scheduled re-exposure."""

    concept_id: str
    slot_id: str
    at_seconds: float
    index: int  # 1 for the first callback, counting the initial exposure as 0


@dataclass
class Schedule:
    """The result: what was placed, and what the document was too short to hold."""

    placements: list[Placement] = field(default_factory=list)
    unplaced: dict[str, int] = field(default_factory=dict)
    next_interval_minutes: dict[str, float] = field(default_factory=dict)

    def for_slot(self, slot_id: str) -> list[Placement]:
        return [p for p in self.placements if p.slot_id == slot_id]

    def for_concept(self, concept_id: str) -> list[Placement]:
        return sorted(
            (p for p in self.placements if p.concept_id == concept_id), key=lambda p: p.at_seconds
        )


def repetitions_for(difficulty: float, importance: float, policy: SpacingPolicy) -> int:
    """How many exposures a concept earns (rule REP-02).

    The budget is ``difficulty x importance`` (rule DIF-02), so a hard idea the paper barely
    uses gets the minimum and a hard idea the paper turns on gets the maximum.
    """
    budget = max(0.0, min(1.0, difficulty * importance))
    span = policy.repetitions_max - policy.repetitions_min
    return policy.repetitions_min + round(span * budget)


def schedule(
    requests: list[Request],
    slots: list[Slot],
    policy: SpacingPolicy,
) -> Schedule:
    """Place the callbacks. Deterministic: the same inputs give the same schedule."""
    result = Schedule()
    ordered_slots = sorted(slots, key=lambda s: (s.at_seconds, s.id))
    used: dict[str, int] = {}
    min_gap = policy.min_gap_minutes * 60.0

    for request in sorted(
        requests, key=lambda r: (-r.repetitions, -r.priority, r.first_at, r.concept_id)
    ):
        last_at = request.first_at
        last_interval = 0.0
        placed = 0
        wanted = max(0, request.repetitions - 1)

        for index in range(1, wanted + 1):
            target_interval = min_gap * policy.interval_ratio ** (index - 1)
            # Rule SPC-01 says *increasing*: never let an interval come in under the last one.
            required = max(min_gap, last_interval)
            slot = _choose(
                ordered_slots,
                used,
                earliest=last_at + required,
                target=last_at + max(target_interval, required),
                home_section_id=request.home_section_id,
            )
            if slot is None:
                break
            used[slot.id] = used.get(slot.id, 0) + 1
            result.placements.append(
                Placement(
                    concept_id=request.concept_id,
                    slot_id=slot.id,
                    at_seconds=slot.at_seconds,
                    index=index,
                )
            )
            last_interval = slot.at_seconds - last_at
            last_at = slot.at_seconds
            placed += 1

        missing = wanted - placed
        if missing:
            result.unplaced[request.concept_id] = missing
        # What part two should do next: keep doubling from where the document left off.
        following = max(min_gap, last_interval) * policy.interval_ratio
        result.next_interval_minutes[request.concept_id] = round(following / 60.0, 2)

    result.placements.sort(key=lambda p: (p.at_seconds, p.concept_id, p.index))
    return result


def _choose(
    slots: list[Slot],
    used: dict[str, int],
    *,
    earliest: float,
    target: float,
    home_section_id: str | None,
) -> Slot | None:
    """The free slot closest to the ideal time, never earlier than ``earliest``."""
    best: Slot | None = None
    best_cost = float("inf")
    for slot in slots:
        if slot.at_seconds < earliest or used.get(slot.id, 0) >= slot.capacity:
            continue
        cost = abs(slot.at_seconds - target)
        if home_section_id is not None and slot.section_id == home_section_id:
            cost -= HOME_SECTION_BONUS
        if cost < best_cost:
            best, best_cost = slot, cost
    return best
