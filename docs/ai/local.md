---
icon: lucide/cpu
---

# A model on your own machine

Free, private, and offline once the weights are downloaded. mimem talks to local runtimes
through the same adapter it uses for hosted APIs, because Ollama, llama.cpp, LM Studio, vLLM and
Jan all serve the OpenAI `/chat/completions` shape. The only difference is the URL.

## Ollama

```bash
ollama serve
ollama pull llama3.1:8b
```

Then check mimem can see it:

```bash
uv run mimem doctor
```

```
  local      configured    ollama on 11434
             -> mimem build paper.pdf --llm --provider local --base-url http://localhost:11434/v1
```

And run it:

```bash
uv run mimem build paper.pdf --out out/paper --llm --provider local --model llama3.1:8b
```

`--base-url` is optional when the server is on a default port: `--provider local` finds it.

## The others

| Runtime | Start it | Base URL |
|---|---|---|
| Ollama | `ollama serve` | `http://localhost:11434/v1` |
| LM Studio | start the app, **Developer → Start Server** | `http://localhost:1234/v1` |
| llama.cpp | `llama-server -m model.gguf --port 8080` | `http://localhost:8080/v1` |
| vLLM | `vllm serve <model>` | `http://localhost:8000/v1` |

`mimem doctor` probes all four ports, so if yours is running it will be found and named.

For anything on a non-standard port, or a server on another machine:

```bash
uv run mimem build paper.pdf --llm --provider local --base-url http://192.168.1.9:8080/v1
```

## Which models actually work

**This is the real question with local models, and it is not about quality.** mimem needs
*typed* answers — a `GlossOut` with a `short_def` and a `long_def`, a `FigureOut` with seven
fields and a confidence — and small models are much worse at holding a schema than at writing
the sentence inside it.

The adapter negotiates, once, down a ladder:

1. **`json_schema`** — the server validates the shape itself. Recent Ollama, vLLM, OpenAI.
2. **`json_object`** — the server guarantees valid JSON and nothing more; the schema goes in the
   prompt. Most local servers.
3. **prompted** — no server-side support at all; the reply is scanned for the first JSON object.

Below that, it retries twice, handing the model its own validation error. If it still cannot
produce the shape, **the task degrades** — it does not half-parse. A smaller programme is
something you can notice; a wrongly-filled one is not.

Rules of thumb, offered as starting points rather than measurements:

- **7–8B instruct models** generally manage `gloss` and `compress`. They are unreliable on
  `figure`, which has seven fields.
- **Below 7B**, expect frequent degradation. Check the elaboration report rather than assuming.
- **Vision** needs a multimodal model (`llama3.2-vision`, `qwen2-vl`, `gemma3`). Without one,
  figures fall back to their captions, which is a documented degradation and not a failure.

`mimem doctor --live` reports which rung your server settled on and how many schema retries the
probe needed. A server needing retries on a one-field ping will struggle with the real tasks.

## Expect it to be slow

A 98-page review produces dozens of requests, each carrying the source document as context. On a
laptop CPU that is minutes to hours; on a GPU with an 8B model, a few minutes. Two things help,
and both are on by default:

- **the cache** — answers are stored by content, so fixing one paragraph re-asks about that
  paragraph and nothing else;
- **`--dry-run`** — see how many calls a document will make before making any.

## When it goes wrong

| What you see | What it means |
|---|---|
| `could not reach http://localhost:11434/v1` | the server is not running — `ollama serve` |
| `...was not found (404)` | usually a missing `/v1`, or a model you have not pulled |
| `did not produce GlossOut in 3 attempts` | this model cannot hold that schema; try a larger one |
| everything degraded in the manifest | look at the elaboration report; it names each reason |

!!! warning "Not yet verified against a real server"

    The adapter is tested thoroughly against a fake server — every rung of the ladder, the
    retries, the wrapped-JSON cases, each HTTP failure — but it has not been run against a real
    Ollama or llama.cpp instance, because none is installed on the machine mimem is developed
    on. `mimem doctor` will tell you the truth about *your* machine. If something here is wrong,
    please say so.
