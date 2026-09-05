---
icon: lucide/play
---

# Your first paper

One command, then five minutes of looking at what came out. The looking matters more than the
command.

## Run it

```bash
uv run mimem build paper.pdf --out out/paper
```

That is the whole pipeline: read the PDF, work out what is worth saying, decide how to say it,
lay it out as a programme, write the four files, and check the result against ninety design
rules. It exits with an error if it broke one, so a bad script cannot be produced quietly.

You will see something like this:

```
   dehyphenated: joined 12 hyphenated line breaks, kept 10 as real hyphens
   page_artifacts: marked 44 repeated header/footer blocks across 23 pages
   triage: keep 99, compress 37, transform 32, drop 74 (81% of words retained)
wrote out/paper: audio.md, study.md, cards.json, manifest.json
  21 sections, 50 segments, 411 beats, 68 prompts
  84.2 min against a 90.2 min budget at 155 wpm
  38 concepts come back at least once; 47 cards
lint: 0 error(s), 320 warning(s)
```

Read those lines. `triage: ... 81% of words retained` is the one to watch — if it says 30 %,
something went wrong upstream and the programme will be missing most of the paper.

!!! tip "Warnings are not errors"

    A few hundred warnings is normal and mostly means "this sentence is longer than 35 words" and
    "this acronym was never expanded". They are quality notes for a future version, not defects
    in your output. Errors are what stop the build, and there should be none.

## Look at what came out

Open `out/paper/audio.md` in any text editor. Read the first twenty lines aloud, slowly, at about
the pace of a podcast. That is the experience.

Then open `out/paper/study.md` beside it. Same programme, but with the exact numbers, the source
sentence behind every beat, and a page number on each one. This is the file to have open if you
are listening at a desk.

## Listen to it

mimem does not synthesise speech yet — that is Part 2. In the meantime, `audio.md` is plain text
that any engine will take:

- **macOS**: `say -f out/paper/audio.md -o paper.aiff`
- **ElevenLabs, or any web reader**: paste the file in. It is deliberately free of anything that
  would trip an engine up.
- **A local voice** (Piper, Kokoro): feed it the file directly.

The pauses are the one thing plain text cannot carry. They live in `manifest.json`, one
`pause_after` per chunk, ready for an engine adapter to render — and every retrieval pause is
*also* spoken out loud ("take a few seconds"), so a voice that ignores break markers still leaves
you the time.

## Make it yours

The single biggest improvement available to you is telling mimem what you already know. Copy the
example and edit it:

```bash
cp listener.example.yaml listener.yaml
```

```yaml
name: jepe
default_expertise: familiar
expertise:
  electrochemistry: expert
  machine-learning: familiar
domain_terms:
  electrochemistry: [anode, cathode, electrolyte, cell, electrode]
known_terms: [coulombic efficiency, C-rate, SEI]
```

Then:

```bash
uv run mimem build paper.pdf --out out/paper --listener listener.yaml
```

For a battery specialist reading a battery teardown paper, this is the difference between a
programme that explains "prismatic cell" to you and one that spends that minute on the
methodology instead. It genuinely changes what the programme is about — see
[tuning](tuning.md).

## When you disagree with it

Every beat can explain itself:

```bash
uv run mimem explain out/paper --beat t_4e4756d5592f
```

which tells you which design rule produced that beat, which sentence of the paper is behind it,
which concept it serves, and what it cost in seconds. The beat IDs are in `manifest.json`.

And when it ranks something wrongly, you can just say so. `out/paper/registry.json` is meant to
be edited:

```json
"c_a1b2c3d4e5": {
  "canonical": "solid electrolyte interphase",
  "difficulty": 0.62,
  "overrides": { "importance": 0.95, "short_def": "the crust that forms on the anode" }
}
```

Anything under `overrides` survives every future run. Correcting a bad ranking is a one-line
change, not an argument with a heuristic.

## Next

[Tuning it to you](tuning.md){ .md-button .md-button--primary } &nbsp;
[What the commands do](../reference/cli.md){ .md-button }
