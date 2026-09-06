"""The sentences that back a concept, ranked.

Everything the planner says about a concept has to come from somewhere. With no model in the
loop -- M4 is deterministic by design -- "somewhere" means a specific sentence of the source,
carried around with its span so that the answer to a prompt, the text of a callback and the
line in ``study.md`` all point at the same place a reader can check (rules GRD-01, GRD-04).

That constraint turns out to solve a harder problem too. Rule ``REP-01`` says a repeat is never
verbatim: hearing the same sentence twice produces the fluency illusion, not memory. A template
cannot paraphrase, and an unavoidably verbatim repeat would be a rule violation dressed up as a
feature. But a paper says more than one thing about any concept that matters, so each exposure
draws a *different* supporting sentence from the source. The variation is real and it is the
author's, not ours.

When a concept's supply of distinct sentences runs out, the planner is told so rather than
repeating one; see :func:`SupportPool.take`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from mimem.config import Listener, Profile
from mimem.ir import Block, BlockKind, BlockRole, Concept, Document, Span
from mimem.triage.rules import retained
from mimem.verbalize import verbalize_text

#: A sentence that defines something is the one to introduce a concept with.
DEFINITIONAL = re.compile(
    r"\b(?:is|are)\s+(?:defined|known|referred\s+to)\s+as\b"
    r"|\b(?:we|the\s+authors?)\s+(?:call|term|define)\b"
    r"|\b(?:that\s+is|in\s+other\s+words)\b"
    r"|\bconsists?\s+of\b|\brefers?\s+to\b",
    re.I,
)

#: A sentence that explains *why* supports a mechanism prompt (rules ELB-01, RET-02).
CAUSAL = re.compile(
    r"\bbecause\b|\btherefore\b|\bthus\b|\bhence\b|\bdue\s+to\b|\bleads?\s+to\b"
    r"|\bresults?\s+in\b|\bcauses?\b|\bso\s+that\b|\bexplains?\b|\bdriven\s+by\b",
    re.I,
)

#: Roles where a sentence is the paper stating its own point.
_ROLE_WEIGHT = {
    BlockRole.ABSTRACT: 1.0,
    BlockRole.CONCLUSION: 0.9,
    BlockRole.TITLE: 0.8,
    BlockRole.INTRODUCTION: 0.6,
    BlockRole.DISCUSSION: 0.6,
    BlockRole.RESULTS: 0.5,
    BlockRole.BODY: 0.4,
    BlockRole.METHODS: 0.3,
}

#: Below this many words a sentence is a fragment, not a statement worth an exposure.
MIN_SUPPORT_WORDS = 6

#: Above this, a sentence is too long to be a self-contained answer (rule SENT-01).
MAX_SUPPORT_WORDS = 35


@dataclass(frozen=True)
class Support:
    """One source sentence that says something about one concept."""

    concept_id: str
    spoken: str  # verbalized, ready for the audio track
    written: str  # the source sentence, for study.md
    span: Span
    section_id: str | None
    score: float
    definitional: bool = False
    causal: bool = False


@dataclass
class SupportPool:
    """The supporting sentences for every concept, consumed as exposures are laid down."""

    by_concept: dict[str, list[Support]] = field(default_factory=dict)
    _used: set[tuple[str, str]] = field(default_factory=set)

    def best(self, concept_id: str, *, definitional: bool = False) -> Support | None:
        """The strongest support for a concept, used or not. For a first introduction."""
        options = self.by_concept.get(concept_id, [])
        if definitional:
            return next((s for s in options if s.definitional), options[0] if options else None)
        return options[0] if options else None

    def take(self, concept_id: str) -> Support | None:
        """The strongest support this concept has not spent yet (rule REP-01).

        ``None`` means the source has nothing left to say about it that has not been said. The
        planner turns that into a naming beat rather than a repetition, and records it.
        """
        for support in self.by_concept.get(concept_id, []):
            key = (concept_id, support.spoken)
            if key in self._used:
                continue
            self._used.add(key)
            return support
        return None

    def spend(self, support: Support) -> None:
        """Mark a support as used, for exposures placed by some other route."""
        self._used.add((support.concept_id, support.spoken))

    def spend_covered(self, spans: Iterable[Span]) -> int:
        """Mark every support the listener has already heard inside ``spans``.

        An exposition beat is several sentences long, and a support is one of them. Without
        this, a callback could hand back a sentence the exposition had just read out -- which is
        the verbatim repetition rule ``REP-01`` forbids, and which the pool could not see
        because it only tracked the sentences *it* had handed out.
        """
        ranges = [(s.block_id, s.char_start, s.char_end) for s in spans]
        spent = 0
        for concept_id, options in self.by_concept.items():
            for support in options:
                key = (concept_id, support.spoken)
                if key in self._used:
                    continue
                if any(
                    support.span.block_id == block_id
                    and support.span.char_start >= start
                    and support.span.char_end <= end
                    for block_id, start, end in ranges
                ):
                    self._used.add(key)
                    spent += 1
        return spent


def concept_pattern(concept: Concept) -> re.Pattern[str]:
    """Match any surface form of a concept, on word boundaries."""
    forms = sorted((f for f in concept.all_forms() if f.strip()), key=len, reverse=True)
    if not forms:
        return re.compile(r"(?!)")  # matches nothing
    body = "|".join(re.escape(f) for f in forms)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.I)


def concepts_in(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    """Which concepts a piece of text mentions, in registry order."""
    return [cid for cid, pattern in patterns.items() if pattern.search(text)]


def _informativeness(sentence: str) -> float:
    """How much a sentence carries, roughly: numbers and length, minus hedging."""
    words = sentence.split()
    if not words:
        return 0.0
    numbers = len(re.findall(r"\d", sentence)) / max(len(words), 1)
    length = min(len(words) / 25.0, 1.0)
    hedge = 0.2 if re.search(r"\bmay\b|\bmight\b|\bcould\b|\bpossibly\b", sentence, re.I) else 0.0
    return 0.5 * length + 0.5 * min(numbers * 4, 1.0) - hedge


def sentences_of(block: Block) -> list[tuple[int, int]]:
    """Sentence spans of a block, falling back to the whole block."""
    return block.sentences or [(0, len(block.text))]


def best_sentence(
    blocks: list[Block],
    profile: Profile,
    listener: Listener | None = None,
    *,
    strip_superscripts: bool = False,
) -> Support | None:
    """The most informative sentence in a run of blocks, with its span.

    Used when a section has no concept to hang a question on. It is the same ranking the
    per-concept pool uses, minus the concept: role weight plus informativeness.
    """
    best: Support | None = None
    for block in blocks:
        if block.kind in {BlockKind.HEADING, BlockKind.REFERENCE, BlockKind.PAGE_ARTIFACT}:
            continue
        weight = _ROLE_WEIGHT.get(block.role, 0.4)
        for start, end in sentences_of(block):
            raw = block.text[start:end].strip()
            if not (MIN_SUPPORT_WORDS <= len(raw.split()) <= MAX_SUPPORT_WORDS):
                continue
            spoken = verbalize_text(
                raw, profile, listener, strip_superscripts=strip_superscripts
            ).strip()
            if len(spoken.split()) < MIN_SUPPORT_WORDS:
                continue
            score = weight + _informativeness(raw)
            if best is None or score > best.score:
                best = Support(
                    concept_id="",
                    spoken=spoken,
                    written=raw,
                    span=Span(block_id=block.id, char_start=start, char_end=end, page=block.page),
                    section_id=block.section_id,
                    score=score,
                )
    return best


def gather(
    doc: Document,
    concepts: dict[str, Concept],
    profile: Profile,
    listener: Listener | None = None,
    *,
    strip_superscripts: bool = False,
) -> SupportPool:
    """Collect and rank the supporting sentences for every concept in ``concepts``."""
    patterns = {cid: concept_pattern(c) for cid, c in concepts.items()}
    pool: dict[str, list[Support]] = {cid: [] for cid in concepts}

    for block in retained(doc):
        # A caption is excluded for the same reason a heading is: it is a label, not a claim.
        # Left in, it became the supporting sentence for a callback -- and since the caption is
        # also its figure's announcement, the programme said the same words twice and REP-01
        # caught it.
        if block.kind in {
            BlockKind.HEADING,
            BlockKind.REFERENCE,
            BlockKind.PAGE_ARTIFACT,
            BlockKind.CAPTION,
        }:
            continue
        weight = _ROLE_WEIGHT.get(block.role, 0.4)
        for start, end in sentences_of(block):
            raw = block.text[start:end].strip()
            words = len(raw.split())
            if not (MIN_SUPPORT_WORDS <= words <= MAX_SUPPORT_WORDS):
                continue
            mentioned = concepts_in(raw, patterns)
            if not mentioned:
                continue
            spoken = verbalize_text(
                raw, profile, listener, strip_superscripts=strip_superscripts
            ).strip()
            if len(spoken.split()) < MIN_SUPPORT_WORDS:
                continue  # the verbalizer removed most of it: a citation-only sentence
            definitional = bool(DEFINITIONAL.search(raw))
            causal = bool(CAUSAL.search(raw))
            span = Span(
                block_id=block.id,
                char_start=start,
                char_end=end or len(block.text),
                page=block.page,
            )
            score = weight + _informativeness(raw) + (0.8 if definitional else 0.0)
            for cid in mentioned:
                pool[cid].append(
                    Support(
                        concept_id=cid,
                        spoken=spoken,
                        written=raw,
                        span=span,
                        section_id=block.section_id,
                        score=score,
                        definitional=definitional,
                        causal=causal,
                    )
                )

    for cid, options in pool.items():
        options.sort(key=lambda s: (-s.score, s.span.block_id, s.span.char_start))
        pool[cid] = _dedupe(options)
    return SupportPool(by_concept=pool)


def _dedupe(options: list[Support]) -> list[Support]:
    """Drop near-duplicates, so a repeat is a genuinely different sentence (rule REP-01)."""
    kept: list[Support] = []
    for option in options:
        if any(_overlap(option.spoken, other.spoken) > 0.6 for other in kept):
            continue
        kept.append(option)
    return kept


def _overlap(a: str, b: str) -> float:
    """Word-level Jaccard overlap. Cheap, and enough to catch a restated sentence."""
    wa = {w.lower() for w in re.findall(r"[\w'-]+", a)}
    wb = {w.lower() for w in re.findall(r"[\w'-]+", b)}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
