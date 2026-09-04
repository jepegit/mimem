"""Render a triaged document into narration text.

This is not the planner. There are no prequestions, no retrieval beats, no spacing and no
anchors yet -- those are M4, and they are what make the output *memorable*. What this produces
is the thing that has to work first: a straight reading of the retained content in which
nothing is unspeakable.

That distinction matters for judging the output. If it sounds flat, it is supposed to; if it
says "open square bracket twelve" or "milli ampere hour slash gram", something here is broken.

Two tracks are emitted from the same content, deliberately not identical (rule 4.6):

* ``audio.md`` -- only what the engine should say;
* ``study.md`` -- the same material with the source text, page anchors and everything the audio
  track had to leave behind, so that no exact value is ever destroyed (rule NUM-06).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mimem.config import Listener, Profile
from mimem.ir import Block, BlockKind, Document, TriageAction
from mimem.triage.rules import retained
from mimem.verbalize import count_superscript_citations, verbalize_block, verbalize_text
from mimem.verbalize.citations import MIN_SUPERSCRIPT_EVIDENCE

#: Headings are spoken, not displayed, so they need to sound like speech.
_SECTION_LEAD = "Section: "


@dataclass
class Narration:
    """The rendered output of stage 8, in its M2 form."""

    audio: str
    study: str
    spoken_words: int = 0
    blocks_rendered: int = 0
    pending: dict[str, int] = field(default_factory=dict)

    def estimated_seconds(self, profile: Profile) -> float:
        return 60.0 * self.spoken_words / profile.wpm


def uses_superscript_citations(doc: Document) -> bool:
    """Does this paper cite with superscript numbers rather than brackets?

    Decided once for the whole document, like line numbering: a single digit welded to a
    word is far more likely to be a variable than a citation, and deleting it on that
    evidence would be silent corruption. A few dozen of them is a house style.
    """
    found = sum(count_superscript_citations(b.text) for b in retained(doc))
    return found >= MIN_SUPERSCRIPT_EVIDENCE


def _heading_line(
    block: Block,
    profile: Profile,
    listener: Listener | None,
    *,
    strip_superscripts: bool = False,
) -> str:
    """A heading is speech too.

    It is easy to forget, because a heading looks like a label rather than a sentence --
    and then "Tesla 4680 cell" and "retaining up to 70-80%" reach the engine unverbalized.
    """
    text = (
        verbalize_text(block.text, profile, listener, strip_superscripts=strip_superscripts)
        .strip()
        .rstrip(".")
    )
    return f"{_SECTION_LEAD}{text}." if text else ""


def narrate(doc: Document, profile: Profile, listener: Listener | None = None) -> Narration:
    """Render the retained blocks of ``doc`` into narration text."""
    audio: list[str] = []
    study: list[str] = []
    pending: dict[str, int] = {}
    spoken_words = 0
    rendered = 0

    superscripts = uses_superscript_citations(doc)

    title = doc.source.title or "Untitled"
    spoken_title = verbalize_text(title, profile, listener, strip_superscripts=superscripts).rstrip(
        "."
    )
    audio.append(f"{spoken_title}.")
    study.append(f"# {title}\n")
    if doc.source.authors:
        study.append(f"*{', '.join(doc.source.authors[:6])}*\n")

    for block in retained(doc):
        assert block.triage is not None
        if block.kind is BlockKind.HEADING:
            spoken = _heading_line(block, profile, listener, strip_superscripts=superscripts)
            study.append(f"\n{'#' * min((block.level or 1) + 1, 6)} {block.text.strip()}\n")
        else:
            spoken = verbalize_block(block, profile, listener, strip_superscripts=superscripts)
            if block.triage.action is TriageAction.TRANSFORM:
                pending[block.kind.value] = pending.get(block.kind.value, 0) + 1
            study.append(_study_entry(block))

        if not spoken.strip():
            continue
        audio.append(spoken)
        spoken_words += len(spoken.split())
        rendered += 1

    return Narration(
        audio="\n\n".join(audio).strip() + "\n",
        study="\n".join(study).strip() + "\n",
        spoken_words=spoken_words,
        blocks_rendered=rendered,
        pending=pending,
    )


def _study_entry(block: Block) -> str:
    """The written counterpart of a block: the source text, plus where it came from."""
    anchor = f"p{block.page}" if block.page else block.id[:8]
    marker = ""
    if block.triage and block.triage.action is TriageAction.COMPRESS:
        marker = "  <sub>marked for compression (COH-02)</sub>"
    if block.kind in {BlockKind.TABLE, BlockKind.FIGURE, BlockKind.EQUATION, BlockKind.CODE}:
        marker = f"  <sub>{block.kind.value}: full verbalizer lands in M5</sub>"
    body = block.text.strip()
    if block.kind is BlockKind.EQUATION or block.kind is BlockKind.CODE:
        body = f"```\n{body}\n```"
    return f"\n{body}  <sub>[{anchor}]</sub>{marker}\n"
