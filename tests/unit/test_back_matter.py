"""Where a paper stops arguing and starts crediting people.

Two of the twelve corpus papers run the whole of their back matter -- author information,
contributions, competing interests, acknowledgements and the reference list -- onto the end of
the concluding paragraph, and the abstract onto the front of the keyword list. Neither block
could be dropped, because both carry the argument, so all of it was narrated.
"""

from __future__ import annotations

import pytest

from mimem.clean.back_matter import find_boundary, split_back_matter
from mimem.ir import Block, BlockKind, Document, SourceMeta

CONCLUSION = (
    "In summary, we have designed a yolk-shell structure for a scalable Si electrode. "
    "It is a promising candidate for next generation Li-ion batteries. "
)


def _paragraph(text: str) -> Document:
    return Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[Block(id="b1", kind=BlockKind.PARAGRAPH, text=text, page=1, order=0)],
    )


@pytest.mark.parametrize(
    "tail",
    [
        # The corpus case, verbatim: an ACS section marker.
        "■ASSOCIATED CONTENT * S Supporting Information Experimental procedures.",
        "■AUTHOR INFORMATION Notes The authors declare no competing financial interest.",
        "■ACKNOWLEDGMENTS This work was partially supported by the Assistant Secretary.",
        # ...and the same headings with no marker, after a sentence has ended.
        "Author Contributions ⊥These authors contributed equally.",
        "Notes The authors declare no competing financial interest.",
        "KEYWORDS: Silicon nanoparticle, Li-ion battery, anode, yolk-shell",
        "Conflict of Interest: The authors declare none.",
        "Data Availability Statements are available on request.",
    ],
)
def test_back_matter_is_cut_off_the_end_of_a_paragraph(tail: str) -> None:
    doc = split_back_matter(_paragraph(CONCLUSION + tail))
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == CONCLUSION.rstrip()
    assert doc.blocks[1].text == tail
    assert doc.blocks[1].attrs["split_from"] == "b1"


@pytest.mark.parametrize(
    "text",
    [
        # A heading word doing ordinary work in a sentence. The first is why the match has to
        # start with a capital; the second is why something heading-shaped has to follow it.
        CONCLUSION + "The procedure is described in the supporting information.",
        CONCLUSION + "References to earlier work suggest the same mechanism.",
        CONCLUSION + "Funding of this kind is rare and the notes below explain why.",
        # And a paragraph with no back matter in it at all.
        CONCLUSION,
    ],
)
def test_a_paragraph_that_merely_mentions_one_is_left_whole(text: str) -> None:
    doc = split_back_matter(_paragraph(text))
    assert len(doc.blocks) == 1
    assert doc.blocks[0].text == text


def test_a_block_that_is_nothing_but_back_matter_is_left_for_triage() -> None:
    """Splitting it would leave an empty head. Triage drops the whole block instead."""
    whole = "■AUTHOR INFORMATION Notes The authors declare no competing financial interest."
    assert find_boundary(whole) is None
    doc = split_back_matter(_paragraph(whole))
    assert len(doc.blocks) == 1


def test_the_rights_notice_is_cut_off_the_abstract_rather_than_taking_it_along() -> None:
    """Back matter printed at the front, and it cost one paper its abstract.

    Triage's boilerplate hint is not anchored, so one licence sentence anywhere inside a block
    condemns the block -- and this paper runs the licence straight on from the last sentence of
    the abstract.
    """
    abstract = (
        "A first review of hard carbon materials as negative electrodes for sodium ion "
        "batteries is presented, covering the electrochemical performance and the synthetic "
        "methods. "
    )
    rights = (
        "© The Author(s) 2015. Published by ECS. This is an open access article distributed "
        "under the terms of the Creative Commons Attribution 4.0 License."
    )
    doc = split_back_matter(_paragraph(abstract + rights))
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == abstract.strip()
    assert doc.blocks[1].text == rights


@pytest.mark.parametrize(
    "tail",
    [
        # The words of a rights notice doing ordinary work in a sentence.
        "The copyright position was unclear until the publisher responded.",
        "All rights were retained by the authors under the agreement they signed.",
    ],
)
def test_a_sentence_about_rights_is_not_a_rights_notice(tail: str) -> None:
    text = CONCLUSION + tail
    doc = split_back_matter(_paragraph(text))
    assert len(doc.blocks) == 1
