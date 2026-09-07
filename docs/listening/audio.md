---
icon: lucide/volume-2
---

# Turning it into audio

Everything up to this point produces a script that is *meant* to be spoken. This turns it into
a file you can play.

```bash
uv run mimem build paper.pdf --out out/paper --speak sapi
```

That is the whole thing: a PDF goes in, `out/paper/audio.wav` comes out, with the pauses in it.

If you already have a programme, synthesise it on its own:

```bash
uv run mimem speak out/paper --engine sapi --voice "Microsoft Zira Desktop"
```

## Choosing an engine

| `--engine` | Needs | Good for |
|---|---|---|
| `silent` | nothing | Seeing a programme's true length and shape before paying to voice it. The default. |
| `sapi` | Windows | Hearing whether a programme *works*, free and offline. Not a nice voice. |
| `piper` | a Piper install and a voice file | Listening properly, offline and free. |
| `openai` | a URL, usually a key | Listening properly, at the best quality, for money. |

List what a voice engine offers:

```bash
uv run mimem voices --engine sapi
```

`--engine openai` speaks the `POST /audio/speech` shape, which is not only OpenAI's: point
`--base-url` at a local [VoiceStudio](https://github.com/debpalash/VoiceStudio) or any other
compatible server and it is the same code path.

```bash
uv run mimem speak out/paper --engine openai --base-url http://localhost:8000/v1 --voice nova
```

!!! tip "Start with `silent`"

    It produces correctly-shaped silence at a plausible speaking rate, so you can check the
    length, the structure and the timing map without a voice, a key or a network. If something
    is wrong with the *programme*, this is where you find out, in a second and for nothing.

## What you get

`audio.wav`
: The programme. One WAV, uncompressed, because that is what concatenates exactly and needs no
    dependency to write. Convert it afterwards if you want something smaller.

`timings.json`
: Where every beat landed: its start, how long it actually ran, how long the pause after it
    actually was, and what the profile had predicted. This is what a player needs to jump to a
    beat, and what tells you whether the duration arithmetic is any good.

## The pauses are real silence

A retrieval prompt is only useful if the gap after it is long enough to actually try to
remember. mimem does not ask the engine for a break — engines vary in whether they honour one,
and `TTS-02` forbids relying on prosody markup — it inserts the silence itself, in frames,
during assembly.

Two consequences worth knowing. The pauses are exact, and they are identical whichever engine
you choose; that is what rule `TTS-05`'s *engine choice must not change the content* means in
practice. And a 20-minute programme typically contains around **two minutes of deliberate
silence**, which is not a bug in the file.

## The second run is cheap

Audio is cached by content. Fix one sentence, run again, and one beat is re-synthesised:

```
synthesising 89 beats with sapi
  19.9 min of audio, 1 beats synthesised, 88 reused from cache
```

The key is the text plus the engine and voice, so changing voice re-synthesises rather than
replaying the old one under a new name. Beats whose text is identical — the retrieval cue is
said many times in a programme — are synthesised once and heard as often as the script says.

`--no-cache` disables it. Deleting `out/paper/.speech` is the whole of cache invalidation.

## Predicted length versus real length

Every duration in mimem up to this point was a word count divided by the profile's
words-per-minute. Now there is a measurement to compare it against, and it prints on every run:

```
  19.9 min of audio, 73 beats synthesised, 16 reused from cache
  predicted 19.2 min, so 0.7 min over (4%)
```

Four percent, on that paper, through that engine — close, but consistently *short*, at a median
of about three-quarters of a second per beat. If you are tuning segment lengths, the real
numbers are in `timings.json`.

## Known limits

- **Output is WAV only.** A 20-minute programme is around 50 MB. Adding MP3 would mean shelling
    out to `ffmpeg`, which is a dependency and a platform matrix this project does not want.
- **`sapi` starts a PowerShell process per beat**, which costs about a second each: a 90-beat
    programme takes under two minutes to synthesise, and almost all of it is startup.
- **`piper` will not download a voice for you.** A tool that quietly pulls hundreds of megabytes
    from a third party on first run is not one to trust with your reading; fetch the `.onnx`
    yourself and pass it with `--voice`.
- **Nothing plays it for you yet.** Scheduling, playback and review across sessions are part
    two.
