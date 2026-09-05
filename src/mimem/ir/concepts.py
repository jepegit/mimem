"""The concept registry: what the document is *about*, and how hard each idea is.

This is the part of the IR that decides where effort goes. Rule DIF-02 spends the elaboration
budget as a function of ``difficulty x importance``, so these two numbers determine which ideas
get a gloss, which get a concrete anchor, which get repeated three times and which are simply
said once and left alone.

Two commitments follow from that:

**Every score is auditable.** ``signals`` keeps the components that produced it, so a concept
ranked too high can be explained rather than guessed at.

**The registry is meant to be edited.** You know your field better than any heuristic does, and
the fastest way to fix a bad ranking is to change it. ``overrides`` survives regeneration, so a
hand edit is not lost the next time the document is processed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from mimem.ir.models import SCHEMA_VERSION, Base, Span


class ConceptKind(StrEnum):
    TERM = "term"  # "solid electrolyte interphase"
    SYMBOL = "symbol"  # "tau", "C_rate"
    QUANTITY = "quantity"  # "coulombic efficiency"
    ENTITY = "entity"  # "NMC811", "Tesla 4680"
    METHOD = "method"  # "cyclic voltammetry"
    CLAIM = "claim"  # a proposition the paper argues for
    UNKNOWN = "unknown"


class Anchor(Base):
    """A concrete, imageable scene that instantiates an abstract concept (rules IMG-01..03).

    Generated in M5. Stable and unique by construction: the same concept gets the same anchor
    every time it recurs, which is what turns the anchor into a retrieval cue.
    """

    text: str
    generated_by: str | None = None


class Analogy(Base):
    """An analogy, which must state where it breaks (rule ANA-01).

    ``limit`` is not optional and not decorative. An analogy without its limit is how a listener
    ends up remembering the analogy instead of the concept.
    """

    text: str
    limit: str
    generated_by: str | None = None

    @model_validator(mode="after")
    def _limit_is_present(self) -> Self:
        if not self.limit.strip():
            raise ValueError("an analogy must state its limit (rule ANA-01)")
        return self


class Exposure(Base):
    """One time the listener meets a concept (rule SPC-03).

    Filled by the planner in M4. Part 1 does not schedule across sessions, but it must emit
    everything Part 2 needs to: what was said, when in the programme, and in what form.
    """

    beat_id: str | None = None
    at_seconds: float = 0.0
    form: str = "statement"  # statement | prompt | anchor | recap | callback


class Concept(Base):
    """One idea the document turns on."""

    id: str
    canonical: str
    aliases: list[str] = Field(default_factory=list)
    spoken: str | None = None  # rule SYM-01/02, filled from the lexicon or generated
    kind: ConceptKind = ConceptKind.UNKNOWN

    short_def: str | None = None  # one line, for the term pre-load (rule PRE-01)
    long_def: str | None = None
    anchor: Anchor | None = None
    analogy: Analogy | None = None

    difficulty: float = 0.0  # 0..1 (rule DIF-01)
    importance: float = 0.0  # 0..1 (rule DIF-01)
    signals: dict[str, float] = Field(default_factory=dict)

    first_span: Span | None = None
    mentions: int = 0
    exposures: list[Exposure] = Field(default_factory=list)

    #: Hand edits. Applied after scoring and preserved across regeneration, because the fastest
    #: way to fix a ranking is to say what it should be.
    overrides: dict[str, Any] = Field(default_factory=dict)

    @property
    def budget(self) -> float:
        """``difficulty x importance`` -- what rule DIF-02 spends the elaboration budget on."""
        return self.difficulty * self.importance

    def all_forms(self) -> list[str]:
        return [self.canonical, *self.aliases]

    def apply_overrides(self) -> None:
        """Let a hand edit win over anything the heuristics computed."""
        for field, value in self.overrides.items():
            if field in type(self).model_fields and field != "overrides":
                setattr(self, field, value)


class ConceptRegistry(Base):
    """Every concept in one document, plus how it was scored.

    Written as JSON that a person can open and change. Regenerating merges rather than
    overwrites: see :func:`mimem.concepts.registry.merge`.
    """

    schema_version: int = SCHEMA_VERSION
    doc_id: str
    concepts: dict[str, Concept] = Field(default_factory=dict)
    listener: str | None = None  # which listener profile the difficulty scores were shifted by

    def add(self, concept: Concept) -> None:
        self.concepts[concept.id] = concept

    def get(self, concept_id: str) -> Concept:
        return self.concepts[concept_id]

    def ranked(self, limit: int | None = None) -> list[Concept]:
        """Concepts by elaboration budget, most deserving first."""
        out = sorted(self.concepts.values(), key=lambda c: (-c.budget, c.canonical))
        return out[:limit] if limit else out

    def by_form(self, text: str) -> Concept | None:
        needle = text.strip().lower()
        for concept in self.concepts.values():
            if any(form.strip().lower() == needle for form in concept.all_forms()):
                return concept
        return None

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str | bytes) -> ConceptRegistry:
        registry = cls.model_validate_json(data)
        if registry.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"registry schema version {registry.schema_version} != {SCHEMA_VERSION}"
            )
        return registry
