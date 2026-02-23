"""Coding agent loop library."""

from attractor_agent.types import ExecResult, DirEntry
from attractor_agent.environments.base import ExecutionEnvironment
from attractor_agent.environments.local import LocalExecutionEnvironment
from attractor_agent.tools.registry import ToolRegistry
from attractor_agent.tools.core import register_core_tools
from attractor_agent.tools.truncation import truncate_output
from attractor_agent.tools.patch import apply_patch, make_apply_patch_tool
from attractor_agent.profiles.base import BaseProfile, ProviderProfile
from attractor_agent.profiles.openai import OpenAIProfile, create_openai_profile
from attractor_agent.profiles.anthropic import AnthropicProfile, create_anthropic_profile
from attractor_agent.profiles.gemini import GeminiProfile, create_gemini_profile
from attractor_agent.prompt import build_system_prompt, build_environment_context, discover_project_docs
from attractor_agent.events import EventEmitter, EventKind, SessionEvent, SteeringQueue, FollowUpQueue
from attractor_agent.detection import detect_loop, tool_call_signature
from attractor_agent.session import (
    Session,
    SessionConfig,
    SessionState,
    UserTurn,
    AssistantTurn,
    ToolResultsTurn,
    SteeringTurn,
    SystemTurn,
    process_input,
)
from attractor_agent.subagent import SubAgentManager, SubAgentHandle, SubAgentResult, make_subagent_tools
