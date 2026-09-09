"""Splitting the source's long sentences (rule SENT-01).

The design rule is one line and the whole module follows from it: *long source sentences are
split, not compressed*. A sentence a reader parses by going back a line is simply lost in audio,
and 465 of the stress corpus's sentences are over the thirty-five-word cap -- the largest single
family of lint findings in the project, and the one the rule's own docstring says belongs to a
rewriting stage.

**Why a split is the one rewrite that can be checked.** Everything else stage 6 produces is
*new* text -- a gloss, an anchor, an analogy -- and the check can only ask whether it invented
something. A split invents nothing by definition, so the check runs both ways: every number and
name in the source must appear in the split, and every number and name in the split must appear
in the source. A summary passes the first test and fails the second; that asymmetry is what
makes the difference between splitting and compressing mechanically detectable, and it is the
only reason this is safe to do to a paper's own words.

**The source is never edited.** The split is stored beside the sentence it replaces and the span
still points at what the paper wrote, so ``study.md`` can show one against the other and the
groundedness check has something real to check against. What changes is only what is spoken.

**Selection is measured on the spoken form, not the written one.** "298 K" is two words on the
page and four in the ear, so a sentence that is comfortably inside the cap when read can be well
over it when heard -- which is what the linter sees and what the listener gets.
"""

from __future__ import annotations

from dataclasses import dataclass

from mimem.config import Listener, Profile
from mimem.ir import Block, BlockKind, Document, TriageAction
from mimem.verify import Finding, Severity, numbers_in

#: Kinds whose text is not read out as prose. A table announced by its caption has no sentences
#: to split, and an equation's words are not the thing it means.
NOT_PROSE = frozenset(
    {BlockKind.TABLE, BlockKind.FIGURE, BlockKind.EQUATION, BlockKind.CODE, BlockKind.CAPTION}
)

#: How much longer the split may be than the sentence it replaces. Splitting costs words --
#: a repeated subject, a connective made explicit -- and a little growth is the point. Half as
#: much again is not a split, it is an expansion, and expansion is where facts get added.
MAX_GROWTH = 1.5

#: Sentences to split in one build, most over the cap first. A cap on calls, because this is the
#: one task whose candidate count scales with the length of the document rather than with the
#: number of concepts: a ninety-eight page review offered 1,400 of them.
DEFAULT_MAX_SPLITS = 40


@dataclass(frozen=True)
class LongSentence:
    """A sentence over the cap, and where it is."""

    block_id: str
    start: int
    end: int
    text: str
    spoken_words: int

    @property
    def key(self) -> str:
        return f"{self.start}:{self.end}"


def _narrated(doc: Document) -> list[Block]:
    """Blocks whose sentences the programme will read out one by one."""
    return [
        block
        for block in doc.blocks
        if block.text.strip()
        and block.kind not in NOT_PROSE
        and not (block.triage is not None and block.triage.action is not TriageAction.KEEP)
    ]


def over_long(
    doc: Document, profile: Profile, listener: Listener | None = None, *, cap: int | None = None
) -> list[LongSentence]:
    """Every sentence the listener would meet over the cap, longest first.

    Counted on the verbalized text, because that is the sentence the listener hears and the one
    the linter measures. Reading the written form instead misses the sentences that are long
    *because* of what they state: "a capacity of 3867.3 mAhg-1 at 0.1 C" is seven words written
    and nineteen spoken.
    """
    from mimem.lint.rules import SentenceLength
    from mimem.render.narrate import uses_superscript_citations
    from mimem.verbalize import verbalize_text

    limit = cap if cap is not None else SentenceLength.HARD_CAP
    superscripts = uses_superscript_citations(doc)

    out: list[LongSentence] = []
    for block in _narrated(doc):
        for start, end in block.sentences or [(0, len(block.text))]:
            written = block.text[start:end].strip()
            if not written:
                continue
            spoken = verbalize_text(written, profile, listener, strip_superscripts=superscripts)
            words = len(spoken.split())
            if words > limit:
                out.append(LongSentence(block.id, start, end, written, words))
    out.sort(key=lambda s: -s.spoken_words)
    return out


def verify_split(original: str, sentences: list[str], *, cap: int) -> list[Finding]:
    """Everything wrong with a proposed split, or nothing (rules SENT-01, GRD-03).

    Six checks, and the first two are the ones that matter. A split is *lossless*, so the numbers
    have to match in both directions -- a dropped value is a fact the listener will never hear
    and an added one is a fact the paper never stated. Neither is visible in the prose.
    """
    out: list[Finding] = []
    joined = " ".join(sentences).strip()

    # The direction rule GRD-03 cannot check, because everything else stage 6 writes is allowed
    # to leave things out and a split is not. A summary of a sentence passes every check in
    # `check` and fails this one, which is the whole basis for doing this to a paper's own words.
    for value in sorted(set(numbers_in(original)) - set(numbers_in(joined))):
        out.append(
            Finding(
                kind="number",
                value=value,
                message="dropped by the split; a split may not lose a value",
            )
        )

    # ...and the direction it can: invented numbers, invented names, and a flipped comparison.
    # "higher" for "lower" is the worst thing this system can produce and it reads perfectly.
    from mimem.verify import check

    out.extend(check(joined, original))

    if len(sentences) < 2:
        out.append(
            Finding(
                kind="split",
                value=str(len(sentences)),
                message="one sentence back; nothing was split",
                severity=Severity.WARNING,
            )
        )
    over = [s for s in sentences if len(s.split()) > cap]
    if over:
        out.append(
            Finding(
                kind="split",
                value=f"{len(over)} of {len(sentences)}",
                message=f"still over the {cap}-word cap, so the split did not do its job",
                severity=Severity.WARNING,
            )
        )
    if len(joined.split()) > MAX_GROWTH * len(original.split()):
        out.append(
            Finding(
                kind="split",
                value=f"{len(joined.split())} words from {len(original.split())}",
                message="longer than a split should be; this is an expansion",
            )
        )
    return out
