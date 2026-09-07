"""The paper's own definition of its own terms (rules STR-03, GRD-01, PRE-01).

Rule ``STR-03`` says a programme opens by establishing at most seven terms, one line each,
before the exposition starts. Until this module existed, that never happened on a build without
a model: ``short_def`` was set by the elaboration layer, or by a pattern that only matched
single-letter symbols, and by nothing else. ``preload_terms`` requires a definition, an acronym
or a symbol, so a paper whose vocabulary is ordinary noun phrases -- which is most papers --
produced **zero** pre-load beats and defined nothing. The evaluation harness had been reporting
``gloss_coverage: 0.00`` on every local build since it was written, which is the number saying
exactly this.

The fix needs no model, because **the paper has already written the definition**. Scientific
prose introduces its own vocabulary constantly and in a small number of shapes: *X is defined
as D*, *X, that is, D*, *X refers to D*, *X, which is D*, *D, known as X*. The extractor was
already matching several of those to decide that something *was* a term, and throwing away the
definition in the same line.

**The guards are the substance here, not the patterns.** A wrong definition spoken with
confidence in the first minute of a programme is worse than no definition at all -- it is the
failure mode the whole grounding apparatus exists to prevent, arriving through a door nobody
was watching. So a candidate has to survive all of :func:`acceptable`: it must not restate the
term, must not be a measurement, must be a phrase rather than a paragraph, and must come from a
sentence that actually contains the term, carrying the span that proves it (``GRD-01``). What
survives is the author's own words, which is the same standard every other spoken sentence in
the system is held to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mimem.ir import NON_CONTENT_ROLES, Block, BlockKind, Document, Span

#: A definition is a phrase. Below this it says nothing ("a method"); above it, it is the
#: sentence the exposition will say anyway, and the pre-load stops being one line each.
MIN_WORDS = 3
MAX_WORDS = 18

#: How far into the document to keep looking. A term defined for the first time in the
#: conclusion is not being introduced, it is being summarised, and the pre-load claims to say
#: what you need *before* the paper starts.
MAX_BLOCK_FRACTION = 0.8

#: Definitions in the shape "<term> <connective> <definition>". Ordered most explicit first,
#: because the first match wins and an explicit connective is better evidence than a copula.
FORWARD = (
    re.compile(r"^is\s+defined\s+as\s+(?P<definition>.+)", re.I),
    re.compile(r"^is\s+known\s+as\s+(?P<definition>.+)", re.I),
    re.compile(r"^refers?\s+to\s+(?P<definition>.+)", re.I),
    re.compile(r"^denotes?\s+(?P<definition>.+)", re.I),
    re.compile(r"^means\s+(?P<definition>.+)", re.I),
    re.compile(r"^,\s*(?:that\s+is|i\.e\.)\s*,?\s*(?P<definition>.+)", re.I),
    re.compile(r"^,?\s*which\s+(?:is|are)\s+(?P<definition>.+)", re.I),
    # "is a/an/the ..." -- a copula with a determiner is a classification, which is what a
    # definition is. Without the determiner it is usually a finding ("is far larger than the
    # noise floor"), so the determiner is doing real work here and is not decoration.
    re.compile(r"^is\s+(?P<definition>(?:a|an|the)\s+.+)", re.I),
    # The plural copula, with the same determiner requirement as the singular. Without it,
    # "lithium-ion batteries are widely deployed, thermal runaway ... poses severe safety risks"
    # came back as the definition of lithium-ion batteries.
    re.compile(r"^are\s+(?P<definition>(?:a|an|the)\s+.+)", re.I),
    # "is mechanically decoupled from ...", "is held free at one end". A participle describes
    # what the thing *is*; a comparative ("is far larger than") reports a result, and is
    # excluded by COMPARATIVE below.
    re.compile(r"^is\s+(?P<definition>(?:\w+ly\s+)?\w+ed\s+.+)", re.I),
)

#: Definitions with no connective at all, where the author simply brackets a description off:
#: "a reference resonator, held mechanically free on the same die, reproduces ...". These are
#: tried only after every explicit form has failed, and they have to pass :func:`bracketed_ok`
#: as well as :func:`acceptable`.
#:
#: **They are separated because one of them was wrong on the first real run.** A keywords line
#: -- "thermal drift, resonant strain sensor, compensation network" -- is a comma-separated
#: list, and the first pattern below read the next item in the list as the definition of the
#: previous one, producing "thermal drift. Resonant strain sensor." in the pre-load. The
#: bracketing that makes an appositive trustworthy is exactly what a list also looks like.
#: The bare comma appositive is **not** here, and that is the main finding of building this. It
#: is the shape with no connective at all -- "X, <something>, ..." -- and on a 98-page review it
#: produced six definitions of which one was right: "working conditions" defined as "with a
#: false alarm rate reduced by about 20-40%", "battery TR" as "feature extraction of electrical
#: signals is essential". Every guard added for it caught the previous example and let the next
#: one through, because a comma pair in scientific prose brackets whatever the author felt like
#: bracketing. Parentheses are different: an author who writes "(...)" is glossing, not aside-ing.
LOOSE = (re.compile(r"^\(\s*(?P<definition>[^)]{8,140}?)\s*\)", re.I),)

#: What tells an appositive apart from the next item in a list. A description says how the thing
#: relates to something else ("held mechanically free *on* the same die") or classifies it ("*a*
#: passivating layer"); a list item is a bare noun phrase with neither.
BRACKETED_OK = re.compile(
    r"^(?:a|an|the)\b|"
    r"\b(?:of|in|on|for|with|from|by|at|to|between|under|over|into|through|across|"
    r"that|which|whose|where|when)\b|"
    r"\w+(?:ing|ed)\b",
    re.I,
)


#: An appositive that says *why*, *how* or *when* rather than *what it is*. The distinction is
#: the participle: a past one describes the thing ("held mechanically free on the same die"), a
#: present one describes a circumstance around it. On a real review this pair produced "TR
#: warning. Following a logical framework of Data." and "lithium-ion batteries. Owing to their
#: high energy density and long cycle life." -- both true sentences, neither a definition.
ADVERBIAL = re.compile(
    r"^\s*(?:\w+ing\b|owing\s+to|due\s+to|thanks\s+to|because\s+of|based\s+on|given\b|"
    r"despite\b|unlike\b|after\b|before\b|during\b|while\b|whereas\b|since\b)",
    re.I,
)


def bracketed_ok(candidate: str) -> bool:
    """Is this a description of the thing, or something else the author put in commas?

    Two ways it can be something else, both seen on real papers: the next item in a
    comma-separated list, and an adverbial phrase explaining why or how.
    """
    return bool(BRACKETED_OK.search(candidate)) and not ADVERBIAL.match(candidate)


#: Definitions written the other way round: "the crust that forms on the anode, called the SEI".
REVERSED = (
    re.compile(r"(?P<definition>.+?)\s*,\s*(?:known\s+as|called|termed)\s+", re.I),
    re.compile(r"\bwe\s+(?:call|term)\s+(?:this|these)\s+(?P<definition>.+)", re.I),
)

#: Ends a definition early: the author has stopped defining and started arguing.
#: A comma is included, and it does the most work of anything here: a relative clause closes on
#: one ("the interphase, which is a thin film of decomposition products, passivates it"), and a
#: run-on definition keeps going past one. Cutting there rather than rejecting the whole match
#: is what lets `which is` survive its own closing comma. The cost is a definition with a
#: coordinate adjective -- "a thin, flexible film" becomes "a thin" and is then too short to
#: accept, which is the right way to lose it.
STOP = re.compile(
    r"\s*(?:[;:,]|\s—\s|\s--\s|\.\s|\s+(?:because|whereas|while|since)\b)",
    re.I,
)

#: A "definition" that is really a measurement. "The drift coefficient is 0.0142 %/K" tells you
#: the value, not what the thing is, and read aloud in a pre-load it is a number with no
#: referent. Rule NUM-01 owns values; this module does not compete with it.
#: Anchored at the start rather than matching the whole string, because the version that
#: required the whole string to be a quantity let "10-60 min in advance" through as the
#: definition of "early warning" -- a true fact about the thing, and not what it is. Nothing
#: that begins with a number is telling you what a term means.
MEASUREMENT = re.compile(
    r"^\W*(?:about|roughly|approximately|around|up\s+to|at\s+least|over|under)?\s*"
    r"(?:[\d.]+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)

#: A comparison is a result, not a definition: "is far larger than the measurement noise
#: floor" says what was found, not what the thing is.
COMPARATIVE = re.compile(
    r"\b(?:than|compared\s+with|compared\s+to|relative\s+to|versus)\b|"
    r"^\W*(?:far|much|somewhat|slightly|considerably)?\s*\w+er\b",
    re.I,
)

#: Openings that mean the sentence is about *this paper* rather than about the term.
META = re.compile(r"^\s*(?:shown|described|discussed|reported|given|presented|listed)\b", re.I)

#: Words too empty to be the whole of a definition.
EMPTY_HEADS = frozenset(
    {"one", "ones", "it", "them", "this", "that", "these", "those", "such", "so", "then", "also"}
)

#: Openings that continue a list rather than define anything. On a 98-page review the appositive
#: pattern produced "application scenarios. Including early electro-thermal signal warning." --
#: grammatical, span-backed, and not a definition of anything.
CONTINUATION = re.compile(
    r"^\s*(?:including|include[sd]?|such\s+as|for\s+example|e\.g\.|especially|notably|"
    r"particularly|together\s+with|along\s+with|as\s+well\s+as|and\s|or\s|but\s)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Definition:
    """A definition the paper wrote, and where it wrote it."""

    term: str
    text: str
    span: Span
    pattern: str

    @property
    def words(self) -> int:
        return len(self.text.split())


#: Blocks that are not prose the author wrote about the subject: page furniture, references, and
#: the front and back matter triage drops under ``COH-01``. Uses the same role list the linter
#: does, so "what counts as the paper's own prose" has one answer in this project.
_FURNITURE = frozenset({BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE, BlockKind.CAPTION})


def _is_prose(block: Block) -> bool:
    return (
        block.role not in NON_CONTENT_ROLES
        and block.kind not in _FURNITURE
        and bool(block.text.strip())
    )


def _sentences(text: str) -> list[tuple[int, str]]:
    """Sentence starts and texts, without pulling in a segmenter for a one-line job.

    :mod:`mimem.verbalize` owns real segmentation; here the only thing that matters is not
    running a definition past a full stop, and a split on terminal punctuation does that.
    """
    out: list[tuple[int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+", text):
        out.append((start, text[start : match.start()]))
        start = match.end()
    if start < len(text):
        out.append((start, text[start:]))
    return out


def _trim(candidate: str) -> str:
    """Cut a definition at the point the sentence stops defining and starts arguing."""
    stop = STOP.search(candidate)
    if stop is not None:
        candidate = candidate[: stop.start()]
    # The pre-load template supplies its own sentence punctuation, so a trailing stop from the
    # source would arrive as "... under test.." in the audio track.
    return candidate.strip().strip(",;:.—-").strip()


def acceptable(term: str, candidate: str) -> bool:
    """Would this be safe to say aloud, in the first minute, as what the term means?

    Every clause here is a way a plausible-looking match is actually wrong, and the circularity
    check is the one that matters most: ``X is the X that ...`` matches half the patterns above
    and defines nothing, while sounding exactly like a definition.
    """
    if not candidate:
        return False
    words = candidate.split()
    if not (MIN_WORDS <= len(words) <= MAX_WORDS):
        return False
    if MEASUREMENT.match(candidate) or META.match(candidate) or COMPARATIVE.search(candidate):
        return False
    if CONTINUATION.match(candidate):
        return False
    # No values, anywhere in it. A pre-load says what a word means; what value the thing took is
    # a finding, and rule NUM-01 owns findings. The last survivor of every other guard was "heat
    # generation" defined as "peak temperatures exceeding 800 degrees C", which is true, is not
    # a definition, and would have been the first thing a listener heard.
    if any(character.isdigit() for character in candidate):
        return False
    # A gloss is one line (rule STR-03), and one line does not need a comma. This is blunt, and
    # it is the guard that did the most work: on a real review the plural copula matched
    # "lithium-ion batteries are widely deployed, thermal runaway, or TR, poses severe safety
    # risks, ..." and handed back the lot as a definition of lithium-ion batteries. Every
    # correct definition found across both test papers is comma-free; every wrong one was not.
    if "," in candidate:
        return False

    lowered = candidate.lower()
    head = words[0].lower().strip(",.")
    if head in EMPTY_HEADS:
        return False
    # Circular: the definition contains the thing being defined, or its head noun.
    if term.lower() in lowered:
        return False
    term_head = term.lower().split()[-1]
    return not (len(term_head) > 4 and term_head in lowered.split())


def _from_sentence(term: str, sentence: str) -> tuple[str, str] | None:
    """The definition of ``term`` in ``sentence``, and the pattern that found it."""
    lowered = sentence.lower()
    at = lowered.find(term.lower())
    if at < 0:
        return None

    # ``match`` anchors at position 0, and what follows the term begins with the space that
    # separated them -- so every forward pattern failed to fire until this lstrip existed.
    after = sentence[at + len(term) :].lstrip()
    for pattern in FORWARD:
        match = pattern.match(after)
        if match is None:
            continue
        candidate = _trim(match.group("definition"))
        if acceptable(term, candidate):
            return candidate, pattern.pattern[:24]

    before = sentence[:at]
    for pattern in REVERSED:
        match = pattern.search(before)
        if match is None:
            continue
        candidate = _trim(match.group("definition"))
        if acceptable(term, candidate):
            return candidate, pattern.pattern[:24]

    # Last, and only if nothing with a connective matched: the bracketed forms, which need the
    # extra check that they are a description rather than the next item in a list.
    for pattern in LOOSE:
        match = pattern.match(after)
        if match is None:
            continue
        candidate = _trim(match.group("definition"))
        if acceptable(term, candidate) and bracketed_ok(candidate):
            return candidate, pattern.pattern[:24]
    return None


def find(doc: Document, terms: list[str]) -> dict[str, Definition]:
    """The first acceptable definition each term gets in the document.

    First, not best: a paper introduces a term where it first needs it, and a later sentence
    that happens to match a pattern more cleanly is usually further from the introduction the
    pre-load is standing in for.
    """
    blocks = [b for b in doc.blocks if _is_prose(b)]
    cutoff = max(1, int(len(blocks) * MAX_BLOCK_FRACTION))
    found: dict[str, Definition] = {}
    wanted = {t.lower(): t for t in terms}

    for block in blocks[:cutoff]:
        lowered = block.text.lower()
        for key, term in list(wanted.items()):
            if key not in lowered:
                continue
            definition = _in_block(term, block)
            if definition is not None:
                found[term] = definition
                del wanted[key]
        if not wanted:
            break
    return found


def _in_block(term: str, block: Block) -> Definition | None:
    for offset, sentence in _sentences(block.text):
        hit = _from_sentence(term, sentence)
        if hit is None:
            continue
        text, pattern = hit
        return Definition(
            term=term,
            text=text,
            span=Span(
                block_id=block.id,
                char_start=offset,
                char_end=offset + len(sentence),
                page=block.page,
            ),
            pattern=pattern,
        )
    return None
