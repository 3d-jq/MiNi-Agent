"""提示词与工具注册表的一致性测试:防止「实现了函数但忘了注册」这类静默断链。"""
import tool_registry as tr

EXPECTED_TOOLS = {
    "web_search", "fetch_url", "read", "grep", "write",
    "edit", "glob", "list_dir", "bash", "sub_agent",
    "save_memory", "clear_memory",
}


def test_every_schema_has_implementation():
    schema_names = {t["function"]["name"] for t in tr.tools}
    assert schema_names == EXPECTED_TOOLS
    assert set(tr.TOOL_CALL_MAP) == EXPECTED_TOOLS, \
        f"schema 与实现不一致:多出 {set(tr.TOOL_CALL_MAP) - EXPECTED_TOOLS},缺失 {EXPECTED_TOOLS - set(tr.TOOL_CALL_MAP)}"


def test_every_tool_has_emoji():
    for name in EXPECTED_TOOLS:
        assert name in tr.TOOL_EMOJI, f"工具 {name} 缺少 emoji,打印时会 KeyError"


def test_schemas_are_valid_shape():
    for t in tr.tools:
        fn = t["function"]
        assert t["type"] == "function"
        assert isinstance(fn["name"], str) and fn["name"]
        assert isinstance(fn.get("description"), str) and len(fn["description"]) >= 5
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        for req in params.get("required", []):
            assert req in params["properties"], f"{fn['name']} 的 required 里有未定义的参数 {req}"


def test_registry_functions_callable():
    import inspect

    for name, fn in tr.TOOL_CALL_MAP.items():
        assert callable(fn), f"TOOL_CALL_MAP[{name}] 不是可调用对象"
        sig = inspect.signature(fn)
        # 每个 required 参数必须是函数真实存在的形参(否则模型传参会 TypeError)
        schema = next(t["function"] for t in tr.tools if t["function"]["name"] == name)
        for req in schema["parameters"].get("required", []):
            assert req in sig.parameters, f"{name} 的必填参数 {req} 在函数签名里不存在"
