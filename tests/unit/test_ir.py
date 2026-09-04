from __future__ import annotations

import pytest
from pydantic import ValidationError

from mimem.ir import (
    SCHEMA_VERSION,
    Block,
    BlockKind,
    BlockRole,
    Document,
    SourceMeta,
    Span,
    block_id,
)


def _doc() -> Document:
    blocks = [
        Block(
            id=block_id("heading", 1, 0, "Results"),
            kind=BlockKind.HEADING,
            text="Results",
            order=0,
            level=1,
            page=1,
            role=BlockRole.RESULTS,
        ),
        Block(
            id=block_id("paragraph", 1, 1, "Capacity fell."),
            kind=BlockKind.PARAGRAPH,
            text="Capacity fell.",
            order=1,
            page=1,
            role=BlockRole.RESULTS,
        ),
    ]
    return Document(id="d_test", source=SourceMeta(format="txt"), blocks=blocks)


def test_document_round_trips_through_json() -> None:
    doc = _doc()
    restored = Document.from_json(doc.to_json())
    assert restored == doc
    assert restored.schema_version == SCHEMA_VERSION


def test_from_json_rejects_a_future_schema() -> None:
    payload = _doc().model_dump()
    payload["schema_version"] = SCHEMA_VERSION + 1
    import json

    with pytest.raises(ValueError, match="schema version"):
        Document.from_json(json.dumps(payload, default=str))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Block(id="b", kind=BlockKind.PARAGRAPH, text="x", nonsense=1)  # type: ignore[call-arg]


def test_block_ids_are_stable_and_content_derived() -> None:
    assert block_id("paragraph", 1, 0, "hello") == block_id("paragraph", 1, 0, "hello")
    assert block_id("paragraph", 1, 0, "hello") != block_id("paragraph", 1, 0, "hallo")
    # Same text in a different position is a different block (running heads).
    assert block_id("paragraph", 1, 0, "hello") != block_id("paragraph", 2, 0, "hello")


def test_span_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Span(block_id="b", char_start=10, char_end=3)


def test_lookup_helpers() -> None:
    doc = _doc()
    assert doc.by_kind(BlockKind.HEADING)[0].text == "Results"
    assert len(doc.by_role(BlockRole.RESULTS)) == 2
    assert doc.word_count == 3
    with pytest.raises(KeyError):
        doc.block("nope")


def test_text_of_span_returns_the_cited_substring() -> None:
    doc = _doc()
    para = doc.blocks[1]
    assert doc.text_of(Span(block_id=para.id, char_start=0, char_end=8)) == "Capacity"
    assert doc.text_of(para.span()) == para.text


def test_renumber_repairs_order_after_edits() -> None:
    doc = _doc()
    doc.blocks.reverse()
    doc.renumber()
    assert [b.order for b in doc.blocks] == [0, 1]
