"""Repair damage that belongs to the extractor, not the author.

Two things a tagged PDF leaves in the text stream that no author ever wrote:

**Control characters.** Springer articles carry ``\\x07`` as an internal separator. It is
invisible on the page, meaningless in the IR, and unspeakable.

**Math placeholders.** Where an equation or an inline symbol sits, the accessibility layer
emits a marker such as ``inline-eq-IEq19`` instead of the mathematics. The symbol itself is
simply not in the text layer, so no amount of cleverness downstream can recover it -- the honest
move is to normalise the marker so later stages can *see* that mathematics was there and treat
the passage accordingly, rather than narrating "in line eq I Eq nineteen".

The markers arrive mangled, because span joining inserts spaces inside the word itself:
``inline-eq``, ``in line-eq``, ``i nline-eq`` and ``inli ne-eq`` all occur in one paper. The
pattern therefore tolerates whitespace between any two characters.
"""

from __future__ import annotations

import re

from mimem.ir import DiagnosticLevel, Document

#: The canonical form every math placeholder is normalised to. Lower case and hyphenated so it
#: cannot be mistaken for an acronym by the later stages.
MATH_PLACEHOLDER = "inline-eq"


def _spaced(word: str) -> str:
    """A regex matching ``word`` with optional whitespace between any two characters."""
    return r"\s*".join(re.escape(c) for c in word)


MATH_MARKER = re.compile(
    rf"(?:{_spaced('inline')}|{_spaced('display')})\s*-\s*eq\s*-?\s*[A-Za-z]*\d+",
    re.IGNORECASE,
)

#: C0 and C1 control characters, keeping the two that carry layout meaning.
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def strip_extraction_artifacts(doc: Document) -> Document:
    """Remove control characters and normalise math placeholders."""
    controls = 0
    markers = 0

    for block in doc.blocks:
        if not block.text:
            continue
        text, n_controls = CONTROL_CHARS.subn(" ", block.text)
        text, n_markers = MATH_MARKER.subn(MATH_PLACEHOLDER, text)
        controls += n_controls
        markers += n_markers
        if n_markers:
            block.attrs["math_placeholders"] = n_markers
        if n_controls or n_markers:
            block.text = re.sub(r"[ \t]{2,}", " ", text).strip()

    if controls:
        doc.note(
            "control_characters",
            f"removed {controls} control characters left by the extractor",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    if markers:
        doc.note(
            "math_placeholders",
            f"normalised {markers} inline-mathematics placeholders; the symbols themselves are "
            f"not in the PDF text layer",
            stage="clean",
            level=DiagnosticLevel.WARNING,
        )
    return doc


def math_placeholder_count(text: str) -> int:
    return text.count(MATH_PLACEHOLDER)


#: A TeX maths font whose glyphs were mapped to the wrong code points on the way out of the PDF.
#: Elsevier articles typeset with it emit Icelandic letters where the operators should be:
#: ``Li/Liþ`` is the lithium ion, ``ðR3mÞ`` is the space group ``(R3m)``, and one paper's
#: diffusion equation reads ``Dc Dr þ two omega 2E nine RTð1 nu Þ``. Three of twelve corpus
#: papers carried it, 104 characters between them, and every one of them reached the audio.
MATH_FONT = {
    "\u00fe": "+",  # thorn, for the superscript plus of an ion
    "\u00f0": "(",  # eth
    "\u00de": ")",  # capital thorn
    "\u00d0": "(",  # capital eth
}

#: Evidence that this is a broken font rather than Icelandic. In Icelandic, thorn begins a word
#: and is followed by a vowel; here it *ends* a token, hard against a digit or a capital --
#: ``Ni3þ``, ``Liþ``. Gated like the superscript-citation rule, and for the same reason: a
#: repair that fires on one ambiguous character is worse than one that waits for a pattern.
MATH_FONT_EVIDENCE = re.compile(r"[A-Za-z0-9][\u00fe\u00de]|\u00f0[A-Za-z0-9]")

#: Below this many matches, leave the text alone. One thorn in a document is a name.
MIN_MATH_FONT_EVIDENCE = 3


def uses_broken_math_font(doc: Document) -> bool:
    """Does this document map its maths operators onto Icelandic letters?"""
    text = "\n".join(block.text for block in doc.blocks)
    return len(MATH_FONT_EVIDENCE.findall(text)) >= MIN_MATH_FONT_EVIDENCE


def repair_math_font(doc: Document) -> int:
    """Put the operators back, when the document shows it needs it.

    Whole-document rather than per-block, because the evidence is a property of the typesetting
    and a single block may hold one ambiguous character.
    """
    if not uses_broken_math_font(doc):
        return 0
    repaired = 0
    for block in doc.blocks:
        if not block.text:
            continue
        text = block.text
        for wrong, right in MATH_FONT.items():
            text = text.replace(wrong, right)
        if text != block.text:
            repaired += sum(block.text.count(w) for w in MATH_FONT)
            block.text = text
    if repaired:
        doc.note(
            "math_font",
            f"repaired {repaired} operators mapped onto Icelandic letters by a broken maths font",
            stage="clean",
            level=DiagnosticLevel.INFO,
        )
    return repaired
