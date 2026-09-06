"""Stage 3: decide what reaches the narration at all (rules COH-*).

The coherence principle is the largest single lever in the multimedia literature -- removing
interesting-but-extraneous material *improves* learning, with an effect size close to 1.0 --
so the most effective thing this whole system does is delete. That makes triage the stage with
the most leverage and the most risk, which is why every decision carries a reason and lands in
a report a human can skim (rule COH-05).

Three tiers, cheapest first, exactly as planned:

1. **structural rules** over the roles and kinds that stage 2 already established;
2. **pattern rules** for boilerplate that survived role assignment;
3. a classifier for genuinely ambiguous blocks -- deferred to M5, because on real papers the
   first two tiers decide almost everything, and a model guessing at what to delete is the
   worst possible place to put one.
"""

from __future__ import annotations

import re

from mimem.clean.extraction import math_placeholder_count
from mimem.ir import (
    NON_CONTENT_ROLES,
    Block,
    BlockKind,
    BlockRole,
    DiagnosticLevel,
    Document,
    TriageAction,
    TriageDecision,
)

#: Kinds that are never narrated as prose.
_DROP_KINDS = frozenset({BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE})

#: Kinds that need a verbalizer rather than a reading.
_TRANSFORM_KINDS = frozenset(
    {BlockKind.TABLE, BlockKind.FIGURE, BlockKind.EQUATION, BlockKind.CODE}
)

#: Back-matter paragraphs usually carry their own label, and the label is often the only thing
#: separating them from prose: "Conflicts of Interest: The authors declare none." Anchoring the
#: declaration patterns at the start of the block missed every paper that writes it that way,
#: and a competing-interests sentence reached the audio track of a real paper before the COH-01
#: lint rule found it. Kept short and colon-terminated so it cannot swallow a real sentence.
_LABEL = r"(?:[A-Z][A-Za-z' -]{2,40}:\s*)?"

#: Sentences that exist to organise the page, not to say anything.
BOILERPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "paper roadmap",
        re.compile(
            r"^\s*the\s+(remainder|rest)\s+of\s+th(is|e)\s+(paper|article|manuscript|chapter)"
            r"\s+is\s+organi[sz]ed",
            re.I,
        ),
    ),
    (
        "declaration",
        re.compile(
            r"^\s*" + _LABEL + r"(the\s+authors?\s+declare|no\s+conflicts?\s+of\s+interest|"
            r"all\s+authors?\s+(have\s+)?(read|approved)|data\s+(will\s+be\s+)?available)",
            re.I,
        ),
    ),
    (
        "copyright",
        re.compile(r"©|\ball rights reserved\b|\bcreative commons\b|\bunder a cc[- ]by\b", re.I),
    ),
    ("license", re.compile(r"^\s*(this is an open access article|licen[sc]ed under)", re.I)),
    ("submission dates", re.compile(r"^\s*received:.{0,80}accepted:", re.I | re.S)),
    (
        "graphical abstract furniture",
        re.compile(r"^\s*(graphical abstract|highlights|in brief|key ?points)\s*:?\s*$", re.I),
    ),
    ("correspondence", re.compile(r"^\s*(correspondence|corresponding author)\b", re.I)),
    (
        # Keywords are a heading in some journals and a bold run-in line in others. The
        # heading-driven role assignment catches the first and could never catch the second, so
        # a keyword list narrated as prose -- five noun phrases and no verb -- reached the
        # audio track until rule COH-01 was written.
        "keyword list",
        re.compile(r"^\s*\**\s*key\s?words?\s*\**\s*:", re.I),
    ),
    (
        # "Supplemental information can be found online at ..." -- a pointer to something the
        # listener cannot follow, ending in an identifier that must never be spoken (NUM-05).
        "pointer to material the listener cannot reach",
        re.compile(
            r"\b(supplement(al|ary)\s+(information|material|data)"
            r"|(data|code)\s+(and\s+\w+\s+)?(is|are)\s+available)\b.{0,80}"
            r"\b(online|at|from|upon request|in the (repository|appendix))\b",
            re.I | re.S,
        ),
    ),
    (
        "article type banner",
        re.compile(
            r"^\s*(research(\s+article)?|original\s+(research|article)|review(\s+article)?"
            r"|article|letter|communication|perspective|editorial|mini[- ]?review)\s*$",
            re.I,
        ),
    ),
    (
        # The journal's own citation line: "Ionics (2026) 32:7477-7499  https://doi.org/10...".
        "journal citation line",
        # DOTALL: the line and its DOI arrive as two lines in an equation-shaped block, whose
        # line structure cleanup deliberately preserves.
        re.compile(r"^.{0,120}\(\s*(19|20)\d{2}\s*\).{0,80}(10\.\d{4,9}/|doi)", re.I | re.S),
    ),
)

#: Below this many words a paragraph is a fragment -- a stray label, a column artefact, an
#: axis title that escaped a figure. Headings and list items are exempt.
MIN_PARAGRAPH_WORDS = 4

#: Sections that are kept but shortened (rule COH-02).
_COMPRESS_ROLES = frozenset({BlockRole.METHODS})

#: Above this many inline-mathematics placeholders, the sentence depends on symbols that are
#: not in the PDF at all, and reading the words between them says nothing true.
MAX_MATH_PLACEHOLDERS = 2

#: Front matter that the orientation block will speak properly in M4. Narrating the raw
#: blocks now would say the title twice and read affiliation superscripts as numbers.
_ORIENTATION_ROLES = frozenset({BlockRole.TITLE, BlockRole.AUTHORS})


def _decide(block: Block) -> TriageDecision:
    role, kind = block.role, block.kind

    if kind in _DROP_KINDS:
        return TriageDecision(
            action=TriageAction.DROP, rule="COH-01", reason=f"{kind.value} is page furniture"
        )
    if role in _ORIENTATION_ROLES:
        return TriageDecision(
            action=TriageAction.DROP,
            rule="COH-01",
            reason="front matter, spoken by the orientation block instead (STR-01)",
        )
    if role in NON_CONTENT_ROLES:
        return TriageDecision(
            action=TriageAction.DROP, rule="COH-01", reason=f"{role.value} carries no content"
        )
    # Boilerplate is checked before the transform kinds, so that a drop always beats a
    # transform. A journal's own citation line is symbol-dense enough to look like an equation,
    # and announcing "there is an equation here" about it would be worse than saying nothing.
    for name, pattern in BOILERPLATE_PATTERNS:
        if pattern.search(block.text):
            return TriageDecision(action=TriageAction.DROP, rule="COH-01", reason=name)

    if kind in _TRANSFORM_KINDS:
        return TriageDecision(
            action=TriageAction.TRANSFORM,
            rule="COH-04",
            reason=f"{kind.value} needs verbalizing, not reading",
        )

    if math_placeholder_count(block.text) > MAX_MATH_PLACEHOLDERS:
        return TriageDecision(
            action=TriageAction.TRANSFORM,
            rule="COH-04",
            reason="prose depends on inline mathematics the PDF does not contain",
        )

    if (
        kind is BlockKind.PARAGRAPH
        and len(block.text.split()) < MIN_PARAGRAPH_WORDS
        and not block.text.rstrip().endswith((".", "!", "?"))
    ):
        return TriageDecision(
            action=TriageAction.DROP,
            rule="COH-01",
            reason="fragment, too short to be a sentence",
            confidence=0.6,
        )

    if role in _COMPRESS_ROLES and kind is BlockKind.PARAGRAPH:
        return TriageDecision(
            action=TriageAction.COMPRESS,
            rule="COH-02",
            reason="methods detail is summarised, not read in full",
            confidence=0.8,
        )

    return TriageDecision(action=TriageAction.KEEP, rule="COH-04", reason="carries the argument")


def triage(doc: Document) -> Document:
    """Attach a :class:`TriageDecision` to every block."""
    if "triage" in doc.stages:
        return doc

    counts: dict[TriageAction, int] = dict.fromkeys(TriageAction, 0)
    for block in doc.blocks:
        block.triage = _decide(block)
        counts[block.triage.action] += 1

    kept_words = sum(
        len(b.text.split()) for b in doc.blocks if b.triage and b.triage.action != TriageAction.DROP
    )
    total_words = doc.word_count or 1
    doc.note(
        "triage",
        f"keep {counts[TriageAction.KEEP]}, compress {counts[TriageAction.COMPRESS]}, "
        f"transform {counts[TriageAction.TRANSFORM]}, drop {counts[TriageAction.DROP]} "
        f"({100 * kept_words // total_words}% of words retained)",
        stage="triage",
        level=DiagnosticLevel.INFO,
    )
    doc.stages.append("triage")
    return doc


def retained(doc: Document) -> list[Block]:
    """Blocks that reach the narration, in reading order."""
    return [
        b
        for b in doc.blocks
        if b.triage is not None and b.triage.action is not TriageAction.DROP and b.text.strip()
    ]


def dropped(doc: Document) -> list[Block]:
    return [b for b in doc.blocks if b.triage is not None and b.triage.action is TriageAction.DROP]
