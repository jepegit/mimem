"""The document intermediate representation.

Everything downstream of ingestion reads and writes this. Adapters differ; the IR does not --
that is the whole point of it. See docs/PLAN-part1.md section 3.

Only the *document* side of the IR lives here (M0/M1). Concept, Beat and Script models arrive
with M3/M4; they will share this module's conventions: pydantic v2, JSON round-trippable,
``schema_version`` on every top-level artefact.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


class Base(BaseModel):
    """Shared configuration: reject unknown fields so schema drift fails loudly."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BlockKind(StrEnum):
    """What a block *is*, structurally."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    FIGURE = "figure"
    TABLE = "table"
    EQUATION = "equation"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    CODE = "code"
    REFERENCE = "reference"
    PAGE_ARTIFACT = "page_artifact"  # running heads, folios, watermarks
    UNKNOWN = "unknown"


class BlockRole(StrEnum):
    """What a block is *for*, in the rhetoric of a scientific paper.

    Papers are the primary material (PLAN section 10.6), so the role vocabulary is IMRaD-shaped.
    Book chapters collapse onto BODY.
    """

    TITLE = "title"
    AUTHORS = "authors"
    AFFILIATION = "affiliation"
    ABSTRACT = "abstract"
    KEYWORDS = "keywords"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    BODY = "body"
    REFERENCES = "references"
    ACKNOWLEDGEMENT = "acknowledgement"
    FUNDING = "funding"
    ETHICS = "ethics"
    APPENDIX = "appendix"
    BOILERPLATE = "boilerplate"
    UNKNOWN = "unknown"


#: Roles that carry no listenable content. Stage 3 (triage) owns the real decision; this is a
#: shared vocabulary so that triage rules and tests agree on what "boilerplate" means.
NON_CONTENT_ROLES: frozenset[BlockRole] = frozenset(
    {
        BlockRole.AFFILIATION,
        BlockRole.KEYWORDS,
        BlockRole.REFERENCES,
        BlockRole.ACKNOWLEDGEMENT,
        BlockRole.FUNDING,
        BlockRole.ETHICS,
        BlockRole.BOILERPLATE,
    }
)


class BBox(Base):
    """Position on the page, in PDF points, origin top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class Span(Base):
    """A citable location in the source. The unit of provenance (rule GRD-01)."""

    block_id: str
    char_start: int = 0
    char_end: int = 0
    page: int | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.char_end < self.char_start:
            raise ValueError(f"span end {self.char_end} precedes start {self.char_start}")
        return self


class AssetKind(StrEnum):
    IMAGE = "image"
    TABLE_CSV = "table_csv"
    LATEX = "latex"


class Asset(Base):
    """A non-text payload extracted alongside a block: a figure crop, a table, a formula."""

    id: str
    kind: AssetKind
    block_id: str
    path: str | None = None  # relative to the artefact directory
    page: int | None = None
    bbox: BBox | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class TriageAction(StrEnum):
    """What stage 3 decided to do with a block (rules ``COH-*``)."""

    KEEP = "keep"
    COMPRESS = "compress"  # retained, but shortened before narration
    TRANSFORM = "transform"  # not prose: a figure, table or equation needs verbalizing
    DROP = "drop"


class TriageDecision(Base):
    """A triage decision, with its reason.

    Rule COH-05: drops are recorded, never silent. The reason is written for a human reading
    the drop report, and ``rule`` names the design rule that justified it.
    """

    action: TriageAction
    rule: str  # e.g. "COH-01"
    reason: str
    confidence: float = 1.0  # 1.0 for rule-based decisions, lower for heuristics


class Block(Base):
    """One structural unit of the source document."""

    id: str
    kind: BlockKind = BlockKind.UNKNOWN
    role: BlockRole = BlockRole.UNKNOWN
    text: str = ""
    order: int = 0  # reading order within the document, 0-based
    level: int | None = None  # heading depth, 1-based
    page: int | None = None
    column: int | None = None
    bbox: BBox | None = None
    parent_id: str | None = None
    section_id: str | None = None  # ID of the heading block that governs this block
    sentences: list[tuple[int, int]] = Field(default_factory=list)  # char offsets into `text`
    triage: TriageDecision | None = None  # filled by stage 3
    attrs: dict[str, Any] = Field(default_factory=dict)

    #: Sentences stage 6 split, keyed ``"start:end"`` by the offsets of the sentence they
    #: replace (rule SENT-01). The *source* is never edited: a span still points at what the
    #: paper wrote, which is what makes the rewrite checkable and what rule GRD-02 asks for.
    #: What changes is only what gets spoken.
    rewrites: dict[str, str] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def span(self) -> Span:
        """The span covering this whole block."""
        return Span(block_id=self.id, char_start=0, char_end=len(self.text), page=self.page)

    def sentence_texts(self) -> list[str]:
        return [self.text[a:b] for a, b in self.sentences]

    def spoken_text(self, start: int, end: int) -> str:
        """What the programme says for this span: the split, where there is one."""
        return self.rewrites.get(f"{start}:{end}") or self.text[start:end]


class DiagnosticLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Diagnostic(Base):
    """Something the pipeline noticed and a human may need to know.

    Ingestion problems are not exceptions -- a paper with one unreadable page is still worth
    processing. They are recorded, surfaced by ``mimem inspect``, and counted in the eval
    metrics.
    """

    level: DiagnosticLevel = DiagnosticLevel.WARNING
    code: str
    message: str
    stage: str = "ingest"
    block_id: str | None = None
    page: int | None = None


class SourceMeta(Base):
    """Where the document came from, and what we know about it."""

    path: str | None = None
    format: str = "unknown"  # pdf | epub | txt | md | html
    sha256: str | None = None
    n_pages: int | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    language: str | None = None
    adapter: str = "unknown"
    adapter_version: str = "0"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attrs: dict[str, Any] = Field(default_factory=dict)


class Document(Base):
    """A source document in canonical form. The output of stage 1 and stage 2."""

    schema_version: int = SCHEMA_VERSION
    id: str
    source: SourceMeta
    blocks: list[Block] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)  # stages applied, in order

    # -- lookup helpers ------------------------------------------------------------------

    def block(self, block_id: str) -> Block:
        for b in self.blocks:
            if b.id == block_id:
                return b
        raise KeyError(block_id)

    def by_kind(self, *kinds: BlockKind) -> list[Block]:
        wanted = set(kinds)
        return [b for b in self.blocks if b.kind in wanted]

    def by_role(self, *roles: BlockRole) -> list[Block]:
        wanted = set(roles)
        return [b for b in self.blocks if b.role in wanted]

    def text_of(self, span: Span) -> str:
        return self.block(span.block_id).text[span.char_start : span.char_end]

    @property
    def word_count(self) -> int:
        return sum(len(b.text.split()) for b in self.blocks)

    def note(self, code: str, message: str, **kw: Any) -> None:
        self.diagnostics.append(Diagnostic(code=code, message=message, **kw))

    def renumber(self) -> None:
        """Re-apply reading order after blocks have been reordered or removed."""
        for i, b in enumerate(self.blocks):
            b.order = i

    # -- persistence ---------------------------------------------------------------------

    def content_fingerprint(self) -> str:
        """Hash of everything that is *content*, ignoring volatile metadata.

        Ingestion time is not content, so two runs over the same file produce the same
        fingerprint even though their JSON differs. This is what the stage caches key on, and
        what "ingestion is deterministic" actually means.
        """
        import hashlib

        payload = self.model_dump(
            mode="json", exclude={"source": {"ingested_at", "path"}, "diagnostics": True}
        )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.blake2s(canonical.encode("utf-8"), digest_size=16).hexdigest()

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str | bytes) -> Document:
        doc = cls.model_validate_json(data)
        if doc.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"document schema version {doc.schema_version} != supported {SCHEMA_VERSION}"
            )
        return doc
