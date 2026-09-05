# mimem

Convert your library into audio that is designed for remembering.

Listening to a book or a paper usually leaves nothing behind. That is not a personal failing — it is
what happens when you remove the reader's ability to slow down, re-read, jump back and build a
picture, and put nothing in its place. **mimem rewrites a document so that the text itself does what
a careful reader would have done**, and then hands the result to a text-to-speech engine.

## Status

Milestones **M0** (skeleton), **M1** (ingest + clean), **M2** (triage, deterministic
verbalizers, narration, lint) and **M3** (concepts and scoring) are done. A paper now comes out as narration text with no citation
noise, no raw numerals and nothing unspeakable in it — a straight reading, not yet the memorable
version. It also knows which ideas the paper turns on and how hard each one is, which is what decides
where effort goes. Prequestions, retrieval prompts, concrete anchors and spaced repetition are
M4–M6. See
[docs/PLAN-part1.md](docs/PLAN-part1.md) §7 for the roadmap.

## Try it

```bash
uv venv --python 3.13 && uv pip install -e ".[dev,epub]"
```

```bash
mimem ingest tests/fixtures/docs/synthetic-paper.pdf -o paper.ir.json
```

```bash
mimem narrate paper.ir.json -o out/
```

That writes `out/audio.md` (what a TTS engine should say), `out/study.md` (the same material with
the exact numbers, page anchors and everything the audio track had to leave behind) and
`out/drop-report.md` (everything triage removed, and why), then lints the result.

```bash
mimem inspect paper.ir.json --show 3
```

`inspect` is the other one to look at: it prints the section outline, the block and role counts, the
estimated narration time, and every diagnostic the pipeline raised. Reading it is how you find out
that ingestion quietly ate the methods section.

## Documentation

| Document | What it is |
|---|---|
| [docs/knowledge-base/](docs/knowledge-base/README.md) | What the research says about learning from text and from audio, with confidence tags and sources |
| [docs/DESIGN-RULES.md](docs/DESIGN-RULES.md) | The rules the generated documents must obey — numbered, traceable to the literature, machine-checkable |
| [docs/examples/sample-output.md](docs/examples/sample-output.md) | A worked before/after example: what the output should sound like |
| [docs/PLAN-part1.md](docs/PLAN-part1.md) | Implementation plan — architecture, data model, stages, milestones, evaluation |

Code that implements a design rule names it (`# SEG-01`), so the literature and the implementation
stay connected.

## The two parts

**Part 1 (in progress)** — ingest a paper and produce an audio-ready script plus a written
companion: hard concepts glossed and repeated at spaced intervals, abstract ideas given concrete
mental images, retrieval questions built into the narration, and figures, tables, equations, numbers
and citations rewritten into something worth hearing.

**Part 2 (later)** — synthesis, playback and spaced review across sessions. Part 1 already emits the
retrieval items and the exposure log that Part 2 schedules from.

## Configuration

`profiles/*.yaml` control how hard the document works on you (`skim`, `study`, `drill`).
`listener.example.yaml` is where you tell mimem what you already know — copy it to `listener.yaml`
and edit. For a domain specialist that file is the single biggest quality lever: it is what stops
the system explaining "electrolyte" to you for the hundredth time.

```bash
mimem profiles
```
