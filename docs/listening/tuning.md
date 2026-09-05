---
icon: lucide/sliders-horizontal
---

# Tuning it to you

Two files decide what the programme is like. One says how hard it should work you; the other says
what you already know. The second matters more.

## `listener.yaml` — what you already know

This is the single biggest quality lever for anyone who has a field. It is what stops the system
explaining "electrolyte" to you for the hundredth time.

```yaml
name: jepe
default_expertise: familiar        # novice | familiar | expert

expertise:
  electrochemistry: expert
  machine-learning: familiar

# What vocabulary belongs to each domain. Without this, declaring expertise does nothing:
# no concept in a real paper is called "electrochemistry".
domain_terms:
  electrochemistry: [anode, cathode, electrolyte, cell, electrode, lithiation]
  machine-learning: [model, training, validation, hyperparameter]

# Terms you know exactly. Knowing "anode" also makes "anode active material" easier.
known_terms: [coulombic efficiency, C-rate, SEI, state of charge]

# How to say things a text-to-speech engine will get wrong.
lexicon:
  NMC811: "N M C eight one one"
  LiFePO4: "lithium iron phosphate"
  Li-ion: "lithium ion"
```

!!! note "`domain_terms` is not optional decoration"

    The first version of this feature matched the *domain name* against concepts, which is inert:
    no concept in a real paper is called "electrochemistry", so every concept fell back to the
    default level and declaring yourself an expert changed nothing at all. Naming a domain's
    vocabulary is what makes the declaration mean something.

### What it actually changes

On a battery teardown paper, for a declared electrochemistry expert:

| Concept | Default | Expert |
|---|---|---|
| teardown analysis | #3 | **#1** — the method is what you are here for |
| BYD Blade cell | #1 | #2 — difficulty 0.32 → 0.18 |
| prismatic cell | #4 | #4 — difficulty 0.45 → 0.25 |

The programme does not just skip a few definitions. Where the effort goes changes, so the
*subject* of the programme changes: for a specialist, the methodology; for a newcomer, the
objects.

## `profiles/*.yaml` — how hard it works you

Three ship with mimem. Pick with `--profile`.

| | `skim` | `study` | `drill` |
|---|---|---|---|
| Length vs. the paper | 0.5× | 1.4× | 2.2× |
| Questions | 1 per section | 1 per segment | 2 per segment |
| Times an idea comes back | 1 | 2–3 | 3–5 |
| Use it for | deciding whether to read it properly | the default | material you have to own |

```bash
uv run mimem build paper.pdf --profile drill --out out/paper
```

Every knob in those files is documented in place, and each names the design rule it enforces.
The ones people change most:

`wpm`
:   Speech rate for the duration estimate. Default 155, which is a normal technical narration
    pace. Comprehension holds up to about 270 and falls off a cliff after — the config refuses
    anything outside 80–270.

`numeric_fidelity`
:   `exact` by default. Every value is spoken at the precision the paper states. Set to `rounded`
    for two significant figures in running prose, which never applies to a value a retained claim
    turns on.

`spacing.min_gap_minutes`
:   How far apart two encounters with the same idea must be. Default 3. Lower it and you get more
    repetition that does less good; the whole point of spacing is that the forgetting between
    exposures is what makes the next one work.

`max_preload_terms`
:   How many terms are defined before the paper starts. Default 7, and the number is not
    arbitrary — more than a handful of new labels at once is exactly the load that pre-training
    exists to avoid.

## The elaboration layer

Off by default. Switched on, a model writes the glosses, the concrete images, the
why-explanations and the analogies — the parts that are genuinely writing problems rather than
structural ones.

```bash
uv run mimem elaborate paper.ir.json --dry-run
```

```
29 call(s) to claude-opus-5: 3 x analogy, 4 x anchor, 11 x gloss, 11 x why
  estimated $1.67 -- an estimate, not a quote
```

Then, if that looks reasonable:

```bash
uv run mimem build paper.pdf --llm --budget 3.00 --out out/paper
```

`--budget` is a hard cap, checked *before* each call rather than reported after it. Answers are
cached, so re-running a build after editing one paragraph does not re-pay for the document.

!!! danger "What the model is not allowed to do"

    It never chooses a number, spells a name, or decides the structure. What it writes is checked
    against the sentences it was written from: a number the paper does not state is **rejected**,
    and so is a claim that reverses a direction the paper gives — if the paper says a thickness
    increased and the sentence says it decreased, the sentence does not ship.

    An anchor and an analogy are exempt from most of that, because they are *supposed* to contain
    things the paper never said. In exchange they are announced as ours whenever they are spoken.

## Everything else

Both files are plain YAML with comments, and `mimem profiles` prints what is currently loaded:

```bash
uv run mimem profiles
```

If you want to know why a knob exists at all, every one of them names a rule in
[the design rules](../DESIGN-RULES.md), and every rule names the finding behind it in
[the knowledge base](../knowledge-base/README.md).
