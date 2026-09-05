"""Stage 4a: find the concepts a document turns on.

No model is involved, and that is deliberate. What we need here is not judgement but
*bookkeeping*: which terms the author defined, which symbols they introduced, which phrases
they kept coming back to. A paper tells you all three, explicitly, in patterns that have been
stable for a century.

Four sources, strongest evidence first:

1. **Parenthetical acronym definitions** -- "solid electrolyte interphase (SEI)". The author has
   done the work; we just record it. This is by far the highest-precision signal in a paper.
2. **Definitional sentences** -- "X is defined as", "we refer to X as", "X, which is".
3. **Symbols** -- Greek letters and short variables introduced with a gloss.
4. **Repeated noun phrases** -- multi-word phrases that recur often enough to be the subject
   rather than the scenery.

The output is candidates, not truth. Scoring decides what matters, and the registry is editable
because neither the patterns nor the scores know your field.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from mimem.ir import Block, BlockKind, BlockRole, Document, Span
from mimem.ir.concepts import Concept, ConceptKind
from mimem.verbalize.symbols import GREEK

#: Words that cannot start or end a technical term. Kept small on purpose -- an aggressive
#: stoplist throws away "state of charge" and "loss of active material".
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "his",
        "her",
        "our",
        "your",
        "my",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "into",
        "onto",
        "over",
        "under",
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "if",
        "then",
        "than",
        "as",
        "because",
        "while",
        "when",
        "where",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "may",
        "might",
        "must",
        "shall",
        "should",
        "will",
        "would",
        "we",
        "they",
        "he",
        "she",
        "you",
        "i",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "how",
        "why",
        "not",
        "no",
        "more",
        "most",
        "less",
        "least",
        "such",
        "very",
        "much",
        "many",
        "few",
        "both",
        "each",
        "other",
        "another",
        "same",
        "different",
        "all",
        "any",
        "some",
        "one",
        "two",
        "three",
        "first",
        "second",
        "third",
        "new",
        "old",
        "high",
        "low",
        "here",
        "there",
        "also",
        "thus",
        "hence",
        "however",
        "therefore",
        "moreover",
        "furthermore",
    ]
)

#: "solid electrolyte interphase (SEI)" -- the definition and its acronym.
ACRONYM_DEFINITION = re.compile(
    r"(?P<expansion>(?:\b[\w'-]+\s+){1,6}[\w'-]+)\s*\(\s*(?P<acronym>[A-Z][A-Za-z0-9]{1,9}s?)\s*\)"
)

#: "X is defined as ...", "we call X ...", "X refers to ..."
DEFINITIONAL = (
    re.compile(
        r"\b(?P<term>[\w'-]+(?:\s+[\w'-]+){0,4})\s+is\s+(?:defined\s+as|known\s+as)\b", re.I
    ),
    re.compile(
        r"\bwe\s+(?:call|term|refer\s+to)\s+(?:this\s+)?(?P<term>[\w'-]+(?:\s+[\w'-]+){0,4})", re.I
    ),
    re.compile(r"\b(?P<term>[\w'-]+(?:\s+[\w'-]+){0,4})\s*,\s*(?:that\s+is|i\.e\.)\s*,", re.I),
)

#: A symbol introduced with its meaning: "tau is the time constant", "C is the capacity".
SYMBOL_GLOSS = re.compile(
    r"(?<![\w])(?P<symbol>[A-Za-z]|[" + "".join(GREEK) + r"])(?:\s*_\s*\{?\w+\}?)?\s+"
    r"is\s+(?:the\s+|a\s+)?(?P<gloss>[\w'-]+(?:\s+[\w'-]+){0,4})",
)

#: Words that mark the sentence around them as the author's own emphasis (importance signal).
AUTHOR_SIGNALS = re.compile(
    r"\b(we\s+(show|demonstrate|find|report|conclude|argue)|crucially|importantly|notably|"
    r"the\s+key\b|central\s+to|most\s+important|our\s+(main|principal)\s+(result|finding))\b",
    re.I,
)

#: Phrases that recur constantly and mean nothing on their own. "et al" is the clearest case:
#: it appeared fourteen times in one paper and was ranked as a concept.
NON_CONCEPTS = frozenset(
    {
        "et al",
        "in press",
        "supplementary information",
        "supplementary material",
        "data availability",
        "open access",
        "creative commons",
        "all rights",
        "corresponding author",
    }
)

#: Verbs and participles that a sliding window drags in behind a real term. "battery
#: degradation was measured" is not a concept; "battery degradation" is. They are barred from
#: the *boundaries* of a phrase only, so "measured capacity" is still available if a paper
#: really uses it that way.
PHRASE_BOUNDARY_VERBS = frozenset(
    [
        "measured",
        "observed",
        "shown",
        "used",
        "given",
        "reported",
        "obtained",
        "performed",
        "applied",
        "based",
        "considered",
        "described",
        "presented",
        "calculated",
        "determined",
        "investigated",
        "studied",
        "analyzed",
        "analysed",
        "evaluated",
        "tested",
        "found",
        "achieved",
        "required",
        "expected",
        "discussed",
        "increased",
        "decreased",
        "improved",
        "compared",
        "selected",
        "proposed",
        "developed",
        "conducted",
    ]
)

#: A coordinator inside a phrase means it is two ideas, not one: "charging and discharging".
#: "of" and "in" are fine -- "state of charge" and "loss of active material" are single terms.
_INTERNAL_COORDINATOR = re.compile(r"\b(and|or|but|versus|vs)\b", re.I)

_TOKEN = re.compile(r"[A-Za-z][\w'-]*")
_MIN_PHRASE_WORDS = 2
_MAX_PHRASE_WORDS = 4

#: A repeated phrase must appear at least this often to be a concept rather than a coincidence.
MIN_PHRASE_MENTIONS = 4

#: Blocks that never contribute candidates.
_SKIP_KINDS = frozenset(
    {BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE, BlockKind.CODE, BlockKind.EQUATION}
)
_SKIP_ROLES = frozenset(
    {
        BlockRole.REFERENCES,
        BlockRole.AFFILIATION,
        BlockRole.AUTHORS,
        BlockRole.BOILERPLATE,
    }
)


@dataclass
class Candidate:
    """A concept before it has been scored."""

    canonical: str
    kind: ConceptKind
    aliases: set[str] = field(default_factory=set)
    short_def: str | None = None
    first_span: Span | None = None
    mentions: int = 0
    evidence: set[str] = field(default_factory=set)  # which extractor found it


def concept_id(canonical: str) -> str:
    digest = hashlib.blake2s(canonical.lower().encode("utf-8"), digest_size=8).hexdigest()
    return f"c_{digest[:10]}"


def _normalise(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", phrase).strip(" ,;:.()[]")
    return phrase


def _is_phrase_like(words: list[str]) -> bool:
    """A technical term does not begin or end with a function word."""
    if not (_MIN_PHRASE_WORDS <= len(words) <= _MAX_PHRASE_WORDS):
        return False
    boundary = STOPWORDS | PHRASE_BOUNDARY_VERBS
    if words[0].lower() in boundary or words[-1].lower() in boundary:
        return False
    phrase = " ".join(words).lower()
    if phrase in NON_CONCEPTS or _INTERNAL_COORDINATOR.search(phrase):
        return False
    return all(len(w) > 1 for w in words)


def _content_blocks(doc: Document) -> list[Block]:
    return [
        b
        for b in doc.blocks
        if b.kind not in _SKIP_KINDS and b.role not in _SKIP_ROLES and b.text.strip()
    ]


def extract(doc: Document) -> list[Candidate]:
    """Find every concept candidate in the document."""
    candidates: dict[str, Candidate] = {}

    def record(
        canonical: str,
        kind: ConceptKind,
        block: Block,
        *,
        evidence: str,
        alias: str | None = None,
        short_def: str | None = None,
    ) -> None:
        canonical = _normalise(canonical)
        if not canonical or len(canonical) < 3:
            return
        key = canonical.lower()
        existing = candidates.get(key)
        if existing is None:
            existing = Candidate(canonical=canonical, kind=kind, first_span=block.span())
            candidates[key] = existing
        existing.evidence.add(evidence)
        if alias:
            existing.aliases.add(alias)
        if short_def and not existing.short_def:
            existing.short_def = short_def
        if existing.kind is ConceptKind.UNKNOWN:
            existing.kind = kind

    blocks = _content_blocks(doc)

    for block in blocks:
        text = block.text
        for m in ACRONYM_DEFINITION.finditer(text):
            expansion, acronym = m.group("expansion"), m.group("acronym")
            words = expansion.split()
            # Trim leading function words: "of the solid electrolyte interphase" -> the term.
            while words and words[0].lower() in STOPWORDS:
                words.pop(0)
            if len(words) < 1 or not _plausible_expansion(words, acronym):
                continue
            record(
                " ".join(words),
                ConceptKind.TERM,
                block,
                evidence="acronym",
                alias=acronym,
            )

        for pattern in DEFINITIONAL:
            for m in pattern.finditer(text):
                term = m.group("term")
                if _is_phrase_like(term.split()) or len(term.split()) == 1:
                    record(term, ConceptKind.TERM, block, evidence="definition")

        for m in SYMBOL_GLOSS.finditer(text):
            symbol, gloss = m.group("symbol"), m.group("gloss")
            if symbol in GREEK or (symbol.isupper() and len(symbol) == 1):
                record(
                    GREEK.get(symbol, symbol),
                    ConceptKind.SYMBOL,
                    block,
                    evidence="symbol",
                    alias=symbol,
                    short_def=gloss,
                )

    author_words = _author_words(doc)
    for phrase, count in _repeated_phrases(blocks).items():
        if count < MIN_PHRASE_MENTIONS or _is_person_name(phrase, author_words):
            continue
        home: Block | None = next(
            (b for b in blocks if phrase in b.text.lower()), blocks[0] if blocks else None
        )
        if home is not None:
            record(_surface_form(blocks, phrase), ConceptKind.TERM, home, evidence="repetition")

    for candidate in candidates.values():
        candidate.mentions = count_mentions(doc, candidate.canonical, candidate.aliases)
    return _drop_redundant(sorted(candidates.values(), key=lambda c: -c.mentions))


def _author_words(doc: Document) -> frozenset[str]:
    """The words that make up this paper's author names.

    A repeated capitalised phrase is usually a technical term; sometimes it is the
    corresponding author, whose name appears in the header of every page. The document already
    knows who wrote it, so ask it rather than guessing from orthography.
    """
    words: set[str] = set()
    for author in doc.source.authors:
        parts = [w.lower().strip(".,") for w in _TOKEN.findall(author) if len(w) > 2]
        # Surnames only. A given name like "Mark" or "Bree" is far too likely to collide with
        # ordinary vocabulary to reject a phrase on its own.
        if parts:
            words.add(parts[-1])
    return frozenset(words)


def _is_person_name(phrase: str, author_words: frozenset[str]) -> bool:
    """Does this phrase contain one of the paper's own author surnames?

    A single surname is enough to reject the phrase. "Yadav for the dataset" is a sliding-window
    artefact whichever way you count it, and requiring a majority of name words let those
    through. The cost is that a term named after one of the authors would be lost -- rare, and
    the registry is editable when it happens.
    """
    words = {w.lower() for w in phrase.split()}
    return bool(words & author_words)


def _surface_form(blocks: list[Block], phrase: str) -> str:
    """The phrase as the document actually writes it.

    Candidate counting is case-insensitive, so "optimized GBDT" arrives lower-cased. Speaking
    a term back in a casing the author never used is a small thing that reads as carelessness.
    """
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.I)
    seen: Counter[str] = Counter()
    for block in blocks:
        seen.update(m.group(0) for m in pattern.finditer(block.text))
    return seen.most_common(1)[0][0] if seen else phrase


def _drop_redundant(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse overlapping n-grams.

    A sliding window over the text produces "battery degradation", "lithium-ion battery
    degradation" and "battery capacity loss" as separate candidates, which then compete for the
    same elaboration budget. Two rules settle it, both based on how much of one phrase's
    occurrences the other explains:

    * a shorter phrase that almost only ever appears inside a longer one is the longer one;
    * a longer phrase that is rare next to its own core is an incidental elaboration of it.

    Anything in between is two genuinely different ideas and both survive.
    """
    by_words = {id(c): c.canonical.lower().split() for c in candidates}
    doomed: set[int] = set()

    for a in candidates:
        for b in candidates:
            if a is b or id(a) in doomed or id(b) in doomed:
                continue
            short, long_ = by_words[id(a)], by_words[id(b)]
            if len(short) >= len(long_) or not _contains(long_, short):
                continue
            if b.mentions >= 0.8 * a.mentions:
                doomed.add(id(a))  # "battery" only ever inside "battery degradation"
            elif b.mentions < 0.35 * a.mentions:
                doomed.add(id(b))  # a rare elaboration of a common core
    return [c for c in candidates if id(c) not in doomed]


def _contains(haystack: list[str], needle: list[str]) -> bool:
    return any(
        haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1)
    )


def _plausible_expansion(words: list[str], acronym: str) -> bool:
    """Do the initials line up? Guards against "(Figure 2)"-shaped false positives.

    Deliberately loose: real expansions skip function words ("state of health" -> SOH) and
    sometimes a whole word, so a majority of matching initials is enough.
    """
    letters = [c for c in acronym.rstrip("s") if c.isalpha()]
    if len(letters) < 2:
        return False
    initials = [w[0].lower() for w in words if w.lower() not in STOPWORDS]
    if not initials:
        return False
    hits = sum(
        1 for a, b in zip(letters[: len(initials)], initials, strict=False) if a.lower() == b
    )
    return hits >= max(2, len(letters) // 2)


def _repeated_phrases(blocks: list[Block]) -> Counter[str]:
    """Count candidate phrases, one sentence at a time.

    Per *sentence*, not per block: a window that runs over a full stop invents phrases nobody
    wrote. "...degradation matters. Battery degradation..." yields "degradation matters battery",
    which then competes for the same elaboration budget as the real term inside it.
    """
    counts: Counter[str] = Counter()
    for block in blocks:
        spans = block.sentences or [(0, len(block.text))]
        for start, end in spans:
            tokens = _TOKEN.findall(block.text[start:end])
            for size in range(_MIN_PHRASE_WORDS, _MAX_PHRASE_WORDS + 1):
                for i in range(len(tokens) - size + 1):
                    window = tokens[i : i + size]
                    if _is_phrase_like(window):
                        counts[" ".join(w.lower() for w in window)] += 1
    return counts


def count_mentions(doc: Document, canonical: str, aliases: set[str] | list[str]) -> int:
    """How often a concept is referred to, by any of its forms."""
    forms = [canonical, *aliases]
    patterns = [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in forms if f]
    return sum(
        len(pattern.findall(block.text)) for block in _content_blocks(doc) for pattern in patterns
    )


def cooccurrence(doc: Document, concepts: list[Concept]) -> dict[str, set[str]]:
    """Which concepts appear in the same sentence as which others.

    The degree of this graph is an importance signal (rule DIF-01): an idea the rest of the
    paper keeps having to mention is load-bearing, whatever its own frequency.
    """
    patterns = {
        c.id: [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in c.all_forms() if f]
        for c in concepts
    }
    graph: dict[str, set[str]] = defaultdict(set)
    for block in _content_blocks(doc):
        for start, end in block.sentences or [(0, len(block.text))]:
            sentence = block.text[start:end]
            present = [
                cid for cid, pats in patterns.items() if any(p.search(sentence) for p in pats)
            ]
            for cid in present:
                graph[cid].update(other for other in present if other != cid)
    return graph
