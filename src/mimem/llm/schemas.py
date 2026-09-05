"""What each task is allowed to return.

Every task has a strict output schema and there is no free-text parsing anywhere. That is partly
hygiene and partly enforcement: several design rules are structural claims about the output --
an analogy has a limit, a figure description follows a six-part template, an anchor is under
forty words -- and a schema turns each of them from a hope in a prompt into a value the model
either supplies or does not.

The validators here are the second line of defence, not the first. The prompt asks for the right
thing; the schema refuses the wrong thing; the linter catches what gets through both. Rule
``ANA-01`` in particular is checked in all three places, because an analogy without its limit is
how a listener ends up remembering the analogy instead of the concept.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Rule IMG-01: an anchor is a short scene, not a paragraph. Long enough to be specific, short
#: enough to be held while the exposition continues.
MAX_ANCHOR_WORDS = 40

#: Rule FIG-01: the title-like statement is a caption, not a description.
MAX_FIGURE_STATEMENT_CHARS = 125


class Out(BaseModel):
    """Shared configuration for every task output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GlossOut(Out):
    """A term explained (rules PRE-01, DIF-02).

    Two lengths, because they are used in two places: ``short_def`` goes in the term pre-load
    where seven of them arrive in a row, and ``long_def`` is the full introduction at the point
    the concept first matters.
    """

    short_def: str = Field(max_length=200, description="one line, for the term pre-load")
    long_def: str = Field(max_length=600, description="the first full introduction")
    spoken: str | None = Field(default=None, description="how to say it, if not obvious")


class AnchorOut(Out):
    """A concrete scene for an abstract idea (rules IMG-01, IMG-03)."""

    text: str = Field(max_length=400)

    @model_validator(mode="after")
    def _short_enough(self) -> Self:
        words = len(self.text.split())
        if words > MAX_ANCHOR_WORDS:
            raise ValueError(f"anchor is {words} words, over the {MAX_ANCHOR_WORDS}-word limit")
        return self


class AnalogyOut(Out):
    """An analogy and where it breaks (rule ANA-01)."""

    text: str = Field(max_length=400)
    limit: str = Field(min_length=1, max_length=300, description="where the analogy breaks down")

    @model_validator(mode="after")
    def _limit_is_a_limit(self) -> Self:
        if not self.limit.strip():
            raise ValueError("an analogy must state its limit (rule ANA-01)")
        return self


class WhyOut(Out):
    """One or two sentences on why a claim holds (rule ELB-01)."""

    text: str = Field(max_length=500)


class CompressOut(Out):
    """A shortened restatement of a block triage marked ``compress`` (rule COH-02)."""

    text: str = Field(max_length=1200)


class FigureOut(Out):
    """A figure description in the accessibility template order (rule FIG-01).

    The fields *are* the template. A single free-text description would let the model reorder or
    omit parts of it and leave the linter with prose to pattern-match; six fields make template
    compliance a schema property. ``confidence`` is required because this is the
    highest-hallucination-risk output in the system (rule FIG-07), and a low one degrades to
    caption-only narration rather than being spoken as fact.
    """

    statement: str = Field(max_length=MAX_FIGURE_STATEMENT_CHARS)
    kind: str = Field(max_length=120, description="what kind of figure this is")
    axes: str = Field(max_length=300, description="axes, labels and units")
    trend: str = Field(max_length=400, description="the trend or pattern")
    exceptions: str = Field(default="", max_length=300, description="notable exceptions, if any")
    claim: str = Field(max_length=300, description="the claim the figure supports")
    confidence: float = Field(ge=0.0, le=1.0)


class VerifyOut(Out):
    """The entailment verdict (rule GRD-02)."""

    entailed: bool
    evidence: str = Field(default="", max_length=600, description="the sentence that supports it")
    note: str = Field(default="", max_length=300, description="what is wrong, when it is not")
