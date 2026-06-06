from core import langchain_model_adapters, llm


def test_langchain_model_adapters_report_optional_capability():
    payload = langchain_model_adapters.capabilities()

    assert payload["layer"] == "optional_langchain_adapter"
    assert "anthropic" in payload["adapters"]
    assert "ollama" in payload["adapters"]
    assert payload["policy"]


def test_llm_model_gateway_status_keeps_friday_gateway_on_top():
    payload = llm.model_gateway_status()

    assert payload["layer"] == "friday_internal_model_gateway"
    assert payload["decision"]["keep_core_llm"] is True
    assert payload["architecture"][:2] == ["Friday Product Brain", "Friday Model Gateway"]
    assert "langchain_adapters" in payload
