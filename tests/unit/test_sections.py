from __future__ import annotations

import pytest

from mimem.clean.sections import assign_sections, role_for_heading
from mimem.ir import Block, BlockKind, BlockRole, Document, SourceMeta, block_id


@pytest.mark.parametrize(
    ("heading", "role"),
    [
        ("Abstract", BlockRole.ABSTRACT),
        ("1. Introduction", BlockRole.INTRODUCTION),
        ("2 Materials and Methods", BlockRole.METHODS),
        ("3. Experimental Section", BlockRole.METHODS),
        ("4. Results and Discussion", BlockRole.RESULTS),
        ("Discussion", BlockRole.DISCUSSION),
        ("5. Conclusions", BlockRole.CONCLUSION),
        ("References", BlockRole.REFERENCES),
        ("Acknowledgements", BlockRole.ACKNOWLEDGEMENT),
        ("Funding", BlockRole.FUNDING),
        ("Declaration of competing interest", BlockRole.ETHICS),
        ("Data availability", BlockRole.ETHICS),
        ("Appendix A", BlockRole.APPENDIX),
    ],
)
def test_heading_roles(heading: str, role: BlockRole) -> None:
    assert role_for_heading(heading) is role


def test_content_headings_have_no_role() -> None:
    assert role_for_heading("3.2 Interphase growth and lithium inventory") is None


def _build(*items: tuple[str, str, int | None]) -> Document:
    blocks = []
    for i, (kind, text, level) in enumerate(items):
        k = BlockKind(kind)
        blocks.append(
            Block(id=block_id(kind, 1, i, text), kind=k, text=text, order=i, level=level, page=1)
        )
    return Document(id="d", source=SourceMeta(format="txt"), blocks=blocks)


def test_blocks_inherit_the_role_of_their_section() -> None:
    doc = assign_sections(
        _build(
            ("heading", "1. Introduction", 1),
            ("paragraph", "Background prose.", None),
            ("heading", "2. Methods", 1),
            ("paragraph", "Cells were assembled.", None),
        )
    )
    assert [b.role for b in doc.blocks] == [
        BlockRole.INTRODUCTION,
        BlockRole.INTRODUCTION,
        BlockRole.METHODS,
        BlockRole.METHODS,
    ]


def test_subheadings_keep_the_parent_section_role_and_nest() -> None:
    doc = assign_sections(
        _build(
            ("heading", "3. Results", 1),
            ("heading", "3.1 Capacity fade", 2),
            ("paragraph", "It fell.", None),
        )
    )
    sub = doc.blocks[1]
    assert sub.role is BlockRole.RESULTS
    assert sub.parent_id == doc.blocks[0].id
    assert doc.blocks[2].section_id == sub.id


def test_reference_entries_are_retyped() -> None:
    doc = assign_sections(
        _build(
            ("heading", "References", 1),
            ("paragraph", "[1] E. Peled, J. Electrochem. Soc. 126 (1979) 2047.", None),
        )
    )
    assert doc.blocks[1].kind is BlockKind.REFERENCE
    assert doc.blocks[1].role is BlockRole.REFERENCES


def test_a_reference_list_without_a_heading_is_still_recognised() -> None:
    items = [("heading", "4. Conclusions", 1), ("paragraph", "It works.", None)]
    items += [
        ("paragraph", f"[{i}] A. Author, J. Journal {i} (200{i}) 1{i}-2{i}, doi:10.1/x{i}.", None)
        for i in range(1, 7)
    ]
    doc = assign_sections(_build(*items))
    assert sum(b.role is BlockRole.REFERENCES for b in doc.blocks) == 6
    assert any(d.code == "references_without_heading" for d in doc.diagnostics)
