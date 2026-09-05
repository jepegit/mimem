---
icon: lucide/brain
---

# Why it is built like this

Every choice in mimem traces to a finding about how people learn, and the findings are not all
comfortable. This page is the argument in plain language. The
[knowledge base](../knowledge-base/README.md) is the same argument with the effect sizes,
confidence tags and citations attached, and [the design rules](../DESIGN-RULES.md) are what the
code actually enforces.

The chain is deliberate and one-directional:

``` mermaid
graph LR
  A[a finding<br/>in the literature] --> B[a numbered rule<br/>in DESIGN-RULES]
  B --> C[code that names<br/>the rule in a comment]
  C --> D[a lint rule<br/>that fails the build]
```

If a rule cannot be traced back to a finding, it should not be a rule. If it cannot be checked,
it is a hope.

## The problem, stated precisely

Reading is **self-regulated**. You control the rate, re-read on failure, jump back to recover a
definition, pause to build a picture, skip what you know.

Listening is **transient**. Each word is gone when it is spoken, and going back is expensive
enough that nobody does it. Sweller's transient information effect is the formal version: the
same material that works fine on a page degrades badly in speech, and it degrades *more* the more
complex the material is — exactly backwards from what you would want.

So a text-to-speech reading of a paper strips out the machinery that made reading work and adds
nothing back. "I listened to it and remember nothing" is the expected outcome, not a personal
failing.

**The thesis:** if the listener can no longer regulate their own encoding, the text has to do it
for them.

## What actually works

Six findings do most of the work, and they are large, replicated, and mostly free.

### Retrieval beats restatement

Trying to recall something, and failing, then hearing the answer, beats hearing it again
(*g* ≈ 0.50 across hundreds of studies). The catch in audio is that a question needs *time* to be
a question. A prompt with no pause is a rhetorical device and produces none of the benefit — so
every prompt in mimem is followed by real silence, and by a spoken cue telling you to use it.

### Spacing is the biggest effect, and audio is worst at it

Spaced repetition is the largest effect in the literature (*g* ≈ 0.74). Linear audio is the
format least able to deliver it: you cannot flip back, so if the programme does not bring an idea
back, nothing does. mimem schedules re-exposures at growing intervals measured in narration
minutes — and each one uses a *different* sentence of the source, because hearing the same words
twice produces the feeling of knowing without the knowing.

### Working memory is small, and new labels are expensive

Element interactivity, not "difficulty", is what overloads a listener. Meeting a new name and a
new mechanism in the same sentence costs both. Hence a term pre-load of at most seven items, a
budget of three new terms per segment, and glosses placed *before* the thing that needs them.

### Concrete beats abstract, reliably

The concreteness effect is among the most replicated findings in memory research. An abstract but
central idea earns a short, sensory, physically imaginable scene — and the same scene every time
it recurs, so that the image becomes a retrieval cue rather than decoration.

### Coherence: removing helps more than adding

The largest single effect in the multimedia-learning literature is not something you add. It is
what you take out (*d* ≈ 0.97 for the coherence principle). Interesting-but-tangential material —
"seductive details" — actively *reduces* learning of what surrounds it. So mimem drops
acknowledgements, funding statements, ORCIDs and running heads without ceremony, records every
drop, and never adds colour for its own sake.

### Structure has to be audible

You cannot see a heading. Position statements, announced enumerations that get closed out, and
audible segment boundaries are how structure survives the loss of the page (signaling, *d* ≈ 0.52).

## What does not work, or does not work here

This is the part worth reading twice.

!!! failure "Interleaving the exposition"

    Interleaving is a famous desirable difficulty — and the meta-analytic estimate for expository
    text is 0.21 and **not significant**, with a *negative* estimate for word learning. It helps
    when the skill is telling similar things apart. So mimem interleaves only inside the closing
    review block, and never the exposition.

!!! failure "Desirable difficulties for material you have not consolidated"

    Difficulty helps when you already have something to retrieve. Applied to a first encounter it
    is just difficulty. Above the element-interactivity threshold, mimem's budget shifts from
    generating difficulty to providing *support*.

!!! failure "Speeding up the hard parts"

    Difficulty is expressed as more words, more repetition and longer pauses — never as a change
    in speech rate. Comprehension is roughly flat to about 270 wpm and then falls off a cliff,
    and a listener who has fallen off it does not know they have.

!!! failure "Trusting how well you feel it went"

    Fluent, well-produced audio produces high confidence and poor retention. The feeling of
    understanding is not evidence of it, which is precisely why the system is built around
    retrieval attempts you can fail rather than explanations you can nod along to.

## The honest limits

- **The evidence is mostly about reading and about classrooms.** Very little of it is about
  listening to a scientific paper alone at a desk. The knowledge base tags each finding with a
  confidence level for exactly this reason.
- **Effect sizes do not add up.** Six interventions with *g* ≈ 0.5 do not produce *g* = 3. What
  they produce is unknown, and probably much less.
- **None of this has been measured on mimem's own output.** The evaluation harness that would
  settle it is the next milestone. Until then, this is a design argued from the literature, not a
  result.

## Read further

[The knowledge base](../knowledge-base/README.md){ .md-button .md-button--primary } &nbsp;
[The design rules](../DESIGN-RULES.md){ .md-button } &nbsp;
[Sources](../knowledge-base/99-sources.md){ .md-button }
