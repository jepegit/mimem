"""Pairing captions with the figures they speak for (``PLAN-figures.md`` stage A).

The unit under test is the *caption*, not the image, and these tests are mostly about the two
ways that goes wrong: claiming too much, so two figures on one page become one, and claiming too
little, so a figure is announced as "there is a figure here" with the paper's own description of
it sitting unused three lines away.

The geometry cases are built as bounding boxes rather than as a PDF, because what is being tested
is the walk -- take fragments away from the caption, stop when the gap widens -- and a PDF fixture
would test PyMuPDF instead.
"""

from __future__ import annotations

import pytest

from mimem.clean.figures import MAX_FRAGMENT_GAP, link_figures
from mimem.config import Profile
from mimem.ingest.pdf import CAPTION_RE
from mimem.ir import BBox, Block, BlockKind, Document, SourceMeta


def _doc(blocks: list[Block]) -> Document:
    for i, b in enumerate(blocks):
        b.order = i
    return Document(id="d_fig", source=SourceMeta(format="pdf"), blocks=blocks)


def _fragment(bid: str, page: int, y0: float, y1: float) -> Block:
    return Block(id=bid, kind=BlockKind.FIGURE, page=page, bbox=BBox(x0=50, y0=y0, x1=500, y1=y1))


def _caption(bid: str, page: int, y0: float, text: str) -> Block:
    return Block(
        id=bid,
        kind=BlockKind.CAPTION,
        text=text,
        page=page,
        bbox=BBox(x0=50, y0=y0, x1=500, y1=y0 + 10),
    )


# -- telling a caption from a sentence about a figure -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Figure 1. Chain side reactions during thermal runaway.",
        "Figure 10: Early detection of internal short circuits.",
        "Table 2. Comparison of deep learning models.",
        "Fig. 3 - Capacity against cycle number.",
    ],
)
def test_a_caption_is_recognised(text: str) -> None:
    assert CAPTION_RE.match(text)


@pytest.mark.parametrize(
    "text",
    [
        "Figure 6 exemplifies how transfer learning improves prediction across conditions.",
        "Figure 4 shows that capacity falls with cycle count.",
        "Table 1 lists every cell we tested.",
    ],
)
def test_a_sentence_about_a_figure_is_not_a_caption(text: str) -> None:
    """The delimiter after the number is the whole discriminator; length cannot do it.

    A real 45-word caption and a 45-word sentence opening with a figure number both exist in the
    paper this was written against.
    """
    assert not CAPTION_RE.match(text)


# -- pairing ------------------------------------------------------------------------------------


def test_a_caption_claims_the_fragments_above_it() -> None:
    doc = _doc(
        [
            _fragment("f1", 1, 400, 500),
            _fragment("f2", 1, 300, 395),
            _caption("c1", 1, 520, "Figure 1. Capacity against cycle number."),
        ]
    )
    link_figures(doc)
    meta = doc.block("c1").attrs["caption"]
    assert set(meta["members"]) == {"f1", "f2"}
    assert meta["region"]["y0"] == 300
    assert meta["region"]["y1"] == 500
    assert doc.block("f1").parent_id == "c1"


def test_two_figures_on_one_page_do_not_merge() -> None:
    """Page 26 of the test paper carries Figures 8 and 9 and 38 fragments between them.

    Pairing by page would give one of them everything and the other nothing.
    """
    doc = _doc(
        [
            _fragment("top", 1, 600, 700),
            _caption("c_top", 1, 720, "Figure 8. The fire chamber."),
            _fragment("bottom", 1, 300, 400),
            _caption("c_bottom", 1, 420, "Figure 9. The simulation flow."),
        ]
    )
    link_figures(doc)
    assert doc.block("c_top").attrs["caption"]["members"] == ["top"]
    assert doc.block("c_bottom").attrs["caption"]["members"] == ["bottom"]


def test_a_wide_gap_ends_the_figure() -> None:
    """Body text between the caption and a fragment means the fragment is a different figure."""
    doc = _doc(
        [
            _fragment("far", 1, 100, 150),
            _fragment("near", 1, 400, 500),
            _caption("c1", 1, 520, "Figure 1. Something."),
        ]
    )
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["members"] == ["near"]
    assert doc.block("far").attrs.get("decorative") is True
    assert 150 + MAX_FRAGMENT_GAP < 400, "the fixture must straddle the gap threshold"


def test_a_fragment_nobody_captions_is_decorative() -> None:
    """Rule FIG-06. In the test paper this is 139 of 155 blocks -- logos and ornaments."""
    doc = _doc([_fragment("logo", 1, 700, 720)])
    link_figures(doc)
    assert doc.block("logo").attrs["decorative"] is True


def test_a_caption_below_its_artwork_is_also_found() -> None:
    """Some journals caption above. Nothing above means look below."""
    doc = _doc(
        [
            _caption("c1", 1, 700, "Figure 1. Something."),
            _fragment("f1", 1, 400, 690),
        ]
    )
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["members"] == ["f1"]


def test_pairing_without_geometry_uses_reading_order() -> None:
    """A Markdown source has no bounding boxes and no fragments: the table is simply next door."""
    doc = _doc(
        [
            Block(id="t1", kind=BlockKind.TABLE, text="| a | b |\n|---|---|\n| 1 | 2 |"),
            Block(id="c1", kind=BlockKind.CAPTION, text="Table 1. Two columns."),
        ]
    )
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["members"] == ["t1"]
    assert doc.block("t1").parent_id == "c1"


def test_linking_twice_changes_nothing() -> None:
    doc = _doc([_fragment("f1", 1, 400, 500), _caption("c1", 1, 520, "Figure 1. Something.")])
    link_figures(doc)
    before = doc.block("c1").attrs["caption"]
    link_figures(doc)
    assert doc.block("c1").attrs["caption"] == before


# -- what the caption says ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("caption", "subject"),
    [
        (
            "Figure 1. Chain side reactions during TR of batteries [9]. Copyright 2023, Science.",
            "Chain side reactions during TR of batteries [9]",
        ),
        # A panel legend is a list of labels for parts of a picture: useless in speech.
        (
            "Figure 3. Gas production composition. (a) Sample No.1 (NCM); (b) Sample No.2.",
            "Gas production composition",
        ),
        # A caption that opens on its legend has no title above it, so the first panel serves.
        (
            "Figure 8. (a) A schematic image of the fire chamber; (b) images of the test.",
            "A schematic image of the fire chamber",
        ),
    ],
)
def test_the_subject_is_the_title_like_statement(caption: str, subject: str) -> None:
    doc = _doc([_fragment("f1", 1, 400, 500), _caption("c1", 1, 520, caption)])
    link_figures(doc)
    got = doc.block("c1").attrs["caption"]["subject"]
    assert got.startswith(subject[:20])


def test_a_caption_that_is_only_a_credit_line_has_no_subject() -> None:
    """And the announcement falls back to "there's a figure here", which is what it used to be
    for every figure. Saying "there's a figure here showing reproduced with permission from
    Smith and colleagues" would be worse than saying nothing about it."""
    doc = _doc(
        [
            _fragment("f1", 1, 400, 500),
            _caption("c1", 1, 520, "Figure 4. Reproduced with permission from Smith et al."),
        ]
    )
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["subject"] == ""


def test_the_subject_is_never_cut_mid_sentence() -> None:
    """The cap used to apply to raw characters, ending an announcement on "...GPR stands"."""
    long_caption = (
        "Figure 5. A probabilistic machine learning pipeline for battery state estimation "
        "across many chemistries and conditions. Among the algorithms listed here, GPR stands "
        "out for its calibrated uncertainty."
    )
    doc = _doc([_fragment("f1", 1, 400, 500), _caption("c1", 1, 520, long_caption)])
    link_figures(doc)
    subject = doc.block("c1").attrs["caption"]["subject"]
    assert "GPR" not in subject
    assert subject.endswith("conditions")


def test_references_are_collected_for_placement() -> None:
    """Rule FIG-04 places a description where the prose first mentions the figure."""
    doc = _doc(
        [
            Block(
                id="p1",
                kind=BlockKind.PARAGRAPH,
                text="As Figure 1 shows, capacity falls steadily over the first hundred cycles.",
            ),
            _fragment("f1", 1, 400, 500),
            _caption("c1", 1, 520, "Figure 1. Capacity against cycle number."),
        ]
    )
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["references"] == ["p1"]


def test_a_figure_nobody_mentions_has_no_references() -> None:
    """Two of the eleven figures in the test paper are never referred to, so FIG-04 needs a
    fallback and the caller has to be told there is nothing to anchor to."""
    doc = _doc([_fragment("f1", 1, 400, 500), _caption("c1", 1, 520, "Figure 9. Unmentioned.")])
    link_figures(doc)
    assert doc.block("c1").attrs["caption"]["references"] == []


# -- what the listener hears ----------------------------------------------------------------


def test_the_announcement_says_what_the_figure_is_of(study_profile: Profile) -> None:
    """Before stage A a PDF's figures reached the planner not at all, and their captions were
    read out as loose prose in the middle of a paragraph."""
    from mimem.plan.beats import BeatFactory, exposition_beats

    doc = _doc(
        [
            _fragment("f1", 1, 400, 500),
            _caption("c1", 1, 520, "Figure 1. Capacity against cycle number for both cells."),
        ]
    )
    link_figures(doc)
    beats = exposition_beats(doc.block("c1"), BeatFactory(profile=study_profile), {})
    assert len(beats) == 1
    assert beats[0].text == (
        "There's a figure here showing Capacity against cycle number for both cells. "
        "It's in the written notes."
    )


def test_a_block_its_caption_speaks_for_stays_silent(study_profile: Profile) -> None:
    """Otherwise the programme says "there is a table here" and then announces it again."""
    from mimem.plan.beats import BeatFactory, exposition_beats

    doc = _doc(
        [
            Block(id="t1", kind=BlockKind.TABLE, text="| a | b |\n|---|---|\n| 1 | 2 |"),
            Block(id="c1", kind=BlockKind.CAPTION, text="Table 1. Two columns."),
        ]
    )
    link_figures(doc)
    assert exposition_beats(doc.block("t1"), BeatFactory(profile=study_profile), {}) == []


def test_the_written_track_keeps_what_the_caption_speaks_for(study_profile: Profile) -> None:
    """Suppressing the table's own beat took its values out of study.md, and NUM-06 caught it."""
    from mimem.plan.beats import BeatFactory, exposition_beats

    doc = _doc(
        [
            Block(id="t1", kind=BlockKind.TABLE, text="| a | b |\n|---|---|\n| 0.0138 | 2 |"),
            Block(id="c1", kind=BlockKind.CAPTION, text="Table 1. Two columns."),
        ]
    )
    link_figures(doc)
    beat = exposition_beats(doc.block("c1"), BeatFactory(profile=study_profile), {})[0]
    assert beat.written_text is not None
    assert "0.0138" in beat.written_text
