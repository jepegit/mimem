"""Manuscript line numbers.

Every case here comes from a real paper. The stripping case is a preprint under review whose
line numbers were interleaved with the text; the two negative cases are a published article
whose lone integers are affiliation superscripts and journal folio numbers, which used to be
eaten by an earlier version of the detector.
"""

from __future__ import annotations

from mimem.clean import clean
from mimem.clean.line_numbers import looks_like_line_numbering, strip_line_numbers
from mimem.ir import Block, BlockKind, Document, SourceMeta, block_id


def _doc(*texts: str) -> Document:
    blocks = [
        Block(id=block_id("paragraph", 1, i, t), kind=BlockKind.PARAGRAPH, text=t, order=i, page=1)
        for i, t in enumerate(texts)
    ]
    return Document(id="d", source=SourceMeta(format="pdf"), blocks=blocks)


def _numbered_manuscript(n_lines: int = 60) -> Document:
    """Text where every line is followed by its line number on a line of its own."""
    lines: list[str] = []
    for i in range(1, n_lines + 1):
        lines.append(f"body text line number {i} carrying some words")
        lines.append(str(i))
    return _doc("\n".join(lines))


def test_line_numbers_are_removed_from_a_numbered_manuscript() -> None:
    doc = strip_line_numbers(_numbered_manuscript())
    remaining = doc.blocks[0].text.split("\n")
    assert all(not line.strip().isdigit() for line in remaining)
    assert len(remaining) == 60
    assert any(d.code == "line_numbers" for d in doc.diagnostics)


def test_a_line_number_between_a_hyphen_and_its_continuation_is_repaired() -> None:
    """The failure that motivated this module: `recov-` / `19` / `ery` became `recov-19 ery`."""
    lines = [f"filler line {i}\n{i}" for i in range(1, 41)]
    lines.insert(20, "the capacity recov-\n21\nery was complete")
    doc = clean(_doc("\n".join(lines)))
    text = doc.blocks[0].text
    assert "recovery was complete" in text
    assert "recov-21" not in text


def test_affiliation_superscripts_and_folios_are_not_mistaken_for_line_numbers() -> None:
    """A published Springer article: superscripts 1-9, then folio numbers 7478-7499.

    Both sequences increase, so the monotonic test alone accepted them. Density is what
    separates them from real line numbering.
    """
    affiliations = [f"{i}\nDepartment of Something, A University, Somewhere" for i in range(1, 10)]
    folios = [f"{p}\nJournal of Things (2026) 32:{p}" for p in range(7478, 7500)]
    doc = _doc(*affiliations, *folios)
    before = [b.text for b in doc.blocks]
    strip_line_numbers(doc)
    assert [b.text for b in doc.blocks] == before
    assert not any(d.code == "line_numbers" for d in doc.diagnostics)


def test_a_document_with_a_few_stray_numbers_is_left_alone() -> None:
    doc = _doc("a paragraph\n1\nmore text", "another paragraph\n2\nand more")
    before = [b.text for b in doc.blocks]
    strip_line_numbers(doc)
    assert [b.text for b in doc.blocks] == before


def test_the_sequence_test_requires_density_not_just_monotonicity() -> None:
    rising = list(range(1, 41))
    assert looks_like_line_numbering(rising, total_lines=80)
    assert not looks_like_line_numbering(rising, total_lines=4000)  # too sparse to be numbering
    assert not looks_like_line_numbering([5, 5, 5, 5] * 10, total_lines=80)  # not increasing
    assert not looks_like_line_numbering([1, 2, 3], total_lines=6)  # too few


def test_stripping_does_not_touch_tables_or_code() -> None:
    doc = _numbered_manuscript()
    doc.blocks[0].kind = BlockKind.TABLE
    before = doc.blocks[0].text
    strip_line_numbers(doc)
    assert doc.blocks[0].text == before
