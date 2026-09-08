"""Running heads and footers, and the page label that hid one of them.

The corpus case: two ACS papers awaiting an issue number are paginated A, B, C..., and the
footer carries that letter beside the citation line. Every page's footer therefore had its own
signature, none of them repeated, and the block stayed in the document -- where, because a
footer sits between two halves of a column, paragraph merging pulled it *into a sentence*:
"the yolk-shell structure is much higher dx.doi.org Nano Lett." Nine lint errors across two
papers, all of them mid-paragraph.
"""

from __future__ import annotations

import pytest

from mimem.clean.artifacts import strip_page_artifacts
from mimem.ir import BBox, Block, BlockKind, Document, SourceMeta

FOOTER = "dx.doi.org/10.1021/nl3014814 | Nano Lett. XXXX, XXX, XXX-XXX"
PAGES = 7


def _paper(footers: list[str]) -> Document:
    """A paper with a body block and a footer on each page, the footer at the bottom edge."""
    blocks: list[Block] = []
    for page, footer in enumerate(footers, start=1):
        blocks.append(
            Block(
                id=f"body{page}",
                kind=BlockKind.PARAGRAPH,
                text="The capacity retention of the yolk-shell structure is much higher than",
                page=page,
                bbox=BBox(x0=50, y0=100, x1=550, y1=700),
                order=len(blocks),
            )
        )
        blocks.append(
            Block(
                id=f"foot{page}",
                kind=BlockKind.PARAGRAPH,
                text=footer,
                page=page,
                bbox=BBox(x0=300, y0=760, x1=555, y1=770),
                order=len(blocks),
            )
        )
    return Document(id="d", source=SourceMeta(format="pdf", n_pages=len(footers)), blocks=blocks)


def _kinds(doc: Document) -> list[BlockKind]:
    return [b.kind for b in doc.blocks if b.id.startswith("foot")]


@pytest.mark.parametrize(
    "label",
    [
        # Its own line, which is how the PDF emits it...
        "{footer}\n{letter}",
        # ...and joined onto the line, which is how it arrives here, because dehyphenate runs
        # first and closes the gap.
        "{letter} {footer}",
    ],
    ids=["own-line", "joined"],
)
def test_a_page_label_does_not_hide_a_repeated_footer(label: str) -> None:
    letters = "ABCDEFG"
    doc = _paper([label.format(footer=FOOTER, letter=letters[i]) for i in range(PAGES)])
    strip_page_artifacts(doc)
    assert _kinds(doc) == [BlockKind.PAGE_ARTIFACT] * PAGES


def test_the_first_page_footer_is_the_same_furniture_with_more_stuck_to_it() -> None:
    """It appears once, so repetition alone never reaches it.

    On the first page the running footer carries the copyright line, or the received-and-revised
    dates. It is read out in the same place and says as little.
    """
    footers = [f"© XXXX American Chemical Society\nA\n{FOOTER}"]
    footers += [f"{FOOTER}\n{letter}" for letter in "BCDEFG"]
    doc = _paper(footers)
    strip_page_artifacts(doc)
    assert _kinds(doc) == [BlockKind.PAGE_ARTIFACT] * PAGES
    assert doc.block("foot1").attrs["artifact_reason"].startswith("contains a footer")


def test_the_same_footer_spaced_differently_is_the_same_footer() -> None:
    """ "| Nano Lett." on one page and "|Nano Lett." on the next, in one real paper."""
    doc = _paper([FOOTER, FOOTER.replace("| Nano", "|Nano")] * 3 + [FOOTER])
    strip_page_artifacts(doc)
    assert _kinds(doc) == [BlockKind.PAGE_ARTIFACT] * PAGES


def test_a_paragraph_that_happens_to_reach_the_bottom_of_the_page_is_not_furniture() -> None:
    """The guard. Repetition and position are the evidence; neither alone is enough.

    The sentences have to differ in their *words*, not just their numbers: "page 4 of 12" and
    "page 5 of 12" are the same furniture, and normalising the digits away is how that is known.
    """
    closings = [
        "and the capacity fades within twenty cycles.",
        "so the interphase keeps consuming lithium.",
        "which the diffraction pattern confirms.",
        "before the electrode was recovered and washed.",
        "leaving a porous residue on the separator.",
        "though neither sample cracked visibly.",
        "as the impedance spectra make clear.",
    ]
    doc = _paper(closings)
    strip_page_artifacts(doc)
    assert _kinds(doc) == [BlockKind.PARAGRAPH] * PAGES


def test_a_short_shared_phrase_is_not_enough_to_be_called_furniture() -> None:
    """Containment needs a substantial match, or every block that ends in "et al." is furniture."""
    doc = _paper(["Table 1" for _ in range(PAGES - 1)] + ["Table 1 shows the capacities measured"])
    strip_page_artifacts(doc)
    assert _kinds(doc)[-1] is BlockKind.PARAGRAPH
