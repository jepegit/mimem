"""Chemical formulas, said the way a chemist says them (rules NUM-02, SYM-01).

``Li3.3SnS3.3Cl0.7`` reached the audio track of a real paper as three loose decimals, and rule
``NUM-02`` failed the build three times over one string. It is not the number verbalizer's
fault: it deliberately leaves digits that follow letters alone, because that is what stops
``NMC811`` becoming "N M C eight hundred and eleven" and ``H2O`` becoming a quantity. A formula
needs to be recognised *as a formula* before either rule can do anything sensible with it.

**Element names, not letters.** "L I three point three" is a spelling test; "lithium three point
three" is what someone reading the paper aloud would say. The subscripts go through the ordinary
number verbalizer afterwards, so the profile's numeric fidelity applies to them like anything
else.

**A real element table, and at least two elements.** Matching capitals-and-digits without one
turns ``AI4`` and ``NGB2`` into chemistry. Requiring two element groups is the other half:
``Li`` alone in a sentence is a word about lithium, and rewriting it would be noise. Both
restrictions exist because the loose version of this rewrote things that were not formulas.
"""

from __future__ import annotations

import re

#: Every element symbol, longest first so that ``Cl`` is matched before ``C``.
ELEMENTS: dict[str, str] = {
    "H": "hydrogen", "He": "helium", "Li": "lithium", "Be": "beryllium", "B": "boron",
    "C": "carbon", "N": "nitrogen", "O": "oxygen", "F": "fluorine", "Ne": "neon",
    "Na": "sodium", "Mg": "magnesium", "Al": "aluminium", "Si": "silicon", "P": "phosphorus",
    "S": "sulfur", "Cl": "chlorine", "Ar": "argon", "K": "potassium", "Ca": "calcium",
    "Sc": "scandium", "Ti": "titanium", "V": "vanadium", "Cr": "chromium", "Mn": "manganese",
    "Fe": "iron", "Co": "cobalt", "Ni": "nickel", "Cu": "copper", "Zn": "zinc",
    "Ga": "gallium", "Ge": "germanium", "As": "arsenic", "Se": "selenium", "Br": "bromine",
    "Kr": "krypton", "Rb": "rubidium", "Sr": "strontium", "Y": "yttrium", "Zr": "zirconium",
    "Nb": "niobium", "Mo": "molybdenum", "Tc": "technetium", "Ru": "ruthenium",
    "Rh": "rhodium", "Pd": "palladium", "Ag": "silver", "Cd": "cadmium", "In": "indium",
    "Sn": "tin", "Sb": "antimony", "Te": "tellurium", "I": "iodine", "Xe": "xenon",
    "Cs": "caesium", "Ba": "barium", "La": "lanthanum", "Ce": "cerium", "Pr": "praseodymium",
    "Nd": "neodymium", "Pm": "promethium", "Sm": "samarium", "Eu": "europium",
    "Gd": "gadolinium", "Tb": "terbium", "Dy": "dysprosium", "Ho": "holmium", "Er": "erbium",
    "Tm": "thulium", "Yb": "ytterbium", "Lu": "lutetium", "Hf": "hafnium", "Ta": "tantalum",
    "W": "tungsten", "Re": "rhenium", "Os": "osmium", "Ir": "iridium", "Pt": "platinum",
    "Au": "gold", "Hg": "mercury", "Tl": "thallium", "Pb": "lead", "Bi": "bismuth",
    "Po": "polonium", "At": "astatine", "Rn": "radon", "Fr": "francium", "Ra": "radium",
    "Ac": "actinium", "Th": "thorium", "Pa": "protactinium", "U": "uranium",
    "Np": "neptunium", "Pu": "plutonium", "Am": "americium", "Cm": "curium",
}  # fmt: skip

#: One element and its optional subscript, which may be fractional in a non-stoichiometric
#: compound -- which is exactly the case that broke, since ``Li3.3`` has a decimal point in it.
#: The subscript may be written without its leading zero. Typesetters drop it constantly --
#: ``LiNi.5Co.2Mn.3O2`` is the NMC-532 cathode, and it is the *title* of one corpus paper, so
#: it recurs in the orientation and in every callback. Requiring a digit first left 71 raw
#: decimals in one programme.
_GROUP = re.compile(r"([A-Z][a-z]?)(\d+(?:\.\d+)?|\.\d+)?")

#: A candidate formula: a run of capital-led groups, each with an *optional* subscript.
#:
#: Requiring a digit on every group was the first version and it matched nothing real: in
#: ``Li3.3SnS3.3Cl0.7`` the ``Sn`` carries no subscript, so the run broke there and the whole
#: token was skipped -- the exact string this module exists for. The digit requirement lives in
#: :func:`_parse` instead, along with "every group must be a real element", which is the check
#: that keeps ``AI4`` and ``NGB2`` out.
CANDIDATE = re.compile(r"\b(?:[A-Z][a-z]?\d*(?:\.\d+)?)+\b")

#: Below this many element groups it is an abbreviation, not a compound.
MIN_GROUPS = 2


def _parse(token: str) -> list[tuple[str, str]] | None:
    """Split a token into ``(element, subscript)`` pairs, or ``None`` if it is not a formula."""
    groups: list[tuple[str, str]] = []
    position = 0
    while position < len(token):
        match = _GROUP.match(token, position)
        if match is None or match.end() == position:
            return None
        symbol, subscript = match.group(1), match.group(2) or ""
        if symbol not in ELEMENTS:
            return None
        groups.append((symbol, subscript))
        position = match.end()
    if len(groups) < MIN_GROUPS:
        return None
    # **Only non-stoichiometric formulas**, meaning at least one fractional subscript. This is
    # the narrow scope, and the first version did not have it: expanding every formula turned
    # ``CO2`` into "carbon oxygen two", which nobody says, and two existing tests said so
    # immediately. Integer subscripts already work -- ``CO2`` reaches the audio as "CO two" via
    # the ordinary number pass -- and it is the decimal point that the number verbalizer skips,
    # because a digit that follows a letter is a product name far more often than a quantity.
    if not any("." in sub for _, sub in groups):
        return None
    return groups


def spoken_formula(token: str) -> str | None:
    """``Li3.3SnS3.3Cl0.7`` -> ``lithium 3.3 tin sulfur 3.3 chlorine 0.7``, or ``None``.

    The digits are left as digits on purpose. The number verbalizer runs after this and applies
    the profile's fidelity to them, so a formula's subscripts are spoken by the same rules as
    every other number in the programme rather than by a second set living here.
    """
    groups = _parse(token)
    if groups is None:
        return None
    parts: list[str] = []
    for symbol, subscript in groups:
        parts.append(ELEMENTS[symbol])
        if subscript:
            # Put the leading zero back before handing it on: the number verbalizer says
            # "zero point five" for "0.5" and nothing at all for ".5".
            parts.append(f"0{subscript}" if subscript.startswith(".") else subscript)
    return " ".join(parts)


def verbalize_formulas(text: str) -> str:
    """Rewrite every chemical formula in ``text`` before the numbers are read.

    Runs early for the same reason ``normalize`` does: once the number verbalizer has walked
    past ``Li3.3`` -- and it does walk past it, deliberately -- nothing downstream can tell that
    the ``3.3`` was ever part of a compound.
    """

    def replace(match: re.Match[str]) -> str:
        return spoken_formula(match.group(0)) or match.group(0)

    return CANDIDATE.sub(replace, text)


def element_groups(token: str) -> int:
    """How many element symbols ``token`` is made of, or ``0`` if it is not made of them.

    ``AlCl`` is two, ``conditions`` is none. Case does the work: an element symbol is a capital
    followed by an optional lower-case letter, so an ordinary word can never be one.

    Used by the citation stripper, which cannot otherwise tell a subscript from a reference
    marker. Both are digits welded to a lower-case letter, and it was deleting "AlCl3" down to
    "AlCl" -- along with ``TiCl4``, ``FeCl3``, ``SiCl4`` and every other formula ending in a
    two-letter element. Silently: nothing downstream can tell a compound lost its subscript.
    """
    groups = 0
    position = 0
    while position < len(token):
        match = _GROUP.match(token, position)
        if match is None or match.end() == position or match.group(1) not in ELEMENTS:
            return 0
        groups += 1
        position = match.end()
    return groups
