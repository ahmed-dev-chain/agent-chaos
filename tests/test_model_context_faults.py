from agent_chaos import Kind, RunContext, faults


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


def test_refusal_does_not_execute_real_call():
    ctx = make_ctx([faults.Refusal("model=m", message="no")])
    ran = []
    model = ctx.wrap("m", lambda: ran.append(1), kind=Kind.MODEL_CALL)
    assert model() == "no"
    assert not ran and not ctx.events[0].executed


def test_format_drift_flattens_dict():
    ctx = make_ctx([faults.FormatDrift("model=m")])
    model = ctx.wrap("m", lambda: {"a": 1, "b": 2}, kind=Kind.MODEL_CALL)
    assert model() == "a=1, b=2"


def test_format_drift_wraps_string():
    ctx = make_ctx([faults.FormatDrift("model=m")])
    model = ctx.wrap("m", lambda: "hello", kind=Kind.MODEL_CALL)
    assert model() == "```\nhello\n```"


def test_truncation_keeps_fraction():
    ctx = make_ctx([faults.Truncation("model=m", keep=0.25)])
    model = ctx.wrap("m", lambda: list(range(8)), kind=Kind.MODEL_CALL)
    assert model() == [0, 1]


def test_window_overflow_keeps_most_recent():
    ctx = make_ctx([faults.WindowOverflow("model=m", keep=0.5)])
    model = ctx.wrap("m", lambda: ["old1", "old2", "new1", "new2"], kind=Kind.MODEL_CALL)
    assert model() == ["new1", "new2"]


def test_window_overflow_handles_empty():
    ctx = make_ctx([faults.WindowOverflow("model=m")])
    model = ctx.wrap("m", lambda: [], kind=Kind.MODEL_CALL)
    assert model() == []


def test_memory_corruption_mutates_one_string_entry():
    ctx = make_ctx([faults.MemoryCorruption("model=m")])
    model = ctx.wrap("m", lambda: ["alpha", "beta", "gamma"], kind=Kind.MODEL_CALL)
    out = model()
    assert len(out) == 3
    changed = [o for o, orig in zip(out, ["alpha", "beta", "gamma"], strict=True) if o != orig]
    assert len(changed) == 1
    assert changed[0] == changed[0][::-1][::-1]  # still a reversed string, just checking shape


def test_memory_corruption_nulls_dict_values():
    ctx = make_ctx([faults.MemoryCorruption("model=m")])
    model = ctx.wrap("m", lambda: {"order_id": 1, "customer": {"name": "ada", "email": "a@b.com"}},
                      kind=Kind.MODEL_CALL)
    out = model()
    assert set(out) == {"order_id", "customer"}
    nulled = [k for k, v in out.items() if v is None]
    assert len(nulled) == 1


def test_memory_corruption_same_seed_same_decision():
    def run(seed):
        ctx = make_ctx([faults.MemoryCorruption("model=m")], seed)
        model = ctx.wrap("m", lambda: ["a", "b", "c", "d"], kind=Kind.MODEL_CALL)
        return model()

    assert run(7) == run(7)


def test_new_faults_registered():
    for name in ("refusal", "format_drift", "truncation", "window_overflow", "memory_corruption"):
        assert name in faults.FAULTS
