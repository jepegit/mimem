"""Spoken forms for units of measurement (rule NUM-03).

"mAh/g" read as letters is three syllables of noise; read as "milliamp hours per gram" it is
the quantity the sentence is about. Units are always expanded and always attached to their
number, because a value without its unit is not a fact.

The approach is a small curated lexicon plus a prefix-and-base parser for everything else. A
lexicon entry wins over the parser, because conventional spoken forms are not derivable: an
electrochemist says "milliamp hours per gram", not "milli ampere hours per gram".

This is deliberately not built on a units library. ``pint`` and friends model dimensional
algebra, which we do not need, and none of them know how a unit is *said*, which is the only
thing we do need.
"""

from __future__ import annotations

import re

#: SI prefixes, spoken.
PREFIXES: dict[str, str] = {
    "Y": "yotta",
    "Z": "zetta",
    "E": "exa",
    "P": "peta",
    "T": "tera",
    "G": "giga",
    "M": "mega",
    "k": "kilo",
    "h": "hecto",
    "da": "deca",
    "d": "deci",
    "c": "centi",
    "m": "milli",
    "µ": "micro",
    "μ": "micro",
    "u": "micro",
    "n": "nano",
    "p": "pico",
    "f": "femto",
    "a": "atto",
    "z": "zepto",
    "y": "yocto",
}

#: Base units: symbol -> (singular, plural). A plural equal to the singular means the unit does
#: not inflect in speech ("hertz", "siemens").
BASE_UNITS: dict[str, tuple[str, str]] = {
    "m": ("metre", "metres"),
    "g": ("gram", "grams"),
    "s": ("second", "seconds"),
    "A": ("amp", "amps"),
    "K": ("kelvin", "kelvin"),
    "mol": ("mole", "moles"),
    "cd": ("candela", "candelas"),
    "Hz": ("hertz", "hertz"),
    "N": ("newton", "newtons"),
    "Pa": ("pascal", "pascals"),
    "J": ("joule", "joules"),
    "W": ("watt", "watts"),
    "C": ("coulomb", "coulombs"),
    "V": ("volt", "volts"),
    "F": ("farad", "farads"),
    "Ω": ("ohm", "ohms"),
    "S": ("siemens", "siemens"),
    "T": ("tesla", "tesla"),
    "H": ("henry", "henries"),
    "L": ("litre", "litres"),
    "l": ("litre", "litres"),
    "eV": ("electron volt", "electron volts"),
    "bar": ("bar", "bar"),
    "min": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "Ah": ("amp hour", "amp hours"),
    "Wh": ("watt hour", "watt hours"),
    "B": ("byte", "bytes"),
    "Da": ("dalton", "daltons"),
    "b": ("bar", "bar"),
}

#: Whole compounds whose conventional spoken form is not derivable from prefix plus base, plus
#: the domain shorthand a battery paper leans on. Extend via the listener lexicon (rule SYM-03).
COMPOUND_UNITS: dict[str, tuple[str, str]] = {
    "mAh": ("milliamp hour", "milliamp hours"),
    "Ah": ("amp hour", "amp hours"),
    "kWh": ("kilowatt hour", "kilowatt hours"),
    "MWh": ("megawatt hour", "megawatt hours"),
    "Wh": ("watt hour", "watt hours"),
    "°C": ("degree Celsius", "degrees Celsius"),
    "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "K": ("kelvin", "kelvin"),
    "rpm": ("revolution per minute", "revolutions per minute"),
    "ppm": ("part per million", "parts per million"),
    "ppb": ("part per billion", "parts per billion"),
    "wt%": ("weight percent", "weight percent"),
    "at%": ("atomic percent", "atomic percent"),
    "vol%": ("volume percent", "volume percent"),
    "N": ("newton", "newtons"),
    "ohm": ("ohm", "ohms"),
    "Ohm": ("ohm", "ohms"),
    # "C" and "M" are deliberately absent. A bare C is a C-rate to an electrochemist, coulombs
    # to a physicist and Celsius to everyone else; M is molar or mega. Left alone, a lone
    # capital is simply read as the letter, which is what the author wrote and what a reader of
    # the field will understand. Add the reading you want via the listener lexicon (SYM-03).
    "Å": ("angstrom", "angstroms"),
    "°": ("degree", "degrees"),
    "%": ("percent", "percent"),
}

#: Beyond this, trailing digits name a product rather than raise a unit to a power.
MAX_UNIT_EXPONENT = 4

#: Exponents that have a spoken name rather than a number.
_EXPONENT_WORDS = {2: "square", 3: "cubic"}

#: Units that are ever squared or cubed in prose, and so may take a *positive* exponent welded
#: on with no separator. Without this list "H2" reads as "square henries" -- and in a paper
#: about batteries venting hydrogen it appears constantly, giving "the square henries
#: concentration". Area and volume are the only readings a bare trailing 2 or 3 plausibly has,
#: so the units that have an area or a volume are the units that may claim one. Negative
#: exponents are not restricted: "s-1" is per second whatever the unit, and nothing else is
#: spelled that way.
_DIMENSIONAL = frozenset({"m", "cm", "mm", "km", "nm", "µm", "μm", "um", "Å", "in", "ft", "yd"})

_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")

#: A unit token as it appears after a number: letters, degree signs, slashes, exponents.
#: An exponent must be *adjacent* to its unit ("cm2", "cm^-1"), never separated by a space.
#: Allowing a space lets the pattern reach across into the next number: "100 to 200 nm" would
#: match "to 200" as a unit-with-exponent and swallow the 200.
UNIT_TOKEN = re.compile(
    r"(?:°[CFK]?|[A-Za-zΩµμÅ][A-Za-zΩµμÅ°]*|%)"
    r"(?:[⁻\-^]?[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]+)?"
    r"(?:\s*(?:/|·|\*)\s*(?:[A-Za-zΩµμÅ][A-Za-zΩµμÅ°]*|%)"
    r"(?:[⁻\-^]?[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]+)?)*"
)


def _split_exponent(symbol: str) -> tuple[str, int]:
    """``cm2`` -> ``("cm", 2)``; ``cm-1`` -> ``("cm", -1)``; ``cm`` -> ``("cm", 1)``."""
    symbol = symbol.translate(_SUPERSCRIPTS).replace("^", "").strip()
    m = re.match(r"^(.*?)(-?\d+)$", symbol)
    if not m or not m.group(1):
        return symbol, 1
    stem, exponent = m.group(1), int(m.group(2))
    # Real unit exponents are small. "V10" is a product name, not volts to the tenth power,
    # and treating it as a unit leaves its digits in the audio track.
    if abs(exponent) > MAX_UNIT_EXPONENT:
        return symbol, 1
    # A trailing digit is only an exponent if the stem is a unit we recognise; otherwise it is
    # part of a name ("NMC811", "H2O") and must not be pulled apart.
    if _lookup(stem) is None:
        return symbol, 1
    # ...and, for a positive exponent, only if the unit is one that has an area or a volume.
    # "H2" is hydrogen far more often than it is square henries.
    if exponent > 1 and stem not in _DIMENSIONAL:
        return symbol, 1
    return stem, exponent


def _lookup(symbol: str) -> tuple[str, str] | None:
    """Resolve a bare unit symbol to (singular, plural), or None if it is not a unit."""
    if symbol in COMPOUND_UNITS:
        return COMPOUND_UNITS[symbol]
    if symbol in BASE_UNITS:
        return BASE_UNITS[symbol]
    # Prefix + base: try the two-character prefix "da" first, then single characters.
    for size in (2, 1):
        if len(symbol) > size:
            prefix, base = symbol[:size], symbol[size:]
            if prefix in PREFIXES:
                if base in COMPOUND_UNITS:
                    singular, plural = COMPOUND_UNITS[base]
                    if base in {"Ah", "Wh"}:  # "mAh" is already in COMPOUND_UNITS; others derive
                        return f"{PREFIXES[prefix]}{singular}", f"{PREFIXES[prefix]}{plural}"
                if base in BASE_UNITS:
                    singular, plural = BASE_UNITS[base]
                    return f"{PREFIXES[prefix]}{singular}", f"{PREFIXES[prefix]}{plural}"
    return None


def _factor_words(symbol: str, plural: bool) -> str | None:
    stem, exponent = _split_exponent(symbol)
    entry = _lookup(stem)
    if entry is None:
        return None
    word = entry[1] if plural else entry[0]
    if exponent == 1:
        return word
    if exponent in _EXPONENT_WORDS:
        return f"{_EXPONENT_WORDS[exponent]} {word}"
    if exponent < 0:
        inverse = _factor_words(f"{stem}{-exponent}" if -exponent > 1 else stem, plural=False)
        return f"per {inverse}" if inverse else None
    return f"{word} to the power {exponent}"


#: Single capitals that are units in a table and variables in a sentence. Bare, they are left
#: as the letter; inside a compound they resolve normally, so "µS/cm" is still
#: "microsiemens per centimetre" while "0.5 C" stays "zero point five C" -- which is what an
#: electrochemist means by it, and certainly not "zero point five coulombs".
AMBIGUOUS_BARE = frozenset({"C", "T", "S", "F", "H", "M", "B"})


def spoken_unit(symbol: str, *, plural: bool = True) -> str | None:
    """Spoken form of a unit expression, or ``None`` if this is not a unit.

    Returning ``None`` matters as much as returning a string: it is how the number verbalizer
    knows that the word after a number is ordinary prose ("5 cells") and not a unit.
    """
    symbol = symbol.strip()
    if not symbol or symbol in AMBIGUOUS_BARE:
        return None
    if symbol in COMPOUND_UNITS:
        entry = COMPOUND_UNITS[symbol]
        return entry[1] if plural else entry[0]

    parts = re.split(r"\s*/\s*", symbol)
    if len(parts) > 2:
        return None  # "a/b/c" is ambiguous when spoken; leave it alone
    numerator, denominator = parts[0], parts[1] if len(parts) == 2 else None

    numerator_words: list[str] = []
    for i, factor in enumerate(re.split(r"\s*[·*]\s*", numerator)):
        words = _factor_words(factor, plural=plural and i == 0)
        if words is None:
            return None
        numerator_words.append(words)
    spoken = " ".join(numerator_words)

    if denominator is not None:
        denom_words = _factor_words(denominator, plural=False)
        if denom_words is None:
            return None
        spoken = f"{spoken} per {denom_words}"
    return spoken


def is_unit(symbol: str) -> bool:
    return spoken_unit(symbol) is not None
