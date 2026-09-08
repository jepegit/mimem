"""Stage 6: the elaboration layer's transport, tasks, cache and cost control.

Everything a model is asked for lives here; what is done with the answers is
:mod:`mimem.elaborate`. The split matters because the second half has to work when the first
half is switched off -- ``--local`` mode runs the whole pipeline with :class:`NullClient` and
every task degrades along a documented path.
"""

from mimem.llm import tasks
from mimem.llm.cache import Cached, CacheStats
from mimem.llm.client import (
    DEFAULT_MODEL,
    AnthropicClient,
    BaseClient,
    Client,
    FixtureClient,
    LLMRefusedError,
    LLMUnavailableError,
    NullClient,
    RecordingClient,
    Request,
    Response,
    ScriptedClient,
)
from mimem.llm.cost import BudgetExceededError, Ledger, Plan, estimate, estimate_tokens
from mimem.llm.openai import OpenAICompatibleClient
from mimem.llm.reach import Check, State, survey
from mimem.llm.schemas import (
    AnalogyOut,
    AnchorOut,
    CompressOut,
    FigureOut,
    GlossOut,
    VerifyOut,
    WhyOut,
)

__all__ = [
    "DEFAULT_MODEL",
    "AnalogyOut",
    "AnchorOut",
    "AnthropicClient",
    "BaseClient",
    "BudgetExceededError",
    "CacheStats",
    "Cached",
    "Check",
    "Client",
    "CompressOut",
    "FigureOut",
    "FixtureClient",
    "GlossOut",
    "LLMRefusedError",
    "LLMUnavailableError",
    "Ledger",
    "NullClient",
    "OpenAICompatibleClient",
    "Plan",
    "RecordingClient",
    "Request",
    "Response",
    "ScriptedClient",
    "State",
    "VerifyOut",
    "WhyOut",
    "estimate",
    "estimate_tokens",
    "survey",
    "tasks",
]
