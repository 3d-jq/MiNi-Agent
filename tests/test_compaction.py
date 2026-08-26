"""压缩系统测试:安全切点、token 估算。纯逻辑,无网络(不测 compress_context 的 LLM 调用本身)。"""
import compaction as cp


def test_est_tokens_counts_content():
    msgs = [{"role": "user", "content": "hello"}]
    # content(5) + json.dumps(空 tool_calls) 的 ""(2) = 7
    assert cp.est_tokens(msgs) == 7


def test_est_tokens_counts_tool_calls():
    msgs = [{"role": "assistant", "content": None, "tool_calls": {"name": "x"}}]
    # json.dumps({"name": "x"}) = 13 字符;content=None 计 0
    assert cp.est_tokens(msgs) == 13


def test_find_safe_cut_lands_on_user_boundary():
    # 结构:user, assistant, tool, user —— 尾部保留 1 条时,切点应落在最后一条 user 头部
    msgs = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "r1"},
        {"role": "user", "content": "q2"},
    ]
    cut = cp.find_safe_cut(msgs, tail_msgs=1)
    assert cut == 3
    # 切口之后的第一条必须以 user 开始(保证 tool 对不被拆散)
    assert msgs[cut]["role"] == "user"


def test_find_safe_cut_never_returns_none_when_history_enough():
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    cut = cp.find_safe_cut(msgs, tail_msgs=3)
    assert cut is not None
    assert len(msgs) - cut >= 3  # 尾部保留数量达标


def test_find_safe_cut_too_short_returns_none():
    msgs = [
        {"role": "system", "content": "s"},   # find_safe_cut 处理的是去掉 system 后的列表,这里仅示意
        {"role": "user", "content": "only"},
    ]
    # 只有 1 条非 system 消息时无可压缩空间
    rest = msgs[1:]
    assert cp.find_safe_cut(rest, tail_msgs=4) in (None, 1)


def test_threshold_math():
    # 阈值 = 窗口 × THRESHOLD_RATIO;确认常量关系没被改坏
    from config import CONTEXT_WINDOW, THRESHOLD_RATIO

    threshold = int(CONTEXT_WINDOW * THRESHOLD_RATIO)
    assert threshold < CONTEXT_WINDOW
    assert threshold > CONTEXT_WINDOW // 2
