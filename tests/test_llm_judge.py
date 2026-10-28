import pytest

from agent_chaos import Level, RunContext, oracles


def make_ctx():
    return RunContext(0, [])


def test_llm_judge_passes_above_threshold():
    judge = oracles.llm_judge("quality", lambda ctx, result: 0.9, threshold=0.7)
    assert judge(make_ctx(), "anything") is None


def test_llm_judge_degraded_below_threshold():
    judge = oracles.llm_judge("quality", lambda ctx, result: 0.5, threshold=0.7)
    v = judge(make_ctx(), "anything")
    assert v.level == Level.DEGRADED and "0.50" in v.reason


def test_llm_judge_boundary_at_threshold_passes():
    judge = oracles.llm_judge("quality", lambda ctx, result: 0.7, threshold=0.7)
    assert judge(make_ctx(), "anything") is None


def test_llm_judge_rejects_out_of_range_score():
    judge = oracles.llm_judge("quality", lambda ctx, result: 1.5)
    with pytest.raises(ValueError):
        judge(make_ctx(), "anything")


def test_llm_judge_receives_ctx_and_result():
    seen = {}

    def judge_fn(ctx, result):
        seen["ctx"] = ctx
        seen["result"] = result
        return 1.0

    ctx = make_ctx()
    oracles.llm_judge("quality", judge_fn)(ctx, "my-result")
    assert seen == {"ctx": ctx, "result": "my-result"}


def test_calibrate_agreement_rate():
    def judge_fn(ctx, result):
        return 1.0 if result == "good" else 0.0

    labeled = [
        (make_ctx(), "good", True),
        (make_ctx(), "bad", False),
        (make_ctx(), "good", False),  # disagreement
    ]
    assert oracles.calibrate(judge_fn, labeled) == pytest.approx(2 / 3)


def test_calibrate_empty_set_is_zero():
    assert oracles.calibrate(lambda ctx, result: 1.0, []) == 0.0
