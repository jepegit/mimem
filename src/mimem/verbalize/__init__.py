"""Stage 5 (deterministic half): turn written text into speakable text.

Order matters and is the reason this is a pipeline rather than a bag of functions:

1. **citations** first, so that ``[12]`` is deleted rather than read as "twelve";
2. **parentheses** next, while the brackets that mark an aside are still there;
3. **numbers** next, while ``2.5 × 10⁻³`` and ``25 °C`` still have the symbols that identify
   them as scientific notation and a temperature;
4. **symbols** last, to sweep up whatever the first two left behind.

The LLM-backed half of stage 5 -- figure descriptions, table strategy, equation glosses --
arrives in M5. What is here needs no model, and deliberately so: everything that touches a
number, a name or a unit stays in code that can be tested.
"""

from __future__ import annotations

from mimem.config import Listener, Profile
from mimem.ir import Block, BlockKind, TriageAction
from mimem.verbalize.citations import (
    count_superscript_citations,
    strip_identifiers,
    verbalize_citations,
)
from mimem.verbalize.numbers import (
    digits_to_words,
    int_to_words,
    number_to_words,
    ordinal_to_words,
    verbalize_numbers,
)
from mimem.verbalize.parens import verbalize_parentheticals
from mimem.verbalize.symbols import apply_lexicon, verbalize_indices, verbalize_symbols
from mimem.verbalize.units import is_unit, spoken_unit

__all__ = [
    "apply_lexicon",
    "count_superscript_citations",
    "digits_to_words",
    "int_to_words",
    "is_unit",
    "number_to_words",
    "ordinal_to_words",
    "spoken_unit",
    "strip_identifiers",
    "verbalize_block",
    "verbalize_citations",
    "verbalize_indices",
    "verbalize_numbers",
    "verbalize_parentheticals",
    "verbalize_symbols",
    "verbalize_text",
]

#: Placeholders for the block kinds whose real verbalizers need a model (M5). They are honest
#: about the gap rather than silently dropping content the listener would want.
_PENDING = {
    BlockKind.TABLE: "There is a table here. It is in the written notes.",
    BlockKind.FIGURE: "There is a figure here. It is in the written notes.",
    BlockKind.EQUATION: "There is an equation here. It is in the written notes.",
    BlockKind.CODE: "There is a code listing here. It is in the written notes.",
}

#: For prose whose meaning lives in symbols the PDF text layer never contained.
_PENDING_PROSE = "There is a passage of mathematics here. It is in the written notes."


def verbalize_text(
    text: str,
    profile: Profile,
    listener: Listener | None = None,
    *,
    strip_superscripts: bool = False,
) -> str:
    """Run the deterministic verbalization pipeline over a piece of prose."""
    if not text.strip():
        return ""
    # The listener's lexicon goes first, before anything else can claim a token. Rule SYM-03
    # says a domain term wins over every default, and it cannot win if the number verbalizer
    # has already turned "NMC811" into "NMC eight one one" on its own terms.
    if listener and listener.lexicon:
        text = apply_lexicon(text, listener.lexicon)
    text = verbalize_citations(
        text, verbosity=profile.citations, strip_superscripts=strip_superscripts
    )
    text = verbalize_parentheticals(text)
    text = verbalize_indices(text)
    text = verbalize_numbers(
        text,
        fidelity=profile.numeric_fidelity,
        significant_figures=profile.significant_figures,
    )
    return verbalize_symbols(text, lexicon=listener.lexicon if listener else None)


def verbalize_block(
    block: Block,
    profile: Profile,
    listener: Listener | None = None,
    *,
    strip_superscripts: bool = False,
) -> str:
    """Speakable text for one block, or ``""`` if it has nothing to say."""
    pending = _PENDING.get(block.kind)
    if pending is not None:
        return pending
    if block.triage is not None and block.triage.action is TriageAction.TRANSFORM:
        # Prose that triage marked for transformation but whose kind has no verbalizer yet --
        # a nomenclature table, a paragraph built around inline symbols the PDF never carried.
        # Reading the words between the missing symbols produces "a quantity, a quantity,
        # a quantity", which is worse than saying nothing.
        return _PENDING_PROSE
    return verbalize_text(block.text, profile, listener, strip_superscripts=strip_superscripts)
