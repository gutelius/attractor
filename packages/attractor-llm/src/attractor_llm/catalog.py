"""Model catalog for known LLM models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelInfo:
    id: str
    provider: str
    display_name: str
    context_window: int
    max_output: int | None = None
    supports_tools: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    aliases: list[str] = field(default_factory=list)


# Catalog ordered by provider, newest first within each provider.
MODELS: list[ModelInfo] = [
    # Anthropic
    ModelInfo(
        id="claude-opus-4-6",
        provider="anthropic",
        display_name="Claude Opus 4.6",
        context_window=200_000,
        max_output=32_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["opus", "claude-opus"],
    ),
    ModelInfo(
        id="claude-sonnet-4-5",
        provider="anthropic",
        display_name="Claude Sonnet 4.5",
        context_window=200_000,
        max_output=16_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["sonnet", "claude-sonnet"],
    ),
    # OpenAI
    ModelInfo(
        id="gpt-5.2",
        provider="openai",
        display_name="GPT-5.2",
        context_window=1_047_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["gpt5"],
    ),
    ModelInfo(
        id="gpt-5.2-mini",
        provider="openai",
        display_name="GPT-5.2 Mini",
        context_window=1_047_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["gpt5-mini"],
    ),
    ModelInfo(
        id="gpt-5.2-codex",
        provider="openai",
        display_name="GPT-5.2 Codex",
        context_window=1_047_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["codex"],
    ),
    # Gemini
    ModelInfo(
        id="gemini-3-pro-preview",
        provider="gemini",
        display_name="Gemini 3 Pro (Preview)",
        context_window=1_048_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["gemini-pro", "gemini-3-pro"],
    ),
    ModelInfo(
        id="gemini-3-flash-preview",
        provider="gemini",
        display_name="Gemini 3 Flash (Preview)",
        context_window=1_048_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        aliases=["gemini-flash", "gemini-3-flash"],
    ),
]

# Build lookup indices
_BY_ID: dict[str, ModelInfo] = {m.id: m for m in MODELS}
_BY_ALIAS: dict[str, ModelInfo] = {}
for _m in MODELS:
    for _a in _m.aliases:
        _BY_ALIAS[_a] = _m


def get_model_info(model_id: str) -> ModelInfo | None:
    """Look up a model by ID or alias. Returns None if unknown."""
    return _BY_ID.get(model_id) or _BY_ALIAS.get(model_id)


def list_models(provider: str | None = None) -> list[ModelInfo]:
    """List all known models, optionally filtered by provider."""
    if provider is None:
        return list(MODELS)
    return [m for m in MODELS if m.provider == provider]


def get_latest_model(
    provider: str, capability: str | None = None
) -> ModelInfo | None:
    """Return the newest/best model for a provider.

    Optionally filter by capability: "reasoning", "vision", "tools".
    """
    candidates = [m for m in MODELS if m.provider == provider]
    if capability == "reasoning":
        candidates = [m for m in candidates if m.supports_reasoning]
    elif capability == "vision":
        candidates = [m for m in candidates if m.supports_vision]
    elif capability == "tools":
        candidates = [m for m in candidates if m.supports_tools]
    return candidates[0] if candidates else None
