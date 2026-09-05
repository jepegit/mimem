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


# -- regressions from real papers -----------------------------------------------------------


def _paged(*items: tuple[str, str, int | None, int] | tuple[str, str, int | None, int, float]):
    """Build a document with pages: (kind, text, level, page[, font_max]).

    ``font_max`` matters because the title is identified as the biggest type near the top.
    """
    blocks = []
    for i, item in enumerate(items):
        kind, text, level, page = item[:4]
        font = item[4] if len(item) > 4 else 10.0
        blocks.append(
            Block(
                id=block_id(kind, page, i, text),
                kind=BlockKind(kind),
                text=text,
                order=i,
                level=level,
                page=page,
                attrs={"font_max": font},
            )
        )
    return Document(id="d", source=SourceMeta(format="pdf"), blocks=blocks)


def test_front_matter_is_found_when_the_body_starts_on_page_two() -> None:
    """Springer: the Introduction is on page 2, so a short scan from the top found nothing
    structural and the title was lost entirely."""
    doc = assign_sections(
        _paged(
            ("paragraph", "Ionics (2026) 32:7477-7499", None, 1),
            ("heading", "RESEARCH", 1, 1),
            ("paragraph", "Optimization driven gradient boosting for battery life", None, 1, 16.0),
            ("paragraph", "Anupam Yadav1 · Mustafa Abdullah2 · V. Vivek3", None, 1),
            ("paragraph", "Abstract The accelerating electrification of transport", None, 1),
            ("paragraph", "Keywords Lithium-ion battery · Degradation", None, 1),
            ("heading", "Introduction", 1, 2),
            ("paragraph", "Battery degradation matters.", None, 2),
        )
    )
    roles = {b.text[:20]: b.role for b in doc.blocks}
    assert roles["Optimization driven "] is BlockRole.TITLE
    assert roles["Anupam Yadav1 · Must"] is BlockRole.AUTHORS
    assert roles["Abstract The acceler"] is BlockRole.ABSTRACT
    assert roles["Keywords Lithium-ion"] is BlockRole.KEYWORDS
    assert doc.source.title.startswith("Optimization driven")


def test_authors_separated_by_middle_dots_are_recognised() -> None:
    doc = assign_sections(
        _paged(
            ("paragraph", "A Paper About Batteries And Their Behaviour", None, 1, 16.0),
            ("paragraph", "Anupam Yadav1 · Mustafa Abdullah2 · V. Vivek3", None, 1),
            ("heading", "1. Introduction", 1, 2),
        )
    )
    authors = doc.by_role(BlockRole.AUTHORS)
    assert authors and "Yadav" in authors[0].text
    assert doc.source.authors[:2] == ["Anupam Yadav1", "Mustafa Abdullah2"]


def test_summary_mid_document_is_a_conclusion_not_an_abstract() -> None:
    """'6 Summary and future perspectives' used to be read as an abstract, which relabelled
    every block after it."""
    doc = assign_sections(
        _build(
            ("heading", "1 Introduction", 1),
            ("paragraph", "Why this matters.", None),
            ("heading", "6 Summary and future perspectives", 1),
            ("paragraph", "What we found.", None),
        )
    )
    assert doc.blocks[2].role is BlockRole.CONCLUSION
    assert doc.blocks[3].role is BlockRole.CONCLUSION


def test_summary_in_the_front_matter_is_the_abstract() -> None:
    doc = assign_sections(
        _paged(
            ("paragraph", "A Paper About Batteries And Their Behaviour", None, 1, 16.0),
            ("paragraph", "Summary We show that capacity fades gradually.", None, 1),
            ("heading", "1. Introduction", 1, 2),
        )
    )
    assert doc.blocks[1].role is BlockRole.ABSTRACT


def test_repository_cover_sheets_are_marked_as_boilerplate() -> None:
    """Chalmers ODR wraps the paper in a cover page; none of it should ever be narrated."""
    doc = assign_sections(
        _paged(
            ("heading", "Artificial intelligence for battery reuse", 1, 1, 16.0),
            ("heading", "Downloaded from: https://research.chalmers.se, 2026-09-04", 2, 1),
            ("paragraph", "Citation for the original published paper: Tao, S. et al.", None, 1),
            (
                "paragraph",
                "N.B. When citing this work, cite the original published paper.",
                None,
                1,
            ),
            ("heading", "(article starts on next page)", 2, 1),
            ("heading", "1 Introduction", 1, 2),
        )
    )
    boilerplate = doc.by_role(BlockRole.BOILERPLATE)
    assert len(boilerplate) == 4
    assert doc.blocks[0].role is BlockRole.TITLE


def test_unidentified_front_matter_stays_unknown_rather_than_becoming_body() -> None:
    """Positive evidence only: triage decides, not a default."""
    doc = assign_sections(
        _paged(
            ("paragraph", "A Paper About Batteries And Their Behaviour", None, 1, 16.0),
            ("paragraph", "Some unrecognisable front-page fragment", None, 1),
            ("heading", "1. Introduction", 1, 2),
        )
    )
    assert doc.blocks[1].role is BlockRole.UNKNOWN


def test_a_long_reference_list_is_found_from_its_start_not_its_end() -> None:
    """A fixed-size tail finds the end of the list and misses its beginning: on a paper with
    thirty references, entries one to fifteen were narrated as prose, DOIs and all."""
    items: list[tuple[str, str, int | None]] = [
        ("heading", "4. Conclusions", 1),
        ("paragraph", "Capacity fade is dominated by interphase repair.", None),
    ]
    items += [
        (
            "paragraph",
            f"{i}. Author, A., and Other, B. (20{i:02d}). A title. Journal 12, 3-4.",
            None,
        )
        for i in range(1, 31)
    ]
    doc = assign_sections(_build(*items))
    references = doc.by_role(BlockRole.REFERENCES)
    assert len(references) == 30
    assert doc.blocks[1].role is not BlockRole.REFERENCES  # the conclusion survives


def test_a_short_run_of_numbered_lines_is_not_a_reference_list() -> None:
    items = [("heading", "3. Results", 1)]
    items += [("paragraph", f"{i}. A numbered step in the protocol.", None) for i in range(1, 4)]
    doc = assign_sections(_build(*items))
    assert not doc.by_role(BlockRole.REFERENCES)
