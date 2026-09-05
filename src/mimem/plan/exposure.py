"""What counts as meeting a concept, and when.

Rule ``SPC-01`` is unenforceable without this definition, so it lives in one module that both
the planner and the linter read. The linter recomputes the log from the script rather than
trusting the planner's bookkeeping, which is the only way the check means anything.

An **exposure** is a *deliberate* encounter with a concept: the first time it is explained, a
callback, a retrieval prompt, a recap, a review item, an anchor. Not every mention -- a paper
names its central concept in most paragraphs, and counting those would make the minimum-gap rule
fire on every document ever written.

Two refinements make the rule match what a listener actually experiences:

**Episodes, not events.** Rule ``STR-06`` requires a section to end with a recap *and* a prompt.
Those are fifteen seconds apart by construction. They are one re-exposure episode, not two, so
exposures inside :data:`EPISODE_WINDOW_SECONDS` are coalesced before any interval is measured.

The same argument runs further, and the first real build proved it: in a section shorter than
the minimum gap, the introduction of a concept and the prompt that closes the section are
minutes apart at most, and no plan can change that -- ``STR-06`` decides where the prompt goes,
not the spacing scheduler. So exposures **inside one section** merge into one episode whenever
they are closer than the minimum gap. Spacing asks whether an idea comes back after you have
moved on; the clock starts at the section boundary.

**Three regions, not one.** The opening names concepts *before* their content exists -- that is
pre-training (``STR-03``), not repetition -- and the closing review is deliberately massed
retrieval across the whole document (``STR-07``). Spacing governs the body, which is where
spacing is a choice rather than a consequence of the structure the other rules require.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mimem.ir import BeatType, ExposureForm, Script

#: Two exposures closer than this are one episode.
EPISODE_WINDOW_SECONDS = 60.0


class Region(StrEnum):
    """Where in the programme an exposure happened."""

    OPENING = "opening"
    BODY = "body"
    REVIEW = "review"


#: Which beat types are an exposure at all, and in what form.
BEAT_FORMS: dict[BeatType, ExposureForm] = {
    BeatType.EXPOSITION: ExposureForm.STATEMENT,
    BeatType.CALLBACK: ExposureForm.CALLBACK,
    BeatType.PROMPT: ExposureForm.PROMPT,
    BeatType.RECAP: ExposureForm.RECAP,
    BeatType.ANCHOR: ExposureForm.ANCHOR,
    BeatType.PRELOAD: ExposureForm.PRELOAD,
    BeatType.PREQUESTION: ExposureForm.PREQUESTION,
}

#: Forms the spacing intervals are measured over (body only; see the module docstring).
SPACED_FORMS: frozenset[str] = frozenset(
    {
        ExposureForm.STATEMENT.value,
        ExposureForm.CALLBACK.value,
        ExposureForm.PROMPT.value,
        ExposureForm.RECAP.value,
        ExposureForm.ANCHOR.value,
    }
)

#: Forms that count as having met the concept, for the part-two hand-off.
COUNTED_FORMS: frozenset[str] = SPACED_FORMS | {ExposureForm.REVIEW.value}


@dataclass(frozen=True)
class LoggedExposure:
    concept_id: str
    at_seconds: float
    beat_id: str
    form: str
    region: Region
    section_id: str | None = None


def exposure_log(script: Script) -> dict[str, list[LoggedExposure]]:
    """Every deliberate exposure in the script, per concept, in programme order."""
    log: dict[str, list[LoggedExposure]] = {}
    introduced: set[str] = set()
    review_ids = {b.id for b in script.review}
    opening_ids = {b.id for b in script.opening}
    sections = {b.id: s.id for s in script.sections for b in s.beats()}

    for beat, at in script.timeline():
        form = BEAT_FORMS.get(beat.type)
        if form is None:
            continue
        if beat.id in review_ids:
            region, form = Region.REVIEW, ExposureForm.REVIEW
        elif beat.id in opening_ids:
            region = Region.OPENING
        else:
            region = Region.BODY
        for concept_id in beat.concept_ids:
            if beat.type is BeatType.EXPOSITION:
                if concept_id in introduced:
                    continue  # only the introduction; the rest are mentions
                introduced.add(concept_id)
            log.setdefault(concept_id, []).append(
                LoggedExposure(concept_id, at, beat.id, form.value, region, sections.get(beat.id))
            )
    for entries in log.values():
        entries.sort(key=lambda e: e.at_seconds)
    return log


def spaced(entries: list[LoggedExposure], min_gap_seconds: float = 0.0) -> list[LoggedExposure]:
    """The exposures the spacing rules apply to: body only, coalesced into episodes."""
    body = [e for e in entries if e.region is Region.BODY and e.form in SPACED_FORMS]
    return coalesce(body, min_gap_seconds=min_gap_seconds)


def coalesce(
    entries: list[LoggedExposure],
    window: float = EPISODE_WINDOW_SECONDS,
    min_gap_seconds: float = 0.0,
) -> list[LoggedExposure]:
    """Merge exposures inside one episode, keeping the first.

    Two exposures are one episode if they are within ``window`` of each other, or if they are in
    the same section and closer than the minimum gap -- see the module docstring for why a
    section boundary is where the spacing clock starts.
    """
    out: list[LoggedExposure] = []
    for entry in entries:
        if not out:
            out.append(entry)
            continue
        previous = out[-1]
        gap = entry.at_seconds - previous.at_seconds
        same_section = previous.section_id is not None and previous.section_id == entry.section_id
        if gap < window or (same_section and gap < min_gap_seconds):
            continue
        out.append(entry)
    return out
