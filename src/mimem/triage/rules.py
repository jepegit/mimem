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

#: What a journal prints in front of a back-matter label. ACS sets its section headings with a
#: filled square, correspondence lines with an asterisk, affiliations with daggers -- and the
#: anchored patterns below all begin ``^\s*``, so a single character of furniture in front of
#: the label was enough to miss the block entirely. "*Correspondence to: ... Ningbo 315103,
#: P. R. China Tel/Fax: +86 574 87902102" was narrated in full, postcode and telephone number
#: included, in a paper whose only two errors were those two numbers.
_MARK = r"[\s*\u25a0\u25aa\u2022\u00b7\u2020\u2021\u00a7#|_-]*"

#: The headings a journal puts over its back matter. Everything after one of these is
#: acknowledgement, funding, competing interests or an address -- none of it for a listener.
#:
#: They matter because the heading and its section arrive as **one paragraph**: ACS emits
#: "\u25a0AUTHOR INFORMATION Notes The authors declare no competing financial interest.
#: \u25a0ACKNOWLEDGMENTS We gratefully acknowledge funding from Department of Energy..." as a
#: single block, so every pattern that anchors on the declaration itself begins in the wrong
#: place and matches nothing. Six COH-01 errors across four papers were this one shape.
_BACK_MATTER_HEADING = (
    r"author\s+information|author\s+contributions?|acknowledge?ments?|acknowledgements?"
    r"|associated\s+content|supporting\s+information|conflicts?\s+of\s+interest"
    r"|competing\s+(financial\s+)?interests?|declarations?\s+of\s+(competing\s+)?interest"
    r"|funding(\s+sources?)?|abbreviations?\s+used|data\s+availability"
)

#: Sentences that exist to organise the page, not to say anything.
BOILERPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "paper roadmap",
        re.compile(
            r"^"
            + _MARK
            + r"the\s+(remainder|rest)\s+of\s+th(is|e)\s+(paper|article|manuscript|chapter)"
            r"\s+is\s+organi[sz]ed",
            re.I,
        ),
    ),
    (
        "declaration",
        re.compile(
            r"^"
            + _MARK
            + r""
            + _LABEL
            + r"(the\s+authors?\s+declare|no\s+conflicts?\s+of\s+interest|"
            r"all\s+authors?\s+(have\s+)?(read|approved)|data\s+(will\s+be\s+)?available)",
            re.I,
        ),
    ),
    (
        "copyright",
        re.compile(r"©|\ball rights reserved\b|\bcreative commons\b|\bunder a cc[- ]by\b", re.I),
    ),
    (
        "license",
        re.compile(r"^" + _MARK + r"(this is an open access article|licen[sc]ed under)", re.I),
    ),
    (
        # The publication history, however the journal words it. Anchoring on "Received:" and
        # "Accepted:" matched one house style: "Manuscript submitted July 2, 2015; revised
        # manuscript received August 17, 2015. Published October 9, 2015." was narrated in full.
        "submission dates",
        re.compile(
            r"^" + _MARK + r"(?:manuscript\s+)?(?:received|submitted)\b"
            r".{0,160}\b(?:accepted|revised|published)\b",
            re.I | re.S,
        ),
    ),
    (
        "graphical abstract furniture",
        re.compile(
            r"^" + _MARK + r"(graphical abstract|highlights|in brief|key ?points)\s*:?\s*$", re.I
        ),
    ),
    ("correspondence", re.compile(r"^" + _MARK + r"(correspondence|corresponding author)\b", re.I)),
    (
        # Keywords are a heading in some journals and a bold run-in line in others. The
        # heading-driven role assignment catches the first and could never catch the second, so
        # a keyword list narrated as prose -- five noun phrases and no verb -- reached the
        # audio track until rule COH-01 was written.
        "keyword list",
        re.compile(r"^" + _MARK + r"\**\s*key\s?words?\s*\**\s*:", re.I),
    ),
    (
        # A row of panel labels lifted out of a figure: "(a) (b) (c) (d)". It is a legend for
        # regions of a picture and carries no sentence at all -- narrated, it becomes "a, b, c,
        # d, e, f." spoken aloud, which happened.
        "panel labels",
        re.compile(r"^" + _MARK + r"[(\[]?[a-h][)\]]?(?:[\s,;]+[(\[]?[a-h][)\]]?){1,7}\s*$", re.I),
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
            r"^"
            + _MARK
            + r"(research(\s+article)?|original\s+(research|article)|review(\s+article)?"
            r"|article|letter|communication|perspective|editorial|mini[- ]?review)\s*$",
            re.I,
        ),
    ),
    (
        # A whole back-matter section in one paragraph, heading and all. Dropping it on the
        # heading rather than on the declaration is what makes it reachable: the declaration is
        # in the middle of the block, and every other pattern here is anchored at the start.
        "back matter",
        re.compile(r"^" + _MARK + r"(" + _BACK_MATTER_HEADING + r")\b", re.I),
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


#: The commonest function words in English. A sentence cannot avoid them: across 668 kept blocks
#: from twelve papers, every one that was genuinely prose contained at least one, and every block
#: of eight words or more that contained none was not prose at all.
FUNCTION_WORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "of",
        "in",
        "to",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "with",
        "that",
        "this",
        "by",
        "on",
        "as",
        "at",
        "from",
        "be",
        "been",
        "it",
        "its",
        "which",
        "we",
        "our",
        "their",
        "have",
        "has",
        "had",
        "than",
        "these",
        "those",
        "but",
        "not",
    ]
)

#: Below this, a run of words without function words is a heading or a name, both of which are
#: legitimate. "Structural Changes in Silicon Anodes" has "in"; "Nano Letters" has nothing and
#: is four words long. Eight is where the corpus separates cleanly.
MIN_NOT_PROSE_WORDS = 8


def reads_as_prose(text: str) -> bool:
    """Would a person reading this aloud be reading sentences?

    The signal is function words, not digits. A table of unit-cell parameters is only 20%
    numerals -- ``Li~1! 12a 0.375 0 0.25 Li~2! 48e`` -- so a numeric-density test misses it,
    while a contents page is 98% full stops and a figure's axis labels are 100% numerals. What
    all three share is that nothing in them is doing grammatical work.

    Found by profiling the corpus rather than by choosing a rule: of 668 kept blocks this
    rejects 37, and every one is journal front matter, an address, a contents page, a table, a
    reference entry, an axis, or a heading whose letters were spaced out (``h i g h l i g h t
    s``). No prose block in twelve papers has eight words and no function word.
    """
    words = text.split()
    if len(words) < MIN_NOT_PROSE_WORDS:
        return True
    return any(word.lower().strip(".,;:()[]\u2019'\"") in FUNCTION_WORDS for word in words)


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

    if kind not in _TRANSFORM_KINDS and not reads_as_prose(block.text):
        return TriageDecision(
            action=TriageAction.DROP,
            rule="COH-01",
            reason="no function words: a table, an axis, a contents page or front matter",
            confidence=0.8,
        )

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
