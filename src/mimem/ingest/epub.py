"""EPUB ingestion.

Books are the secondary material (PLAN section 10.6), so this adapter is deliberately thin: it
walks the spine, converts each chapter's HTML into blocks, and leans on the fact that EPUB
already carries the structure a PDF makes us reconstruct.

Requires the optional extra:  ``pip install mimem[epub]``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from mimem.ingest.base import Adapter, IngestError, register
from mimem.ir import Block, BlockKind, Document, SourceMeta, block_id, document_id, file_sha256

_BLOCK_TAGS = {
    "p": BlockKind.PARAGRAPH,
    "h1": BlockKind.HEADING,
    "h2": BlockKind.HEADING,
    "h3": BlockKind.HEADING,
    "h4": BlockKind.HEADING,
    "h5": BlockKind.HEADING,
    "h6": BlockKind.HEADING,
    "li": BlockKind.LIST_ITEM,
    "blockquote": BlockKind.PARAGRAPH,
    "pre": BlockKind.CODE,
    "figcaption": BlockKind.CAPTION,
    "caption": BlockKind.CAPTION,
    "table": BlockKind.TABLE,
}


@register
class EpubAdapter(Adapter):
    """Ingest ``.epub``."""

    name: ClassVar[str] = "epub"
    version: ClassVar[str] = "1"
    extensions: ClassVar[tuple[str, ...]] = (".epub",)

    def __init__(self) -> None:
        try:
            import ebooklib  # noqa: F401
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on install
            raise IngestError(
                "EPUB support needs the optional extra: pip install 'mimem[epub]'"
            ) from exc

    def load(self, path: Path) -> Document:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub as ebook

        try:
            book = ebook.read_epub(str(path))
        except Exception as exc:  # pragma: no cover - depends on the file
            raise IngestError(f"could not open {path}: {exc}") from exc

        blocks: list[Block] = []
        order = 0
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "lxml")
            for node in soup.find_all(list(_BLOCK_TAGS)):
                if node.find_parent(["li", "blockquote", "table"]) is not None and node.name in {
                    "p"
                }:
                    continue  # avoid emitting the same text twice via nesting
                text = " ".join(node.get_text(" ", strip=True).split())
                if not text:
                    continue
                kind = _BLOCK_TAGS[node.name]
                level = int(node.name[1]) if kind is BlockKind.HEADING else None
                blocks.append(
                    Block(
                        id=block_id(kind.value, None, order, text),
                        kind=kind,
                        text=text,
                        order=order,
                        level=level,
                        attrs={"href": getattr(item, "file_name", None)},
                    )
                )
                order += 1

        source = SourceMeta(
            path=str(path),
            format="epub",
            sha256=file_sha256(path),
            title=_first_meta(book, "title"),
            authors=[a for a in [_first_meta(book, "creator")] if a],
            language=_first_meta(book, "language"),
            adapter=self.name,
            adapter_version=self.version,
        )
        return Document(
            id=document_id(source.sha256 or "", self.name),
            source=source,
            blocks=blocks,
            stages=["ingest"],
        )


def _first_meta(book: Any, name: str) -> str | None:
    try:
        values = book.get_metadata("DC", name)
    except Exception:  # pragma: no cover - depends on the file
        return None
    if not values:
        return None
    value = values[0][0]
    return str(value).strip() or None
