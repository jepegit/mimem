"""The script: the plan for what gets said, in what order, with what silences.

This is the artefact everything after stage 7 reads. A :class:`Script` is a tree --
sections hold segments, segments hold beats -- plus the bookkeeping that makes the design
rules checkable: which rule produced each beat, which source span backs it, when each concept
is met, and what was dropped to fit the duration budget.

Three commitments are encoded in the model itself.

**A beat knows why it exists.** ``rules`` names the design rules that produced it and ``spans``
names the source it came from. That pair is what makes ``mimem explain`` and rule ``GRD-01``
real rather than aspirational: a beat with no span must be typed as generated scaffolding.

**A pause is a property of a boundary, not a thing that is said.** The plan sketched a ``pause``
beat type; it is a field here instead (``pause_after``). An empty-text beat would need a special
case in every renderer, in the duration arithmetic, and in ``GRD-01`` -- for something that has
no text, no provenance and no concept. Rule ``PAU-01`` is checked on the beat the pause belongs
to, which is also where a human would look for it.

**Nothing vanishes silently.** ``dropped`` records every beat the duration budget removed, with
the rule that authorised the removal (``DUR-02``, ``COH-05``).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from mimem.ir.concepts import Concept
from mimem.ir.models import SCHEMA_VERSION, Base, SourceMeta, Span


class BeatType(StrEnum):
    """What a beat is doing for the listener (rule STR-04).

    The set follows the plan, with the additions the sentence-level rules turned out to need:
    ``position`` for ``ORI-01``, ``prequestion``/``prequestion_close`` for ``STR-02``/``PRQ-02``,
    ``emphasis`` for ``SIG-02``, ``preload`` for ``STR-03``.
    """

    ORIENTATION = "orientation"
    PREQUESTION = "prequestion"
    PREQUESTION_CLOSE = "prequestion_close"
    PRELOAD = "preload"
    POSITION = "position"
    EXPOSITION = "exposition"
    GLOSS = "gloss"
    ANCHOR = "anchor"
    ANALOGY = "analogy"
    ELABORATION = "elaboration"
    EMPHASIS = "emphasis"
    PROMPT = "prompt"
    ANSWER = "answer"
    RECAP = "recap"
    CALLBACK = "callback"
    TRANSITION = "transition"
    FIGURE = "figure"
    TABLE = "table"
    EQUATION = "equation"
    REVIEW = "review"


#: Beat types that are ours rather than the source's, and so may carry no span (rule GRD-01).
#: Every other type makes a claim about the document and must be able to point at where.
GENERATED_TYPES: frozenset[BeatType] = frozenset(
    {
        BeatType.ORIENTATION,
        BeatType.PREQUESTION,
        BeatType.PREQUESTION_CLOSE,
        BeatType.PRELOAD,
        BeatType.POSITION,
        BeatType.ANCHOR,
        BeatType.ANALOGY,
        BeatType.EMPHASIS,
        BeatType.PROMPT,
        BeatType.RECAP,
        BeatType.TRANSITION,
        BeatType.REVIEW,
    }
)

#: Beat types that carry a retrieval attempt, and therefore need a pause (rule PAU-01).
PROMPTING_TYPES: frozenset[BeatType] = frozenset({BeatType.PROMPT, BeatType.PREQUESTION})

#: Beat types that actually *teach* a concept rather than naming it in passing. Rule ``SEG-03``
#: budgets new terms over these: a transition that says "next, gradient boosting" has announced
#: gradient boosting, not introduced it, and charging the segment for it made the working-memory
#: budget fire on segments that were inside it.
TEACHING_TYPES: frozenset[BeatType] = frozenset(
    {
        BeatType.EXPOSITION,
        BeatType.GLOSS,
        BeatType.PRELOAD,
        BeatType.ANCHOR,
        BeatType.ANALOGY,
        BeatType.ELABORATION,
        BeatType.CALLBACK,
        BeatType.ANSWER,
        BeatType.TABLE,
        BeatType.FIGURE,
        BeatType.EQUATION,
    }
)


class PromptType(StrEnum):
    """What a prompt asks for. Recorded on the card so ``RET-02`` is checkable."""

    DEFINITION = "definition"
    MECHANISM = "mechanism"
    DISTINCTION = "distinction"
    VALUE = "value"
    RECALL = "recall"


class ExposureForm(StrEnum):
    """How a concept was met, for the exposure log (rule SPC-03).

    ``PRELOAD`` and ``PREQUESTION`` are the two forms that come *before* the content they name.
    They belong in the log -- the listener did meet the term -- but not in the spacing intervals,
    because a pre-load is pre-training (``STR-03``) rather than a repetition of anything.
    """

    STATEMENT = "statement"
    PROMPT = "prompt"
    ANCHOR = "anchor"
    RECAP = "recap"
    CALLBACK = "callback"
    REVIEW = "review"
    PRELOAD = "preload"
    PREQUESTION = "prequestion"


class Provenance(Base):
    """Where a beat's text came from.

    In M4 every generated beat comes from a named template, and saying so is the point: a
    template is auditable in a way a model output is not, and when the elaboration layer starts
    writing beats in M5 the difference must be visible in the artefact.
    """

    generator: str  # "template:recap", or a model id once M5 lands
    prompt_hash: str | None = None
    verified: bool | None = None  # groundedness verdict (rule GRD-02), filled in M5


class Beat(Base):
    """One thing that gets said, or one silence that follows it."""

    id: str
    type: BeatType
    text: str = ""
    written_text: str | None = None  # richer variant for study.md
    concept_ids: list[str] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    est_seconds: float = 0.0  # speech only
    pause_after: float = 0.0  # silence that follows, in seconds (rules PAU-01..03)
    generated: bool = False  # ours, not the source's
    provenance: Provenance | None = None
    card_id: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        return self.est_seconds + self.pause_after

    @property
    def needs_span(self) -> bool:
        """Rule GRD-01: does this beat have to point at the source?"""
        return self.type not in GENERATED_TYPES


class Segment(Base):
    """A duration-bounded run of beats (rules SEG-01..03)."""

    id: str
    section_id: str
    beats: list[Beat] = Field(default_factory=list)

    @property
    def est_seconds(self) -> float:
        return sum(b.total_seconds for b in self.beats)

    @property
    def concept_ids(self) -> list[str]:
        seen: dict[str, None] = {}
        for beat in self.beats:
            for cid in beat.concept_ids:
                seen.setdefault(cid, None)
        return list(seen)

    def has(self, *types: BeatType) -> bool:
        wanted = set(types)
        return any(b.type in wanted for b in self.beats)


class Section(Base):
    """A run of segments following one section of the source."""

    id: str
    title: str
    order: int = 0
    source_block_id: str | None = None
    segments: list[Segment] = Field(default_factory=list)

    @property
    def est_seconds(self) -> float:
        return sum(s.est_seconds for s in self.segments)

    def beats(self) -> list[Beat]:
        return [b for seg in self.segments for b in seg.beats]


class Card(Base):
    """A retrieval item (rule RET-05). The seed for part two's scheduler.

    ``concept_id`` is optional and ``subject`` is not. Rule ``STR-06`` gives every section a
    closing question, and on a document the extractor finds no concepts in -- a short note, a
    paper whose vocabulary never repeats -- the subject of that question is the section itself.
    A card with no concept still carries a prompt, an answer and the span the answer came from;
    what it cannot do is take part in the spacing schedule, which is a limitation of the
    document rather than of the card.
    """

    id: str
    concept_id: str | None = None
    subject: str  # what the question is about: a concept's name, or the section's
    prompt: str
    answer: str
    prompt_type: PromptType = PromptType.RECALL
    difficulty: float = 0.0
    section_id: str | None = None
    spans: list[Span] = Field(default_factory=list)


class ScheduledReview(Base):
    """When part two should bring a concept back (rule SPC-03).

    Part 1 does not schedule across sessions. It emits what part 2 needs to: how many times the
    listener met the concept, when the last exposure was, and the interval the within-document
    schedule was heading towards when the document ran out.
    """

    concept_id: str
    exposures: int = 0
    last_at_seconds: float = 0.0
    next_interval_minutes: float = 0.0
    unplaced: int = 0  # exposures the document was too short to hold


class DropRecord(Base):
    """A beat the duration budget removed (rules DUR-02, COH-05)."""

    beat_id: str
    beat_type: BeatType
    rule: str
    reason: str
    est_seconds: float = 0.0
    text: str = ""


class Script(Base):
    """The canonical plan for one document."""

    schema_version: int = SCHEMA_VERSION
    doc_id: str
    source: SourceMeta
    profile: str = "study"
    listener: str | None = None
    opening: list[Beat] = Field(default_factory=list)  # orientation, prequestions, pre-load
    sections: list[Section] = Field(default_factory=list)
    review: list[Beat] = Field(default_factory=list)  # the closing review block (rule STR-07)
    registry: dict[str, Concept] = Field(default_factory=dict)
    cards: list[Card] = Field(default_factory=list)
    schedule: list[ScheduledReview] = Field(default_factory=list)
    dropped: list[DropRecord] = Field(default_factory=list)
    budget_seconds: float = 0.0
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- traversal -----------------------------------------------------------------------

    def beats(self) -> list[Beat]:
        """Every beat in speaking order."""
        out = list(self.opening)
        for section in self.sections:
            out.extend(section.beats())
        out.extend(self.review)
        return out

    def segments(self) -> list[Segment]:
        return [seg for section in self.sections for seg in section.segments]

    def beat(self, beat_id: str) -> Beat:
        for b in self.beats():
            if b.id == beat_id:
                return b
        raise KeyError(beat_id)

    def section_of(self, beat_id: str) -> Section | None:
        for section in self.sections:
            if any(b.id == beat_id for b in section.beats()):
                return section
        return None

    def card(self, card_id: str) -> Card | None:
        return next((c for c in self.cards if c.id == card_id), None)

    def timeline(self) -> list[tuple[Beat, float]]:
        """Each beat with the second it starts at. The clock every spacing rule is measured on."""
        out: list[tuple[Beat, float]] = []
        at = 0.0
        for beat in self.beats():
            out.append((beat, at))
            at += beat.total_seconds
        return out

    @property
    def est_seconds(self) -> float:
        return sum(b.total_seconds for b in self.beats())

    # -- persistence ---------------------------------------------------------------------

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str | bytes) -> Script:
        script = cls.model_validate_json(data)
        if script.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"script schema version {script.schema_version} != supported {SCHEMA_VERSION}"
            )
        return script


def beat_id(beat_type: BeatType | str, text: str, salt: str = "") -> str:
    """Content-addressed beat ID (rule TTS-03).

    Content-addressed so that re-rendering a changed document only re-synthesises the beats
    that actually changed. ``salt`` disambiguates beats whose text is genuinely identical --
    two "take a moment" cues are two chunks of audio, not one.
    """
    h = hashlib.blake2s(digest_size=16)
    for part in (str(beat_type), text, salt):
        h.update(part.encode("utf-8", errors="replace"))
        h.update(b"\x1f")
    return "t_" + h.hexdigest()[:12]
