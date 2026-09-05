# mimem

Convert your library into audio that is designed for remembering.

Listening to a book or a paper usually leaves nothing behind. That is not a personal failing — it is
what happens when you remove the reader's ability to slow down, re-read, jump back and build a
picture, and put nothing in its place. **mimem rewrites a document so that the text itself does what
a careful reader would have done**, and then hands the result to a text-to-speech engine.

## Status

Milestones **M0**–**M5** are done. A paper comes out as a *programme*: an orientation, questions
to hold on to, a term pre-load, the paper's own sentences cut into segments, a question at the end
of each one, key ideas brought back at increasing intervals, and a review that mixes the sections
together. With `--llm` it also gets glosses, concrete anchors and analogies — and everything a
model writes is checked against the sentences it was written from before it is spoken.

Still to come: the full lint suite and evaluation harness (**M6**), and the hand-off to a speech
engine (**M7**). See [docs/PLAN-part1.md](docs/PLAN-part1.md) §7. One caveat worth knowing: the
live API adapter has never been run — there was no key in the environment it was written in — so
validate it on one short paper before pointing it at a book.

## Try it

```bash
uv venv --python 3.13 && uv pip install -e ".[dev,epub]"
```

```bash
mimem build tests/fixtures/docs/synthetic-paper.pdf --out out/paper
```

That runs the whole pipeline and writes:

| File | What it is |
|---|---|
| `audio.md` | What the engine says, and nothing else — no numerals, no brackets, no citations |
| `study.md` | The written companion: the source sentence behind every beat, with its page |
| `cards.json` | The retrieval items, with the span each answer came from |
| `manifest.json` | Scores, the exposure log, the spacing hand-off, and one addressable chunk per beat |

It exits non-zero if the result breaks a design rule, so a bad script cannot be emitted quietly.

Nothing is billed unless you ask. The default runs the deterministic pipeline and reports what it
skipped; `--dry-run` prints the calls and an estimate without making any; `--budget` stops rather
than surprising you:

```bash
mimem elaborate paper.ir.json --dry-run
```

```bash
mimem build paper.pdf --llm --budget 3.00 --out out/paper
```

Each stage is also a file-to-file transform, so you can stop anywhere, edit the JSON by hand, and
resume — `mimem ingest`, `triage`, `concepts`, `plan`, `render`, `lint`:

```bash
mimem concepts paper.ir.json --listener listener.yaml
```

Two commands are worth knowing about. `mimem inspect paper.ir.json --show 3` prints the section
outline, the block counts, the estimated narration time and every diagnostic — reading it is how
you find out that ingestion quietly ate the methods section. And when you disagree with something
the programme did:

```bash
mimem explain out/paper --beat t_4e4756d5592f
```

which answers *why does this beat exist* — which design rule produced it, which source span backs
it, which concept it is about, and what it cost in seconds.

## Documentation

| Document | What it is |
|---|---|
| [docs/knowledge-base/](docs/knowledge-base/README.md) | What the research says about learning from text and from audio, with confidence tags and sources |
| [docs/DESIGN-RULES.md](docs/DESIGN-RULES.md) | The rules the generated documents must obey — numbered, traceable to the literature, machine-checkable |
| [docs/examples/programme.md](docs/examples/programme.md) | Real output from `mimem build`: what a programme sounds like today |
| [docs/examples/sample-output.md](docs/examples/sample-output.md) | A worked before/after example: what the output should sound like once M5 lands |
| [docs/PLAN-part1.md](docs/PLAN-part1.md) | Implementation plan — architecture, data model, stages, milestones, evaluation |

Code that implements a design rule names it (`# SEG-01`), so the literature and the implementation
stay connected.

## The two parts

**Part 1 (in progress)** — ingest a paper and produce an audio-ready script plus a written
companion: hard concepts glossed and repeated at spaced intervals, abstract ideas given concrete
mental images, retrieval questions built into the narration, and figures, tables, equations, numbers
and citations rewritten into something worth hearing. The structure, the questions and the spacing
are there now; the glosses, anchors and figure descriptions are M5.

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
