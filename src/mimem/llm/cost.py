"""What a build will cost, before it costs it.

Two mechanisms, from the plan's cross-cutting concerns: a ``--dry-run`` that prints the planned
calls and an estimate, and a hard cap that aborts rather than surprising anyone. Both matter more
for a book than for a paper -- a 120 000-word book is ten to fifteen times a paper per full pass,
which is the number that will actually decide the default model per task.

The estimates here are **estimates**, from a token count that is itself approximate. They are
sized to answer "is this two dollars or two hundred", which is the question that changes a
decision, and they are replaced by measurements as soon as a real run has happened -- every
response carries its own usage, and :class:`Ledger` records what was actually spent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mimem.llm.client import Request, Response

#: Rough characters per token for English prose. Deliberately conservative: an underestimate
#: makes a budget cap fire late, which is the wrong direction to be wrong in.
CHARS_PER_TOKEN = 3.6

#: US dollars per million tokens. A table, not a lookup, because it changes and because a wrong
#: number here is visible: it is printed next to the estimate it produced.
PRICES: dict[str, tuple[float, float]] = {
    # model: (input, output)
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}

#: What a cached prefix costs to read, as a fraction of the input price.
CACHE_READ_FACTOR = 0.1

#: Batch requests are half price and not latency-sensitive, which is every bulk task here.
BATCH_FACTOR = 0.5


class BudgetExceededError(RuntimeError):
    """The build would cost more than the cap allows, so it stopped."""


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def price_for(model: str) -> tuple[float, float]:
    """Input and output price per million tokens, falling back to the most expensive listed."""
    if model in PRICES:
        return PRICES[model]
    return max(PRICES.values(), key=lambda p: p[0])


def estimate(request: Request, *, cached_prefix: bool = False, batch: bool = False) -> float:
    """Estimated dollars for one request."""
    prefix = estimate_tokens(request.system) + estimate_tokens(request.document)
    suffix = estimate_tokens(request.instruction)
    output = request.max_tokens // 2  # tasks return a sentence or two, not a full budget

    input_price, output_price = price_for(request.model)
    prefix_price = input_price * (CACHE_READ_FACTOR if cached_prefix else 1.0)
    cost = (prefix * prefix_price + suffix * input_price + output * output_price) / 1_000_000
    return cost * (BATCH_FACTOR if batch else 1.0)


@dataclass
class Plan:
    """What a run intends to do. The ``--dry-run`` report."""

    requests: list[Request] = field(default_factory=list)

    def add(self, request: Request) -> None:
        self.requests.append(request)

    @property
    def by_task(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for request in self.requests:
            out[request.task] = out.get(request.task, 0) + 1
        return out

    def total(self, *, batch: bool = False) -> float:
        """Estimated dollars, assuming the prefix is cached after the first call per document."""
        seen: set[str] = set()
        cost = 0.0
        for request in self.requests:
            key = request.system + request.document
            cost += estimate(request, cached_prefix=key in seen, batch=batch)
            seen.add(key)
        return cost

    def report(self, *, batch: bool = False) -> str:
        if not self.requests:
            return "no model calls planned"
        lines = [f"{n} x {task}" for task, n in sorted(self.by_task.items())]
        model = self.requests[0].model
        return (
            f"{len(self.requests)} call(s) to {model}: {', '.join(lines)}\n"
            f"  estimated ${self.total(batch=batch):.2f}"
            + (" with batching" if batch else "")
            + " -- an estimate, not a quote"
        )


@dataclass
class Ledger:
    """What a run actually spent. Replaces the estimate with a measurement."""

    cap: float | None = None
    spent: float = 0.0
    calls: int = 0
    cached_reads: int = 0

    def record(self, response: Response) -> None:
        if not response.billable:
            return
        input_price, output_price = price_for(response.model)
        fresh = max(0, response.input_tokens - response.cached_tokens)
        self.spent += (
            fresh * input_price
            + response.cached_tokens * input_price * CACHE_READ_FACTOR
            + response.output_tokens * output_price
        ) / 1_000_000
        self.calls += 1
        self.cached_reads += response.cached_tokens

    def check(self, upcoming: float = 0.0) -> None:
        """Raise before spending, not after."""
        if self.cap is not None and self.spent + upcoming > self.cap:
            raise BudgetExceededError(
                f"this build would spend ${self.spent + upcoming:.2f}, over the "
                f"${self.cap:.2f} cap; raise --budget or use --local"
            )

    def summary(self) -> str:
        if not self.calls:
            return "no billable calls"
        return f"{self.calls} call(s), ${self.spent:.2f} spent, {self.cached_reads} cached tokens"
