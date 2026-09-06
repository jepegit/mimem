---
icon: lucide/message-square
---

# Using it from Claude or ChatGPT

mimem produces a script. Two things are missing before that is useful on its own: a voice, and
something that comes back tomorrow to ask you about it. An assistant cannot be a voice — that is
still to come — but it can be everything else, and it can write the explanations that otherwise
need a paid API key.

With this set up you can say **"make me a study programme from this paper"** and then, days
later, **"quiz me on what's due"**.

## Set it up

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), and the app.

=== "Claude Desktop"

    Open **Settings → Developer → Edit Config**, and add mimem to `mcpServers`:

    ```json
    {
      "mcpServers": {
        "mimem": {
          "command": "uvx",
          "args": [
            "--from", "git+https://github.com/jepegit/mimem",
            "--with", "mcp",
            "mimem-mcp"
          ]
        }
      }
    }
    ```

    Restart Claude Desktop. mimem's tools appear under the connectors icon.

=== "ChatGPT Desktop"

    **Settings → Connectors → Advanced → Developer mode**, then add a connector of type
    **STDIO** with the command:

    ```
    uvx --from git+https://github.com/jepegit/mimem --with mcp mimem-mcp
    ```

    Restart, and the tools appear.

=== "Already cloned it"

    ```json
    {
      "mcpServers": {
        "mimem": {
          "command": "uv",
          "args": ["run", "--directory", "/path/to/mimem", "mimem-mcp"]
        }
      }
    }
    ```

=== "Claude Code"

    No server needed — there is a skill:

    ```bash
    uv run mimem build paper.pdf --out out/paper
    ```

    and ask it to quiz you from `out/paper/cards.json`.

!!! warning "ChatGPT on the web cannot do this"

    Web clients only reach servers on the internet. This one runs on your machine, which is the
    point — your papers never leave it. Use the desktop app.

## Try it

> **Make a study programme from ~/Downloads/paper.pdf**

It builds, and tells you how long the programme is, how it is structured, what it thinks the key
ideas are, and whether anything failed the design rules. Nothing is uploaded anywhere; the files
land in `~/mimem/programmes/`.

> **Now write the explanations yourself**

This is the good part. The assistant fetches the concepts that want explaining, along with the
paper's own sentences about each one, writes the glosses, the concrete images and the analogies,
and sends them back.

**And they are checked.** Every number in what it wrote is looked up in the sentences it was
given; a claim that reverses a direction the paper states is rejected. Not warned about —
rejected, and reported back so it can try again. This is the same check that runs when a paid API
writes them, which is why letting the conversation do it is safe:

> *Rejected — gloss for "solid electrolyte interphase": number '41.85' does not appear in the
> cited source. Rewrite it using only what the source sentences say.*

> **Read me the opening**

One section at a time. A hundred-minute programme is fifteen thousand words, so the tools return
summaries and let you ask for the parts you want.

## The part that makes it worth doing

> **Quiz me on what's due**

Every question mimem generated is a card, and answering one is recorded. Get it right and it
comes back later; get it wrong and it comes back tomorrow. That is the spacing effect, which is
the largest thing in [the science](../science/index.md) and the reason any of this exists.

Ask for a session the next day and it will know which cards are ready and which you have never
seen.

The log is a plain text file at `~/mimem/reviews.jsonl`, one line per answer. You can read it,
graph it, or delete it.

## Where things are

| | |
|---|---|
| `~/mimem/programmes/<name>/` | One directory per programme: `audio.md`, `study.md`, `cards.json`, `manifest.json`, and every intermediate stage |
| `~/mimem/reviews.jsonl` | Every answer you have given |
| `MIMEM_WORKSPACE` | Set it to put all of that somewhere else |

`audio.md` is what you hand to a speech engine. mimem does not synthesise it yet — that is the
next milestone — so for now: `say -f audio.md` on macOS, or paste it into a web reader.

## What it can do

| | |
|---|---|
| **Build a programme** | From a file on your machine, a link, or text pasted into the chat |
| **Write the explanations** | Glosses, concrete images, analogies — checked against the paper |
| **Read it back** | The outline, or one section of the audio or study track |
| **Quiz you** | What is due, across every programme |
| **Record how it went** | And schedule the next showing |
| **Explain a choice** | Which rule produced a beat, and which sentence it came from |
| **Take a correction** | Disagree with a ranking; it survives every future run |

## If it does not show up

??? failure "The tools do not appear after restarting"

    Check `uvx --from git+https://github.com/jepegit/mimem --with mcp mimem-mcp` runs in a
    terminal. It should sit there silently waiting for input — that is a working server. Ctrl-C
    to stop it. If it fails, the error will say why.

??? failure "It cannot find my PDF"

    Give the full path — `/Users/you/Downloads/paper.pdf`, not `paper.pdf`. The assistant cannot
    see where a chat attachment lives on disk; if you only have it as an attachment, ask the
    assistant to pass the text instead.

??? failure "Everything is rejected when it writes the explanations"

    Working as intended, and worth reading: the rejections say which number or direction the
    paper does not support. If they look wrong, that is a bug worth
    [reporting](https://github.com/jepegit/mimem/issues).

??? failure "It read the whole programme into the chat"

    Ask it to read one section at a time. The tools return summaries by default, but an assistant
    can always ask for more than it needs.
