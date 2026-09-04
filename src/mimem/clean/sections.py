"""Section structure and rhetorical roles.

Papers are the primary material, so the role vocabulary is IMRaD-shaped. Roles are what let
stage 3 apply rule COH-01 without a classifier: an acknowledgement is dropped because it is an
acknowledgement, not because a model guessed.

Two things happen here:

* every block is attached to the heading that governs it (``section_id``, ``parent_id``);
* every block gets a :class:`~mimem.ir.models.BlockRole`, inherited from its section heading,
  with front matter (title, authors, affiliation, abstract) handled specially because it
  usually arrives before any heading at all.
"""

from __future__ import annotations

import re

from mimem.ir import Block, BlockKind, BlockRole, DiagnosticLevel, Document

#: Ordered: the first pattern that matches a heading wins.
_ROLE_PATTERNS: tuple[tuple[BlockRole, re.Pattern[str]], ...] = (
    (BlockRole.ABSTRACT, re.compile(r"^\s*(abstract|summary)\b", re.I)),
    (BlockRole.KEYWORDS, re.compile(r"^\s*key\s*words?\b", re.I)),
    (BlockRole.REFERENCES, re.compile(r"^\s*(references|bibliography|literature cited)\b", re.I)),
    (BlockRole.ACKNOWLEDGEMENT, re.compile(r"^\s*acknowledge?ment", re.I)),
    (
        BlockRole.FUNDING,
        re.compile(r"^\s*(funding|financial support|grant information)\b", re.I),
    ),
    (
        BlockRole.ETHICS,
        re.compile(
            r"^\s*(ethic|conflicts? of interest|competing interests?|declaration|"
            r"author contributions?|data availability|credit authorship|supporting information)",
            re.I,
        ),
    ),
    (BlockRole.APPENDIX, re.compile(r"^\s*(appendix|supplementary)\b", re.I)),
    (BlockRole.INTRODUCTION, re.compile(r"^\s*(introduction|background)\b", re.I)),
    (
        BlockRole.METHODS,
        re.compile(
            r"^\s*(methods?|materials and methods|experimental(\s+(section|details?|methods?))?|"
            r"methodology|model(ling|ing)? (setup|details)|computational details)\b",
            re.I,
        ),
    ),
    (
        BlockRole.RESULTS,
        re.compile(r"^\s*(results?)(\s+and\s+discussion)?\b", re.I),
    ),
    (BlockRole.DISCUSSION, re.compile(r"^\s*discussion\b", re.I)),
    (BlockRole.CONCLUSION, re.compile(r"^\s*(conclusions?|concluding remarks|outlook)\b", re.I)),
)

_LEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_AFFILIATION_HINT = re.compile(
    r"\b(university|universitet|institute|institutt|department|dept\.|laborator|college|"
    r"school of|centre|center|academy|hospital|gmbh|inc\.|ltd|a/?s|norway|sweden|denmark)\b",
    re.I,
)
#: A reference entry needs *both* a list marker and a bibliographic signal. Requiring only the
#: marker matches every numbered heading in the paper ("4. Conclusions").
_REFERENCE_MARKER = re.compile(r"^\s*(\[\d+\]|\(\d+\)|\d{1,3}\.\s)")
_REFERENCE_SIGNAL = re.compile(
    r"\b(19|20)\d{2}\b|\bdoi\b|\barxiv\b|\bpp?\.\s*\d|\bvol\.|\bno\.\s*\d|\bed(s)?\.", re.I
)


def _is_reference_entry(text: str) -> bool:
    return bool(_REFERENCE_MARKER.match(text) and _REFERENCE_SIGNAL.search(text))


def role_for_heading(text: str) -> BlockRole | None:
    """Map a heading's text onto a rhetorical role, or ``None`` if it is a content heading."""
    stripped = _LEADING_NUMBER.sub("", text.strip())
    for role, pattern in _ROLE_PATTERNS:
        if pattern.match(stripped):
            return role
    return None


def assign_sections(doc: Document) -> Document:
    """Attach blocks to headings and give every block a role.

    Front matter is handled first and separately. It has to be: a paper's title, authors,
    affiliation and abstract usually arrive *before* any heading the section walk would
    recognise, and in a PDF they are not reliably marked as anything at all.
    """
    front_end = _front_matter_end(doc)
    _assign_front_matter(doc, doc.blocks[:front_end])

    stack: list[Block] = []  # heading blocks, outermost first
    current_role = BlockRole.UNKNOWN
    seen_heading = False
    in_backmatter = False

    for block in doc.blocks[front_end:]:
        if block.kind is BlockKind.HEADING:
            level = block.level or 1
            while stack and (stack[-1].level or 1) >= level:
                stack.pop()
            block.parent_id = stack[-1].id if stack else None
            block.section_id = block.id

            role = role_for_heading(block.text)
            if role is not None:
                current_role = role
                in_backmatter = role in {
                    BlockRole.REFERENCES,
                    BlockRole.ACKNOWLEDGEMENT,
                    BlockRole.FUNDING,
                    BlockRole.ETHICS,
                }
            elif not seen_heading:
                current_role = BlockRole.BODY
            elif in_backmatter:
                # An unrecognised heading after the references ends the back matter only if it
                # looks like real content; otherwise assume more back matter.
                current_role = BlockRole.BODY if (block.level or 1) == 1 else current_role
                in_backmatter = current_role is not BlockRole.BODY
            else:
                current_role = _inherit(current_role)

            block.role = current_role
            stack.append(block)
            seen_heading = True
            continue

        block.parent_id = stack[-1].id if stack else None
        block.section_id = stack[-1].id if stack else None
        block.role = current_role if seen_heading else BlockRole.UNKNOWN
        if current_role is BlockRole.REFERENCES and block.kind is BlockKind.PARAGRAPH:
            block.kind = BlockKind.REFERENCE

    _rescue_unheaded_references(doc)

    unknown = sum(1 for b in doc.blocks if b.role is BlockRole.UNKNOWN and b.text.strip())
    if unknown:
        doc.note(
            "unclassified_blocks",
            f"{unknown} blocks have no rhetorical role; triage will fall back to heuristics",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return doc


def _inherit(role: BlockRole) -> BlockRole:
    """A sub-heading inside a recognised section keeps that section's role."""
    return role if role is not BlockRole.UNKNOWN else BlockRole.BODY


#: How many blocks at the head of a document may be front matter before we give up looking.
MAX_FRONT_MATTER_BLOCKS = 15


def _front_matter_end(doc: Document) -> int:
    """Index of the first block that belongs to the body proper.

    A "structural" heading -- one we recognise by name (Introduction, Methods, References) or by
    numbering ("2. Experimental") -- marks the end of the front matter. If none is found in the
    first few blocks, there is no front matter to speak of.
    """
    for i, block in enumerate(doc.blocks[:MAX_FRONT_MATTER_BLOCKS]):
        if block.kind is not BlockKind.HEADING:
            continue
        if role_for_heading(block.text) is not None:
            return i
        if re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+\S", block.text):
            return i
    return 0


def _assign_front_matter(doc: Document, front: list[Block]) -> None:
    """Label title / authors / affiliation / abstract / keywords.

    Everything here is a heuristic over a part of the document that has no reliable structure,
    so the guesses are recorded in ``attrs`` and shown by ``mimem inspect`` rather than trusted
    silently.
    """
    candidates = [b for b in front if b.text.strip() and b.kind is not BlockKind.PAGE_ARTIFACT]
    if not candidates:
        return

    # The title is the biggest type near the top -- not simply the first block, because a
    # running head usually beats it in reading order.
    title = max(
        candidates[:5],
        key=lambda b: (float(b.attrs.get("font_max") or 0.0), -b.order),
    )
    title.role = BlockRole.TITLE
    title.attrs["front_matter_guess"] = True
    if title.kind is BlockKind.PARAGRAPH:
        title.kind = BlockKind.HEADING
        title.level = 1
    if not doc.source.title:
        doc.source.title = title.text.strip()

    in_abstract = False
    for block in candidates:
        if block is title:
            continue
        text = block.text.strip()
        if block.order < title.order:
            continue  # running heads and journal furniture above the title: leave for triage

        if re.match(r"^\s*key\s*words?\b", text, re.I):
            block.role, in_abstract = BlockRole.KEYWORDS, False
        elif re.match(r"^\s*abstract\b", text, re.I):
            block.role, in_abstract = BlockRole.ABSTRACT, True
        elif in_abstract:
            block.role = BlockRole.ABSTRACT
        elif _EMAIL.search(text) or _AFFILIATION_HINT.search(text):
            block.role = BlockRole.AFFILIATION
        elif _looks_like_author_list(text):
            block.role = BlockRole.AUTHORS
            # A short line of capitalised names is often mistaken for a heading by the font
            # heuristics; front-matter context is better evidence than font size.
            if block.kind is BlockKind.HEADING:
                block.kind = BlockKind.PARAGRAPH
                block.level = None
            if not doc.source.authors:
                doc.source.authors = [a.strip() for a in text.split(",") if a.strip()]
        else:
            block.role = BlockRole.BODY
        block.attrs["front_matter_guess"] = True


def _looks_like_author_list(text: str) -> bool:
    if len(text) > 400 or text.endswith("."):
        return False
    commas = text.count(",")
    capitals = sum(1 for w in text.split() if w[:1].isupper())
    return commas >= 1 and capitals >= 2 and len(text.split()) <= 60


def _rescue_unheaded_references(doc: Document) -> None:
    """Some PDFs lose the 'References' heading entirely; the tail still looks like a list."""
    if any(b.role is BlockRole.REFERENCES for b in doc.blocks):
        return
    tail = [b for b in doc.blocks if b.text.strip() and b.kind is not BlockKind.HEADING][-25:]
    hits = [b for b in tail if _is_reference_entry(b.text)]
    if len(hits) >= 5:
        start = min(b.order for b in hits)
        for block in doc.blocks:
            if block.order >= start and block.text.strip():
                block.role = BlockRole.REFERENCES
                if block.kind is BlockKind.PARAGRAPH:
                    block.kind = BlockKind.REFERENCE
        doc.note(
            "references_without_heading",
            f"treated {len(hits)} trailing blocks as a reference list (no heading found)",
            stage="clean",
        )
