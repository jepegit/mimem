"""Plain text and Markdown ingestion.

Small, but not a toy: it is the fastest way to test the whole downstream pipeline without a PDF
in the loop, and it is how pasted abstracts and preprint sources get in.

Equations, tables and figures are recognised as themselves rather than as prose. That mattered
more than it looked: a display equation left as a paragraph is *narrated*, and the linter has no
way to object, because by the time it sees the beat there is nothing left to say the thing was
ever an equation. Rules ``MTH-04``, ``TBL-02`` and ``FIG-01`` are all statements about blocks
that this adapter previously could not produce, so on a Markdown source they were unfalsifiable
-- which is a worse condition than failing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from mimem.ingest.base import Adapter, register
from mimem.ir import Block, BlockKind, Document, SourceMeta, block_id, document_id, text_sha256

ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")
SETEXT_H1_RE = re.compile(r"^=+\s*$")
SETEXT_H2_RE = re.compile(r"^-{2,}\s*$")
LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+\S")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

#: A display equation: ``$$`` on its own line, or a whole line wrapped in one pair.
MATH_FENCE_RE = re.compile(r"^\s*\$\$\s*$")
MATH_INLINE_RE = re.compile(r"^\s*\$\$(?P<body>.+?)\$\$\s*$")

#: A pipe table. The separator row is what distinguishes one from a line that happens to
#: contain pipes, so a table is only recognised once its second row confirms it.
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE_RE = re.compile(r"^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$")

#: An image, and the caption convention every paper uses for one.
IMAGE_RE = re.compile(r"^\s*!\[(?P<alt>[^\]]*)\]\([^)]*\)\s*$")
CAPTION_RE = re.compile(r"^\s*\**(?:figure|fig\.|table|scheme)\s*\d+", re.IGNORECASE)


@register
class TextAdapter(Adapter):
    """Ingest ``.txt``, ``.md`` and ``.markdown``."""

    name: ClassVar[str] = "text"
    version: ClassVar[str] = "1"
    extensions: ClassVar[tuple[str, ...]] = (".txt", ".md", ".markdown")

    def load(self, path: Path) -> Document:
        raw = path.read_text(encoding="utf-8", errors="replace")
        blocks = list(self._blocks(raw))
        source = SourceMeta(
            path=str(path),
            format=path.suffix.lstrip(".").lower() or "txt",
            sha256=text_sha256(raw),
            title=self._title(blocks),
            adapter=self.name,
            adapter_version=self.version,
        )
        return Document(
            id=document_id(source.sha256 or "", self.name),
            source=source,
            blocks=blocks,
            stages=["ingest"],
        )

    def _blocks(self, raw: str) -> list[Block]:
        blocks: list[Block] = []
        order = 0

        def emit(kind: BlockKind, text: str, level: int | None = None) -> None:
            nonlocal order
            text = text.strip()
            if not text:
                return
            blocks.append(
                Block(
                    id=block_id(kind.value, None, order, text),
                    kind=kind,
                    text=text,
                    order=order,
                    level=level,
                )
            )
            order += 1

        lines = raw.replace("\r\n", "\n").split("\n")
        buffer: list[str] = []
        buffer_kind = BlockKind.PARAGRAPH
        in_fence = False
        fence_marker = ""

        def flush() -> None:
            nonlocal buffer, buffer_kind
            if buffer:
                emit(buffer_kind, "\n".join(buffer))
            buffer = []
            buffer_kind = BlockKind.PARAGRAPH

        in_math = False

        for i, line in enumerate(lines):
            fence = FENCE_RE.match(line)
            if in_fence:
                buffer.append(line)
                if fence and line.strip().startswith(fence_marker):
                    in_fence = False
                    flush()
                continue
            if in_math:
                if MATH_FENCE_RE.match(line):
                    in_math = False
                    flush()
                else:
                    buffer.append(line)
                continue
            if fence:
                flush()
                in_fence = True
                fence_marker = fence.group(1)
                buffer_kind = BlockKind.CODE
                buffer.append(line)
                continue

            inline_math = MATH_INLINE_RE.match(line)
            if inline_math:
                flush()
                emit(BlockKind.EQUATION, inline_math.group("body"))
                continue
            if MATH_FENCE_RE.match(line):
                flush()
                in_math = True
                buffer_kind = BlockKind.EQUATION
                continue

            image = IMAGE_RE.match(line)
            if image:
                flush()
                emit(BlockKind.FIGURE, image.group("alt") or "figure")
                continue

            if TABLE_ROW_RE.match(line) and TABLE_RULE_RE.match(
                lines[i + 1] if i + 1 < len(lines) else ""
            ):
                flush()
                buffer_kind = BlockKind.TABLE
                buffer.append(line)
                continue
            if buffer_kind is BlockKind.TABLE:
                if TABLE_ROW_RE.match(line):
                    buffer.append(line)
                    continue
                flush()

            if not buffer and CAPTION_RE.match(line):
                flush()
                buffer_kind = BlockKind.CAPTION

            if not line.strip():
                flush()
                continue

            atx = ATX_HEADING_RE.match(line)
            if atx:
                flush()
                emit(BlockKind.HEADING, atx.group(2), level=len(atx.group(1)))
                continue

            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if buffer_kind is BlockKind.PARAGRAPH and not buffer:
                if SETEXT_H1_RE.match(nxt):
                    emit(BlockKind.HEADING, line, level=1)
                    lines[i + 1] = ""
                    continue
                if SETEXT_H2_RE.match(nxt) and line.strip():
                    emit(BlockKind.HEADING, line, level=2)
                    lines[i + 1] = ""
                    continue

            if LIST_RE.match(line):
                flush()
                emit(BlockKind.LIST_ITEM, line)
                continue

            buffer.append(line)

        flush()
        return blocks

    @staticmethod
    def _title(blocks: list[Block]) -> str | None:
        for b in blocks:
            if b.kind is BlockKind.HEADING and (b.level or 9) <= 2:
                return b.text
        return blocks[0].text[:120] if blocks else None
