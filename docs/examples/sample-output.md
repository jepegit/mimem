# Worked example — what the output should sound like

A short, hand-written target rendering. This is the spec made concrete: it is what the pipeline in
[`PLAN-part1.md`](../PLAN-part1.md) has to be able to produce, and it doubles as the golden fixture
for the linter. Rule IDs from [`DESIGN-RULES.md`](../DESIGN-RULES.md) are annotated in the margin
comments — those are not part of the output.

---

## A. Source paragraph (typical scientific prose)

> Electrolyte decomposition at the negative electrode leads to the formation of a solid electrolyte
> interphase (SEI), which passivates the surface and limits further reduction (Peled, 1979; Winter
> et al., 2018). However, the SEI is not static: repeated volume changes of the active material
> during (de)lithiation, which can exceed 300 % for silicon-based anodes (Obrovac & Christensen,
> 2004), fracture the layer and expose fresh surface, consuming additional lithium inventory. The
> resulting capacity loss was measured at 0.0837 % per cycle over 500 cycles (Fig. 4b), i.e. a
> retention of 82.1 ± 1.4 % at end of test (p < 0.001).

Everything wrong with this in audio: two inline citation groups, a "however" pivot buried in a
72-word sentence, a figure reference, an abbreviation introduced parenthetically, a four-decimal
percentage, a ± interval, and a p-value.

## B. Naive TTS reading

> "Electrolyte decomposition at the negative electrode leads to the formation of a solid electrolyte
> interphase, S E I, which passivates the surface and limits further reduction, Peled comma one nine
> seven nine semicolon Winter et al comma two thousand eighteen. However, the S E I is not static:
> repeated volume changes..."

Roughly 55 seconds, three new concepts, no pauses, four seconds of citation noise, and a number
nobody can hold.

## C. mimem rendering — audio track

```text
Section 2 of 5 — why the battery loses capacity even when nothing breaks.       <!-- ORI-01 -->

Here's a question to hold onto: when a silicon anode loses capacity,            <!-- PRQ-01 -->
what is actually being consumed?
[pause 3s]                                                                     <!-- PAU-01 -->

Two terms first.                                                               <!-- STR-03 -->
The electrolyte is the liquid that carries lithium between the two electrodes.
The S E I — that's the solid electrolyte interphase — is a thin crust that
forms on the negative electrode during the first few charges.
[pause 1s]

Here's how the crust forms. The electrolyte touching the negative electrode
is chemically unstable there, so a little of it decomposes. The decomposition
products stay put and build a layer. Once that layer covers the surface, it
blocks further decomposition. The crust is what stops the reaction that
created it.                                                                    <!-- ELB-01 -->
[pause 1s]

Picture a cast-iron pan that seasons itself: the first heating burns a thin     <!-- IMG-01, VOI-02 -->
layer onto the metal, and that burnt layer is what stops the metal rusting
further. My analogy, not the paper's — and it breaks down in one place, which   <!-- ANA-01 -->
is the whole point of this section: a pan doesn't change size.
[pause 3s]                                                                     <!-- PAU-02 -->

Because a silicon particle does. When lithium goes in, silicon swells — more
than triple its volume. When lithium comes out, it shrinks back.                <!-- NUM-01 -->
[pause 1s]

And that's the core of the argument.                                            <!-- SIG-02 -->
The crust is brittle. The particle underneath it is not staying still.
So the crust cracks, fresh silicon surface is exposed, and new crust forms
on it — which costs more lithium. Every one of those repairs takes lithium
out of circulation permanently.

So: what's being consumed isn't the silicon. It's the lithium inventory,        <!-- PRQ-02 -->
locked up in crust that keeps rebuilding itself. That was the question I
asked at the start.

How much does that cost? About a twelfth of a percent of capacity per cycle.    <!-- NUM-01 -->
That sounds like nothing, until you run it five hundred times: the cell ends
at about 82 percent of where it started. That decline is a real effect,         <!-- NUM-04 -->
not measurement noise.

The evidence is a capacity-versus-cycle-number curve: cycle number along the    <!-- FIG-01 -->
bottom, discharge capacity up the side, running out to five hundred cycles.
The line falls steadily and almost straight, with no sudden drop — which is
what tells you this is gradual lithium loss rather than a single mechanical
failure.                                                                       <!-- FIG-01 (claim) -->
[pause 1s]

Three sentences to close the section.                                          <!-- STR-06 -->
Silicon anodes fade because the protective crust cracks when the particle
swells. Each crack is repaired with lithium that never comes back. The
signature of that mechanism is a straight, gradual decline, not a cliff.
[pause 1s]

One to answer for yourself: if the fade came from the particles cracking       <!-- RET-01, RET-02 -->
apart instead of the crust cracking, what would the curve look like instead?
[pause 5s]
It would show a sharper drop, and it would come at a particular cycle rather
than being spread evenly across all of them. A straight line points at a
process that repeats a little bit every cycle.                                 <!-- RET-04 -->
[pause 2s]
```

Roughly 2 minutes 40 seconds, three segments, one prequestion closed, one anchor, one analogy with
its limit stated, one figure reduced to its claim, one retrieval item — and zero spoken citations.

## D. Same content — written track (`study.md`, excerpt)

> ### 2.1 SEI formation and mechanical failure  <sub>[source: p. 4, ¶2]</sub>
>
> **Concept: solid electrolyte interphase (SEI)** — passivating layer formed by electrolyte
> decomposition at the negative electrode; self-limiting once the surface is covered.
> *Anchor used in audio: self-seasoning cast-iron pan.*
> First described by Peled (1979); review in Winter et al. (2018).
>
> **Mechanism.** Volume change on (de)lithiation of silicon exceeds **300 %**
> (Obrovac & Christensen, 2004) → SEI fracture → fresh surface → repeated SEI formation →
> irreversible loss of lithium inventory.
>
> **Reported values.** Capacity loss **0.0837 % per cycle** over 500 cycles;
> retention at end of test **82.1 ± 1.4 %**, *p* < 0.001. Evidence: Figure 4b (capacity vs. cycle
> number, 0–500 cycles).
>
> **Spoken in audio as:** "about a twelfth of a percent per cycle", "about 82 percent",
> "a real effect, not measurement noise". *(NUM-01, NUM-04 — exact values retained here.)*
>
> **Retrieval item #7** — *prompt type: mechanism-contrast.*
> Q: If fade came from particle fracture rather than SEI fracture, how would the capacity curve
> differ? A: Sharper, cycle-localised drop rather than a uniform gradual decline.

## E. What a reviewer should check in this example

1. Nothing in C states a fact that is not in A or in general background (`GRD-01`).
2. Every number in C is reduced, and every exact value survives in D (`NUM-06`).
3. The analogy is marked as ours and its limit is stated (`ANA-01`, `VOI-02`).
4. The figure never has a number spoken and its description ends in the claim it supports
   (`FIG-01`, `FIG-04`).
5. The prequestion is drawn from the card pool and is explicitly closed (`PRQ-01`, `PRQ-02`).
6. No sentence exceeds 35 words; no pronoun crosses a beat boundary (`SENT-01`, `SENT-02`).
