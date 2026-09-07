"""Group a document's figure fragments into figures, and pair each one with its caption.

A figure in a PDF is not an image. It is between one and sixty-six embedded fragments -- panels,
axis labels, legend swatches, each its own block -- plus, for anything a plotting library drew,
vector content that produces no block at all. On a ninety-eight page review, 155 blocks
classified ``FIGURE`` were eleven actual figures and five tables.

So the unit is the **caption**, not the image. The caption is the paper's own sentence about what
the figure shows; it is the only reliable index of which of those 155 fragments are a figure at
all; and it is text, which means everything downstream can use it without a vision model.

Before this pass, on a PDF, both halves were wrong in opposite directions. Figure blocks carry no
text, and ``retained`` requires text, so **no figure ever reached the planner** -- a document's
figures were silently absent rather than announced. Their captions, meanwhile, are ordinary text
blocks, so they were narrated as loose prose: "Chain side reactions during T R of lithium-ion
batteries. Copyright two thousand and twenty three, Science." -- a sentence about a picture the
listener cannot see, with the credit line read out after it.

What this pass produces is one *figure* per caption, carrying the region to crop later
(``PLAN-figures.md`` stage B), the fragments it is made of, and the places in the prose that
refer to it (stage D). Rule ``FIG-06`` -- drop the decorative -- stops being a judgement call and
becomes arithmetic: a fragment nobody captioned is furniture.
"""

from __future__ import annotations

import re

from mimem.ir import BBox, Block, BlockKind, Document

_STAGE = "figures"

#: The caption's own label and number: "Figure 3.", "Table 1:", "Scheme 2 —".
LABEL_RE = re.compile(
    r"^\s*(?P<label>fig(?:ure)?|table|scheme|chart|plate)\s*\.?\s*(?P<number>\d+|[IVXLC]+)"
    r"(?:\s*[.:)]|\s+[-–—]\s+)\s*",  # noqa: RUF001 - a spaced dash delimits some captions
    re.IGNORECASE,
)

#: Credit and copyright lines that publishers append to a reproduced figure's caption. They are
#: furniture in the sense of ``COH-01``, but they arrive welded to a sentence worth keeping, so
#: they are trimmed here rather than dropped by triage.
CREDIT_RE = re.compile(
    r"\s*(?:reproduced|adapted|reprinted)\s+(?:with\s+permission\s+)?from\b.*$"
    r"|\s*copyright\s*(?:©|\(c\))?\s*\d{4}.*$"
    r"|\s*©\s*\d{4}.*$",
    re.IGNORECASE | re.DOTALL,
)

#: A figure's fragments sit directly above its caption, with nothing else between. Walking up and
#: stopping at the first non-figure block is what separates two figures on one page: page 26 of
#: the test paper carries Figures 8 and 9 and 38 fragments between them.
#:
#: Some journals set the caption above the artwork instead. When nothing is found above, the same
#: walk runs downward.
_TABLE_LABELS = frozenset({"table"})


def link_figures(doc: Document) -> Document:
    """Pair every caption with its region, and mark the fragments that belong to it.

    A pass within stage 2 rather than a stage of its own, so it does not appear in
    ``doc.stages`` -- that list is the pipeline's contract with the CLI, which lets you stop
    after any stage and resume. Idempotence comes from the marker on the captions themselves.
    """
    captions = [b for b in doc.blocks if b.kind is BlockKind.CAPTION]
    if any("caption" in b.attrs for b in captions):
        return doc
    fragments = [b for b in doc.blocks if b.kind is BlockKind.FIGURE]
    tables = [b for b in doc.blocks if b.kind is BlockKind.TABLE]
    claimed: set[str] = set()
    figures = 0

    for caption in captions:
        parsed = LABEL_RE.match(caption.text)
        label = (parsed.group("label") if parsed else "figure").lower()
        number = parsed.group("number") if parsed else ""
        subject = _subject(caption.text)

        is_table = label in _TABLE_LABELS
        caption.attrs["caption"] = {
            "label": "table" if is_table else "figure",
            "number": number,
            "subject": subject,
            "references": _references(doc, label, number),
        }

        members = _members(caption, tables if is_table else fragments, claimed)
        claimed.update(b.id for b in members)
        for member in members:
            # The caption speaks for these now, so they must not announce themselves as well.
            # In a Markdown source the table block carries its own text and would otherwise
            # produce a second "there is a table here" beside the caption's.
            member.parent_id = caption.id
        caption.attrs["caption"]["members"] = [b.id for b in members]
        # The written track has to keep what the audio track cannot say. Suppressing the table
        # block's own beat removed its values from study.md along with its announcement, and
        # NUM-06 caught it within one build -- so the caption carries its content forward.
        # Figure fragments have no text, so this costs nothing on a PDF.
        content = "\n\n".join(b.text.strip() for b in members if b.text.strip())
        if content:
            caption.attrs["caption"]["content"] = content

        if is_table:
            # A table is text. Its caption sits above its content rather than below it, and
            # rendering the region would produce a picture of words -- so tables are paired for
            # TBL-01's benefit and never given a region.
            continue
        region = _union(members)
        caption.attrs["caption"]["region"] = region.model_dump() if region else None
        if members:
            figures += 1

    orphans = [b for b in fragments if b.id not in claimed]
    for orphan in orphans:
        orphan.attrs["decorative"] = True

    doc.note(
        "figures",
        f"paired {figures} figures with their captions; "
        f"{len(orphans)} of {len(fragments)} fragments have no caption (rule FIG-06)",
        stage=_STAGE,
    )
    return doc


def _subject(text: str) -> str:
    """The title-like statement: what this figure is *of*, in one clause.

    "Figure 1. Chain side reactions during TR of lithium-ion batteries [9]. Copyright 2023,
    Science." becomes "Chain side reactions during TR of lithium-ion batteries [9]" -- the
    citation is left for the citation verbalizer, which already removes it.

    Panel enumerations stop it. A caption reading "Early detection of ISC using Dynamic Time
    Warping. (a) DTW distance matrix; (b) warping path..." is a title followed by a legend, and
    the legend is unusable in speech: it is a list of labels for regions of an image nobody can
    see. ``FIG-01`` asks for a title-like statement under 125 characters and that is exactly the
    part worth saying, so the rest stays in the written track where it can be read against the
    picture.
    """
    body = LABEL_RE.sub("", text.strip())
    body = CREDIT_RE.sub("", body)

    # The first segment that is not a panel marker. Usually that is the text before the first
    # one; captions that open on "(a)" have no title above their legend, and the first panel's
    # own description is the best short answer to what the figure is of.
    segments = [s.strip() for s in PANEL_RE.split(body) if s and s.strip()]
    body = segments[0] if segments else body

    # Cut at a sentence, never at a character. The cap used to apply to the raw string, which
    # ended announcements on "...among the probabilistic ML algorithms listed here, GPR stands."
    # -- a clause severed mid-verb and then closed with a full stop by the beat factory.
    first = _SENTENCE_END.split(body, maxsplit=1)[0]
    body = " ".join(first.split()).rstrip(" .;,:")
    if len(body) > TITLE_CHARS:
        body = body[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" .;,:")
    return body


#: A panel marker: "(a)", a panel range such as "(b-d)", and the bare "a)" some journals use.
#: Everything from the first one onward is a legend for parts of a picture, not a description of
#: it.
PANEL_RE = re.compile(
    r"\s*[(\[]\s*[a-h]\s*(?:[-–—,]\s*[a-h]\s*)?[)\]]|\s+[a-h]\)\s"  # noqa: RUF001
)

#: Rule FIG-01's cap on the title-like statement.
TITLE_CHARS = 125

#: A sentence boundary inside a caption. Deliberately stricter than the document splitter: a
#: caption is full of "No.1" and "et al." and "vs.", and splitting on those would truncate the
#: title. Requires the period to be followed by a capital or an opening bracket.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


def _members(caption: Block, candidates: list[Block], claimed: set[str]) -> list[Block]:
    """What this caption speaks for: contiguous, same page, nothing else between.

    Falls back to reading-order adjacency when there is no geometry. A PDF has bounding boxes
    and needs them -- page 26 of the test paper carries two figures and 38 fragments. A Markdown
    or EPUB source has neither boxes nor fragments: the table is the block next to its caption,
    and that is the whole of it.
    """
    free = [b for b in candidates if b.id not in claimed]
    if not free:
        return []
    if caption.bbox is None or caption.page is None:
        return _adjacent(caption, free)
    same_page = [b for b in free if b.page == caption.page and b.bbox is not None]
    if not same_page:
        return _adjacent(caption, free)
    above = _walk(caption, same_page, upward=True)
    return above or _walk(caption, same_page, upward=False)


def _adjacent(caption: Block, candidates: list[Block]) -> list[Block]:
    """The block immediately before or after the caption in reading order."""
    neighbours = [b for b in candidates if abs(b.order - caption.order) == 1]
    neighbours.sort(key=lambda b: b.order)
    return neighbours[:1]


def _walk(caption: Block, fragments: list[Block], *, upward: bool) -> list[Block]:
    """Take fragments away from the caption until something that is not a fragment intervenes.

    "Something that intervenes" is judged by position alone: the fragments are sorted by how far
    they are from the caption, and the walk stops at the first gap wider than a paragraph. That
    is enough to separate two figures on one page without needing to know what sits between them.
    """
    assert caption.bbox is not None
    edge = caption.bbox.y0 if upward else caption.bbox.y1
    candidates = [
        b
        for b in fragments
        if b.bbox is not None and (b.bbox.y1 <= edge + 2 if upward else b.bbox.y0 >= edge - 2)
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda b: -b.bbox.y1 if upward else b.bbox.y0)  # type: ignore[union-attr]

    taken: list[Block] = []
    frontier = edge
    for block in candidates:
        assert block.bbox is not None
        gap = frontier - block.bbox.y1 if upward else block.bbox.y0 - frontier
        if taken and gap > MAX_FRAGMENT_GAP:
            break
        taken.append(block)
        frontier = block.bbox.y0 if upward else block.bbox.y1
    return taken


#: Points of whitespace between two fragments of one figure. Wider than this and they belong to
#: different figures, or the caption's figure has ended and body text follows.
MAX_FRAGMENT_GAP = 60.0


def _union(blocks: list[Block]) -> BBox | None:
    boxes = [b.bbox for b in blocks if b.bbox is not None]
    if not boxes:
        return None
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def _references(doc: Document, label: str, number: str) -> list[str]:
    """Blocks whose prose refers to this figure, for rule ``FIG-04``'s placement.

    Collected here because the caption is what knows its own number. Two of the eleven figures in
    the paper this was written against are never referred to at all, so a caller must have a
    fallback -- this returns an empty list and says nothing about where the figure should go.
    """
    if not number:
        return []
    pattern = re.compile(rf"\b{label}s?\.?\s*{re.escape(number)}\b", re.IGNORECASE)
    return [
        b.id
        for b in doc.blocks
        if b.kind in {BlockKind.PARAGRAPH, BlockKind.LIST_ITEM} and pattern.search(b.text)
    ]
