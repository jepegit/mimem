"""Why the chunk ids are content-addressed (rule TTS-03).

Synthesis is the one stage of the pipeline that is slow or costs money, and it is also the one
whose input barely changes between runs. Fix a verbalizer bug that touches four sentences in a
ninety-minute programme and, without a cache, you pay for ninety minutes again.

The key is the digest of the text actually sent to the engine, plus the engine's own
fingerprint. Both halves matter. Text alone would replay the old voice from disk after you
switched voices, which is a bug that looks like the flag being ignored. The fingerprint alone
would be useless. The chunk *id* is deliberately not part of the key: two beats with identical
text synthesise to identical audio, and there is no reason to pay twice.

Nothing here expires. The store is a directory of small WAVs beside the programme they belong
to, and deleting it is the whole of cache invalidation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

#: Directory name inside the output directory. Hidden, because it is not an artefact.
CACHE_DIR = ".speech"


def key_for(text: str, fingerprint: str) -> str:
    """The cache key: what was said, and what said it."""
    digest = hashlib.blake2s(digest_size=16)
    digest.update(fingerprint.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(text.encode("utf-8", errors="replace"))
    return digest.hexdigest()


@dataclass(slots=True)
class SpeechCache:
    """WAV bytes on disk, keyed by content."""

    root: Path
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def get(self, key: str) -> bytes | None:
        path = self.path_for(key)
        if not path.exists():
            self.misses += 1
            return None
        data = path.read_bytes()
        if not data:
            # An interrupted write leaves an empty file. Treat it as absent rather than
            # letting a zero-byte WAV reach the decoder and be reported as an engine fault.
            self.misses += 1
            return None
        self.hits += 1
        return data

    def put(self, key: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path_for(key)
        # Write beside and rename, so an interrupted run cannot leave a truncated WAV that a
        # later run would happily play half of.
        scratch = target.with_suffix(".partial")
        scratch.write_bytes(data)
        scratch.replace(target)


@dataclass(slots=True)
class NullCache:
    """Synthesise everything, every time. What ``--no-cache`` selects."""

    hits: int = 0
    misses: int = 0

    def get(self, key: str) -> bytes | None:
        self.misses += 1
        return None

    def put(self, key: str, data: bytes) -> None:
        return None
