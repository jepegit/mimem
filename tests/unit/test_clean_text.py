"""Dehyphenation, paragraph merging and sentence splitting.

These three are unglamorous and load-bearing: every one of them corrupts the narration
silently when it is wrong, which is exactly why they get the densest tests in the suite.
"""

from __future__ import annotations

import pytest

from mimem.clean import dehyphenate_text, sentence_spans
from mimem.clean.merge import merge_continuations
from mimem.ir import Block, BlockKind, Document, SourceMeta, block_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("electro-\nlyte decomposes", "electrolyte decomposes"),
        ("inter-\nphase repair", "interphase repair"),
        ("measure-\nments", "measurements"),
    ],
)
def test_hyphen_at_a_line_break_is_removed(raw: str, expected: str) -> None:
    assert dehyphenate_text(raw)[0] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("in-\nsitu measurements", "in-situ measurements"),  # real prefix hyphen
        ("non-\naqueous solvent", "non-aqueous solvent"),
        ("Li-\nion cell", "Li-ion cell"),  # short capitalised stem
        ("X-\nray diffraction", "X-ray diffraction"),
        ("pH-\ndependent", "pH-dependent"),  # internal capital
        ("cycle-\nto-cycle", "cycle-to-cycle"),  # continuation is hyphenated
        ("T-\n2 relaxation", "T-2 relaxation"),  # digit continuation
    ],
)
def test_real_hyphens_survive(raw: str, expected: str) -> None:
    assert dehyphenate_text(raw)[0] == expected


def test_counts_are_reported_for_auditing() -> None:
    _, joined, kept = dehyphenate_text("electro-\nlyte and in-\nsitu")
    assert (joined, kept) == (1, 1)


def test_line_breaks_become_spaces_and_ligatures_are_expanded() -> None:
    cleaned, _, _ = dehyphenate_text("the ﬁrst eﬀect\nof the  layer")
    assert cleaned == "the first effect of the layer"


def _paragraphs(*texts: str) -> Document:
    blocks = [
        Block(id=block_id("paragraph", 1, i, t), kind=BlockKind.PARAGRAPH, text=t, order=i, page=1)
        for i, t in enumerate(texts)
    ]
    return Document(id="d", source=SourceMeta(format="txt"), blocks=blocks)


def test_paragraph_split_by_a_column_break_is_rejoined() -> None:
    doc = merge_continuations(_paragraphs("which is why the process is", "self-limiting here."))
    assert len(doc.blocks) == 1
    assert doc.blocks[0].text == "which is why the process is self-limiting here."
    assert len(doc.blocks[0].attrs["merged_from"]) == 2


def test_complete_paragraphs_are_left_alone() -> None:
    doc = merge_continuations(_paragraphs("A finished sentence.", "another paragraph follows"))
    assert len(doc.blocks) == 2


def test_a_trailing_abbreviation_does_not_end_a_paragraph() -> None:
    doc = merge_continuations(_paragraphs("as reported earlier, e.g.", "by the same group."))
    assert len(doc.blocks) == 1


def test_merging_reaches_across_the_running_head_at_a_page_break() -> None:
    """The case the module exists for, and the one it did not handle.

    A page break puts a running head and a folio between the two halves of a paragraph, so they
    are never adjacent. On a ninety-eight page review that left thirty-one beats opening
    mid-clause -- "voltage and temperature signals, achieving eight to thirteen minutes advanced
    warning", spoken as though it were a sentence.
    """
    doc = _paragraphs("Machine learning offers a new paradigm for", "voltage and temperature.")
    for i, (kind, text) in enumerate(
        (
            (BlockKind.PAGE_ARTIFACT, "https://doi.org/10.3390/x"),
            (BlockKind.PAGE_ARTIFACT, "5 of 35"),
        )
    ):
        doc.blocks.insert(1 + i, Block(id=f"a{i}", kind=kind, text=text, order=0, page=1))
    doc.renumber()

    merged = merge_continuations(doc)
    paragraphs = [b for b in merged.blocks if b.kind is BlockKind.PARAGRAPH]
    assert len(paragraphs) == 1
    assert (
        paragraphs[0].text == "Machine learning offers a new paradigm for voltage and temperature."
    )
    assert len([b for b in merged.blocks if b.kind is BlockKind.PAGE_ARTIFACT]) == 2


def test_merging_reaches_across_a_floating_figure() -> None:
    """Named in the module docstring: artwork in the middle of a column interrupts the text
    around it without ending it. A figure block carries no text of its own."""
    doc = _paragraphs("the interphase keeps growing because", "each repair costs lithium.")
    doc.blocks.insert(1, Block(id="f", kind=BlockKind.FIGURE, text="", order=0, page=1))
    doc.renumber()

    paragraphs = [b for b in merge_continuations(doc).blocks if b.kind is BlockKind.PARAGRAPH]
    assert len(paragraphs) == 1


def test_merging_does_not_reach_across_a_caption() -> None:
    """A caption is real text and belongs to the figure, not to the paragraph around it."""
    doc = _paragraphs("the process is", "self-limiting.")
    doc.blocks.insert(
        1, Block(id="c", kind=BlockKind.CAPTION, text="Figure 1. A cell.", order=0, page=1)
    )
    doc.renumber()
    assert len([b for b in merge_continuations(doc).blocks if b.kind is BlockKind.PARAGRAPH]) == 2


def test_merging_does_not_reach_across_a_heading() -> None:
    doc = _paragraphs("the process is", "self-limiting.")
    doc.blocks.insert(
        1,
        Block(id="h", kind=BlockKind.HEADING, text="2. Methods", order=1, level=1, page=1),
    )
    doc.renumber()
    assert len(merge_continuations(doc).blocks) == 3


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("Capacity fell by 0.0837 % per cycle. The fit was good.", 2),
        ("See Fig. 4 for the trend. It is monotonic.", 2),
        ("Reported by Smith et al. in 2019 and confirmed later.", 1),
        ("Values were low, e.g. 0.5 mA, in every cell.", 1),
        ("One sentence only", 1),
    ],
)
def test_sentence_splitting_survives_scientific_prose(text: str, count: int) -> None:
    assert len(sentence_spans(text)) == count


def test_sentence_spans_are_offsets_into_the_original_text() -> None:
    text = "First one. Second one."
    spans = sentence_spans(text)
    assert [text[a:b] for a, b in spans] == ["First one.", "Second one."]


def test_empty_text_yields_no_sentences() -> None:
    assert sentence_spans("   \n ") == []


# -- stacked headings ---------------------------------------------------------------------------


def _heading(text: str) -> Document:
    return Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[Block(id="h", kind=BlockKind.HEADING, text=text, order=0, level=1, page=1)],
    )


def test_a_heading_stacked_on_its_subsection_is_split() -> None:
    """A section heading set directly above its first subsection comes back as one block, and
    once the lines are joined the section is called "2.3. Core ML Models and Training Strategies
    2.3.1. Model Architectures and General Workflow"."""
    from mimem.clean.headings import split_stacked_headings

    doc = split_stacked_headings(
        _heading("2.3. Core ML Models and Training Strategies\n2.3.1. Model Architectures")
    )
    assert [b.text for b in doc.blocks] == [
        "2.3. Core ML Models and Training Strategies",
        "2.3.1. Model Architectures",
    ]
    assert doc.blocks[1].attrs["split_from"] == "h"
    assert all(b.kind is BlockKind.HEADING for b in doc.blocks)


def test_a_single_level_number_does_not_start_a_new_heading() -> None:
    """ "1. Introduction" on its own line under a heading is far more likely to be a list item,
    and splitting a list into headings would invent sections."""
    from mimem.clean.headings import split_stacked_headings

    doc = split_stacked_headings(_heading("Contents\n1. Introduction\n2. Methods"))
    assert len(doc.blocks) == 1


def test_an_ordinary_heading_is_untouched() -> None:
    from mimem.clean.headings import split_stacked_headings

    doc = split_stacked_headings(_heading("2.1.4. Gas Signals"))
    assert len(doc.blocks) == 1
    assert "split_from" not in doc.blocks[0].attrs


def test_only_headings_are_split() -> None:
    """A paragraph mentioning a subsection number mid-text is not two paragraphs."""
    from mimem.clean.headings import split_stacked_headings

    doc = Document(
        id="d",
        source=SourceMeta(format="pdf"),
        blocks=[
            Block(
                id="p",
                kind=BlockKind.PARAGRAPH,
                text="As described above\n2.1.4. is where the gas signals are discussed.",
                order=0,
            )
        ],
    )
    assert len(split_stacked_headings(doc).blocks) == 1
