---
icon: lucide/terminal
---

# Commands

Every stage is a file-to-file transform, so you can stop after any of them, edit the JSON by
hand, and resume. `mimem build` is all of them at once.

All commands are shown with `uv run`; drop it if you have activated the environment.

## `build`

The whole pipeline, source document to checkable programme.

```bash
uv run mimem build paper.pdf --out out/paper --listener listener.yaml
```

| Option | |
|---|---|
| `--out`, `-o` | Output directory. Default `out`. |
| `--profile`, `-p` | `skim`, `study` (default) or `drill`. |
| `--listener` | Your `listener.yaml`. The single biggest quality lever. |
| `--llm` / `--local` | Call a model for stage 6, or skip it. Default `--local`. |
| `--fixtures` | Replay recorded elaborations from a directory instead of calling anything. |
| `--budget` | Hard cap in US dollars, checked before each call. |

Writes `audio.md`, `study.md`, `cards.json`, `manifest.json`, plus `doc.ir.json`,
`registry.json`, `script.json` and `drop-report.md` so that every intermediate stage is on disk.
**Exits non-zero if the result breaks a design rule.**

## `inspect`

What ingestion actually produced. Read this before trusting a build.

```bash
uv run mimem inspect paper.ir.json --outline --show 3
```

Prints the title and metadata, block and role counts, the section outline, the estimated straight
read time, and every diagnostic the pipeline raised. This is how you find out that ingestion
quietly ate the methods section.

## `explain`

Why does this beat exist?

```bash
uv run mimem explain out/paper --beat t_4e4756d5592f
```

Prints the beat's type, the design rules that produced it, its cost in seconds, whether it is the
source's or ours, the concept it serves with its scores, and the source sentence behind it. Beat
IDs come from `manifest.json`.

Without this, tuning the system is guesswork — which is why it exists from the first version
rather than as a debugging afterthought.

## The stages, individually

### `ingest`

```bash
uv run mimem ingest paper.pdf -o paper.ir.json
```

Reads the source into the canonical IR and cleans it. `--no-clean` stops after stage 1, so you
can run `clean` separately and compare.

### `triage`

```bash
uv run mimem triage paper.ir.json --report drop-report.md
```

Decides what reaches the narration and records why. The drop report is worth skimming: it is
where you notice that a whole section was classified as boilerplate.

### `concepts`

```bash
uv run mimem concepts paper.ir.json --listener listener.yaml --top 20
```

Extracts and scores the concepts, and writes `registry.json`. Prints a table of the top concepts
with their difficulty, importance and budget, and says whether concreteness came from measured
norms or a morphological guess.

**The registry is meant to be edited.** Anything under a concept's `overrides` key survives every
future run.

### `elaborate`

```bash
uv run mimem elaborate paper.ir.json --dry-run
```

Stage 6. `--dry-run` prints the planned calls and an estimate without making any:

```
29 call(s) to claude-opus-5: 3 x analogy, 4 x anchor, 11 x gloss, 11 x why
  estimated $1.67 -- an estimate, not a quote
```

| Option | |
|---|---|
| `--llm` / `--local` | Call a model, or run deterministic-only. Default `--local`. |
| `--dry-run` | Print the calls and the estimate, make none. |
| `--fixtures` | Replay recorded answers from a directory. |
| `--budget` | Hard cap in dollars. |
| `--model` | Override the model. |
| `--no-cache` | Skip the content-addressed cache. |

### `plan`

```bash
uv run mimem plan paper.ir.json --registry registry.json -o script.json
```

Stage 7: beats, segments, prompts, spacing, the review block. Builds the registry first if there
is not one.

### `render`

```bash
uv run mimem render script.json -o out/paper
```

Stage 8: the four artefacts, then lints the result.

### `lint`

```bash
uv run mimem lint out/paper
```

Given a build directory it checks both halves — the narration text against the speakability
rules, and the plan against the structure, retrieval and spacing rules. Given a bare `audio.md`
it can only do the first, and says so. Exits non-zero on any error.

### `narrate`

```bash
uv run mimem narrate paper.ir.json -o out/plain
```

A straight reading: the retained content, verbalized, with no prequestions, retrieval or spacing.
Useful for seeing what the structural layer actually adds, and as a fallback when a document
defeats the planner.

## `profiles`

```bash
uv run mimem profiles
```

Lists the available profiles with their headline settings, and which listener file is currently
loaded.

## `version`

```bash
uv run mimem version
```

Version, and the file formats this build can read.

## Environment

| Variable | |
|---|---|
| `MIMEM_LISTENER_FILE` | Default listener file, so you can stop passing `--listener`. |
| `MIMEM_CONCRETENESS_FILE` | Your copy of the Brysbaert norms. |
| `MIMEM_PROFILES_DIR` | Where to look for profiles. |
| `MIMEM_CACHE_DIR` | Where model answers are cached. Default `.mimem-cache`. |
| `ANTHROPIC_API_KEY` | Only read when you pass `--llm`. |
