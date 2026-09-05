"""Stage 4b: how hard is this idea, and how much does the paper depend on it?

Rule DIF-01 asks for two numbers per concept and rule DIF-02 spends the elaboration budget on
their product. Everything here is a measurable signal rather than a judgement, for the same
reason the verbalizers are: a score you cannot explain is a score you cannot fix.

**Difficulty** is about the listener's working memory, not the subject's prestige:

- *abstractness* -- can you picture it? (knowledge base §3.1)
- *element interactivity* -- how many things must be held at once to understand the definition?
  This is the load that matters in cognitive load theory, and the one that makes "desirable"
  difficulty undesirable (§1.3)
- *unfamiliarity* -- is the word itself rare, long, Latinate?
- *density* -- does it live in sentences that are already crowded?
- *span* -- a four-word term is four things to hold, not one

**Importance** is about the document, not the reader:

- *position* -- title, abstract and conclusion are where a paper says what it means
- *reprise* -- how often the author comes back to it
- *connectedness* -- how much of the rest of the paper cannot be discussed without it
- *author signal* -- "we show that", "crucially"
- *evidence* -- does a figure or table caption mention it?

Both are normalised **within the document**, because "hard" only means anything relative to the
rest of what you are about to hear. Then the listener profile shifts difficulty down for domains
and terms you already know (rule DIF-04) -- which is the single biggest quality lever a
specialist has, and the reason "electrolyte" should never be explained to you again.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from mimem.concepts.extract import AUTHOR_SIGNALS, Candidate, concept_id, cooccurrence
from mimem.concepts.norms import abstractness
from mimem.config import Expertise, Listener
from mimem.ir import BlockKind, BlockRole, Document
from mimem.ir.concepts import Concept, ConceptKind

#: Weights for the difficulty signals. They sum to 1 and are meant to be argued with.
DIFFICULTY_WEIGHTS = {
    "abstractness": 0.30,
    "interactivity": 0.25,
    "unfamiliarity": 0.20,
    "density": 0.15,
    "span": 0.10,
}

IMPORTANCE_WEIGHTS = {
    "position": 0.30,
    "reprise": 0.25,
    "connectedness": 0.20,
    "author_signal": 0.15,
    "evidence": 0.10,
}

#: Roles where a paper states what it means.
_PROMINENT_ROLES = {
    BlockRole.TITLE: 1.0,
    BlockRole.ABSTRACT: 0.85,
    BlockRole.CONCLUSION: 0.7,
    BlockRole.INTRODUCTION: 0.4,
    BlockRole.DISCUSSION: 0.4,
}

#: Expertise shifts difficulty. An expert still meets hard ideas, just fewer of them.
EXPERTISE_FACTOR = {
    Expertise.NOVICE: 1.15,
    Expertise.FAMILIAR: 1.0,
    Expertise.EXPERT: 0.55,
}

_WORD = re.compile(r"[A-Za-z][\w'-]*")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalise(values: dict[str, float]) -> dict[str, float]:
    """Scale to 0..1 across the document, so "hard" means "hard for this paper"."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if math.isclose(lo, hi):
        return dict.fromkeys(values, 0.5)
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _interactivity(short_def: str | None, canonical: str) -> float:
    """How many distinct things must be held at once to understand this.

    Counted from the definition where there is one: each content noun, each coordinator, each
    relative clause is another element the listener has to keep in play. A definition with three
    interacting parts is not three facts, it is one high-load item.
    """
    text = short_def or canonical
    words = _WORD.findall(text)
    content = [w for w in words if len(w) > 3]
    connectives = len(
        re.findall(r"\b(and|or|between|with|relative to|per|versus|while)\b", text, re.I)
    )
    clauses = len(re.findall(r"\b(which|that|where|when|whose)\b", text, re.I))
    return float(len(content) + 2 * connectives + 2 * clauses)


def _unfamiliarity(canonical: str) -> float:
    words = _WORD.findall(canonical)
    if not words:
        return 0.0
    mean_length = sum(len(w) for w in words) / len(words)
    latinate = sum(1 for w in words if len(w) >= 9) / len(words)
    return mean_length / 12.0 + latinate


def _sentence_density(doc: Document, forms: list[str]) -> float:
    """Crowding of the sentences this concept lives in: new terms, numbers, clause count."""
    patterns = [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in forms if f]
    scores: list[float] = []
    for block in doc.blocks:
        if block.kind in {BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE} or not block.text:
            continue
        for start, end in block.sentences or [(0, len(block.text))]:
            sentence = block.text[start:end]
            if not any(p.search(sentence) for p in patterns):
                continue
            words = _WORD.findall(sentence)
            if not words:
                continue
            numbers = len(re.findall(r"\d", sentence))
            commas = sentence.count(",")
            scores.append(len(words) / 25.0 + numbers / 20.0 + commas / 6.0)
    return sum(scores) / len(scores) if scores else 0.0


def _position(doc: Document, forms: list[str]) -> float:
    patterns = [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in forms if f]
    best = 0.0
    for block in doc.blocks:
        weight = _PROMINENT_ROLES.get(block.role)
        if weight is None or not block.text:
            continue
        if any(p.search(block.text) for p in patterns):
            best = max(best, weight)
    return best


def _author_signal(doc: Document, forms: list[str]) -> float:
    patterns = [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in forms if f]
    hits = 0
    for block in doc.blocks:
        if not block.text:
            continue
        for start, end in block.sentences or [(0, len(block.text))]:
            sentence = block.text[start:end]
            if AUTHOR_SIGNALS.search(sentence) and any(p.search(sentence) for p in patterns):
                hits += 1
    return float(hits)


def _evidence(doc: Document, forms: list[str]) -> float:
    patterns = [re.compile(rf"(?<!\w){re.escape(f)}(?!\w)", re.I) for f in forms if f]
    captions = [b for b in doc.blocks if b.kind is BlockKind.CAPTION]
    return float(sum(1 for b in captions if any(p.search(b.text) for p in patterns)))


def _domain_of(concept: Concept, listener: Listener) -> str | None:
    """Which of the listener's domains this concept belongs to.

    Resolved through the listener's declared domain vocabulary. Matching the domain *name*
    against the concept -- which is what this did first -- is inert on real papers: no concept
    is called "electrochemistry", so every concept fell back to the default level and declaring
    yourself an expert changed nothing at all.
    """
    for form in concept.all_forms():
        domain = listener.domain_of(form)
        if domain is not None:
            return domain
    return None


def score(
    doc: Document,
    candidates: list[Candidate],
    listener: Listener | None = None,
) -> list[Concept]:
    """Turn candidates into scored concepts (rules DIF-01, DIF-04)."""
    listener = listener or Listener()
    concepts = [
        Concept(
            id=concept_id(c.canonical),
            canonical=c.canonical,
            aliases=sorted(c.aliases),
            kind=c.kind if c.kind is not ConceptKind.UNKNOWN else ConceptKind.TERM,
            short_def=c.short_def,
            first_span=c.first_span,
            mentions=c.mentions,
            signals={"evidence_sources": float(len(c.evidence))},
        )
        for c in candidates
    ]
    if not concepts:
        return []

    graph = cooccurrence(doc, concepts)
    raw: dict[str, dict[str, float]] = {}
    for concept in concepts:
        forms = concept.all_forms()
        raw[concept.id] = {
            "abstractness": abstractness(concept.canonical),
            "interactivity": _interactivity(concept.short_def, concept.canonical),
            "unfamiliarity": _unfamiliarity(concept.canonical),
            "density": _sentence_density(doc, forms),
            "span": float(len(_WORD.findall(concept.canonical))),
            "position": _position(doc, forms),
            "reprise": float(concept.mentions),
            "connectedness": float(len(graph.get(concept.id, ()))),
            "author_signal": _author_signal(doc, forms),
            "evidence": _evidence(doc, forms),
        }

    normalised = {
        signal: _normalise({cid: values[signal] for cid, values in raw.items()})
        for signal in (*DIFFICULTY_WEIGHTS, *IMPORTANCE_WEIGHTS)
    }

    for concept in concepts:
        difficulty = sum(w * normalised[s][concept.id] for s, w in DIFFICULTY_WEIGHTS.items())
        importance = sum(w * normalised[s][concept.id] for s, w in IMPORTANCE_WEIGHTS.items())

        difficulty *= _expertise_factor(concept, listener)
        if any(listener.knows(f) for f in concept.all_forms()):
            # Rule DIF-04, its bluntest form: you said you know this one.
            difficulty *= 0.15
        elif any(listener.knows_part_of(f) for f in concept.all_forms()):
            # You own a component of it, so the compound is not new ground.
            difficulty *= 0.6

        concept.difficulty = _clamp(difficulty)
        concept.importance = _clamp(importance)
        concept.signals.update({s: round(normalised[s][concept.id], 3) for s in normalised})
        concept.apply_overrides()

    return sorted(concepts, key=lambda c: (-c.budget, c.canonical))


def _expertise_factor(concept: Concept, listener: Listener) -> float:
    domain = _domain_of(concept, listener)
    expertise = listener.expertise_for(domain) if domain else listener.default_expertise
    return EXPERTISE_FACTOR[expertise]


def signal_summary(concepts: list[Concept]) -> Counter[str]:
    """Which extractor found how much -- useful when a paper produces nothing sensible."""
    return Counter(
        "evidence" if c.signals.get("evidence_sources", 0) > 1 else "single-source"
        for c in concepts
    )
