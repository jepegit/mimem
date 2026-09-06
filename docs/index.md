---
icon: lucide/audio-lines
---

# You listened to the whole thing and remember nothing

<p class="mimem-lede">
That is not a failing of attention. It is what happens when you take away everything that made
reading work, and put <em>nothing</em> back.
</p>

When you read, you do a dozen things without noticing. You slow down on the hard sentence. You
re-read the clause that didn't parse. You jump back two pages to recover a definition. You stop
and build a picture. You skip what you already know, and you linger where you don't.

Listening removes every one of those. Speech is gone the moment it is spoken, and a
text-to-speech engine reading a paper aloud adds nothing in their place — it just reads faster
than you can think, through the affiliations, through "open square bracket twelve", through a
four-decimal percentage nobody could hold, and out the other side.

**mimem rewrites the document so the text itself does what a careful reader would have done.**
Then it hands the result to a speech engine.

![Reading loops backwards to re-read and jump back. Listening is a straight line with the words behind you fading out and no way back. mimem builds the loops into the text: a concrete image, a question with a pause after it, and forward arcs bringing each idea back at growing intervals.](assets/lanes-light.svg#only-light)
![Reading loops backwards to re-read and jump back. Listening is a straight line with the words behind you fading out and no way back. mimem builds the loops into the text: a concrete image, a question with a pause after it, and forward arcs bringing each idea back at growing intervals.](assets/lanes-dark.svg#only-dark)

<div class="mimem-cards" markdown>

<div markdown>
### :lucide-headphones: I want to listen to a paper

Install it, point it at a PDF, get a programme you can put in your ears.

[Start here](listening/index.md)
</div>

<div markdown>
### :lucide-brain: Why is it built like that?

Every design decision traces to a finding about how people actually learn. Some of them are
uncomfortable.

[The science](science/index.md)
</div>

<div markdown>
### :lucide-wrench: I want to work on it

Nine stages, ninety numbered rules, and a linter that fails the build.

[Building it](building/index.md)
</div>

<div markdown>
### :lucide-book-open: What do the commands do?

Every stage is a file-to-file transform you can stop, edit and resume.

[Reference](reference/cli.md)
</div>

</div>

## What it actually does to a paper

Here is a sentence from a real battery paper, as a speech engine reads it:

<div class="mimem-before" markdown>
"Electrolyte decomposition at the negative electrode leads to the formation of a solid
electrolyte interphase, S E I, which passivates the surface and limits further reduction, Peled
comma one nine seven nine semicolon Winter et al comma two thousand eighteen. However, the S E I
is not static: repeated volume changes of the active material during…"
</div>

Four seconds of citation noise, three new concepts, a 72-word sentence, and no pause anywhere.
And here is the same content after mimem has been through it:

<div class="mimem-after" markdown>
"**Part two of five. Why the battery loses capacity even when nothing breaks.**

Here's a question to hold on to: when a silicon anode loses capacity, what is actually being
consumed? *(pause)*

Two terms first. The electrolyte is the liquid that carries lithium between the two electrodes.
The S E I — that's the solid electrolyte interphase — is a thin crust that forms on the negative
electrode during the first few charges.

Here's a way to picture it. A cast-iron pan that seasons itself: the first heating burns a thin
layer onto the metal, and that burnt layer is what stops the metal rusting further. My analogy,
not theirs — and it breaks down in one place, which is the whole point of this section: a pan
doesn't change size. *(pause)*"
</div>

The full worked example is in [What a programme sounds like](examples/programme.md).

## What is in there, and why

Nothing in that rewrite is decoration. Each piece is a rule, and each rule is a finding:

| What you hear | Why it is there |
|---|---|
| A question before the content | Prequestions raise recall of the material they point at (*g* ≈ 0.54–0.66) |
| Terms explained before they are used | Pre-training: meeting a label and a mechanism at once overloads working memory |
| A concrete image for an abstract idea | The concreteness effect is one of the most replicated findings in memory research |
| Silence after a question | A retrieval attempt needs time to be an attempt; without it the question is rhetorical |
| Ideas coming back at growing intervals | Spacing is the largest effect in the literature (*g* ≈ 0.74), and audio is worst at it |
| The analogy's limit, said out loud | Otherwise the listener remembers the analogy instead of the concept |

And nothing invents facts. Every sentence in the programme is either the paper's own — carrying
the exact place it came from — or one of about a dozen named templates. Where a model does write
something, the numbers in it are checked against the sentences it was written from before anyone
hears them.

!!! warning "Where this is up to"

    Part 1 — document in, script out — is built and tested. Part 2 — speech synthesis, playback
    and review across sessions — is not. mimem currently produces the text a speech engine
    should say, and everything the scheduler will eventually need. See the
    [plan](PLAN-part1.md) for what is done and what is next.
