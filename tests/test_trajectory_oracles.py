from agent_chaos import Level, RunContext, oracles


def make_ctx(seed=1):
    return RunContext(seed, [])


def test_tool_order_passes_in_order():
    ctx = make_ctx()
    ctx.wrap("read", lambda: 1)()
    ctx.wrap("write", lambda: 2)()
    assert oracles.tool_order("read", "write")(ctx, None) is None


def test_tool_order_fails_out_of_order():
    ctx = make_ctx()
    ctx.wrap("write", lambda: 2)()
    ctx.wrap("read", lambda: 1)()
    v = oracles.tool_order("read", "write")(ctx, None)
    assert v.level == Level.FAILED


def test_tool_order_fails_when_tool_never_called():
    ctx = make_ctx()
    ctx.wrap("read", lambda: 1)()
    v = oracles.tool_order("read", "write")(ctx, None)
    assert v.level == Level.FAILED and "write" in v.reason


def test_tool_order_ignores_unexecuted_calls():
    from agent_chaos import faults

    ctx = RunContext(1, [faults.ErrorStatus("tool=write")])
    ctx.wrap("read", lambda: 1)()
    tool = ctx.wrap("write", lambda: 2)
    try:
        tool()
    except Exception:
        pass
    # "write" was attempted but never executed -> still counts as "never called"
    v = oracles.tool_order("read", "write")(ctx, None)
    assert v.level == Level.FAILED


def test_max_retries_passes_under_limit():
    ctx = make_ctx()
    tool = ctx.wrap("pay", lambda: 1)
    tool()
    tool()
    assert oracles.max_retries("pay", 3)(ctx, None) is None


def test_max_retries_fails_over_limit():
    ctx = make_ctx()
    tool = ctx.wrap("pay", lambda: 1)
    for _ in range(4):
        tool()
    v = oracles.max_retries("pay", 3)(ctx, None)
    assert v.level == Level.FAILED


def test_no_call_loop_passes_below_threshold():
    ctx = make_ctx()
    tool = ctx.wrap("search", lambda q: q)
    tool(q="x")
    tool(q="x")
    tool(q="x")
    assert oracles.no_call_loop(3)(ctx, None) is None


def test_no_call_loop_fails_on_repeated_identical_calls():
    ctx = make_ctx()
    tool = ctx.wrap("search", lambda q: q)
    for _ in range(5):
        tool(q="x")
    v = oracles.no_call_loop(3)(ctx, None)
    assert v.level == Level.FAILED


def test_no_call_loop_resets_on_different_args():
    ctx = make_ctx()
    tool = ctx.wrap("search", lambda q: q)
    tool(q="x")
    tool(q="x")
    tool(q="y")  # different args: streak resets
    tool(q="y")
    assert oracles.no_call_loop(2)(ctx, None) is None
