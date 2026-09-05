"""A content-addressed cache, so editing one paragraph does not re-pay for the document.

Keyed on the request digest, which covers the task, the whole prompt, the model and the output
schema (see :meth:`Request.digest`). Anything that could change the answer changes the key, so a
hit is a hit for the right reasons -- an old answer validated against a since-changed schema is
not a cache hit, it is a bug waiting for a strange afternoon.

Wrapping rather than inheriting: :class:`Cached` is a client that consults the store first and
delegates on a miss, so it composes with every transport including the recording one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mimem.llm.client import BaseClient, Client, Request, Response


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    written: int = 0

    @property
    def rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def summary(self) -> str:
        return f"{self.hits} hit(s), {self.misses} miss(es) ({self.rate:.0%} cached)"


@dataclass
class Cached(BaseClient):
    """A client that answers from disk when it can."""

    inner: Client
    directory: Path
    stats: CacheStats = field(default_factory=CacheStats)
    read_only: bool = False

    def path_for(self, request: Request) -> Path:
        # One directory per task keeps a hand-inspection of the cache navigable, which matters
        # more than it sounds: reading a cached answer is how you find out what the model
        # actually said when the output looks wrong.
        return Path(self.directory) / request.task / f"{request.digest()}.json"

    def complete(self, request: Request) -> Response:
        path = self.path_for(request)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.stats.hits += 1
            return Response(
                data=self._validate(request, payload["output"]),
                model=payload.get("model", request.model),
                source="cache",
            )

        self.stats.misses += 1
        response = self.inner.complete(request)
        if not self.read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "task": request.task,
                        "model": response.model,
                        "digest": request.digest(),
                        "output": response.data.model_dump(mode="json"),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.stats.written += 1
        return response
