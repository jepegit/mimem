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
#: The leading bracket and the ``see`` are one shape: "(see Figure 1a)". Without them the
#: pattern started at "Figure" and left "(see " behind, which the punctuation tidy-up below then
#: reduced to a sentence ending in the word "see" -- "the interlayer distance see." -- in every
#: paper that uses the parenthetical aside, which is most of them.
#: How a table is numbered. Arabic, optionally with a supplementary "S", a decimal part and a
#: panel letter -- or **Roman**, which is how most journals number their tables: "see Table I",
#: "confirm this trend (see Table II)". Five of one paper's eight ``STR-08`` errors were the
#: Roman half, read out as an instruction the listener cannot follow.
#:
#: A bare Roman numeral is never matched: the label has to come first, so the "I" in "I show"
#: is never a table.
_REFERENCE_NUMBER = r"S?\d+(?:\.\d+)*[a-z]?|[IVXLC]{1,6}\b"


CROSS_REFERENCE = re.compile(
    r"\(?\s*\b(?:as\s+)?"
    r"(?:see|shown|seen|illustrated|summari[sz]ed|listed|given|presented|reported)?\s*"
    r"\b(?:in|by)?\s*"
    r"\(?\b(?:Fig(?:ure|s?)?|Tables?|Schemes?|Eq(?:uation|s?)?|Sect(?:ion)?s?|Ref(?:s?|erence)?)\.?\s*"
    r"(?:" + _REFERENCE_NUMBER + r")"
    r"(?:\s*(?:[-–,]|and)\s*(?:" + _REFERENCE_NUMBER + r"))*\)?",
    re.IGNORECASE,
)

#: "as shown in the figure", "see the table above" -- the same instruction as a numbered
#: cross-reference and just as unfollowable, but with no number for the pattern above to anchor
#: on. STR-08 catches these in the finished audio; this is what stops them getting there.
BARE_CROSS_REFERENCE = re.compile(
    r",?\s*(?:"
    r"\b(?:as\s+)?(?:shown|seen|illustrated|summari[sz]ed|listed|given|presented|depicted)"
    r"\s+(?:in|by)\s+the\s+(?:figure|table|plot|graph|chart|scheme|diagram|panel|equation)s?"
    r"(?:\s+(?:above|below|opposite))?"
    # "see Figure" with nothing after it. Left behind by an earlier pass -- a number that was
    # a page label, or a reference the column break took away -- and, in one paper, promoted
    # into a *concept*: "What did they report for see Figure?"
    r"|\(?\s*\bsee\s+(?:the\s+)?"
    r"(?:Fig(?:ure|s)?|Tables?|Schemes?|Eq(?:uation|s)?|Sect(?:ion)?s?)\b\.?\s*\)?"
    r")",
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
#: A run of citation numbers. The separator may be a comma, a dash, **or a space**: superscript
#: digits carry no punctuation of their own, so whether the comma survives extraction is a
#: property of the PDF and not of the citation. Across twelve papers "materials.4 8",
#: "graphite.9 11" and "materials.19,21 23" all appeared, and only the third was being stripped
#: -- the other two left a bare digit in the audio track, which is 68 of 154 ``NUM-02`` failures.
_RUN = r"\d{1,3}(?:\s*[,–-]\s*\d{1,3}|\s+\d{1,3})*"

#: The lookbehind admits ``Å`` and ``Ω`` beside the lower-case letters. They are unit symbols,
#: they are the only capitals that are, and a marker welded to one -- "an expansion to ca. 4.15
#: Å44 while the second causes" -- was reaching the audio as a quantity. Every other capital
#: stays out, because a capital before a digit is a designation: ``NMC811``, ``LiFePO4``, ``H2O``.
_SUPERSCRIPT_AFTER_WORD = re.compile(rf"(?<=[a-zÅΩ])({_RUN})(?=[\s.,;:)]|$)")

#: The letter in the lookbehind is what keeps a decimal safe. ``(?<=[.!?])`` alone matches the
#: "5 3" in "0.5 3 times", because the point of a decimal is also a full stop to a regex; a
#: sentence-ending period has a letter in front of it and a decimal point has a digit.
#:
#: **Any** letter, not a lower-case one. Requiring lower case was the first attempt and it
#: silently stopped stripping after an acronym -- "a stable SEI.26,27 Significant" kept its
#: citation, which is a sentence ending in exactly the way a chemistry paper's sentences do.
#: It cost seventeen new failures on one paper and thirteen on another before the corpus run
#: showed it.
#: A marker is never followed by a letter, and that is the whole lookahead. The first version
#: asked for a capital -- ``(?=\s+[A-Z(]|$)`` -- and so missed every marker that ends a clause
#: rather than a sentence: "on the electrodes.52-55." is followed by its full stop, and
#: "electrodes.52-55 in one line" continues in lower case. Both reached the audio.
#:
#: Dropping the lookahead altogether was the next version and it was worse: "LiNi.5Co.2Mn.3O2"
#: is a letter, a stop and a run three times over, and the NMC-532 cathode lost its subscripts
#: in the one paper that is *named* after it. A digit welded to the letter that follows it is a
#: subscript; a marker always has whitespace or punctuation after it.
#:
#: What makes the rest safe is the *lookbehind*: a letter, a stop, and digits **with no space
#: between them** is not a shape prose has. "Fig. 3" and "Ref. 12" have the space and never
#: match; a decimal has a digit before its point and never matches either.
#:
#: The optional bracket, comma or quotation mark is for a marker that follows a parenthetical
#: or a quotation: "(LEDC).31", "carbonates),.17" and a simplified "falling cards model".25 all
#: put something between the last letter and the stop.
_SUPERSCRIPT_AFTER_STOP = re.compile(
    rf"(?:(?<=[A-Za-z][.!?])|(?<=[A-Za-z][)\],\"'”’][.!?]))({_RUN})(?![A-Za-z])"
)

#: Below this many markers, the pattern is more likely to be data than a citation style.
MIN_SUPERSCRIPT_EVIDENCE = 10

_WORD_BEFORE = re.compile(r"([A-Za-zΩµμÅ]+)$")


def count_superscript_citations(text: str) -> int:
    """How many superscript reference markers this text appears to contain."""
    return len(_SUPERSCRIPT_AFTER_STOP.findall(text)) + sum(
        1
        for m in _SUPERSCRIPT_AFTER_WORD.finditer(text)
        if not _is_unit_exponent(text, m) and not _is_formula_subscript(text, m)
    )


def _is_formula_subscript(text: str, match: re.Match[str]) -> bool:
    """Is this run the subscript of a compound, rather than a reference marker?

    ``AlCl3`` and ``conditions4`` are the same shape to the pattern -- digits welded to a
    lower-case letter -- and the second is a citation. The difference is whether the letters
    spell out element symbols.

    Two groups minimum, for the reason :data:`~mimem.verbalize.formulas.MIN_GROUPS` gives: a
    single symbol is a word about an element far more often than it is a compound, and "Li" and
    "Bi" and "In" are also how a paper writes an author's name.
    """
    from mimem.verbalize.formulas import MIN_GROUPS, element_groups

    word = _WORD_BEFORE.search(text[: match.start()])
    return bool(word and element_groups(word.group(1)) >= MIN_GROUPS)


def _is_unit_exponent(text: str, match: re.Match[str]) -> bool:
    """Is this run the exponent of the unit in front of it, rather than a reference marker?

    Two conditions, and the second is what was missing. ``cm2`` is square centimetres, so the
    word in front must be a unit -- but ``Å44`` is angstroms *and a citation*, because a unit
    exponent is a single digit. Nothing is raised to the forty-fourth power in a battery paper.
    """
    from mimem.verbalize.units import MAX_UNIT_EXPONENT, is_unit

    run = match.group(1)
    if not run.isdigit() or len(run) > 1 or int(run) > MAX_UNIT_EXPONENT:
        return False
    word = _WORD_BEFORE.search(text[: match.start()])
    return bool(word and is_unit(word.group(1)))


def strip_superscript_citations(text: str) -> str:
    """Remove superscript reference markers (rule CIT-01).

    Applied only when the document as a whole shows the style -- see
    :data:`MIN_SUPERSCRIPT_EVIDENCE`. A single stray digit after a word is far more likely to be
    a typo or a variable than a citation, and deleting it would be silent corruption.
    """
    text = _SUPERSCRIPT_AFTER_STOP.sub("", text)
    return _SUPERSCRIPT_AFTER_WORD.sub(
        lambda m: (
            m.group(0) if _is_unit_exponent(text, m) or _is_formula_subscript(text, m) else ""
        ),
        text,
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
    # ...and the coordinator, for the same reason and by the same shape. "The results are
    # given in Table III and Figure 4" loses both references and is left as "the results
    # are and."
    text = re.sub(r"\s+\b(?:and|or)\b\s*(?=[.,;:)])", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    # A removal at the start of a sentence leaves the comma that separated it from the rest.
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r"([.!?])\s*,\s*", r"\1 ", text)
    if strip_superscripts:
        # **A second pass, deliberately.** Deleting a cross-reference exposes markers the first
        # pass could not see: "(see Figure 5).54" has a bracket where the sentence's last letter
        # should be, and only becomes "electrodes.54" once the reference is gone and the space
        # it left has been closed up -- which is why this sits after the tidy-up and not beside
        # the deletion that caused it.
        #
        # The earlier pass is not thereby redundant: the lower-case guard in
        # :data:`_SUPERSCRIPT_AFTER_WORD` has to see the text before "et al." becomes "and
        # colleagues", or the marker in "Heimes et al.24" loses the letter in front of it.
        text = strip_superscript_citations(text)

    text = _recapitalise(text, original)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
