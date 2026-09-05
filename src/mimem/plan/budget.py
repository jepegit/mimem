"""The duration budget: what gets cut when the plan is too long.

Rule ``DUR-02`` gives the document a budget -- by default 1.4x the time it would take to read
the retained content aloud -- and, more importantly, gives the *order* things are cut in:
analogy, then second-order elaboration, then optional figure descriptions, then non-essential
recaps. What that order encodes is that scaffolding is cheaper than content and comfort is
cheaper than retrieval. Retrieval beats and glosses are never the first thing to go, because
they are the reason the programme is longer than the paper in the first place.

There is a floor under all of it: **exposition is never dropped here**. When every droppable
beat is gone and the plan is still over budget, the honest result is an over-budget plan and a
note saying so. A planner that started deleting the paper to hit a time target would be
producing a shorter programme by making it a worse one, and the failure would be invisible --
which is exactly the silent-content-loss failure rule ``COH-05`` exists to prevent.
"""

from __future__ import annotations

from mimem.ir import BeatType, DropRecord, Script, Section

#: Cut in this order (rule DUR-02). Each entry is the beat type and the rule that authorises it.
#:
#: ``DUR-02`` also allows "non-essential recaps" to be cut, and recaps are deliberately absent
#: here: every recap M4 generates is the one rule ``STR-06`` requires at the end of a section, so
#: none of them are non-essential. The first build with recaps in this list produced a plan that
#: satisfied the clock and failed the structure, which is what a budget allowed to overrule a
#: requirement always produces.
DROP_ORDER: tuple[tuple[BeatType, str], ...] = (
    (BeatType.ANALOGY, "ANA-02"),
    (BeatType.ELABORATION, "DUR-02"),
    (BeatType.FIGURE, "DUR-02"),
    (BeatType.EMPHASIS, "DUR-02"),
    (BeatType.CALLBACK, "DUR-02"),
)

#: Never cut to save time. Prompts and their answers are the programme's reason for existing;
#: a prompt cut without its answer would also break rule RET-01.
PROTECTED: frozenset[BeatType] = frozenset(
    {
        BeatType.EXPOSITION,
        BeatType.PROMPT,
        BeatType.ANSWER,
        BeatType.GLOSS,
        BeatType.PREQUESTION,
        BeatType.PREQUESTION_CLOSE,
        BeatType.ORIENTATION,
        BeatType.PRELOAD,
        BeatType.POSITION,
        BeatType.REVIEW,
        BeatType.TABLE,
        BeatType.EQUATION,
        BeatType.RECAP,
    }
)


def budget_seconds(
    straight_read_seconds: float, multiplier: float, floor_seconds: float = 0.0
) -> float:
    """The duration budget for a document (rule DUR-02).

    ``floor_seconds`` is what stops a short document being stripped of the structure that makes
    it a programme: the opening block and the review block cost the same whether the paper is a
    paragraph or a chapter. See :class:`~mimem.config.Profile`.
    """
    return max(straight_read_seconds * multiplier, floor_seconds)


def enforce(script: Script, budget: float) -> list[DropRecord]:
    """Drop beats in the ``DUR-02`` order until the plan fits, and record every removal.

    Mutates ``script``, and records every removal on it: rule COH-05 says a drop is never
    silent, and leaving that to the caller means one caller eventually forgets. The records are
    returned as well, for a caller that wants to report them immediately.
    """
    dropped: list[DropRecord] = []
    if script.est_seconds <= budget:
        return dropped

    for beat_type, rule in DROP_ORDER:
        if beat_type in PROTECTED:  # pragma: no cover - guards a future edit to DROP_ORDER
            continue
        for section in _sections_by_length(script):
            for segment in section.segments:
                if script.est_seconds <= budget:
                    script.dropped.extend(dropped)
                    return dropped
                keep = []
                for beat in segment.beats:
                    if beat.type is beat_type and script.est_seconds > budget:
                        dropped.append(
                            DropRecord(
                                beat_id=beat.id,
                                beat_type=beat.type,
                                rule=rule,
                                reason=f"over the {budget / 60:.0f} minute duration budget",
                                est_seconds=beat.total_seconds,
                                text=beat.text,
                            )
                        )
                        continue
                    keep.append(beat)
                segment.beats = keep
        if script.est_seconds <= budget:
            break

    script.dropped.extend(dropped)
    if script.est_seconds > budget:
        over = (script.est_seconds - budget) / 60.0
        script.notes.append(
            f"over the duration budget by {over:.1f} minutes after cutting everything DUR-02 "
            "allows; exposition is never cut to fit a clock"
        )
    return dropped


def _sections_by_length(script: Script) -> list[Section]:
    """Shortest section first.

    A two-minute section is where a recap is least missed and a callback least needed, so that
    is where the cutting starts. It also spreads the loss: cutting the longest section first
    would strip the part of the paper carrying the most material.
    """
    return sorted(script.sections, key=lambda s: (s.est_seconds, s.order))
