---
name: mimem
description: Turn a paper into a listenable programme designed to be remembered, and run spaced study sessions from it. Use when the user wants to listen to, study, revise or be quizzed on a paper, PDF or document — or says things like "help me remember this paper", "make this listenable", "quiz me on what I read", or "what's due to review".
---

# mimem

mimem rewrites a document so the text itself does what a careful reader would have done —
questions before the content, terms explained before they are used, concrete images for abstract
ideas, silence after a question, and the key ideas brought back at growing intervals.

This skill drives the CLI. In Claude Desktop, the same workflows are available as MCP tools
instead; see `docs/PLAN-assistant.md`.

## Make a programme

```bash
uv run mimem build PAPER.pdf --out out/PAPER --listener listener.yaml
```

Then tell the user what it found: the duration, the structure, the key ideas, and anything the
lint report complains about. `--listener` is optional but it is the single biggest quality lever
— it stops the programme explaining things they already know.

Read the summary lines it prints. `triage: ... 81% of words retained` is the one to watch: if it
says 30%, ingestion went wrong and the programme will be missing most of the paper. Run
`uv run mimem inspect out/PAPER/doc.ir.json --outline` to see what it actually saw.

## Write the explanations yourself

Stage 6 normally needs a paid API key. You are a perfectly good substitute, and it costs nothing.

```bash
uv run mimem elaborate out/PAPER/doc.ir.json --registry out/PAPER/registry.json --dry-run
```

That lists what wants writing. To write them yourself, read the concepts and their supporting
sentences out of `out/PAPER/registry.json` and `doc.ir.json`, write the glosses and anchors into
the registry's `overrides`, then re-plan:

```bash
uv run mimem plan out/PAPER/doc.ir.json --registry out/PAPER/registry.json -o out/PAPER/script.json
uv run mimem render out/PAPER/script.json -o out/PAPER
```

**Write only from the paper's own sentences.** A number the paper does not state, or a direction
reversed, is a real failure — mimem checks for exactly this and rejects it, and you should not be
trying to get past that check.

Mark anything that is your own invention as your own: an anchor is introduced with "here's a way
to picture it", an analogy with "my analogy, not theirs", and the analogy must say where it
breaks.

## Run a study session

The questions are in `out/PAPER/cards.json`, each with the span its answer came from.

Ask them **one at a time**. Wait for the answer before showing anything. The pause where the
person tries to remember is the part that works — showing the answer alongside the question
throws away the entire effect, and it is the most common way to get this wrong.

Then tell them plainly whether they had it, and keep a note of what they keep missing.

## Explain a choice

```bash
uv run mimem explain out/PAPER --beat t_4e4756d5592f
```

Which design rule produced a beat, which sentence of the paper is behind it, and what it cost in
seconds. Beat ids are in `manifest.json`.

## Correct a bad ranking

`out/PAPER/registry.json` is meant to be edited. Anything under a concept's `overrides` key
survives every future run:

```json
"overrides": { "importance": 0.95, "short_def": "the crust that forms on the anode" }
```

Re-plan and re-render afterwards.

## What not to do

- **Do not read `audio.md` into the conversation wholesale.** A hundred-minute programme is
  fifteen thousand words. Read a section at a time.
- **Do not invent content for a figure or an equation.** mimem says "there is a figure here, it
  is in the written notes" on purpose; a confident description of a graph nobody can see is the
  worst output this system can produce.
- **Do not present the audio track as a summary.** It is the paper, restructured — the
  distinction matters to a researcher.
