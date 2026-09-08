---
icon: lucide/cloud
---

# A hosted API

The best quality, and the only option here that costs money. Read [Without a
key](no-key.md) first if you have not: for most people the assistant route is better *and*
free.

## Anthropic

```bash
uv pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-ant-...
uv run mimem doctor --live
```

```bash
uv run mimem build paper.pdf --out out/paper --llm --provider anthropic
```

`--provider anthropic` is the default when you pass `--llm`, so it can be left off. `--model`
picks a different one; the default is the capable model rather than the cheap one, deliberately
— downgrading should be a decision you measure, not one the tool makes for you.

## OpenAI, and everything shaped like it

```bash
export OPENAI_API_KEY=sk-...
uv run mimem build paper.pdf --out out/paper --llm --provider openai --model gpt-4o-mini
```

The same adapter reaches anything serving `POST /chat/completions`, which is most of the market.
Point `--base-url` at it:

| Provider | `--base-url` |
|---|---|
| OpenAI | *(default)* |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Together | `https://api.together.xyz/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| DeepInfra | `https://api.deepinfra.com/v1/openai` |

```bash
uv run mimem build paper.pdf --llm --provider openai \
  --base-url https://openrouter.ai/api/v1 --model anthropic/claude-3.5-sonnet
```

The key comes from `OPENAI_API_KEY` whatever the host, so export the one that provider issued.

## Knowing the cost before you pay it

```bash
uv run mimem elaborate out/paper/doc.ir.json --dry-run
```

prints every planned call and an estimate, and makes none of them. Then cap the real run:

```bash
uv run mimem build paper.pdf --llm --budget 2.00
```

`--budget` is a hard stop, not a warning: the run ends and keeps the artefacts it had already
produced.

Two things make a paper cheaper than the call count suggests. The source document is sent as a
**cached prefix**, so the second task on a document is a fraction of the first. And answers are
**cached by content**, so re-running after an edit re-asks only about what changed.

## Record once, replay for ever

```bash
uv run mimem record paper.pdf --out fixtures/paper --provider openai
uv run mimem build paper.pdf --fixtures fixtures/paper
```

The second command is free and gives byte-identical elaborations. Worth doing on any document
you will build more than twice, and the only honest way to compare two changes to the rest of
the pipeline — otherwise the model moves underneath the comparison.

## What is checked before anything reaches you

Every generated sentence goes through the grounding gate:

- **numbers** — every digit-bearing token must appear in the source sentences it was written
  from;
- **years** — a wrong one is impossible to catch by ear;
- **directions** — if the model says a quantity *increases* and the source says it *decreases*,
  the claim is rejected. This is the check the rule exists for, and the only one that catches a
  failure which reads perfectly;
- **names** — a capitalised word the source never uses, reported as a warning.

Rejections are not failures. The task takes its degradation path, the manifest records it, and
the elaboration report tells you how many were rejected and why. A run with rejections is the
system working.

## When it goes wrong

| What you see | What it means |
|---|---|
| `rejected the credentials (401)` | wrong or expired key |
| `is rate-limiting or out of quota (429)` | wait, or check your billing |
| `...was not found (404)` | the base URL usually ends in `/v1`; check the model name |
| `did not produce FigureOut in 3 attempts` | this model cannot hold that schema |
| `no model configured` | you did not pass `--llm` |

!!! warning "Neither hosted adapter has been run against a real key"

    There is no API key in the environment mimem is developed in. The Anthropic adapter is
    type-checked against the installed SDK — which caught one real bug — and the
    OpenAI-compatible one is tested thoroughly against a fake server, including every failure
    path in the table above. Neither has made a real request. Run `mimem doctor --live` and try
    one short paper before pointing either at a book.
