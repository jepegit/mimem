---
icon: lucide/headphones
---

# What mimem does to a paper

You do not need to know any Python to use this. You need a terminal, one command, and a PDF.

This section is the whole of what a listener needs. If you want to know *why* it makes the
choices it makes, that is [the science](../science/index.md); if you want to change how it makes
them, that is [building it](../building/index.md).

## The shape of a programme

mimem does not read a paper aloud. It builds a **programme** out of it, and the programme has a
shape that a paper does not:

1. **An orientation.** What this is, who wrote it, the problem they set out from, what you should
   be able to say afterwards, and how long it will take. About a minute.
2. **Two to four questions to hold on to.** You are not meant to know the answers. They are the
   questions the paper turns out to answer, asked before it does, and closed explicitly when it
   does.
3. **A handful of terms, defined.** At most seven, one line each, in the order you will need
   them. Meeting a new label and a new mechanism in the same sentence is how a listener loses
   both.
4. **The paper itself**, cut into segments of 45 to 90 seconds, each ending in a boundary you can
   hear. Numbers spoken properly. No citations, no figure numbers, nothing you cannot reach.
5. **A question at the end of every section**, with a pause long enough to actually try, and then
   the answer — in the paper's own words, with the page it came from.
6. **The ideas that matter, coming back**, at growing intervals, each time through a *different*
   sentence of the source.
7. **A review at the end**, mixing the sections together rather than walking through them again.

## What you get out

Four files, and they are deliberately not four copies of the same thing.

<div class="mimem-cards" markdown>

<div markdown>
### :lucide-volume-2: `audio.md`
What the speech engine says, and nothing else. No digits, no brackets, no citations, no markup.
This is the file you feed to a voice.
</div>

<div markdown>
### :lucide-notebook-pen: `study.md`
The written companion: the source sentence behind every beat, the exact numbers the audio had to
spell out, and the page each claim came from.
</div>

<div markdown>
### :lucide-layers: `cards.json`
The questions and answers, with the span each answer came from. The seed for reviewing later.
</div>

<div markdown>
### :lucide-receipt: `manifest.json`
The audit trail: what each concept scored and why, when you met it, what was cut and under which
rule.
</div>

</div>

The two text files being different is a deliberate choice, not an oversight. A written companion
that is a transcript of the audio is a worse document than either — the audio track has to drop
things that only work on a page, and the written track is where they survive.

## What it will not do

!!! danger "It will not make things up"

    Every sentence in the audio track is either the paper's own or a named template. When the
    optional elaboration layer is switched on, what it writes is checked against the sentences it
    was written from: a number the paper never states is rejected before you hear it, and so is a
    claim that reverses a direction the paper gives.

    Anchors and analogies are the exception — they are *supposed* to contain things the paper
    never said — so they are announced as ours: "here's a way to picture it", "my analogy, not
    theirs". You are never in doubt about whose claim you just heard.

!!! note "It will not round your numbers away"

    The default is exact. If the paper says 0.0837 % per cycle, you hear "zero point zero eight,
    three seven percent per cycle" — chunked and paced, because a long digit run said as one
    stream is unhearable, but not shortened. The listener is a researcher and the numbers are the
    point. (You can ask for rounding per profile; it is off by default.)

!!! warning "It cannot yet see a figure"

    Figures and equations are announced honestly — "there is a figure here, it is in the written
    notes" — rather than skipped or invented. Real figure descriptions need a vision model and
    are the next thing on the list.

## Next

[Install it](install.md){ .md-button .md-button--primary } &nbsp;
[Do your first paper](first-paper.md){ .md-button }
