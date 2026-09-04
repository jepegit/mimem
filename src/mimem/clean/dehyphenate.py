"""Repair line-break damage.

PDF extraction hands us text with the printer's line breaks still in it, which means words are
split by hyphens that were never part of the word ("electro-\\nlyte") and sentences are broken by
newlines that were never pauses. Both corrupt everything downstream: sentence splitting, term
matching, and -- worst of all -- the narration, where "electro lyte" is audible.

The judgement call is which hyphens are *real*. We keep a hyphen when the evidence says it
belongs to the word, and drop it otherwise; the counts land in the document diagnostics so
over-eager joining is visible rather than silent.
"""

from __future__ import annotations

import re

from mimem.ir import Block, BlockKind, DiagnosticLevel, Document

#: Prefixes that keep their hyphen in scientific English.
#:
#: The list is deliberately short. Both errors are possible and they are not equally bad: a
#: wrongly *kept* hyphen splits a technical term in two, which breaks term matching in the
#: concept registry and is audible in the narration ("inter phase"), while a wrongly *dropped*
#: one produces a closed compound that still reads correctly ("multiwalled"). So a prefix earns
#: a place here only when the hyphenated form clearly dominates: "self-limiting", "non-aqueous",
#: "quasi-static", "in-plane", "high-rate". Prefixes whose closed form is standard --
#: inter(phase), intra, sub, super, micro, nano, multi, semi, pre, post, anti, re, trans, ultra
#: -- are left out on purpose.
KEEP_HYPHEN_PREFIXES = frozenset(
    {
        "co",
        "cross",
        "ex",
        "high",
        "in",
        "low",
        "mid",
        "near",
        "non",
        "off",
        "on",
        "out",
        "pseudo",
        "quasi",
        "self",
        "well",
    }
)

_HYPHEN_BREAK = re.compile(r"(\w+)[-‐‑]\n(\w+)")
_SOFT_BREAK = re.compile(r"[ \t]*\n[ \t]*")
_MULTISPACE = re.compile(r"[ \t]{2,}")

#: A soft hyphen is an invisible "you may break the word here" marker. Extraction keeps it,
#: and often a space with it, so a hyphenated word arrives split in two and is narrated as
#: two words. It carries no meaning at all, so it and any space it swallowed go.
_SOFT_HYPHEN = re.compile("­" + r"\s*")
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    " ": " ",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "−": "-",
    "‑": "-",  # non-breaking hyphen: a hyphen to a reader, an unknown to a regex
    "‐": "-",  # unicode hyphen
}

#: Blocks whose internal line structure carries meaning and must not be flattened.
_LINE_SENSITIVE = frozenset({BlockKind.CODE, BlockKind.EQUATION, BlockKind.TABLE})


def joins_without_hyphen(left: str, right: str) -> bool:
    """Should ``left-\\nright`` become ``leftright`` rather than ``left-right``?"""
    if not left or not right:
        return False
    if right[0].isupper() or right[0].isdigit():
        return False  # "Li-\nIon" stays hyphenated; "T-\n2" stays "T-2"
    if len(left) <= 1:
        return False
    tail = re.split(r"[\s–—(]", left)[-1]
    # Chemistry and physics are full of short capitalised stems whose hyphen is part of the
    # name: Li-ion, Na-ion, X-ray, pH-dependent, XRD-derived. Joining those invents words.
    if len(tail) <= 3 and tail[:1].isupper():
        return False
    if any(c.isupper() for c in tail[1:]):
        return False
    return tail.lower() not in KEEP_HYPHEN_PREFIXES


def dehyphenate_text(text: str) -> tuple[str, int, int]:
    """Return ``(cleaned, joins, kept)`` for one block of text."""
    text = _SOFT_HYPHEN.sub("", text)
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)

    joins = 0
    kept = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal joins, kept
        left, right = m.group(1), m.group(2)
        # "cycle-\nto-cycle": the continuation is itself hyphenated, so the break fell inside a
        # compound that keeps all of its hyphens.
        continues_compound = m.string[m.end() : m.end() + 1] in {"-", "‐", "‑"}
        if not continues_compound and joins_without_hyphen(left, right):
            joins += 1
            return left + right
        kept += 1
        return f"{left}-{right}"

    text = _HYPHEN_BREAK.sub(repl, text)
    text = _SOFT_BREAK.sub(" ", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip(), joins, kept


def dehyphenate(doc: Document) -> Document:
    """Flatten line breaks and repair split words across the whole document."""
    joins = kept = 0
    for block in doc.blocks:
        if not block.text:
            continue
        if block.kind in _LINE_SENSITIVE:
            block.text = _normalise_only(block.text)
            continue
        cleaned, j, k = dehyphenate_text(block.text)
        block.text = cleaned
        joins += j
        kept += k
    if joins or kept:
        doc.note(
            "dehyphenated",
            f"joined {joins} hyphenated line breaks, kept {kept} as real hyphens",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return doc


def _normalise_only(text: str) -> str:
    """Ligature and quote normalisation without touching line structure."""
    text = _SOFT_HYPHEN.sub("", text)
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    return text.rstrip()


def block_is_blank(block: Block) -> bool:
    return not block.text.strip() and block.kind not in {BlockKind.FIGURE, BlockKind.TABLE}
