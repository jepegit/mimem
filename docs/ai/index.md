---
icon: lucide/brain-circuit
---

# Using a model with mimem

**None of this is required.** mimem's whole argument is that structure matters more than
fluency, and the structure is deterministic: a document goes in and a listenable, checkable
programme comes out with no model involved at all. What a model adds is the explaining — a
one-line gloss, a concrete anchor, an analogy that says where it breaks down, a description of a
figure you cannot see.

Start here:

```bash
uv run mimem doctor
```

It says what is reachable from your machine and, for everything that is not, the exact next
thing to type. On a machine with nothing configured it looks like this — which is a real run,
on the machine mimem is developed on:

```
text generation
  assistant  ready         no key needed; the model is the conversation
  anthropic  no key
             -> export ANTHROPIC_API_KEY=sk-ant-...
  openai     no key
             -> export OPENAI_API_KEY=sk-...
  local      missing       nothing listening on 11434, 1234, 8080, 8000
             -> ollama serve   (or start LM Studio / llama-server / vLLM)

speech
  silent     ready         always available; makes shaped silence
  sapi       ready         9 voices installed
  piper      missing       not on PATH
  openai     no key

tools
  ffmpeg     ready         available for converting audio.wav
  uv         ready         the extension needs it at first start
```

`mimem doctor --live` sends one tiny structured request to each configured provider, because
*the key is set* and *the key works* are different claims.

## Four ways in, in the order most people should try them

| | Needs | Cost | Page |
|---|---|---|---|
| **The assistant** | Claude Desktop, Cursor, or any MCP host | nothing | [Without a key](no-key.md) |
| **A local model** | Ollama or similar, a few GB of disk | nothing | [Local models](local.md) |
| **An API** | a key | cents per paper | [Hosted APIs](api.md) |
| **Nothing at all** | — | nothing | [Without a key](no-key.md) |

The assistant route is first on purpose. It inverts the problem: the model is the conversation
you are already in, so there is no key, no billing and no provider to configure. It is not a
workaround for people who cannot afford an API — for most users it is simply the best option.

## What a model is and is not allowed to do

The division is the whole safety argument, and it is worth knowing before you turn any of this
on:

**Deterministic code owns every fact.** Numbers, units, symbols, what gets dropped, what comes
back and when — none of that is ever a model's decision. Rule `NUM-01` and the verbalizers own
values; the planner owns structure.

**A model owns prose, and every sentence it writes is checked.** Every number in a generated
sentence must appear in the source sentences it was written from; a claim that reverses the
paper's direction is rejected before it reaches the programme (`GRD-03`). You can watch that
happen — the elaboration report lists what was accepted, what was rejected and why.

**When the model is absent, every task degrades along a documented path** and the manifest
records it. A gloss falls back to the paper's own definitional sentence; an anchor is omitted
rather than invented; a figure falls back to its caption. That is why `--local` is the default
and why a forgotten flag cannot start billing you.

## Cost, briefly

`--dry-run` prints the planned calls and an estimate without making any. `--budget 2.00` stops
the run rather than surprising you. Both work with every provider.

A model is called at most a few dozen times per paper — once per concept that earns an
elaboration, once per figure, once per verification — and the source document is sent as a
cached prefix, so the second task on a document costs a fraction of the first.

!!! warning "The live API adapters have had limited exercise"

    The Anthropic adapter has never been run against a real key: there was none in the
    environment it was written in. The OpenAI-compatible adapter is tested thoroughly against a
    fake server — the schema negotiation, the retries, the error paths — but has not been run
    against a real OpenAI or Ollama server either. The assistant route and the whole
    deterministic pipeline *are* exercised. Try any API path on one short paper before pointing
    it at a book, and please report what happens.
