"""The spacing scheduler.

Rules ``SPC-01`` and ``SPC-02`` are a set of invariants over a placement, so they are tested as
invariants: property tests over arbitrary timelines rather than examples over convenient ones.
The scheduler is the one genuinely interesting algorithm in the planner, and the failure mode
that matters is not a crash -- it is a schedule that looks plausible and quietly violates the
minimum gap on the one document where the slots fell awkwardly.

The last property is the important one. A short document *cannot* hold five exposures three
minutes apart at increasing intervals, and the honest response is to place fewer of them, not to
shrink the gap. Anything that placed more than fits would be satisfying the loop rather than
the rule.
"""

from __future__ import annotations

from itertools import pairwise

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from mimem.config import SpacingPolicy
from mimem.plan.spacing import (
    DEFAULT_SLOT_CAPACITY,
    Request,
    Slot,
    repetitions_for,
    schedule,
)

POLICY = SpacingPolicy()
MIN_GAP = POLICY.min_gap_minutes * 60.0


def _slots(count: int, spacing: float = 60.0) -> list[Slot]:
    return [
        Slot(id=f"g{i}", at_seconds=spacing * (i + 1), section_id=f"s{i // 3}")
        for i in range(count)
    ]


slot_lists = st.integers(min_value=1, max_value=40).map(_slots)

requests = st.lists(
    st.builds(
        Request,
        concept_id=st.text("abcdef", min_size=1, max_size=3),
        first_at=st.floats(min_value=0.0, max_value=600.0),
        repetitions=st.integers(min_value=1, max_value=5),
        home_section_id=st.sampled_from([None, "s0", "s1", "s2"]),
        priority=st.floats(min_value=0.0, max_value=1.0),
    ),
    min_size=0,
    max_size=8,
    unique_by=lambda r: r.concept_id,
)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(requests, slot_lists)
def test_placements_respect_the_minimum_gap(rs: list[Request], slots: list[Slot]) -> None:
    """SPC-01, the hard number: never two exposures of one concept inside the minimum gap."""
    result = schedule(rs, slots, POLICY)
    for request in rs:
        times = [request.first_at] + [p.at_seconds for p in result.for_concept(request.concept_id)]
        for previous, current in pairwise(times):
            assert current - previous >= MIN_GAP - 1e-6


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(requests, slot_lists)
def test_intervals_never_shrink(rs: list[Request], slots: list[Slot]) -> None:
    """SPC-01 says *increasing* intervals, which is a separate claim from the minimum gap."""
    result = schedule(rs, slots, POLICY)
    for request in rs:
        times = [request.first_at] + [p.at_seconds for p in result.for_concept(request.concept_id)]
        gaps = [b - a for a, b in pairwise(times)]
        for previous, current in pairwise(gaps):
            assert current >= previous - 1e-6


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(requests, slot_lists)
def test_no_slot_is_overloaded(rs: list[Request], slots: list[Slot]) -> None:
    """A segment boundary carrying six callbacks is not a boundary, it is a quiz."""
    result = schedule(rs, slots, POLICY)
    for slot in slots:
        assert len(result.for_slot(slot.id)) <= slot.capacity


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(requests, slot_lists)
def test_never_more_placements_than_asked_for(rs: list[Request], slots: list[Slot]) -> None:
    placed = {r.concept_id: len(schedule(rs, slots, POLICY).for_concept(r.concept_id)) for r in rs}
    for request in rs:
        assert placed[request.concept_id] <= request.repetitions - 1


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(requests, slot_lists)
def test_unplaced_is_the_honest_remainder(rs: list[Request], slots: list[Slot]) -> None:
    """What did not fit is reported, not silently forgotten -- part two needs to know."""
    result = schedule(rs, slots, POLICY)
    for request in rs:
        wanted = request.repetitions - 1
        placed = len(result.for_concept(request.concept_id))
        assert result.unplaced.get(request.concept_id, 0) == wanted - placed


def test_placement_is_deterministic() -> None:
    """Same inputs, same schedule. Without this a rebuild produces a meaningless diff."""
    rs = [
        Request("a", first_at=10.0, repetitions=3, home_section_id="s0", priority=0.5),
        Request("b", first_at=20.0, repetitions=3, home_section_id="s1", priority=0.5),
    ]
    slots = _slots(20)
    first = schedule(rs, slots, POLICY)
    second = schedule(rs, slots, POLICY)
    assert first.placements == second.placements


def test_a_short_document_places_fewer_rather_than_closer() -> None:
    """The rule that must not bend: five exposures do not fit in four minutes."""
    rs = [Request("a", first_at=0.0, repetitions=5)]
    slots = _slots(4, spacing=60.0)  # four minutes of programme
    result = schedule(rs, slots, POLICY)
    assert len(result.for_concept("a")) == 1  # one callback at three minutes, and no more
    assert result.unplaced["a"] == 3


def test_the_nearest_free_boundary_to_the_target_wins() -> None:
    """SPC-02: intervals track a geometric target, so a callback lands near it, not just after."""
    rs = [Request("a", first_at=0.0, repetitions=2)]
    slots = [
        Slot(id="early", at_seconds=MIN_GAP),
        Slot(id="ideal", at_seconds=MIN_GAP * 1.05),
        Slot(id="late", at_seconds=MIN_GAP * 8),
    ]
    result = schedule(rs, slots, POLICY)
    assert result.for_concept("a")[0].slot_id in {"early", "ideal"}


def test_a_full_slot_pushes_the_next_concept_along() -> None:
    rs = [Request(f"c{i}", first_at=0.0, repetitions=2, priority=1.0 - i / 10) for i in range(3)]
    slots = [Slot(id="only", at_seconds=MIN_GAP), Slot(id="later", at_seconds=MIN_GAP * 3)]
    result = schedule(rs, slots, POLICY)
    assert len(result.for_slot("only")) == DEFAULT_SLOT_CAPACITY
    assert len(result.for_slot("later")) == 1


def test_repetition_count_follows_difficulty_times_importance() -> None:
    """Rule REP-02: the budget is the product, so an easy aside gets the minimum."""
    assert repetitions_for(0.1, 0.1, POLICY) == POLICY.repetitions_min
    assert repetitions_for(1.0, 1.0, POLICY) == POLICY.repetitions_max
    assert POLICY.repetitions_min <= repetitions_for(0.6, 0.6, POLICY) <= POLICY.repetitions_max


def test_a_concept_prefers_a_boundary_in_its_own_section() -> None:
    """The natural position: end of the section that is about it (rule SPC-02)."""
    rs = [Request("a", first_at=0.0, repetitions=2, home_section_id="home")]
    slots = [
        Slot(id="away", at_seconds=MIN_GAP + 5, section_id="elsewhere"),
        Slot(id="home", at_seconds=MIN_GAP + 15, section_id="home"),
    ]
    assert schedule(rs, slots, POLICY).for_concept("a")[0].slot_id == "home"


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(slot_lists)
def test_no_request_is_an_empty_schedule(slots: list[Slot]) -> None:
    assume(slots)
    assert schedule([], slots, POLICY).placements == []
