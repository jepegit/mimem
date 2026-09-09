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
    # "Summary" is deliberately not here. Some journals title the abstract "Summary", but far
    # more papers use it for the closing section ("6 Summary and future perspectives"), and
    # matching it as an abstract mid-document mislabels everything that follows. In the front
    # matter, where it is unambiguous, `_assign_front_matter` accepts it.
    (BlockRole.ABSTRACT, re.compile(r"^\s*abstract\b", re.I)),
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
    (
        BlockRole.CONCLUSION,
        re.compile(
            r"^\s*(conclusions?|concluding remarks|outlook"
            r"|summary and (outlook|future|perspectives?|conclusions?)|summary)\b",
            re.I,
        ),
    ),
)

#: Publisher and repository furniture that shows up in the front matter of a real PDF. A
#: repository cover sheet ("Downloaded from ... (article starts on next page)") is several
#: hundred words of pure noise wrapped around the paper you actually wanted.
_BOILERPLATE_HINT = re.compile(
    r"\bdownloaded from\b|\barticle starts on next page\b"
    r"|\bcitation for the (original|published)\b|\bwhen citing this work\b"
    r"|\boffers the possibility of retrieving\b|\bthis is the (accepted|author)"
    r"|\ball rights reserved\b|\bopen access\b.{0,60}\bcreative commons\b"
    r"|^\s*received:.{0,80}\baccepted:|\bpublished online:\s*\d"
    r"|\bterms of use\b|\bsupplementary (material|information) (is )?available\b",
    re.IGNORECASE | re.DOTALL,
)

_LEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
#: ``A/S`` is the Norwegian limited-company suffix, and it is spelled in capitals. Written
#: ``a/?s`` under ``re.I`` alongside everything else it matched the English word **as**, so any
#: front-matter block containing it was an affiliation -- including one paper's title, "Aluminum
#: hydride *as* a hydrogen and energy storage material". Triage then dropped the title as
#: content-free while the orientation went on saying it, which is what rule ``STR-01`` asks for
#: and what ``COH-01`` then reported as a leak.
_AFFILIATION_HINT = re.compile(
    r"\b(university|universitet|institute|institutt|department|dept\.|laborator|college|"
    r"school of|centre|center|academy|hospital|gmbh|ltd|(?-i:A/?S)|"
    # No full stop on these two: the pattern ends in a word boundary, and there is none
    # between "Dept." and the space after it, so both alternatives never matched anything.
    r"dept|inc|"
    r"norway|sweden|denmark)\b",
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

    # A repository cover sheet is a whole front page of boilerplate wrapped around the paper,
    # whose *real* front matter then begins on page two. Labelling stopped at the end of page
    # one and left the author list to be narrated as prose, superscripts and all. If page one
    # turned out to be nothing but boilerplate, look at the next page too.
    for _ in range(2):
        if not _is_cover_page(doc.blocks[:front_end]):
            break
        extended = _front_matter_end(doc, after=front_end)
        if extended <= front_end:
            break
        _assign_front_matter(doc, doc.blocks[front_end:extended])
        front_end = extended

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
#: Real papers need much more room than it looks: a Springer front page runs journal line,
#: article-type banner, logo, title, a two-line author list, submission dates, abstract,
#: keywords, corresponding-author line and six affiliations before the Introduction begins.
MAX_FRONT_MATTER_BLOCKS = 40


def _is_structural_heading(block: Block) -> bool:
    """A heading that names a section of the paper, rather than a heading inside one."""
    if block.kind is not BlockKind.HEADING:
        return False
    if role_for_heading(block.text) is not None:
        return True
    return bool(re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+\S", block.text))


def _front_matter_end(doc: Document, *, after: int = 0) -> int:
    """Index of the first block that belongs to the body proper.

    The front matter ends at the first structural heading -- one we recognise by name
    (Introduction, Methods, References) or by numbering ("2. Experimental").

    When no such heading appears before the end of the first page, the whole first page is
    treated as front matter instead of giving up. That case is common and it used to lose the
    title outright: on a Springer paper the Introduction starts on page two, so scanning a short
    window from the top found nothing structural and no front matter was labelled at all.
    Labelling is positive-evidence-only, so widening the window costs little -- a block the
    front-matter pass cannot identify stays UNKNOWN and is left for triage.

    ``after`` restarts the scan further into the document, which is how a repository cover
    page is skipped so the paper's own front matter can be labelled.
    """
    blocks = doc.blocks[after : after + MAX_FRONT_MATTER_BLOCKS]
    page = next((b.page for b in blocks if b.page is not None), None)
    window = after
    for i, block in enumerate(blocks, start=after):
        if page is not None and block.page is not None and block.page != page:
            break
        if _is_structural_heading(block):
            return i
        window = i + 1
    return window


def _is_cover_page(blocks: list[Block]) -> bool:
    """Was this whole page publisher furniture rather than the paper's own front matter?"""
    labelled = [b for b in blocks if b.role is not BlockRole.UNKNOWN and b.text.strip()]
    if not labelled:
        return False
    informative = [b for b in labelled if b.role not in {BlockRole.BOILERPLATE, BlockRole.TITLE}]
    return not informative


#: An abstract's heading is often set run-in with its first sentence, so the block arrives as
#: "Abstract The accelerating electrification of transport...". On the page the typography marks
#: it as a label; in speech nothing does, and the listener hears a sentence that starts with a
#: word nobody said. Sentence offsets are rebuilt because they are byte offsets into this text.
_RUN_IN_LABEL = re.compile(r"^\s*(abstract|summary)\s*[:.\u2014-]?\s+(?=[A-Z(])", re.I)


def _strip_run_in_label(block: Block) -> None:
    """Remove a run-in "Abstract" label from the start of a block."""
    stripped = _RUN_IN_LABEL.sub("", block.text, count=1)
    if stripped == block.text or not stripped.strip():
        return
    block.text = stripped
    if block.sentences:
        # Sectioning runs before sentence segmentation, so there is nothing to fix today. The
        # guard is here so that changing that order cannot silently leave every offset in this
        # block pointing a word to the left.
        from mimem.clean.sentences import sentence_spans

        block.sentences = sentence_spans(block.text)


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

        if _BOILERPLATE_HINT.search(text):
            block.role, in_abstract = BlockRole.BOILERPLATE, False
        elif re.match(r"^\s*key\s*words?\b", text, re.I):
            block.role, in_abstract = BlockRole.KEYWORDS, False
        elif re.match(r"^\s*(abstract|summary)\b", text, re.I):
            # In the front matter, "Summary" is unambiguously the abstract.
            block.role, in_abstract = BlockRole.ABSTRACT, True
            _strip_run_in_label(block)
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
                doc.source.authors = [a.strip() for a in _AUTHOR_SEPARATOR.split(text) if a.strip()]
        else:
            # Positive evidence only. An unidentified front-matter block stays UNKNOWN and is
            # left for triage rather than being promoted into the narration by default.
            continue
        block.attrs["front_matter_guess"] = True


#: Author lists are separated by commas, semicolons, or the middle dot Springer favours
#: ("Anupam Yadav1 · Mustafa Abdullah2 · V. Vivek3").
_AUTHOR_SEPARATOR = re.compile(r"[,;·•]")


def _looks_like_author_list(text: str) -> bool:
    if len(text) > 400 or text.endswith("."):
        return False
    separators = len(_AUTHOR_SEPARATOR.findall(text))
    capitals = sum(1 for w in text.split() if w[:1].isupper())
    return separators >= 1 and capitals >= 2 and len(text.split()) <= 60


#: How far back from the end of the document to look for the start of a reference list. A Cell
#: Press article can run to thirty-odd entries, each its own block, spread over three pages.
MAX_REFERENCE_SCAN = 200

#: Entries that must be found before the tail is called a reference list.
MIN_REFERENCE_RUN = 5

#: Non-entry blocks tolerated inside the run: a running head, a page number, a stray fragment,
#: an entry whose year the extractor mangled.
MAX_REFERENCE_GAP = 3

_REFERENCE_HEADING_TEXT = re.compile(
    r"^\s*(references|bibliography|literature cited)\s*:?\s*$", re.I
)


def _reference_run_start(blocks: list[Block]) -> int | None:
    """Index in ``blocks`` where the trailing reference list begins, or ``None``.

    Walking *backwards* from the end and stopping at sustained non-entry content is what
    matters here. Taking a fixed-size tail instead -- which is what this did first -- finds the
    end of the list and misses its beginning: on a paper with thirty references, entries one
    to fifteen fell outside a twenty-five block window and were narrated as prose, DOIs and all.
    """
    start: int | None = None
    entries = 0
    gap = 0
    for i in range(len(blocks) - 1, -1, -1):
        block = blocks[i]
        if _REFERENCE_HEADING_TEXT.match(block.text):
            return i  # the list's own heading, missed by the heading heuristics
        if _is_reference_entry(block.text):
            start, entries, gap = i, entries + 1, 0
            continue
        if block.kind is BlockKind.PAGE_ARTIFACT or not block.text.strip():
            continue
        gap += 1
        if gap > MAX_REFERENCE_GAP:
            break
    return start if entries >= MIN_REFERENCE_RUN else None


def _rescue_unheaded_references(doc: Document) -> None:
    """Some PDFs lose the 'References' heading entirely; the tail still looks like a list."""
    if any(b.role is BlockRole.REFERENCES for b in doc.blocks):
        return
    window = [b for b in doc.blocks if b.kind is not BlockKind.HEADING][-MAX_REFERENCE_SCAN:]
    index = _reference_run_start(window)
    if index is None:
        return

    start = window[index].order
    marked = 0
    for block in doc.blocks:
        if block.order >= start and block.text.strip():
            block.role = BlockRole.REFERENCES
            if block.kind is BlockKind.PARAGRAPH:
                block.kind = BlockKind.REFERENCE
            marked += 1
    doc.note(
        "references_without_heading",
        f"treated the last {marked} blocks as a reference list (no heading found)",
        stage="clean",
    )
