"""Tests for attractor_llm.catalog."""

from attractor_llm.catalog import ModelInfo, get_model_info, list_models, get_latest_model


class TestGetModelInfo:
    def test_known_model(self):
        info = get_model_info("claude-opus-4-6")
        assert info is not None
        assert info.provider == "anthropic"
        assert info.display_name == "Claude Opus 4.6"
        assert info.supports_tools is True

    def test_unknown_model(self):
        assert get_model_info("nonexistent-model-xyz") is None

    def test_alias_lookup(self):
        info = get_model_info("opus")
        assert info is not None
        assert info.id == "claude-opus-4-6"


class TestListModels:
    def test_all_models(self):
        models = list_models()
        assert len(models) >= 7

    def test_filter_by_provider(self):
        anthropic = list_models(provider="anthropic")
        assert all(m.provider == "anthropic" for m in anthropic)
        assert len(anthropic) >= 2

        openai = list_models(provider="openai")
        assert all(m.provider == "openai" for m in openai)
        assert len(openai) >= 2


class TestGetLatestModel:
    def test_latest_anthropic(self):
        model = get_latest_model("anthropic")
        assert model is not None
        assert model.id == "claude-opus-4-6"

    def test_latest_openai(self):
        model = get_latest_model("openai")
        assert model is not None
        assert model.id == "gpt-5.2"

    def test_latest_gemini(self):
        model = get_latest_model("gemini")
        assert model is not None
        assert model.provider == "gemini"

    def test_unknown_provider(self):
        assert get_latest_model("unknown") is None

    def test_with_capability(self):
        model = get_latest_model("anthropic", capability="reasoning")
        assert model is not None
        assert model.supports_reasoning is True
