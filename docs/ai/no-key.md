---
icon: lucide/key-round
---

# Without a key

This page is first because it covers most people. You need no API key, no account and no local
model to get everything mimem is actually *for*.

## What works with nothing configured

```bash
uv run mimem build paper.pdf --out out/paper
```

That is the whole pipeline: the paper read, triaged, verbalized, laid out as a programme with
questions and pauses and spacing, rendered to four files, and checked against thirty lint rules.
It exits non-zero if it broke one.

You get `audio.md`, `study.md`, `cards.json` and `manifest.json`. Add `--speak sapi` on Windows,
or `--speak silent` anywhere, and you get `audio.wav` too — see [Turning it into
audio](../listening/audio.md).

**What you do not get** is the explaining layer: no one-line glosses beyond the ones the paper
writes for itself, no concrete anchors, no analogies, no figure descriptions. The manifest lists
each one as degraded, with the fallback it took. Nothing is invented to fill the gap.

## The assistant route: a model, still no key

The best option for most people. mimem ships an MCP server, so the assistant you are already
talking to does the explaining — no key, no billing, and you watch every number get checked.

=== "Claude Desktop"

    Download **[mimem.mcpb](https://github.com/jepegit/mimem/releases/latest/download/mimem.mcpb)**,
    then **Settings → Extensions → Install extension** and pick the file.

    Then say *"make me a study programme from this paper"*, and days later, *"quiz me on what's
    due"*. Full instructions, including the settings the extension exposes, are on
    [Using it from Claude or ChatGPT](../listening/assistant.md).

=== "Claude Code"

    ```bash
    claude mcp add mimem -- uvx --from git+https://github.com/jepegit/mimem --with mcp mimem-mcp
    ```

=== "Cursor"

    Create `.cursor/mcp.json` in your project, or `~/.cursor/mcp.json` for every project:

    ```json
    {
      "mcpServers": {
        "mimem": {
          "command": "uvx",
          "args": ["--from", "git+https://github.com/jepegit/mimem",
                   "--with", "mcp", "mimem-mcp"],
          "env": {"MIMEM_WORKSPACE": "~/mimem"}
        }
      }
    }
    ```

=== "ChatGPT Desktop"

    **Settings → Connectors → Advanced → Developer mode**, then add a connector of type
    **STDIO**. The command is the same `uvx` line as above.

All of these need [uv](https://docs.astral.sh/uv/) on your PATH; `mimem doctor` checks for it.

!!! note "Which of these are verified"

    The Claude Desktop extension is tested end to end — installed, eleven tools listed, tools
    called. The underlying server is verified to speak MCP correctly over stdio, which is what
    every host on this page uses. The specific config *files* for Cursor and ChatGPT follow each
    host's documented format and have not been tested here; if one is wrong, please open an
    issue and it will be fixed rather than left to be discovered again.

## What the assistant can and cannot do

It writes the explanations, describes figures, and runs study sessions across days. It **cannot
synthesise audio** — speech is a CLI command, because a speech engine is a different kind of
thing from a conversation. Build the programme through the assistant, then:

```bash
uv run mimem speak ~/mimem/programmes/<id> --engine sapi
```

## Recording a fixture set

If you ever *do* run a paid model, keep the answers:

```bash
uv run mimem record paper.pdf --out fixtures/paper
uv run mimem build paper.pdf --fixtures fixtures/paper   # free, forever, identical
```

One paid run becomes a set anyone can replay for nothing. It is how the worked example in these
docs stays reproducible and how the test suite stays free.
