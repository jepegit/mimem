"""Symbols, Greek letters and written-only abbreviations (rules SYM-*, SENT-04, TTS-01).

Everything here exists because it works on the page and fails in the ear. "≈" is instant to a
reader and silent to a listener; "e.g." is read aloud by some engines as "ee gee"; "§3" is
anyone's guess. The rule is simple: if it is not a letter, it either becomes words or it goes.

The listener's own lexicon (rule SYM-03) is applied first, so a domain term always wins over
these defaults.
"""

from __future__ import annotations

import re
import unicodedata

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta",
    "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu",
    "µ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma",
    "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Α": "alpha", "Β": "beta", "Γ": "gamma", "Δ": "delta", "Θ": "theta", "Λ": "lambda",
    "Ξ": "xi", "Π": "pi", "Σ": "sigma", "Φ": "phi", "Ψ": "psi", "Ω": "omega",
    # A typesetter reaching for "delta Q" may pick the Greek letter (U+0394) or the
    # mathematical increment (U+2206), and the two are indistinguishable on the page. NFKC
    # normalization (below) folds most such look-alikes -- the ohm sign onto omega, the
    # micro sign onto mu -- but not this pair, so it is listed. A 98-page review used it
    # exactly once, which was enough to fail TTS-01 and, on a Windows console, to crash the
    # report that was trying to say so.
    "∆": "delta",  # U+2206 INCREMENT
}  # fmt: skip

OPERATORS = {
    "≈": " approximately ", "∼": " approximately ", "~": " approximately ",
    "≤": " less than or equal to ", "≥": " greater than or equal to ",
    "<": " less than ", ">": " greater than ", "=": " equals ",
    "≠": " not equal to ", "±": " plus or minus ", "∓": " minus or plus ",
    "×": " times ", "·": " times ", "∙": " times ", "÷": " divided by ",
    "→": " leads to ", "←": " comes from ", "↔": " is in equilibrium with ",
    "⇒": " implies ", "∞": " infinity ", "∝": " is proportional to ",
    "∑": " the sum of ", "∫": " the integral of ", "∂": " partial ", "∇": " del ",
    "√": " the square root of ", "°": " degrees ", "%": " percent ",
    "+": " plus ", "&": " and ", "@": " at ",
    "−": " minus ", "‰": " per mille ", "′": " prime ", "″": " double prime ",
    # U+2044, which a typesetter uses for a real fraction: one-quarter written that way
    # is "one over four", and a corpus of twelve papers had ten of them.
    "⁄": " over ",
}  # fmt: skip

#: Characters that carry no spoken content at all -- page furniture, footnote markers, marks
#: that only exist to be looked at.
#: Unbalanced brackets and quotes belong here rather than in the parenthetical handler: by the
#: time this runs every *matched* pair has been rewritten, so what is left is an opening bracket
#: whose partner was lost to a column break. Stray diacritics are extraction damage -- "Bo¨ rner"
#: for "Börner" -- degraded either way, but at least speakable.
#:
#: The second row is what a twelve-paper corpus added: the black square that prefixes every
#: heading in an ACS PDF, the asterisk-operator, parallel-to and up-tack characters used as
#: affiliation and footnote markers against an author's name, and the up and down arrows that
#: mark gas and precipitate in a chemical equation -- which the equation handler has already
#: reduced to prose by the time they are seen. None of them is ever said, and together they
#: were 64 of 140 ``TTS-01`` failures across the corpus.
DROP_CHARS = '§¶†‡•▪◦※★☆©®™|¦^_`{}[]()<>\\/*#$€£¥"¨˜´■□▲▼◆●∗∥‖⊥↑↓'

#: Subscripted and superscripted symbols, written the way a source that kept its markup writes
#: them: ``f_0``, ``C_rate``, ``x^2``. Dropping the marker leaves the index stranded as a bare
#: token -- "f 0" -- which reads as a digit to the number rules and reached the audio track of a
#: Markdown source as exactly that. Rewritten before the numbers run, so that the index is
#: verbalized like any other number and a listener hears "f sub zero".
SUB_SUPER_RE = re.compile(r"\b([A-Za-z][A-Za-z]{0,3})([_^])\{?([A-Za-z0-9]{1,6})\}?")

#: Written-only abbreviations. Expanded rather than dropped, because they do carry meaning.
ABBREVIATIONS = {
    r"\be\.\s?g\.(?=\s|,|$)": "for example",
    r"\bi\.\s?e\.(?=\s|,|$)": "that is",
    r"\bcf\.(?=\s|,|$)": "compare",
    r"\bvs\.?(?=\s|,|$)": "versus",
    r"\betc\.(?=\s|,|$)": "and so on",
    r"\bapprox\.(?=\s|,|$)": "approximately",
    r"\bca\.(?=\s\d)": "about",
    r"\bFig(?:s)?\.(?=\s)": "Figure",
    r"\bEq(?:s)?\.(?=\s)": "Equation",
    r"\bRef(?:s)?\.(?=\s)": "Reference",
    r"\bTab\.(?=\s)": "Table",
    r"\bNo\.(?=\s*\d)": "number",
    r"\bwrt\b": "with respect to",
    r"\bw\.r\.t\.": "with respect to",
    r"\band/or\b": "or",
    # "et al." is handled in `mimem.verbalize.citations`, not here. It has to run *before*
    # superscript-marker stripping so that "Heimes et al.24" becomes "Heimes and colleagues24"
    # in time for the lower-case-letter guard to recognise the marker.
}

#: A surviving math placeholder (see mimem.clean.extraction). The symbol is not recoverable,
#: so it is named rather than invented: "a quantity" is true, "x" would be a guess.
_MATH_PLACEHOLDER = re.compile(r"inline-eq(?:-th)?")

_WHITESPACE = re.compile(r"\s{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
_REPEATED_PUNCT = re.compile(r"([.,;:])\1+")


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    """Replace domain terms with their spoken forms (rule SYM-03).

    Longest first, so "NMC811" is matched before "NMC".
    """
    for term in sorted(lexicon, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", lexicon[term], text)
    return text


#: A combining mark that a PDF extractor has put *before* the letter it belongs to, usually
#: with a space in between. Every diacritic in a twelve-paper corpus arrived this way.
_ORPHAN_MARK = re.compile(r"(\s)([̀-ͯ])(\S)")

#: Marks that survive the repair below because their base was not a letter at all -- a macron
#: over a crystallographic index, say, whose digit the number verbalizer has already turned into
#: a word. Nothing can compose those, and a bare accent is unspeakable (rule TTS-01).
_COMBINING = re.compile(r"[̀-ͯ]")


def repair_diacritics(text: str) -> str:
    """Put a stray accent back on the letter it came off, then drop what cannot be repaired.

    PDF text extraction routinely emits a diacritic *ahead* of its base letter and separated by
    a space: ``Hj ̈orvarsson`` for Hjörvarsson, ``nine point nine zero ̊A`` for 9.90 Å, ``R ̄three
    c`` for the space group R3̄c. Across twelve papers this was 76 of 140 unspeakable characters
    -- the largest single cause of ``TTS-01`` failures, and in every case the mark was one
    position early.

    Swapping the mark with the character after it and recomposing recovers the real word:
    ``Å`` becomes an angstrom the unit lexicon can say, and a Scandinavian surname stops being
    two words. What still cannot compose -- a macron whose base was a digit that has since
    become a word -- is stripped, because an unattached accent has no sound.
    """
    repaired = _ORPHAN_MARK.sub(lambda m: f"{m.group(1)}{m.group(3)}{m.group(2)}", text)
    return _COMBINING.sub("", unicodedata.normalize("NFC", repaired))


def normalize(text: str) -> str:
    """Fold compatibility look-alikes onto the code points the rest of the pipeline expects.

    The ohm sign onto omega, the micro sign onto mu, ligatures onto their letters -- and, the
    reason this runs *first* rather than in the symbol pass where it started: subscript and
    superscript digits onto ordinary ones. "CO₂" is a chemical formula written with U+2082,
    which no ``\\d`` matches, so the number verbalizer walks past it. Normalizing after that
    point turned the subscript into a plain "2" too late for anything to say it, and put a raw
    digit in the audio track -- a defect the linter caught within one build of the change that
    caused it.

    Idempotent, so calling it again inside a later stage costs nothing.
    """
    return repair_diacritics(unicodedata.normalize("NFKC", text))


def verbalize_indices(text: str) -> str:
    """Rule SYM-01: say a subscript, do not drop its marker and strand the index."""
    return SUB_SUPER_RE.sub(
        lambda m: f"{m.group(1)} {'sub' if m.group(2) == '_' else 'to the power'} {m.group(3)}",
        text,
    )


def verbalize_symbols(text: str, *, lexicon: dict[str, str] | None = None) -> str:
    """Turn every non-letter that carries meaning into words, and drop the rest."""
    if lexicon:
        text = apply_lexicon(text, lexicon)

    text = normalize(text)
    text = _MATH_PLACEHOLDER.sub("a quantity", text)

    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    for symbol, word in GREEK.items():
        text = text.replace(symbol, f" {word} ")
    for symbol, word in OPERATORS.items():
        text = text.replace(symbol, word)

    text = text.translate({ord(c): " " for c in DROP_CHARS})

    # Dashes: an em dash is a spoken pause, a hyphen inside a word is not.
    text = re.sub(r"\s*[–—]\s*", " — ", text)
    text = re.sub(r"(?<=\s)-(?=\s)", " — ", text)

    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()
