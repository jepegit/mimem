"""Remove or rewrite citations, identifiers and cross-references (rules CIT-*, NUM-05).

Inline citations are the clearest case of extraneous processing in a scientific paper. A
parenthetical with two references is around four seconds of pure noise, several times per
paragraph, and a listener cannot act on any of it. Under the coherence principle the default is
to delete them outright; attribution survives only when the identity of the source is part of
the argument, and then in a form a person would say out loud.

Identifiers -- DOIs, arXiv IDs, URLs, ISBNs -- are never spoken under any setting.
"""

from __future__ import annotations

import re

from mimem.config import CitationVerbosity

#: Bracketed numeric citations: [1], [1,2], [1-3], [1, 2-4].
NUMERIC_CITATION = re.compile(r"\[\s*\d+(?:\s*[-–,;]\s*\d+)*\s*\]")

#: Author-year citations, with or without a leading signal phrase.
AUTHOR_YEAR_CITATION = re.compile(
    r"\(\s*(?:(?:e\.g\.|see|cf\.|i\.e\.)[,.]?\s*)?"
    r"[A-ZÅÄÖØÆ][\w'’-]+(?:\s+(?:et\s+al\.?|and|&|,)\s*[A-ZÅÄÖØÆ]?[\w'’-]*)*"
    r"[,.]?\s*(?:19|20)\d{2}[a-z]?"
    r"(?:\s*[;,]\s*[^()]{0,80}?(?:19|20)\d{2}[a-z]?)*\s*\)"
)

#: A year in parentheses left over after an author name was spoken: "Peled (1979)".
TRAILING_YEAR = re.compile(r"\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)")

DOI = re.compile(r"\b(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/[-._;()/:\w]+", re.I)
ARXIV = re.compile(r"\barxiv\s*:?\s*\d{4}\.\d{4,5}(?:v\d+)?\b", re.I)
URL = re.compile(r"\b(?:https?://|www\.)\S+")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
ISBN = re.compile(r"\bISBN[- ]?(?:13|10)?:?\s*[\d-]{10,17}\b", re.I)

#: "as shown in Figure 4b", "see Table 2", "Eq. (3)" -- meaningless without the page in front
#: of you (rule STR-08). Rewritten rather than deleted, so the sentence still stands up.
CROSS_REFERENCE = re.compile(
    r"\b(?:as\s+)?(?:shown|seen|illustrated|summari[sz]ed|listed|given|presented|reported)?\s*"
    r"\b(?:in|by)?\s*"
    r"\(?\b(?:Fig(?:ure|s?)?|Table|Scheme|Eq(?:uation|s?)?|Sect(?:ion)?|Ref(?:s?|erence)?)\.?\s*"
    r"(?:S)?\d+[a-z]?(?:\s*[-–,]\s*(?:S)?\d+[a-z]?)*\)?",
    re.IGNORECASE,
)

_ET_AL = re.compile(r"\bet\s+al\.?", re.IGNORECASE)


def _attribute(match: re.Match[str]) -> str:
    """Rewrite an author-year citation as something a person would say."""
    inner = match.group(0).strip("()").strip()
    year = re.search(r"(19|20)\d{2}", inner)
    names = inner[: year.start()] if year else inner
    names = re.sub(r"[,;]\s*$", "", names).strip(" ,.;")
    names = _ET_AL.sub("and colleagues", names)
    if not names:
        return ""
    return f" ({names})" if not year else f" (a {year.group(0)} study by {names})"


#: Superscript reference markers, which arrive from the PDF as ordinary digits welded to the
#: end of a word or a sentence: "cold-start conditions4." and "sold vehicles.1 Tesla".
#:
#: Three guards keep this from eating real numbers:
#:
#: * the digits must be followed by whitespace or punctuation, so "H2O" is untouched;
#: * the letter in front must be **lower case**, because a designation ends in a capital --
#:   "NMC811" and "LiFePO4" survive, "conditions4" does not;
#: * the word in front is checked against the unit lexicon, so the exponent in "cm2" survives.
_SUPERSCRIPT_AFTER_WORD = re.compile(r"(?<=[a-z])(\d{1,3}(?:[,–-]\d{1,3})*)(?=[\s.,;:)]|$)")
_SUPERSCRIPT_AFTER_STOP = re.compile(r"(?<=[.!?])(\d{1,3}(?:[,–-]\d{1,3})*)(?=\s+[A-Z(]|$)")

#: Below this many markers, the pattern is more likely to be data than a citation style.
MIN_SUPERSCRIPT_EVIDENCE = 10

_WORD_BEFORE = re.compile(r"([A-Za-z]+)$")


def count_superscript_citations(text: str) -> int:
    """How many superscript reference markers this text appears to contain."""
    return len(_SUPERSCRIPT_AFTER_STOP.findall(text)) + sum(
        1 for m in _SUPERSCRIPT_AFTER_WORD.finditer(text) if not _preceded_by_unit(text, m.start())
    )


def _preceded_by_unit(text: str, index: int) -> bool:
    from mimem.verbalize.units import is_unit

    word = _WORD_BEFORE.search(text[:index])
    return bool(word and is_unit(word.group(1)))


def strip_superscript_citations(text: str) -> str:
    """Remove superscript reference markers (rule CIT-01).

    Applied only when the document as a whole shows the style -- see
    :data:`MIN_SUPERSCRIPT_EVIDENCE`. A single stray digit after a word is far more likely to be
    a typo or a variable than a citation, and deleting it would be silent corruption.
    """
    text = _SUPERSCRIPT_AFTER_STOP.sub("", text)
    return _SUPERSCRIPT_AFTER_WORD.sub(
        lambda m: "" if not _preceded_by_unit(text, m.start()) else m.group(0), text
    )


def strip_identifiers(text: str) -> str:
    """Remove things that must never be spoken (rule NUM-05)."""
    for pattern in (URL, DOI, ARXIV, ISBN, EMAIL):
        text = pattern.sub("", text)
    return text


def verbalize_citations(
    text: str,
    *,
    verbosity: CitationVerbosity = CitationVerbosity.SUPPRESS,
    drop_cross_references: bool = True,
    strip_superscripts: bool = False,
) -> str:
    """Apply the citation policy to a piece of text."""
    text = strip_identifiers(text)
    if strip_superscripts:
        text = strip_superscript_citations(text)

    if verbosity is CitationVerbosity.ATTRIBUTED:
        text = AUTHOR_YEAR_CITATION.sub(_attribute, text)
        text = TRAILING_YEAR.sub(lambda m: f" in {m.group(0).strip(' ()')}", text)
    else:
        text = AUTHOR_YEAR_CITATION.sub("", text)
        text = TRAILING_YEAR.sub("", text)

    text = NUMERIC_CITATION.sub("", text)
    if drop_cross_references:
        text = CROSS_REFERENCE.sub("", text)

    # Tidy the punctuation the removals left behind: " ." and doubled spaces and "( )".
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
