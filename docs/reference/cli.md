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
| `--provider` | With `--llm`: `anthropic` (default), `openai` or `local`. |
| `--base-url` | For `--provider openai` or `local`; any compatible server. |
| `--speak` | Also synthesise audio, with the named engine. |
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
| `--provider` | `anthropic` (default), `openai` or `local`. |
| `--base-url` | For `--provider openai` or `local`. |
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

### `eval`

```bash
uv run mimem eval
```

Builds every document in `tests/fixtures/docs`, measures the result, and compares it against the
committed baseline in `tests/fixtures/eval/baseline.json`. Exits non-zero on a regression.

This is the check the linter cannot do. Nothing in mimem breaks loudly: a concept scorer drifts,
the spacing scheduler finds one fewer slot, a triage rule eats an extra paragraph — and every one
of those produces a programme that lints perfectly clean and teaches less. The metrics are the
handful of quantities the design is a claim about, so a design that stopped being true shows up
as a number that moved.

| Column | What it is |
|---|---|
| `used` | programme length as a fraction of its duration budget |
| `q/min` | retrieval prompts per minute |
| `gloss` | concepts the listener was given a definition for |
| `spaced` | concepts met more than once in the body |
| `expand` | of the concepts met three times or more, those whose gaps never shrink |
| `ground` | beats that can point at a page, of those required to |
| `values` | source values that reached `study.md` |
| `kept` | words of the source that survived triage |

```bash
uv run mimem eval --update
```

Writes the current numbers down as the new baseline. This is the only way to make a real
regression pass, and it is a separate command on purpose: it puts the worse number in the diff
where a reviewer has to look at it.

`--corpus DIR` measures your own documents instead, which is the fastest way to find out whether
mimem falls over on a field it has never seen. `--json` prints the metrics rather than the table.

### `speak`

```bash
uv run mimem speak out/paper --engine sapi --voice "Microsoft Zira Desktop"
```

Stage 9: the script as a playable WAV, with the retrieval pauses written into it as real
silence. Takes a script JSON or a directory containing one.

| | |
|---|---|
| `--engine` / `-e` | `silent`, `sapi`, `piper` or `openai`. Default `silent`. |
| `--voice` | The engine's own voice name. For `piper`, the `.onnx` file. |
| `--model` | Piper voice file, or the TTS model for `openai`. |
| `--base-url` | For `--engine openai`; any compatible server. |
| `--rate` | SAPI speaking rate, -10 to 10. |
| `--cache` / `--no-cache` | Reuse audio for unchanged beats. Default on. |

Writes `audio.wav` and `timings.json`. See [Turning it into audio](../listening/audio.md).

### `voices`

```bash
uv run mimem voices --engine sapi
```

What an engine can sound like. Engines that cannot enumerate their voices say so.

### `narrate`

```bash
uv run mimem narrate paper.ir.json -o out/plain
```

A straight reading: the retained content, verbalized, with no prequestions, retrieval or spacing.
Useful for seeing what the structural layer actually adds, and as a fallback when a document
defeats the planner.

## `rules`

```bash
uv run mimem rules
uv run mimem rules --check
```

Every rule the linter runs, what it reads, and its severity. `--check` exits non-zero if a rule
is *defined but never registered* — a rule the linter never calls is a rule that does not exist,
and enumerating classes and enumerating the registry are different questions.

For the harder question — whether a *test* would fail if a rule silently stopped working — run
`tools/mutate_rules.py`, which answers it by breaking each rule in turn.

## `compare`

```bash
uv run mimem compare paper.pdf --fixtures fixtures/paper
```

Builds one document twice, deterministic and model-assisted, and diffs the metrics. The
deterministic build is the control; the difference is what the model was worth.

| | |
|---|---|
| `--out` / `-o` | Where both builds go. Default `out/compare`. |
| `--fixtures` | Compare against a recorded run, so the comparison is free. |
| `--provider`, `--model`, `--base-url` | As for `build`. |
| `--budget` | Hard cap in US dollars. |
| `--json` | Print the comparison as JSON. |

Writes `<out>/local/` and `<out>/with-model/`, so both programmes are there to read.

## `doctor`

```bash
uv run mimem doctor
uv run mimem doctor --live
```

What AI is reachable from this machine, and the exact next thing to type for whatever is not.
Run it first, and run it when something stops working.

| | |
|---|---|
| `--live` | Send one tiny structured request to each configured provider. |
| `--model` | The model to use for `--live`. |

Without `--live` it reads configuration only and makes no network call, so it is free and
instant. With it, it proves the credentials work rather than merely existing. See [Using a
model](../ai/index.md).

## `record`

```bash
uv run mimem record paper.pdf --out fixtures/paper --provider openai
```

Runs stage 6 against a live model once and keeps every answer as a fixture, so that

```bash
uv run mimem build paper.pdf --fixtures fixtures/paper
```

is free and identical for ever after.

| | |
|---|---|
| `--out` / `-o` | Where the fixtures go. Default `fixtures/`. |
| `--provider` | `anthropic`, `openai` or `local`. |
| `--model`, `--base-url` | As for `build`. |
| `--budget` | Hard cap in US dollars. |

**This is the one command that always bills**, which is why it is separate from `build` rather
than a flag on it.

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
| `ANTHROPIC_API_KEY` | Only read with `--llm --provider anthropic`. |
| `OPENAI_API_KEY` | Only read with `--llm --provider openai`, and by the `openai` speech engine. |
