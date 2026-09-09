"""The tasks: what we ask a model for, and what we refuse to ask it for.

The division of labour in this system is the whole design. Numbers, names, structure, timing and
spacing are code, because they are checkable. What is left for a model is the part that is
genuinely a writing problem: explaining a term in one line, finding a concrete image for an
abstract idea, saying why a claim follows, describing a figure. Each of those is a separate task
with its own schema, its own prompt and its own documented failure path, so that one bad figure
description cannot take down a three-hundred-page book.

Every prompt below is written against specific design rules and says so. The prompt is the first
line of defence, the output schema is the second, and the linter is the third; between them, a
rule like "an analogy states its limit" is enforced three times by three mechanisms that fail
differently. That is not redundancy for its own sake -- it is what lets the elaboration layer be
added to a pipeline that already works without weakening it.

**The rule that shapes every prompt here:** the model is never given the numbers to choose, the
names to spell or the structure to decide. It is given a concept, the sentences the source says
about it, and one job.
"""

from __future__ import annotations

from mimem.config import Listener
from mimem.ir import Concept
from mimem.llm.client import EFFORT_HIGH, EFFORT_LOW, Request
from mimem.llm.schemas import (
    MAX_ANCHOR_WORDS,
    AnalogyOut,
    AnchorOut,
    CompressOut,
    FigureOut,
    GlossOut,
    SplitOut,
    VerifyOut,
    WhyOut,
)

#: The stable prefix. Identical for every call about one document, which is what makes prompt
#: caching worth having, and what makes the house style one thing rather than nine copies of it.
SYSTEM = """\
You are writing narration that will be read aloud by a text-to-speech engine to someone who
cannot see the page, cannot go back, and cannot pause to re-read. Everything you write is
listened to once.

House style, which is not negotiable:

- Second person, spoken register, contractions welcome. Short sentences: at most 35 words, and
  under 20 on average. No sentence with more than two subordinate clauses.
- No filler, no enthusiasm, no rhetorical flourish that carries no information. No interesting
  asides, historical colour or biographical trivia, however tempting: they are remembered
  instead of the material, not alongside it.
- Never refer to anything the listener cannot reach: no "see the figure", no "as shown above",
  no "in the previous section", no citations, no figure or table numbers.
- Write numbers as words if you must write them at all, and prefer not to: another part of this
  system speaks the exact values, and it will get them right.
- Do not state a fact that is not in the source text you are given. If the source does not say
  it, you do not know it. An honest gap is always better than a plausible invention.
"""


def _listener_note(listener: Listener | None) -> str:
    """What the reader already knows, so a gloss can skip what would insult them (rule DIF-04)."""
    if listener is None:
        return ""
    known = ", ".join(listener.known_terms[:12])
    domains = ", ".join(f"{d} ({level.value})" for d, level in listener.expertise.items())
    parts = []
    if domains:
        parts.append(f"The listener's expertise: {domains}.")
    if known:
        parts.append(f"They already know these terms and need no explanation of them: {known}.")
    return " ".join(parts)


def _support_block(sentences: list[str]) -> str:
    return "\n".join(f"- {s.strip()}" for s in sentences if s.strip())


def gloss(
    concept: Concept, support: list[str], document: str, listener: Listener | None = None
) -> Request:
    """Explain a term (rules PRE-01, DIF-02, DIF-04).

    *Degrades to:* the source's own definitional sentence, verbatim. A slightly stiff definition
    the paper wrote is better than none, and much better than one we made up.
    """
    instruction = f"""\
Explain the term "{concept.canonical}" for a listener meeting it in this paper.

The source says this about it:
{_support_block(support)}

{_listener_note(listener)}

Give two lengths. The short one is a single line for a list of terms read out before the paper
starts, so it has to stand alone and be under about 20 words. The long one is the full
introduction, two or three sentences, used at the point the term first matters.

Explain what it *is* and why it matters here. Do not define it by restating its name.
"""
    return Request(
        task="gloss",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=GlossOut,
        effort=EFFORT_LOW,
        max_tokens=600,
        meta={"concept_id": concept.id},
    )


def anchor(
    concept: Concept, support: list[str], document: str, listener: Listener | None = None
) -> Request:
    """A concrete scene for an abstract idea (rules IMG-01, IMG-03).

    *Degrades to:* omitted. An anchor is a gift, not a requirement; a bad one is worse than
    none, because it becomes the thing the listener remembers.
    """
    instruction = f"""\
Give one concrete, physically imaginable scene for "{concept.canonical}".

The source says this about it:
{_support_block(support)}

It must be sensory and specific: objects, motion, scale, sound, something with edges. Not
another abstraction, not a metaphor about a metaphor. Under {MAX_ANCHOR_WORDS} words.

The listener will hear this image every time the concept comes back, so it has to be worth
hearing twice, and it has to be about *this* idea rather than about the subject in general.
"""
    return Request(
        task="anchor",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=AnchorOut,
        effort=EFFORT_HIGH,
        max_tokens=400,
        meta={"concept_id": concept.id},
    )


def analogy(
    concept: Concept, support: list[str], document: str, listener: Listener | None = None
) -> Request:
    """An analogy and where it breaks (rule ANA-01).

    *Degrades to:* omitted, and it is the first thing cut under budget pressure (ANA-02).
    """
    instruction = f"""\
Give one analogy for "{concept.canonical}", and say where it breaks down.

The source says this about it:
{_support_block(support)}

The limit is not a disclaimer, it is half the content: an analogy whose limit is unstated is
remembered instead of the concept. Say what the analogy gets right, then say the specific place
it stops being true — ideally the place that matters most for understanding this paper.

The listener will be told this analogy is ours and not the paper's, so do not pretend otherwise.
"""
    return Request(
        task="analogy",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=AnalogyOut,
        effort=EFFORT_HIGH,
        max_tokens=500,
        meta={"concept_id": concept.id},
    )


def why(concept: Concept, support: list[str], document: str) -> Request:
    """Why a claim holds (rule ELB-01).

    *Degrades to:* omitted. Unlike an anchor, this one makes a claim about the document, so it
    is verified against its spans before it is spoken (GRD-02, GRD-03).
    """
    instruction = f"""\
In one or two sentences, say why the following holds — the mechanism or the reason behind it,
not a restatement of it.

Concept: {concept.canonical}
What the source says:
{_support_block(support)}

Use only what is in those sentences and the document above. If the source does not explain why,
say what it does establish instead, briefly. Do not supply a mechanism the paper does not.
"""
    return Request(
        task="why",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=WhyOut,
        effort=EFFORT_LOW,
        max_tokens=400,
        meta={"concept_id": concept.id},
    )


def compress(text: str, document: str, seconds: float) -> Request:
    """Shorten a block triage marked ``compress`` (rule COH-02).

    *Degrades to:* the source text, unchanged. Longer than we wanted, but nothing is lost.
    """
    instruction = f"""\
Shorten this passage to about {round(seconds)} seconds of speech — roughly {round(seconds * 2.6)}
words — keeping every claim it makes and every number it states.

Cut hedging, repetition, and detail that supports no claim. Do not cut a result, a condition on a
result, or a number. If it cannot be shortened without losing one of those, return it as it is.

Passage:
{text}
"""
    return Request(
        task="compress",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=CompressOut,
        effort=EFFORT_LOW,
        max_tokens=1200,
    )


def split(sentence: str, document: str, cap: int) -> Request:
    """Cut one long source sentence into short ones (rule SENT-01).

    The design rule says **split, not compress**, and the instruction says so four ways, because
    this is the one task where a fluent wrong answer is indistinguishable from a right one. A
    summary of a sentence reads exactly like a split of it, and the listener has no way to know
    which they were given. So the verification is bidirectional -- every number and name has to
    survive in *both* directions -- and the instruction is written to make that verification
    pass rather than to make the prose pretty.

    The subject is repeated rather than pronominalised. "X, which does Y" splits naturally into
    "X. It does Y", and that is a rule ``SENT-02`` violation manufactured by the fix for
    ``SENT-01``: the listener meets "it" at the start of a sentence with the referent now behind
    a full stop. Repeating the noun costs two words and is the whole reason a split is safe.

    *Degrades to:* the source sentence, unchanged. Long, and the linter goes on saying so.
    """
    instruction = f"""\
Split this sentence into two or more shorter sentences, each under {cap} words.

This is a split, not a summary. Every fact, number, unit, name and qualifier in the original
must appear in your sentences, and you must not add any that are not there. Do not shorten by
leaving something out: if a clause cannot be carried over, return the sentence unchanged as a
single-element list and it will be used as it is.

Start each sentence with a noun, not with "it", "this", "they" or "these" — repeat the subject
instead. These sentences are heard, not read, so a pronoun at the start of one points at
something the listener can no longer see.

Keep the paper's own wording wherever it fits. You are moving clauses apart, not rephrasing them.

Sentence:
{sentence}
"""
    return Request(
        task="split",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=SplitOut,
        effort=EFFORT_LOW,
        max_tokens=900,
    )


def figure(
    caption: str, references: list[str], document: str, image: bytes | None = None
) -> Request:
    """Describe a figure (rules FIG-01, FIG-02, FIG-03, FIG-07).

    *Degrades to:* the caption alone, verbalized. Below the confidence threshold it degrades the
    same way, because this is the highest-hallucination-risk output in the system and a
    confidently wrong description of a graph is unfalsifiable by ear.

    The image itself is attached by the caller when a vision-capable model is configured; with
    text only, the caption and the sentences that reference it are what there is, and the
    confidence should say so.
    """
    instruction = f"""\
Describe this figure for someone who cannot see it, in the order the fields ask for.

Caption: {caption}

Sentences in the paper that refer to it:
{_support_block(references)}

Describe only what the figure adds. Do not repeat what those sentences already say. Mention
colour only if colour carries meaning. Never speak the figure's number.

End on the claim the figure supports — that is the part the listener needs, and the rest is
scaffolding for it.

Set confidence honestly: if you are working from the caption alone and cannot see the plotted
data, that is low confidence, and low confidence means the description will not be spoken.
"""
    return Request(
        task="figure",
        system=SYSTEM,
        document=document,
        instruction=instruction,
        schema=FigureOut,
        effort=EFFORT_HIGH,
        max_tokens=800,
        images=(image,) if image else (),
    )


def verify(claim: str, spans: list[str]) -> Request:
    """Is this generated sentence entailed by its spans (rule GRD-02)?

    A separate call with no house style and no document: the only question is entailment, and
    the fewer other instructions are in the context the less room there is for the verifier to
    be agreeable instead of correct.

    *Degrades to:* ``None`` — unknown, not passed. The deterministic checks in
    :mod:`mimem.verify` still run, and the manifest records which ones did.
    """
    instruction = f"""\
Does the statement follow from the evidence? Answer only about entailment.

Statement:
{claim}

Evidence:
{_support_block(spans)}

Entailed means: everything the statement asserts is stated by, or follows directly from, the
evidence. A statement that is true in general but not supported by this evidence is NOT
entailed. A statement that adds a mechanism, a cause, a number or a direction the evidence does
not give is NOT entailed. Quote the sentence that supports it, or say what is missing.
"""
    return Request(
        task="verify",
        system="You check whether a statement follows from evidence. You are strict and literal.",
        document="",
        instruction=instruction,
        schema=VerifyOut,
        effort=EFFORT_HIGH,
        max_tokens=400,
    )
