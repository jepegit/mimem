"""PDF ingestion via PyMuPDF.

Papers are the primary material (PLAN section 10.6), which means this adapter has to survive the
things journal PDFs actually do: two columns, running heads, figures that span the gutter,
captions that look like paragraphs, and hyphens at line ends.

Division of labour: this module handles *layout* -- what is on the page and in what order. It
emits block text with line breaks preserved (``\\n``), because dehyphenation in
:mod:`mimem.clean` needs to know where the lines were. Everything corpus-level happens there.

Figure images are deliberately *not* extracted here. We record page and bounding box, which is
enough to re-render a crop on demand later (stage 5) at whatever resolution the vision call
wants, and avoids writing hundreds of files nobody looks at.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from statistics import median
from typing import Any, ClassVar

import pymupdf

from mimem.ingest.base import Adapter, IngestError, register
from mimem.ir import (
    Asset,
    AssetKind,
    BBox,
    Block,
    BlockKind,
    Diagnostic,
    DiagnosticLevel,
    Document,
    SourceMeta,
    asset_id,
    block_id,
    document_id,
    file_sha256,
)

#: A block wider than this fraction of the text area spans the columns: a title, an abstract,
#: a wide figure. Such blocks act as horizontal separators when rebuilding reading order.
FULL_WIDTH_RATIO = 0.68

#: Half-width of the dead zone around the page midline that a two-column layout must keep clear.
GUTTER_RATIO = 0.035

#: Minimum characters extracted before we believe the PDF has a real text layer.
MIN_TEXT_LAYER_CHARS = 200

#: A caption, and not a sentence that happens to open with a figure number.
#:
#: The delimiter after the numeral is the whole discriminator. A caption writes "Figure 6." or
#: "Figure 6:"; running prose writes "Figure 6 exemplifies how transfer learning...", and
#: without the delimiter that sentence was classified as a caption -- which both lost it as
#: prose and gave the figure a second, wrong caption. Length cannot separate the two: the false
#: caption in the paper that found this is 45 words, and the real captions run from 5 to 88 with
#: one of them also 45.
#: A dash counts only when it is spaced. "Fig. 3 - Capacity against cycle number" is a caption;
#: "Figures 3-5 show that capacity falls" is a reference to a range, and the space is what tells
#: them apart.
CAPTION_RE = re.compile(
    r"^\s*(fig(?:ure)?|table|scheme|chart|plate|eq(?:uation)?)\s*\.?\s*(\d+|[IVXLC]+)"
    r"(?:\s*[.:)]|\s+[-–—]\s+)",
    re.IGNORECASE,
)
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
APPENDIX_HEADING_RE = re.compile(r"^\s*(appendix|supplementary)\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*[-—–]?\s*(?:page\s*)?(\d{1,4}|[ivxlcdm]+)\s*[-—–]?\s*$", re.I)

#: Characters that suggest a display equation rather than prose.
MATH_CHARS = set("=+−-×·/^∑∫∂∇√≈≤≥≠∞±⋅⟨⟩αβγδεθκλμνπρσςτφχψωΔΘΛΞΠΣΦΨΩ_{}")

BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold


class _RawBlock:
    """A block as PyMuPDF gave it to us, before classification."""

    __slots__ = (
        "bbox",
        "bold_ratio",
        "column",
        "font_max",
        "font_mode",
        "is_image",
        "page",
        "text",
        "xref",
    )

    def __init__(
        self,
        *,
        text: str,
        bbox: tuple[float, float, float, float],
        page: int,
        font_max: float = 0.0,
        font_mode: float = 0.0,
        bold_ratio: float = 0.0,
        is_image: bool = False,
        xref: int | None = None,
    ) -> None:
        self.text = text
        self.bbox = bbox
        self.page = page
        self.font_max = font_max
        self.font_mode = font_mode
        self.bold_ratio = bold_ratio
        self.is_image = is_image
        self.xref = xref
        self.column: int | None = None

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def center_x(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def top(self) -> float:
        return self.bbox[1]


@register
class PdfAdapter(Adapter):
    """Ingest a PDF into the document IR."""

    name: ClassVar[str] = "pymupdf"
    version: ClassVar[str] = "1"
    extensions: ClassVar[tuple[str, ...]] = (".pdf",)

    def load(self, path: Path) -> Document:
        try:
            pdf = pymupdf.open(path)
        except Exception as exc:  # pragma: no cover - depends on the file
            raise IngestError(f"could not open {path}: {exc}") from exc

        diagnostics: list[Diagnostic] = []
        pages: list[list[_RawBlock]] = []
        try:
            for pno in range(pdf.page_count):
                page = pdf.load_page(pno)
                pages.append(self._page_blocks(page, pno + 1, diagnostics))
            meta = dict(pdf.metadata or {})
            n_pages = pdf.page_count
        finally:
            pdf.close()

        total_chars = sum(len(rb.text) for pg in pages for rb in pg if not rb.is_image)
        if n_pages and total_chars < MIN_TEXT_LAYER_CHARS:
            raise IngestError(
                f"{path.name} has almost no text layer ({total_chars} characters over "
                f"{n_pages} pages). It is probably a scan -- run OCR first, e.g. "
                f"`ocrmypdf in.pdf out.pdf`, then ingest the result."
            )

        ordered = [rb for pg in pages for rb in self._reading_order(pg)]
        body_size = self._body_font_size(ordered)
        blocks, assets = self._classify(ordered, body_size)

        source = SourceMeta(
            path=str(path),
            format="pdf",
            sha256=file_sha256(path),
            n_pages=n_pages,
            title=(meta.get("title") or "").strip() or None,
            authors=_split_authors(meta.get("author")),
            doi=self._find_doi(blocks),
            adapter=self.name,
            adapter_version=self.version,
            attrs={"body_font_size": round(body_size, 2)},
        )
        doc = Document(
            id=document_id(source.sha256 or "", self.name),
            source=source,
            blocks=blocks,
            assets=assets,
            diagnostics=diagnostics,
            stages=["ingest"],
        )
        if not doc.blocks:
            doc.note("empty_document", "no blocks extracted", level=DiagnosticLevel.ERROR)
        return doc

    # -- page level ----------------------------------------------------------------------

    def _page_blocks(self, page: Any, pno: int, diagnostics: list[Diagnostic]) -> list[_RawBlock]:
        try:
            raw = page.get_text("dict")
        except Exception as exc:  # pragma: no cover - depends on the file
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="page_unreadable",
                    message=f"could not extract text: {exc}",
                    page=pno,
                )
            )
            return []

        out: list[_RawBlock] = []
        for blk in raw.get("blocks", []):
            if blk.get("type") == 1:  # image
                out.append(
                    _RawBlock(
                        text="",
                        bbox=tuple(blk["bbox"]),
                        page=pno,
                        is_image=True,
                        xref=blk.get("number"),
                    )
                )
                continue
            lines: list[str] = []
            sizes: list[tuple[float, int]] = []
            bold_chars = 0
            total_chars = 0
            for line in blk.get("lines", []):
                parts: list[str] = []
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    parts.append(text)
                    sizes.append((round(float(span.get("size", 0.0)), 1), len(text)))
                    total_chars += len(text)
                    if int(span.get("flags", 0)) & BOLD_FLAG:
                        bold_chars += len(text)
                joined = "".join(parts).rstrip()
                if joined.strip():
                    lines.append(joined)
            if not lines:
                continue
            out.append(
                _RawBlock(
                    text="\n".join(lines),
                    bbox=tuple(blk["bbox"]),
                    page=pno,
                    font_max=max((s for s, _ in sizes), default=0.0),
                    font_mode=_weighted_mode(sizes),
                    bold_ratio=(bold_chars / total_chars) if total_chars else 0.0,
                )
            )
        return out

    # -- reading order -------------------------------------------------------------------

    def _reading_order(self, blocks: list[_RawBlock]) -> list[_RawBlock]:
        """Restore reading order on a possibly multi-column page.

        Full-width blocks act as horizontal separators: everything above one is read (column by
        column) before it, everything below after it. That single rule handles the common paper
        layout -- full-width title and abstract, two columns of body, a wide figure in the
        middle -- without needing real layout analysis.
        """
        if len(blocks) < 2:
            return list(blocks)

        text_left = min(b.bbox[0] for b in blocks)
        text_right = max(b.bbox[2] for b in blocks)
        text_width = max(text_right - text_left, 1.0)
        mid = (text_left + text_right) / 2
        gutter = GUTTER_RATIO * text_width

        # A block spans the columns either by being wide, or by straddling the gutter. The
        # second test matters: a two-line title or an affiliation line is often only half the
        # text width but still sits across the middle, and treating it as a column block puts
        # the whole page in the wrong reading order.
        def spans_columns(b: _RawBlock) -> bool:
            if b.width >= FULL_WIDTH_RATIO * text_width:
                return True
            return b.bbox[0] < mid - gutter and b.bbox[2] > mid + gutter

        full_width = {id(b) for b in blocks if spans_columns(b)}
        columnar = [b for b in blocks if id(b) not in full_width]
        two_column = self._is_two_column(columnar, mid)

        def column_of(b: _RawBlock) -> int:
            return 0 if (not two_column or b.center_x < mid) else 1

        ordered: list[_RawBlock] = []
        buffer: list[_RawBlock] = []
        for b in sorted(blocks, key=lambda b: (round(b.top, 1), b.bbox[0])):
            if id(b) in full_width:
                ordered.extend(sorted(buffer, key=lambda x: (column_of(x), x.top, x.bbox[0])))
                buffer = []
                ordered.append(b)
            else:
                buffer.append(b)
        ordered.extend(sorted(buffer, key=lambda x: (column_of(x), x.top, x.bbox[0])))

        if two_column:
            for b in ordered:
                b.column = None if id(b) in full_width else column_of(b)
        return ordered

    @staticmethod
    def _is_two_column(blocks: list[_RawBlock], mid: float) -> bool:
        """True when a real vertical gutter separates the left blocks from the right ones.

        The test is not "are there blocks on both sides" -- a single-column page with a
        marginal note would pass that. It is "does the rightmost edge of everything on the
        left sit clear of the leftmost edge of everything on the right".
        """
        if len(blocks) < 4:
            return False
        left = [b for b in blocks if b.center_x < mid]
        right = [b for b in blocks if b.center_x >= mid]
        if len(left) < 2 or len(right) < 2:
            return False
        return max(b.bbox[2] for b in left) <= min(b.bbox[0] for b in right) + 2.0

    # -- classification ------------------------------------------------------------------

    @staticmethod
    def _body_font_size(blocks: list[_RawBlock]) -> float:
        sizes = [b.font_mode for b in blocks if not b.is_image and b.font_mode > 0]
        return median(sizes) if sizes else 10.0

    def _classify(
        self, ordered: list[_RawBlock], body_size: float
    ) -> tuple[list[Block], list[Asset]]:
        blocks: list[Block] = []
        assets: list[Asset] = []
        for i, rb in enumerate(ordered):
            bbox = BBox(x0=rb.bbox[0], y0=rb.bbox[1], x1=rb.bbox[2], y1=rb.bbox[3])
            if rb.is_image:
                bid = block_id("figure", rb.page, i, f"image@{rb.bbox}")
                blocks.append(
                    Block(
                        id=bid,
                        kind=BlockKind.FIGURE,
                        order=i,
                        page=rb.page,
                        bbox=bbox,
                        attrs={"source": "embedded_image"},
                    )
                )
                assets.append(
                    Asset(
                        id=asset_id(bid, "image", i),
                        kind=AssetKind.IMAGE,
                        block_id=bid,
                        page=rb.page,
                        bbox=bbox,
                        # No file written: page + bbox is enough to re-render a crop on demand.
                        attrs={"xref": rb.xref, "render_on_demand": True},
                    )
                )
                continue

            kind, level = self._kind_of(rb, body_size)
            bid = block_id(kind.value, rb.page, i, rb.text)
            blocks.append(
                Block(
                    id=bid,
                    kind=kind,
                    text=rb.text,
                    order=i,
                    level=level,
                    page=rb.page,
                    column=rb.column,
                    bbox=bbox,
                    attrs={
                        "font_size": rb.font_mode,
                        "font_max": rb.font_max,
                        "bold_ratio": round(rb.bold_ratio, 2),
                    },
                )
            )
        return blocks, assets

    def _kind_of(self, rb: _RawBlock, body_size: float) -> tuple[BlockKind, int | None]:
        text = rb.text.strip()
        first_line = text.split("\n", 1)[0].strip()

        if PAGE_NUMBER_RE.match(text) and len(text) <= 12:
            return BlockKind.PAGE_ARTIFACT, None
        if CAPTION_RE.match(first_line):
            return BlockKind.CAPTION, None
        if self._looks_like_equation(text):
            return BlockKind.EQUATION, None

        heading_level = self._heading_level(rb, body_size, first_line)
        if heading_level is not None:
            return BlockKind.HEADING, heading_level
        if re.match(r"^\s*[-•·▪–]\s+", first_line):
            return BlockKind.LIST_ITEM, None
        return BlockKind.PARAGRAPH, None

    @staticmethod
    def _looks_like_equation(text: str) -> bool:
        stripped = text.strip()
        if not stripped or len(stripped) > 200 or "\n" in stripped[:1]:
            return False
        # Density is measured without whitespace: display equations are usually padded out to
        # centre them, and that padding must not dilute the signal.
        compact = "".join(stripped.split())
        if not compact:
            return False
        letters = sum(c.isalpha() for c in compact)
        mathy = sum(c in MATH_CHARS for c in compact)
        words = stripped.split()
        # Short, symbol-dense, and not a sentence: "C(t) = C0 exp(-t/tau)  (3)"
        return (
            mathy >= 2
            and len(words) <= 20
            and mathy >= 0.10 * len(compact)
            and letters < 0.75 * len(compact)
        )

    @staticmethod
    def _heading_level(rb: _RawBlock, body_size: float, first_line: str) -> int | None:
        # A trailing period is the strongest single signal that this is prose -- except for
        # numbered headings ("3. Results"), which the numbering branch below catches.
        looks_like_prose = (
            not first_line or len(first_line) > 120 or first_line.endswith((".", ";", ","))
        )
        if looks_like_prose and not NUMBERED_HEADING_RE.match(first_line):
            return None
        n_lines = rb.text.count("\n") + 1
        if n_lines > 3:
            return None

        bigger = rb.font_mode > body_size + 0.6
        bold = rb.bold_ratio > 0.6
        numbered = NUMBERED_HEADING_RE.match(first_line)
        appendixish = APPENDIX_HEADING_RE.match(first_line)

        if numbered and (bigger or bold or rb.font_mode >= body_size):
            return min(numbered.group(1).count(".") + 1, 6)
        if appendixish and (bigger or bold):
            return 1
        if bigger and n_lines <= 2:
            # Font-size ranking gives the level: bigger jump, shallower heading.
            delta = rb.font_mode - body_size
            return 1 if delta >= 3.0 else (2 if delta >= 1.5 else 3)
        if bold and n_lines == 1 and len(first_line.split()) <= 10:
            return 3
        return None

    @staticmethod
    def _find_doi(blocks: list[Block]) -> str | None:
        for b in blocks[:40]:
            m = DOI_RE.search(b.text)
            if m:
                return m.group(0).rstrip(".,;")
        return None


def _weighted_mode(sizes: list[tuple[float, int]]) -> float:
    """Most common font size in a block, weighted by how many characters use it."""
    if not sizes:
        return 0.0
    totals: dict[float, int] = {}
    for size, count in sizes:
        totals[size] = totals.get(size, 0) + count
    return max(totals.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _split_authors(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"\s*(?:;|,| and | & )\s*", raw.strip())
    return [p for p in (p.strip() for p in parts) if p]


def iter_page_images(path: Path, page: int, bbox: BBox, dpi: int = 200) -> Iterator[bytes]:
    """Render a figure region on demand as PNG bytes (used by stage 5, kept here with the
    knowledge of how the bbox was produced)."""
    pdf = pymupdf.open(path)
    try:
        pg = pdf.load_page(page - 1)
        clip = pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        yield pg.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
    finally:
        pdf.close()
