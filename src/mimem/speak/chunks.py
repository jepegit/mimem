"""Stage 9: the script as a list of things to synthesise (rules TTS-02, TTS-03, TTS-04).

This is the neutral form every engine adapter receives. It is deliberately thin: an id, some
text, and how much silence follows. Everything an engine might be tempted to interpret --
emphasis, rate, the fact that this beat is a question -- has already been spent, in the wording
and the punctuation, by the time the script exists (``TTS-02``). An adapter that reached for
``<prosody>`` here would be adding something the linter never checked.

**Why the pause is a number and not a marker.** ``PAU-01`` gives a retrieval prompt a real
silence, and the plan's own rule set forbids putting it in ``audio.md``, where it would be
either unspeakable characters or words the engine reads aloud. So it travels here, as seconds,
and :mod:`mimem.speak.assemble` turns it into actual silence rather than asking the engine for
a break it may or may not honour. Two engines therefore produce the *same* pauses, which is
what ``TTS-05``'s "engine choice must not change the content" means in practice.

**Why the id is content-addressed.** Change one sentence in one beat and only that beat's audio
is stale. :mod:`mimem.speak.cache` keys on the digest of what was actually sent to the engine,
so a re-run after an edit re-synthesises the beats that changed and no others.
"""

from __future__ import annotations

from dataclasses import dataclass

from mimem.ir import Script, text_sha256


@dataclass(frozen=True, slots=True)
class SpeechChunk:
    """One request to an engine, and the silence that follows it."""

    id: str
    text: str
    pause_after: float
    at_seconds: float
    sha256: str

    @property
    def has_pause(self) -> bool:
        return self.pause_after > 0.0


def speech_chunks(script: Script) -> list[SpeechChunk]:
    """The script as an ordered list of synthesis requests.

    The same beats, in the same order, that ``manifest.json`` lists as chunks -- both ask
    :attr:`~mimem.ir.Beat.spoken`, so the audio cannot come to contain a beat the audit trail
    does not mention, or omit one it does.
    """
    return [
        SpeechChunk(
            id=beat.id,
            text=beat.text.strip(),
            pause_after=beat.pause_after,
            at_seconds=at,
            sha256=text_sha256(beat.text),
        )
        for beat, at in script.timeline()
        if beat.spoken
    ]
