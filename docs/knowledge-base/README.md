# mimem knowledge base — how humans learn from text, and what that means for audio

This knowledge base exists for one purpose: **to constrain the design of the text that mimem
generates.** It is not a literature review for its own sake. Every entry ends with an
*implication* that is turned into a numbered, testable rule in
[`docs/DESIGN-RULES.md`](../DESIGN-RULES.md).

## The problem we are designing against

Reading with your eyes is an *actively self-regulated* process. The reader controls the rate,
re-reads a hard clause, jumps back three paragraphs to recover a definition, pauses to build a
mental picture, and skips the parts they already know. Listening removes almost all of that
control. Speech is **transient**: each word is gone the moment it is spoken, and the listener
cannot cheaply go back.

So a naive text-to-speech reading of a book or paper strips out the machinery that made reading
work, and adds nothing back. That is the whole reason the experience of "I listened to it and
remember nothing" is normal rather than a personal failing.

**mimem's thesis:** if the listener can no longer regulate their own encoding, then the *text
itself* must perform that regulation on their behalf — slowing down on hard concepts, re-stating,
prompting imagery, and forcing retrieval — before it ever reaches the TTS engine.

## Files

| File | Covers |
|---|---|
| [01-core-effects.md](01-core-effects.md) | Retrieval practice, spacing, generation, desirable difficulties, interleaving |
| [02-audio-constraints.md](02-audio-constraints.md) | Transiency, working memory, listening vs. reading, speech rate, segmentation |
| [03-elaboration-and-imagery.md](03-elaboration-and-imagery.md) | Dual coding, concreteness, elaborative interrogation, analogy, narrative, voice |
| [04-structure-and-attention.md](04-structure-and-attention.md) | Advance organizers, pre-training, prequestions, signaling, coherence |
| [05-verbalizing-nonprose.md](05-verbalizing-nonprose.md) | Numbers, math, tables, figures, citations, code — the accessibility literature |
| [99-sources.md](99-sources.md) | Annotated source list with links |

## Reading the confidence tags

Effect sizes in education research are noisy, moderator-heavy, and subject to publication bias.
Each finding carries a tag so that we know how hard to lean on it:

- **[A] Robust** — large meta-analytic base, replicates across materials, ages and settings.
  Design decisions may depend on it.
- **[B] Solid but bounded** — real effect, but with known moderators or a narrower evidence base.
  Use it, but make it configurable and do not build the architecture around it.
- **[C] Plausible / mechanistic** — theory-driven or thin empirical base, or an engineering
  convention borrowed from accessibility practice rather than an experiment. Use as a default,
  expect to tune it against our own recall data.

Effect sizes below are quoted as reported by the cited sources (Cohen's *d* or Hedges' *g*);
roughly, 0.2 is small, 0.5 medium, 0.8 large.
