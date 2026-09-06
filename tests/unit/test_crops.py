"""Rendering a figure's region out of the source PDF (``PLAN-figures.md`` stage B).

Built against a PDF made here rather than a fixture on disk, because what is being tested is the
arithmetic between a bounding box and a page: does the crop land on the region stage A worked
out, and does it stay inside the page when the region does not.

The other half of these tests is about *not raising*. A crop is a nicety of the written track --
the audio never mentions a file -- so every way this can fail should cost the reader a picture
and nothing else. A build that dies because a PDF moved would be a much worse outcome than a
study.md with one fewer image in it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mimem.ingest.crops import DPI, FIGURE_DIR, MAX_EDGE, render_figures
from mimem.ir import BBox, Block, BlockKind, Document, SourceMeta

pymupdf = pytest.importorskip("pymupdf")


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    """A two-page PDF with something recognisable in a known rectangle."""
    doc = pymupdf.open()
    for page_no in range(2):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(pymupdf.Rect(100, 200, 400, 500), color=(0, 0, 0), fill=(0.2, 0.4, 0.8))
        page.insert_text((110, 520), f"Figure {page_no + 1}. A blue rectangle.")
    path = tmp_path / "paper.pdf"
    doc.save(path)
    doc.close()
    return path


def _doc(path: Path, region: BBox | None, page: int = 1) -> Document:
    meta: dict[str, object] = {"label": "figure", "number": "1", "subject": "A blue rectangle"}
    if region is not None:
        meta["region"] = region.model_dump()
    caption = Block(
        id="c1",
        kind=BlockKind.CAPTION,
        text="Figure 1. A blue rectangle.",
        page=page,
        bbox=BBox(x0=100, y0=510, x1=400, y1=530),
        attrs={"caption": meta},
    )
    return Document(
        id="d1",
        source=SourceMeta(format="pdf", path=str(path)),
        blocks=[caption],
    )


def test_a_figure_becomes_one_png(paper: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500))
    assets = render_figures(doc, out)

    assert len(assets) == 1
    written = out / FIGURE_DIR / "figure-1.png"
    assert written.exists()
    assert written.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert assets[0].path == f"{FIGURE_DIR}/figure-1.png"
    assert assets[0].block_id == "c1"
    assert assets[0].page == 1


def test_the_crop_is_the_region_and_not_the_page(paper: Path, tmp_path: Path) -> None:
    """A crop is a claim about a rectangle. Getting the rectangle wrong is the failure mode."""
    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500))
    assets = render_figures(doc, tmp_path / "out")
    width, height = assets[0].attrs["width"], assets[0].attrs["height"]

    # 300x300 points plus padding on both sides, at 100 dpi.
    assert 400 < width < 440
    assert 400 < height < 440


def test_the_render_records_where_it_came_from(paper: Path, tmp_path: Path) -> None:
    region = BBox(x0=100, y0=200, x1=400, y1=500)
    assets = render_figures(_doc(paper, region), tmp_path / "out")
    assert assets[0].bbox == region
    assert assets[0].attrs["dpi"] == DPI


def test_the_caption_learns_where_its_picture_is(paper: Path, tmp_path: Path) -> None:
    """study.md finds the crop through the document, so the link has to be recorded on it."""
    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500))
    render_figures(doc, tmp_path / "out")
    assert doc.block("c1").attrs["caption"]["image"] == f"{FIGURE_DIR}/figure-1.png"


def test_a_region_larger_than_its_page_is_clipped(paper: Path, tmp_path: Path) -> None:
    """Merged blocks and bad geometry both produce rectangles that run off the page."""
    doc = _doc(paper, BBox(x0=-50, y0=-50, x1=2000, y1=4000))
    assets = render_figures(doc, tmp_path / "out")
    assert len(assets) == 1
    assert assets[0].attrs["width"] <= MAX_EDGE
    assert assets[0].attrs["height"] <= MAX_EDGE


def test_a_whole_a4_page_is_still_rendered_at_full_resolution(paper: Path, tmp_path: Path) -> None:
    """The cap is a guard, not a routine path: A4 at 100 dpi is 1169 px and needs no help."""
    doc = _doc(paper, BBox(x0=0, y0=0, x1=595, y1=842))
    assets = render_figures(doc, tmp_path / "out")
    assert assets[0].attrs["dpi"] == DPI


def test_an_oversized_page_drops_its_resolution(tmp_path: Path) -> None:
    """A conference poster, or a journal that sets a foldout at twice the page height."""
    path = tmp_path / "poster.pdf"
    doc = pymupdf.open()
    doc.new_page(width=1200, height=1800)
    doc.save(path)
    doc.close()

    ir = _doc(path, BBox(x0=0, y0=0, x1=1200, y1=1800))
    assets = render_figures(ir, tmp_path / "out")
    assert assets[0].attrs["dpi"] < DPI
    assert max(assets[0].attrs["width"], assets[0].attrs["height"]) <= MAX_EDGE


# -- the ways this is allowed to fail -----------------------------------------------------------


def test_a_caption_with_no_region_is_skipped(paper: Path, tmp_path: Path) -> None:
    """A table caption gets no region on purpose, and would render a picture of words."""
    assert render_figures(_doc(paper, None), tmp_path / "out") == []


def test_a_missing_source_costs_a_picture_and_nothing_else(tmp_path: Path) -> None:
    doc = _doc(tmp_path / "gone.pdf", BBox(x0=100, y0=200, x1=400, y1=500))
    assert render_figures(doc, tmp_path / "out") == []
    assert any("not at" in d.message for d in doc.diagnostics)


def test_a_page_the_pdf_does_not_have_is_skipped(paper: Path, tmp_path: Path) -> None:
    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500), page=99)
    assert render_figures(doc, tmp_path / "out") == []


def test_a_non_pdf_source_renders_nothing(tmp_path: Path) -> None:
    """Markdown figures have no geometry to crop, and saying so is not an error."""
    doc = Document(id="d1", source=SourceMeta(format="md", path="paper.md"), blocks=[])
    assert render_figures(doc, tmp_path / "out") == []


def test_nothing_is_written_when_there_is_nothing_to_write(paper: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    render_figures(_doc(paper, None), out)
    assert not (out / FIGURE_DIR).exists()


# -- what the reader gets -----------------------------------------------------------------------


def test_study_md_shows_the_figure(paper: Path, tmp_path: Path, study_profile) -> None:
    """The whole point of stage B: the written companion stops sending you back to the PDF."""
    from mimem.ir import Script
    from mimem.plan.beats import BeatFactory, exposition_beats
    from mimem.render import render_study

    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500))
    render_figures(doc, tmp_path / "out")
    beats = exposition_beats(doc.block("c1"), BeatFactory(profile=study_profile), {})

    script = Script(doc_id=doc.id, source=doc.source, opening=beats)
    written = render_study(script, doc)
    assert f"]({FIGURE_DIR}/figure-1.png)" in written
    # The alt text is the caption's subject, not the beat's "it's in the written notes".
    assert "![A blue rectangle]" in written


def test_the_manifest_records_the_region_a_crop_claims(paper: Path, tmp_path: Path) -> None:
    """So a wrong crop is something a reader can check rather than something they must notice."""
    import json

    from mimem.ir import Script
    from mimem.render import render_manifest

    doc = _doc(paper, BBox(x0=100, y0=200, x1=400, y1=500))
    render_figures(doc, tmp_path / "out")

    payload = json.loads(render_manifest(Script(doc_id=doc.id, source=doc.source), doc))
    assert len(payload["figures"]) == 1
    entry = payload["figures"][0]
    assert entry["page"] == 1
    assert entry["region"]["x0"] == 100
    assert entry["subject"] == "A blue rectangle"
    assert entry["path"] == f"{FIGURE_DIR}/figure-1.png"
