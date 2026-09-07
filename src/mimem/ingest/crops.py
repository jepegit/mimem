"""Render each figure's region out of the source PDF (``PLAN-figures.md`` stage B).

Ingestion deliberately writes no image files -- it records a page and a bounding box, which is
enough to re-render a crop at whatever resolution is wanted, and avoids leaving hundreds of
fragments on disk that nobody opens. Stage A turned those fragments into *figures*. This turns
each figure into one PNG.

It lives in the adapter layer rather than beside the renderer because its whole job is reading
the source PDF, and that is what this layer is for -- everything here talks to an untyped
third-party library, and the type checker is configured accordingly. Where the crops then *go* is
a rendering decision, and that half is in ``mimem.render.artefacts``.

Rendering the **region** rather than the embedded images is the point. A plot drawn by a plotting
library is vector content and produces no image block at all: page 10 of the paper this was
written against has one image block and three vector drawings, and the drawings are the figure.
Cropping the page gets both.

Two things this is for, and only the second one needs a model. The written companion currently
tells a reader that a figure exists and then makes them go back to the PDF to see it; a linked
crop ends that. And a crop is what a vision model would be given, so stage C is an argument about
what to do with these files rather than a new pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mimem.ir import Asset, AssetKind, BBox, Block, BlockKind, Document, asset_id

#: Where crops go, relative to the artefact directory.
FIGURE_DIR = "figures"

#: Resolution for a crop. Measured against a real figure region: 72 dpi is ~210 vision tokens and
#: legible, 100 is ~410, 150 is ~930 and no clearer. On the conversation path every one of these
#: crosses the MCP transport as base64, which adds a third again.
DPI = 100

#: Longest edge in pixels. A full-page schematic at 100 dpi is comfortably inside this; a very
#: tall multi-panel figure is not, and is rendered at whatever dpi fits instead.
MAX_EDGE = 1400

#: Points of padding around the region, so a crop does not shave the axis labels off.
PADDING = 4.0


def render_figures(doc: Document, out_dir: Path) -> list[Asset]:
    """Write one PNG per figure, and record each as an asset with its path.

    Never raises. A missing source file, a PDF that has moved since ingestion, a region that
    renders empty -- each of those costs the reader a picture and leaves everything else intact,
    which is the right trade for a written-track nicety. The programme is unchanged either way:
    the audio track never mentions a file.
    """
    if doc.source.format != "pdf" or not doc.source.path:
        return []
    source = Path(doc.source.path)
    if not source.exists():
        doc.note("figure_crops", f"source PDF is not at {source}; no crops rendered")
        return []

    figures = [
        b
        for b in doc.blocks
        if b.kind is BlockKind.CAPTION and _region(b) is not None and b.page is not None
    ]
    if not figures:
        return []

    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a hard dependency of the pdf extra
        return []

    written: list[Asset] = []
    target = out_dir / FIGURE_DIR
    try:
        pdf = pymupdf.open(source)
    except Exception as exc:  # pragma: no cover - depends on the file
        doc.note("figure_crops", f"could not reopen {source.name}: {exc}")
        return []

    try:
        target.mkdir(parents=True, exist_ok=True)
        for block in figures:
            region = _region(block)
            assert region is not None and block.page is not None
            meta = block.attrs.get("caption", {})
            name = _filename(meta)
            asset = _render_one(pdf, doc, block.page, region, target / name)
            if asset is None:
                continue
            asset = asset.model_copy(
                update={
                    "id": asset_id(block.id, "crop", 0),
                    "block_id": block.id,
                    "path": f"{FIGURE_DIR}/{name}",
                }
            )
            doc.assets.append(asset)
            meta["image"] = asset.path
            written.append(asset)
    finally:
        _close(pdf)

    doc.note("figure_crops", f"rendered {len(written)} figure crops into {FIGURE_DIR}/")
    return written


def _close(pdf: Any) -> None:
    """PyMuPDF ships no type information, so its calls are untyped in a strict context."""
    pdf.close()


def _clip(region: BBox, page_rect: Any) -> Any:
    """The region, padded, and never larger than the page it is on."""
    import pymupdf

    box: Any = pymupdf.Rect(
        max(0.0, region.x0 - PADDING),
        max(0.0, region.y0 - PADDING),
        region.x1 + PADDING,
        region.y1 + PADDING,
    )
    return box & page_rect


def _region(block: Block) -> BBox | None:
    meta = block.attrs.get("caption")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("region")
    if not isinstance(raw, dict):
        return None
    try:
        return BBox.model_validate(raw)
    except ValueError:  # pragma: no cover - a malformed region is not worth a crash
        return None


def _filename(meta: dict[str, object]) -> str:
    """``figure-3.png``, or a positional name when the caption had no number to give."""
    number = str(meta.get("number", "")).strip()
    label = "table" if meta.get("label") == "table" else "figure"
    return f"{label}-{number or 'x'}.png"


def _render_one(pdf: Any, doc: Document, page: int, region: BBox, path: Path) -> Asset | None:
    try:
        loaded = pdf.load_page(page - 1)
    except Exception:  # pragma: no cover - a page number from a different document
        return None

    rect = _clip(region, loaded.rect)
    if rect.is_empty or rect.width < 1 or rect.height < 1:
        return None

    dpi = DPI
    longest = max(rect.width, rect.height) * dpi / 72.0
    if longest > MAX_EDGE:
        dpi = max(36, int(dpi * MAX_EDGE / longest))

    try:
        pixmap = loaded.get_pixmap(clip=rect, dpi=dpi)
        data = pixmap.tobytes("png")
    except Exception as exc:  # pragma: no cover - depends on the file
        doc.note("figure_crops", f"page {page}: {exc}")
        return None
    if not data:
        return None

    path.write_bytes(data)
    return Asset(
        id="",
        kind=AssetKind.IMAGE,
        block_id="",
        page=page,
        bbox=region,
        attrs={
            "width": pixmap.width,
            "height": pixmap.height,
            "dpi": dpi,
            "bytes": len(data),
        },
    )
