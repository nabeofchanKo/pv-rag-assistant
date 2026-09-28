"""Per-run cost / latency telemetry (Phase 6).

No network: the graph runs on the fake services from test_triage_graph, with one
of them calling a fake chat model that reports token usage the way ChatOpenAI
does. Pins: the price math, that calls are attributed to the step they ran in
(including the parallel branches), that the paused human-review gate is not
counted as a step, and that telemetry survives the pause → approve round trip.
"""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.schemas import ReviewDecision
from app.services.telemetry import UsageCollector, cost_usd, price_of

from .test_triage_graph import (
    FakeCausality,
    FakeExtraction,
    FakeProductMaster,
    FakeSeriousness,
    _ae,
    _build,
    _drugx,
)

# --- price table ---


def test_dated_snapshots_resolve_and_mini_is_never_billed_as_4o():
    assert price_of("gpt-4o-2024-08-06") == price_of("gpt-4o")
    assert price_of("gpt-4o-mini-2024-07-18") == price_of("gpt-4o-mini")
    assert price_of("gpt-4o-mini") != price_of("gpt-4o")


def test_cached_input_is_billed_at_the_cached_rate():
    # gpt-4o: $2.50 in / $1.25 cached / $10.00 out per 1M
    assert cost_usd("gpt-4o", 1_000_000, 0, 0) == pytest.approx(2.50)
    assert cost_usd("gpt-4o", 1_000_000, 1_000_000, 0) == pytest.approx(1.25)
    assert cost_usd("gpt-4o", 0, 0, 1_000_000) == pytest.approx(10.00)


def test_unknown_model_is_unpriced_not_guessed():
    assert cost_usd("elyza-jp-8b", 1000, 0, 100) is None


# --- attribution through the real graph ---


class _PricedFake(GenericFakeChatModel):
    """Fake chat model that identifies as a priced model, like ChatOpenAI does."""

    model_label: str = "gpt-4o"

    def _get_ls_params(self, stop=None, **kwargs):
        return {**super()._get_ls_params(stop=stop, **kwargs), "ls_model_name": self.model_label}


def _usage(n_in, n_out, cached=0):
    return AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": n_in, "output_tokens": n_out, "total_tokens": n_in + n_out,
            "input_token_details": {"cache_read": cached},
        },
    )


class LlmSeriousness(FakeSeriousness):
    """Seriousness that really calls a (fake) model — on the meddra → seriousness
    branch, which runs in parallel with causality / expectedness."""

    def __init__(self, llm):
        super().__init__("非重篤")
        self.llm = llm

    def assess(self, text, events):
        self.llm.invoke("judge")  # no config passed — must be picked up anyway
        return super().assess(text, events)


class LlmCausality(FakeCausality):
    def __init__(self, llm):
        super().__init__("否定できない")
        self.llm = llm

    def assess(self, text, events, suspect_drugs):
        self.llm.invoke("judge")
        return super().assess(text, events, suspect_drugs)


def _graph(ser_llm, cau_llm, checkpointer=None):
    return _build(
        FakeProductMaster(_drugx()),
        FakeExtraction([_ae("頭痛")]),
        LlmSeriousness(ser_llm),
        LlmCausality(cau_llm),
        checkpointer=checkpointer,
    )


def test_calls_are_attributed_to_their_step_and_priced():
    ser_llm = _PricedFake(messages=iter([_usage(1000, 100, cached=400)]), model_label="gpt-4o")
    cau_llm = _PricedFake(messages=iter([_usage(2000, 50)]), model_label="gpt-4o-mini")
    usage = UsageCollector()

    _graph(ser_llm, cau_llm).invoke(
        {"text": "t", "document_name": "c.txt", "auto_approve": True},
        {"callbacks": [usage]},
    )
    t = usage.summary()
    by = {s.step: s for s in t.steps}

    ser, cau = by["seriousness"], by["causality"]
    assert (ser.llm_calls, ser.models, ser.input_tokens, ser.cached_input_tokens, ser.output_tokens) == (
        1, ["gpt-4o"], 1000, 400, 100,
    )
    assert ser.cost_usd == pytest.approx(cost_usd("gpt-4o", 1000, 400, 100))
    assert (cau.models, cau.input_tokens, cau.output_tokens) == (["gpt-4o-mini"], 2000, 50)

    # Deterministic steps still appear — with their time, and no tokens.
    assert by["product_match"].llm_calls == 0 and by["product_match"].cost_usd == 0
    assert t.total_input_tokens == 3000 and t.total_output_tokens == 150
    assert t.total_cost_usd == pytest.approx(ser.cost_usd + cau.cost_usd)
    assert t.cost_complete
    # Steps are in start order, and all fall inside the run.
    starts = [s.started_ms for s in t.steps]
    assert starts == sorted(starts) and t.steps[0].step == "product_match"
    assert all(s.started_ms + s.latency_ms <= t.wall_ms for s in t.steps)


def test_unpriced_model_makes_the_total_incomplete_not_wrong():
    ser_llm = _PricedFake(messages=iter([_usage(1000, 100)]), model_label="elyza-jp-8b")
    cau_llm = _PricedFake(messages=iter([_usage(1000, 100)]), model_label="gpt-4o")
    usage = UsageCollector()
    _graph(ser_llm, cau_llm).invoke(
        {"text": "t", "document_name": "c.txt", "auto_approve": True}, {"callbacks": [usage]}
    )
    t = usage.summary()

    assert {s.step: s.cost_usd for s in t.steps}["seriousness"] is None
    assert not t.cost_complete
    assert t.total_cost_usd == pytest.approx(cost_usd("gpt-4o", 1000, 0, 100))


def test_paused_review_is_not_a_step_and_telemetry_survives_approval():
    ser_llm = _PricedFake(messages=iter([_usage(10, 1)]))
    cau_llm = _PricedFake(messages=iter([_usage(10, 1)]))
    graph = _graph(ser_llm, cau_llm, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "tel"}}
    usage = UsageCollector()

    # What the router does: run to the review gate, then store the summary.
    graph.invoke({"text": "t", "document_name": "c.txt"}, {**cfg, "callbacks": [usage]})
    telemetry = usage.summary()
    graph.update_state(cfg, {"telemetry": telemetry})

    assert "human_review" not in {s.step for s in telemetry.steps}
    assert graph.get_state(cfg).next == ("human_review",)  # still paused for a person

    graph.invoke(Command(resume=ReviewDecision(action="approve", reviewer="r").model_dump()), cfg)
    vals = graph.get_state(cfg).values
    assert vals["status"] == "approved"
    assert vals["telemetry"] == telemetry
