"""Base provider profile interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from attractor_agent.tools.registry import ToolRegistry
from attractor_llm.types import ToolDefinition


class ProviderProfile(Protocol):
    """Interface for provider-specific tool and prompt profiles."""

    id: str
    model: str
    tool_registry: ToolRegistry
    supports_reasoning: bool
    supports_streaming: bool
    supports_parallel_tool_calls: bool
    context_window_size: int

    def build_system_prompt(
        self,
        environment: dict[str, str] | None = None,
        project_docs: list[str] | None = None,
        user_instructions: str | None = None,
    ) -> str: ...

    def tools(self) -> list[ToolDefinition]: ...

    def provider_options(self) -> dict[str, Any] | None: ...


@dataclass
class BaseProfile:
    """Shared base for all provider profiles."""

    id: str = ""
    model: str = ""
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)
    supports_reasoning: bool = False
    supports_streaming: bool = True
    supports_parallel_tool_calls: bool = True
    context_window_size: int = 128_000
    reasoning_effort: str | None = None

    def tools(self) -> list[ToolDefinition]:
        return self.tool_registry.definitions()

    def _build_prompt_layers(
        self,
        base_instructions: str,
        environment: dict[str, str] | None = None,
        project_docs: list[str] | None = None,
        user_instructions: str | None = None,
    ) -> str:
        """Assemble the 5-layer system prompt."""
        layers: list[str] = []

        # Layer 1: Provider base instructions
        layers.append(base_instructions)

        # Layer 2: Environment context
        if environment:
            env_block = "\n# Environment\n"
            for key, val in environment.items():
                env_block += f"- {key}: {val}\n"
            layers.append(env_block)

        # Layer 3: Tool descriptions
        tool_block = "\n# Available Tools\n"
        for t in self.tools():
            tool_block += f"- **{t.name}**: {t.description}\n"
        layers.append(tool_block)

        # Layer 4: Project docs
        if project_docs:
            docs_block = "\n# Project Documentation\n"
            for doc in project_docs:
                docs_block += doc + "\n\n"
            layers.append(docs_block)

        # Layer 5: User instructions
        if user_instructions:
            layers.append(f"\n# User Instructions\n{user_instructions}\n")

        return "\n".join(layers)
