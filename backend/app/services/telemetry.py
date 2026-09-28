"""Per-run cost and latency, measured rather than estimated (Phase 6).

``UsageCollector`` is a LangChain callback handler passed to ``graph.invoke``.
It needs no cooperation from the six evaluation services: LangGraph propagates
the run's callbacks to every model call made inside a node — including the
parallel branches, which run on other threads — and tags each call with the
node it ran in (``metadata["langgraph_node"]``). So one handler sees:

* every node start/end  → per-step latency and its offset from the run start
* every chat-model call → tokens (``usage_metadata``), attributed to its step

and the services stay unaware they are being measured.

Chat models only. Embedding calls (label / MedDRA retrieval) do not go through
the chat-model callbacks; at this corpus size they are well under a cent.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.schemas import RunTelemetry, StepTelemetry

# USD per 1M tokens: (input, cached input, output). Standard tier, checked on
# OpenAI's pricing page on PRICING_AS_OF. A model missing here is shown as
# "unpriced" rather than guessed; the local (Ollama) models run on our own
# hardware, so they have no per-token price by design.
PRICING_AS_OF = "2026-09-28"
PRICES_PER_1M: dict[str, tuple[float, float, float]] = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4o": (2.50, 1.25, 10.00),
}


def price_of(model: str) -> tuple[float, float, float] | None:
    """Price row for a model name, tolerating dated snapshots
    ("gpt-4o-2024-08-06"). Longest prefix first, so gpt-4o-mini is never
    billed as gpt-4o."""
    for name in sorted(PRICES_PER_1M, key=len, reverse=True):
        if model == name or model.startswith(name + "-"):
            return PRICES_PER_1M[name]
    return None


def cost_usd(model: str, input_tokens: int, cached: int, output_tokens: int) -> float | None:
    price = price_of(model)
    if price is None:
        return None
    p_in, p_cached, p_out = price
    fresh = input_tokens - cached
    return (fresh * p_in + cached * p_cached + output_tokens * p_out) / 1_000_000


@dataclass
class _Step:
    started: float
    ended: float | None = None
    llm_calls: int = 0
    models: set[str] = field(default_factory=set)
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = 0.0


class UsageCollector(BaseCallbackHandler):
    """Collects one run's telemetry. Create one per ``graph.invoke``; thread-safe
    because parallel branches report from worker threads."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._lock = threading.Lock()
        self._steps: dict[str, _Step] = {}
        self._node_runs: dict[UUID, str] = {}  # node run_id -> step name
        self._llm_runs: dict[UUID, tuple[str, str | None]] = {}  # run_id -> (step, model)

    # --- node boundaries ---
    # Every runnable inside a node carries the node's name in its metadata; the
    # node itself is the one whose own name matches it.

    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, **kwargs: Any):
        node = (metadata or {}).get("langgraph_node")
        if node and kwargs.get("name") == node:
            with self._lock:
                self._node_runs[run_id] = node
                self._steps.setdefault(node, _Step(started=time.perf_counter()))

    def on_chain_end(self, outputs, *, run_id, **kwargs: Any):
        with self._lock:
            node = self._node_runs.pop(run_id, None)
            if node:
                self._steps[node].ended = time.perf_counter()

    def on_chain_error(self, error, *, run_id, **kwargs: Any):
        # human_review "fails" with GraphInterrupt when it pauses — it is waiting
        # for a person, not doing work, so it is not a step of this run.
        with self._lock:
            node = self._node_runs.pop(run_id, None)
            if node:
                self._steps.pop(node, None)

    # --- model calls ---

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs: Any):
        meta = metadata or {}
        step = meta.get("langgraph_node")
        if step:
            model = meta.get("ls_model_name") or (kwargs.get("invocation_params") or {}).get("model")
            with self._lock:
                self._llm_runs[run_id] = (step, model)

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs: Any):
        with self._lock:
            entry = self._llm_runs.pop(run_id, None)
        if entry is None:
            return
        step_name, model = entry
        model = model or (response.llm_output or {}).get("model_name") or "unknown"

        usage: dict = {}
        gens = response.generations[0] if response.generations else []
        message = getattr(gens[0], "message", None) if gens else None
        if message is not None and getattr(message, "usage_metadata", None):
            usage = message.usage_metadata
        n_in = int(usage.get("input_tokens", 0))
        n_out = int(usage.get("output_tokens", 0))
        n_cached = int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0)
        cost = cost_usd(model, n_in, n_cached, n_out)

        with self._lock:
            step = self._steps.setdefault(step_name, _Step(started=time.perf_counter()))
            step.llm_calls += 1
            step.models.add(model)
            step.input_tokens += n_in
            step.cached_input_tokens += n_cached
            step.output_tokens += n_out
            step.cost = None if (step.cost is None or cost is None) else step.cost + cost

    # --- result ---

    def summary(self) -> RunTelemetry:
        now = time.perf_counter()
        ms = lambda seconds: int(round(seconds * 1000))  # noqa: E731
        with self._lock:
            steps = sorted(self._steps.items(), key=lambda kv: kv[1].started)
            return RunTelemetry(
                wall_ms=ms(now - self._t0),
                pricing_as_of=PRICING_AS_OF,
                steps=[
                    StepTelemetry(
                        step=name,
                        started_ms=ms(s.started - self._t0),
                        latency_ms=ms((s.ended or now) - s.started),
                        llm_calls=s.llm_calls,
                        models=sorted(s.models),
                        input_tokens=s.input_tokens,
                        cached_input_tokens=s.cached_input_tokens,
                        output_tokens=s.output_tokens,
                        cost_usd=s.cost,
                    )
                    for name, s in steps
                ],
            )
