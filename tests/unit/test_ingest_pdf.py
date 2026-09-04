"""End-to-end ingestion of the synthetic two-column paper.

This is the M1 acceptance test. Each assertion corresponds to something a real journal PDF does
that would otherwise silently wreck the narration.
"""

from __future__ import annotations

import pytest

from mimem.clean import clean
from mimem.ingest import IngestError, load
from mimem.ir import BlockKind, BlockRole, Document


def _text_of(doc: Document, role: BlockRole) -> str:
    return " ".join(b.text for b in doc.by_role(role))


def test_metadata_and_scale(paper_doc: Document) -> None:
    assert paper_doc.source.format == "pdf"
    assert paper_doc.source.adapter == "pymupdf"
    assert paper_doc.source.n_pages >= 2
    assert paper_doc.word_count > 300
    assert paper_doc.stages == ["ingest", "clean"]


def test_reading_order_follows_the_columns_not_the_page(paper_doc: Document) -> None:
    """The failure this guards against: column two read before column one."""
    body = [b for b in paper_doc.blocks if b.kind is BlockKind.PARAGRAPH]
    intro = next(i for i, b in enumerate(body) if b.text.startswith("Lithium-ion cells"))
    interphase = next(i for i, b in enumerate(body) if b.text.startswith("During the first charge"))
    methods = next(i for i, b in enumerate(body) if b.text.startswith("Half cells"))
    assert intro < interphase < methods


def test_front_matter_is_labelled(paper_doc: Document) -> None:
    assert "silicon anode life" in _text_of(paper_doc, BlockRole.TITLE)
    assert "Researcher" in _text_of(paper_doc, BlockRole.AUTHORS)
    assert "Kjeller" in _text_of(paper_doc, BlockRole.AFFILIATION)
    assert "dominant loss channel" in _text_of(paper_doc, BlockRole.ABSTRACT)
    assert "lithium-ion" in _text_of(paper_doc, BlockRole.KEYWORDS)


def test_imrad_sections_are_recognised(paper_doc: Document) -> None:
    headings = {b.text.strip(): b.role for b in paper_doc.by_kind(BlockKind.HEADING)}
    assert headings["1. Introduction"] is BlockRole.INTRODUCTION
    assert headings["2. Experimental"] is BlockRole.METHODS
    assert headings["3. Results and Discussion"] is BlockRole.RESULTS
    assert headings["4. Conclusions"] is BlockRole.CONCLUSION
    assert headings["Acknowledgements"] is BlockRole.ACKNOWLEDGEMENT
    assert headings["References"] is BlockRole.REFERENCES


def test_running_heads_and_folios_are_marked_on_every_page(paper_doc: Document) -> None:
    """Rule COH-01: page furniture must never reach the narration."""
    artifacts = paper_doc.by_kind(BlockKind.PAGE_ARTIFACT)
    heads = [b for b in artifacts if "Journal of Synthetic" in b.text]
    folios = [b for b in artifacts if b.text.strip().isdigit()]
    assert len(heads) == paper_doc.source.n_pages
    assert len(folios) == paper_doc.source.n_pages


def test_hyphenated_line_breaks_are_repaired_but_real_hyphens_survive(paper_doc: Document) -> None:
    body = " ".join(b.text for b in paper_doc.blocks)
    assert "electrolyte decomposes" in body  # joined
    assert "electro lyte" not in body
    assert "in-situ" in body  # kept
    assert "Li-ion cell" in body  # kept


def test_a_paragraph_split_across_columns_is_rejoined(paper_doc: Document) -> None:
    merged = [b for b in paper_doc.blocks if b.text.startswith("During the first charge")]
    assert len(merged) == 1
    assert "self-limiting under normal conditions" in merged[0].text
    assert merged[0].attrs.get("merged_from")


def test_captions_equations_and_references_are_typed(paper_doc: Document) -> None:
    captions = paper_doc.by_kind(BlockKind.CAPTION)
    assert any(c.text.startswith("Figure 1.") for c in captions)
    assert any("C0 exp" in b.text for b in paper_doc.by_kind(BlockKind.EQUATION))
    assert len(paper_doc.by_kind(BlockKind.REFERENCE)) == 3


def test_sentences_are_segmented_for_prose_blocks(paper_doc: Document) -> None:
    abstract = paper_doc.by_role(BlockRole.ABSTRACT)[0]
    sentences = abstract.sentence_texts()
    assert len(sentences) >= 3
    assert all(s.strip() for s in sentences)
    # The decimal in "0.0837 %" must not have been treated as a sentence end.
    assert not any(s.strip().startswith("0837") for s in sentences)


def test_every_block_keeps_a_page_and_a_stable_id(paper_doc: Document) -> None:
    ids = [b.id for b in paper_doc.blocks]
    assert len(ids) == len(set(ids))
    assert all(b.page is not None for b in paper_doc.blocks)


def test_ingestion_is_deterministic(paper_pdf) -> None:
    """Same bytes in, same document out -- block IDs included, so caches can key on it."""
    a = clean(load(paper_pdf))
    b = clean(load(paper_pdf))
    assert a.content_fingerprint() == b.content_fingerprint()
    assert [x.id for x in a.blocks] == [x.id for x in b.blocks]


def test_clean_is_idempotent(paper_pdf) -> None:
    once = clean(load(paper_pdf))
    twice = clean(once.model_copy(deep=True))
    assert twice.content_fingerprint() == once.content_fingerprint()


def test_a_scanned_pdf_fails_with_an_actionable_message(tmp_path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    empty = tmp_path / "scan.pdf"
    doc.save(empty)
    doc.close()
    with pytest.raises(IngestError, match="OCR"):
        load(empty)


def test_unknown_extension_is_refused(tmp_path) -> None:
    path = tmp_path / "thing.xyz"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(IngestError, match="no adapter"):
        load(path)
