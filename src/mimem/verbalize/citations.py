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
#:
#: The number is dotted because section numbers are: "Section 2.1.4" used to match only its
#: "Section 2", leaving the sentence to say "corresponding to.1.4" out loud. A partial match is
#: worse than no match at all here -- an untouched cross-reference is merely useless, and a
#: half-eaten one is a number the listener will try to make sense of. ``\.\d`` requires a digit
#: after the dot, so a reference ending a sentence ("in Figure 4. The next result...") still
#: stops at the 4.
CROSS_REFERENCE = re.compile(
    r"\b(?:as\s+)?(?:shown|seen|illustrated|summari[sz]ed|listed|given|presented|reported)?\s*"
    r"\b(?:in|by)?\s*"
    r"\(?\b(?:Fig(?:ure|s?)?|Tables?|Schemes?|Eq(?:uation|s?)?|Sect(?:ion)?s?|Ref(?:s?|erence)?)\.?\s*"
    r"(?:S)?\d+(?:\.\d+)*[a-z]?(?:\s*(?:[-–,]|and)\s*(?:S)?\d+(?:\.\d+)*[a-z]?)*\)?",
    re.IGNORECASE,
)

#: "as shown in the figure", "see the table above" -- the same instruction as a numbered
#: cross-reference and just as unfollowable, but with no number for the pattern above to anchor
#: on. STR-08 catches these in the finished audio; this is what stops them getting there.
BARE_CROSS_REFERENCE = re.compile(
    r",?\s*\b(?:as\s+)?(?:shown|seen|illustrated|summari[sz]ed|listed|given|presented|depicted)"
    r"\s+(?:in|by)\s+the\s+(?:figure|table|plot|graph|chart|scheme|diagram|panel|equation)s?"
    r"(?:\s+(?:above|below|opposite))?",
    re.IGNORECASE,
)

#: A figure that is the *subject* of its sentence: "Figure 6 exemplifies how...", "Table 2 lists".
#:
#: Rule ``FIG-04`` says a reference is rewritten so that no figure number is spoken -- and this
#: is the shape that has to be rewritten rather than removed. Deleting it takes the subject out
#: of the sentence and leaves a verb-initial fragment, which is not a hypothetical: "exemplifies
#: how transfer learning combined with Shapley additive explanations analysis..." was in the
#: audio track of a real paper, spoken exactly like that.
#:
#: Only at a sentence boundary, and only when a verb follows. Mid-sentence the reference is an
#: aside and :data:`CROSS_REFERENCE` is right to delete it.
SUBJECT_REFERENCE = re.compile(
    r"(?:(?<=^)|(?<=[.!?]\s)|(?<=[.!?]\s\s))"
    r"(?P<label>Fig(?:ure|s)?|Figures|Tables?|Schemes?|Sect(?:ion)?s?)\.?\s*"
    r"(?P<number>\d+(?:\.\d+)*[a-z]?(?:\s*[-–]\s*\d+(?:\.\d+)*[a-z]?)?)\s+"
    r"(?=[a-z])",
    re.IGNORECASE,
)

_ET_AL = re.compile(r"\bet\s+al\.?", re.IGNORECASE)


def _recapitalise(text: str, original: str) -> str:
    """Restore a capital that a removal took away, and only then.

    "In Figure 3, capacity falls" becomes "Capacity falls", because an engine reads a lower-case
    opening as a continuation of whatever came before it. But this module is also called on
    *fragments* -- a clause lifted out of a sentence, which was lower-case to begin with and
    should stay that way. So the test is not "does it start lower-case", it is "did it start
    upper-case and stop".
    """
    if not text or not original:
        return text
    if original[:1].isupper() and text[:1].islower():
        text = text[0].upper() + text[1:]
    return re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def _as_subject(match: re.Match[str]) -> str:
    """ "Figure 6 exemplifies" -> "The figure exemplifies"; the plural stays plural.

    A *section* gets a different noun. "The section" would point at something the listener cannot
    navigate to, which is what ``STR-08`` exists to prevent, and the paper's own numbering does
    not match the parts mimem counts out loud. "Another part of the paper" claims no direction,
    which matters because the reference may point forwards or back and this cannot tell which.
    """
    label = match.group("label").lower().rstrip(".")
    if label.startswith("sect"):
        return "Another part of the paper "
    plural = match.group("number").count("-") or (label.endswith("s") and label != "figures")
    noun = (
        "table"
        if label.startswith("table")
        else "scheme"
        if label.startswith("scheme")
        else "figure"
    )
    return f"The {noun}s " if plural else f"The {noun} "


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
    """Apply the citation policy to a piece of text.

    The order inside here matters. Parenthetical citations go first, because they contain
    "et al." themselves; the bare in-prose "et al." is expanded next; and only then are
    superscript markers stripped. That sequence is what catches "Heimes et al.24", where the
    marker sits after a full stop and so needs the expansion to "and colleagues" to have
    happened before the lower-case-letter guard can see it.
    """
    original = text
    text = strip_identifiers(text)

    if verbosity is CitationVerbosity.ATTRIBUTED:
        text = AUTHOR_YEAR_CITATION.sub(_attribute, text)
        text = TRAILING_YEAR.sub(lambda m: f" in {m.group(0).strip(' ()')}", text)
    else:
        text = AUTHOR_YEAR_CITATION.sub("", text)
        text = TRAILING_YEAR.sub("", text)

    # "Gorsch et al. compare ..." is a citation fragment in running prose, and CIT-01 forbids
    # it in the audio track whatever the verbosity setting.
    text = _ET_AL.sub("and colleagues", text)

    if strip_superscripts:
        text = strip_superscript_citations(text)

    text = NUMERIC_CITATION.sub("", text)
    if drop_cross_references:
        # Rewrite before deleting. A subject-position reference matches CROSS_REFERENCE too, and
        # whichever runs first decides whether the sentence keeps a subject.
        text = SUBJECT_REFERENCE.sub(_as_subject, text)
        text = CROSS_REFERENCE.sub("", text)
        text = BARE_CROSS_REFERENCE.sub("", text)

    # Tidy the punctuation the removals left behind: " ." and doubled spaces and "( )".
    text = re.sub(r"\(\s*\)", "", text)
    # And the preposition, which is the part a reader would notice. Deleting "Section 2.1.4"
    # from "corresponding to Section 2.1.4, where..." leaves "corresponding to, where..." --
    # grammatical debris that a speech engine reads out with a straight face. The preposition
    # only ever belonged to the reference, so it goes with it.
    text = re.sub(
        r"\s+\b(?:in|to|by|at|of|from|see|per)\b\s*(?=[.,;:)])", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    # A removal at the start of a sentence leaves the comma that separated it from the rest.
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r"([.!?])\s*,\s*", r"\1 ", text)
    text = _recapitalise(text, original)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
