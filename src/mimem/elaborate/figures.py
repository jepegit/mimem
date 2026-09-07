"""Saying what a figure shows (``PLAN-figures.md`` stage C).

Stage A found the figures and stage B cropped them. This is the part that needs a model, and it
is the highest-hallucination-risk output in the system: a wrong sentence about a figure is
unfalsifiable by ear, because the listener has no access to the thing being described.

So the gate is the design, and it was written from a measurement rather than from caution. Given
the crop of a real four-panel pie chart, a vision model returned a fluent description with
hydrogen and ethylene swapped throughout -- calling a 0.09% sliver "substantial at ~23%" and
putting the 23.35% wedge in an inset "at ~8%" -- and read a 60.27% label as "~69%". Eleven of its
fourteen numeric claims fail :func:`verify`; the other three passed by coincidence, matching a
citation number and a duration elsewhere in the text.

Two rules fall out of that, and neither is a threshold anyone can tune:

**A description may not quote a value the paper never wrote in a sentence.** Numbers read off a
plot are in the image, and from the text's point of view they are indistinguishable from invented
ones -- ``verify`` rejects a correct description and a fabricated one alike. That is not a gate
failure, it is the specification. A description says "well over half"; the exact value stays in
``study.md`` and on the crop, where a reader can check it against the picture. It costs a listener
nothing they had: speech cannot carry a four-decimal percentage anyway.

**And no card may take its answer from one.** The legend misread above is invisible here -- no
number is wrong, no direction reversed, and the sentence is fluent -- so it would reach the
listener. As one spoken sentence, attributed to a figure they can open, that is a cost worth the
feature. As a card it is that error rehearsed at expanding intervals until they believe it. Both
doors are shut in :mod:`mimem.plan.support`, which is where cards get their answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mimem.elaborate.run import GROUNDING_KINDS, ground
from mimem.ir import Block, BlockKind, Document
from mimem.llm.schemas import FigureOut
from mimem.verify import Finding

#: Below this, the description is not spoken and the caption announcement stands (rule FIG-07).
#:
#: A model asked to describe a plot it cannot resolve does not fall silent, it writes something
#: plausible -- so the prompt asks for an honest confidence and this is what honesty buys. The
#: threshold is deliberately unfussy: the interesting rejections come from :func:`verify`, and a
#: number here that looked precise would suggest otherwise.
MIN_CONFIDENCE = 0.6


@dataclass(frozen=True)
class FigureTask:
    """One figure to describe: what is known about it, and where its picture is."""

    block_id: str
    label: str
    number: str
    subject: str
    caption: str
    references: list[str] = field(default_factory=list)
    image: str | None = None

    @property
    def source(self) -> str:
        """What the description is checked against: the paper's own words about this figure."""
        return "\n".join([self.caption, *self.references])


def figure_tasks(doc: Document) -> list[FigureTask]:
    """Every figure worth describing, in reading order.

    Tables are excluded. A table's content is text and belongs to ``TBL-*``; sending one through
    the image path would be asking a vision model to read a picture of words it could have been
    given directly.
    """
    out: list[FigureTask] = []
    for block in doc.blocks:
        if block.kind is not BlockKind.CAPTION:
            continue
        meta = block.attrs.get("caption")
        if not isinstance(meta, dict) or meta.get("label") != "figure":
            continue
        out.append(
            FigureTask(
                block_id=block.id,
                label="figure",
                number=str(meta.get("number", "")),
                subject=str(meta.get("subject", "")),
                caption=block.text,
                references=[
                    doc.block(ref).text
                    for ref in meta.get("references", [])
                    if _has_block(doc, ref)
                ],
                image=meta.get("image"),
            )
        )
    return out


def _has_block(doc: Document, block_id: str) -> bool:
    try:
        doc.block(block_id)
    except KeyError:
        return False
    return True


def verify(out: FigureOut, source: str) -> list[Finding]:
    """Every claim in a description that the paper's own words do not support.

    Faces the direction checks as well as the numeric ones, unlike an anchor or an analogy. An
    anchor is *ours* and is supposed to contain what the paper never said; a figure description
    is a claim about the document, and "capacity falls" where the paper says it rises is the
    failure this exists for.
    """
    return ground(out, source, kinds=GROUNDING_KINDS["figure"])


def accept(out: FigureOut, source: str) -> tuple[bool, list[Finding]]:
    """Whether this description may be spoken, and why not when it may not."""
    findings = verify(out, source)
    if findings:
        return False, findings
    return out.confidence >= MIN_CONFIDENCE, []


def store(block: Block, out: FigureOut) -> None:
    """Put a checked description on its caption block.

    On the block rather than on a concept because a figure is not one: it belongs to a place in
    the document, and the caption is the thing stage A already made the anchor for everything
    else about it.

    Call :func:`accept` first. This does not check anything.
    """
    meta = block.attrs.setdefault("caption", {})
    meta["description"] = out.model_dump(mode="json")


def described(block: Block) -> FigureOut | None:
    """The stored description, if this figure has one that was allowed through."""
    meta = block.attrs.get("caption")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("description")
    if not isinstance(raw, dict):
        return None
    try:
        return FigureOut.model_validate(raw)
    except ValueError:  # pragma: no cover - a hand-edited manifest is not worth a crash
        return None


def spoken(out: FigureOut) -> str:
    """The description in the order rule ``FIG-01`` asks for.

    Title-like statement, then what kind of figure, then the axes, then the trend, then the
    exceptions, then the claim it supports. The order is the rule and it is not decoration:
    naming the kind before the axes tells the listener what shape of thing to hold the numbers
    in, and the claim last means they hear the evidence before the conclusion rather than filing
    the conclusion and stopping.

    Attributed, not hedged. "The figure shows" is where a listener can go and check; marking it
    as *ours* the way an anchor is marked would be wrong, because the data is the paper's.
    """
    parts = [
        _closed(out.statement),
        _closed(f"it's {_article(out.kind)}" if out.kind else ""),
        _closed(out.axes),
        _closed(out.trend),
        _closed(out.exceptions),
        _closed(out.claim),
    ]
    body = " ".join(part for part in parts if part)
    return f"Here's what the figure shows. {body}"


def _closed(text: str) -> str:
    """One field, as a sentence: opened with a capital and closed with a stop.

    The fields arrive as fragments — "share of total gas volume as a percentage" — and joining
    them raw produced "It's four pie charts. each slice is a share", which a speech engine reads
    with the flat intonation of a continuation rather than a new sentence.
    """
    text = " ".join(text.split()).strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".?!" else text + "."


def _article(kind: str) -> str:
    kind = " ".join(kind.split()).strip().rstrip(".")
    if not kind:
        return ""
    if kind.split()[0].lower() in {"a", "an", "the", "four", "two", "three", "several"}:
        return kind
    return f"{'an' if kind[0].lower() in 'aeiou' else 'a'} {kind}"


def image_bytes(task: FigureTask, out_dir: Path) -> bytes | None:
    """The crop stage B rendered, read from disk. ``None`` when there is not one."""
    if not task.image:
        return None
    path = out_dir / task.image
    if not path.exists():
        return None
    return path.read_bytes()
