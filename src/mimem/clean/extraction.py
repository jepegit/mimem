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
