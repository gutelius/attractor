"""Tests for subagent support."""

import pytest

from attractor_agent.profiles.base import BaseProfile
from attractor_agent.session import Session, SessionConfig, AssistantTurn
from attractor_agent.subagent import SubAgentManager, make_subagent_tools
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    Message,
    Response,
    Role,
    FinishReason,
    Usage,
)


class MockLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self._call_count = 0

    async def complete(self, request):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


def _text_resp(text: str) -> Response:
    msg = Message(
        role=Role.ASSISTANT,
        content=[ContentPart(kind=ContentKind.TEXT, text=text)],
    )
    return Response(id="r1", model="test", message=msg,
                    usage=Usage(input_tokens=5, output_tokens=5),
                    finish_reason=FinishReason(reason="stop"))


class TestSubAgentManager:
    async def test_spawn_and_wait(self):
        client = MockLLMClient([_text_resp("Done with task")])
        profile = BaseProfile(id="test", model="test")
        parent = Session(profile=profile, llm_client=client)
        mgr = SubAgentManager(parent)

        agent_id = await mgr.spawn("Do something")
        result = await mgr.wait(agent_id)
        assert result.success
        assert "Done with task" in result.output

    async def test_close_agent(self):
        client = MockLLMClient([_text_resp("ok")])
        parent = Session(profile=BaseProfile(), llm_client=client)
        mgr = SubAgentManager(parent)

        agent_id = await mgr.spawn("task")
        result = await mgr.close(agent_id)
        assert agent_id in result

    async def test_unknown_agent(self):
        parent = Session(profile=BaseProfile(), llm_client=MockLLMClient([]))
        mgr = SubAgentManager(parent)
        result = await mgr.wait("nonexistent")
        assert not result.success

    async def test_depth_limiting(self):
        client = MockLLMClient([_text_resp("ok")])
        parent = Session(
            profile=BaseProfile(id="test", model="test"),
            llm_client=client,
            config=SessionConfig(max_subagent_depth=1),
        )
        mgr = SubAgentManager(parent)

        # First spawn works
        agent_id = await mgr.spawn("task1")
        assert agent_id

        # Simulate depth > 1 by setting parent_session on parent
        parent._parent_session = Session(  # type: ignore
            profile=BaseProfile(), llm_client=client
        )
        mgr2 = SubAgentManager(parent)
        with pytest.raises(RuntimeError, match="depth"):
            await mgr2.spawn("task2")

    async def test_shared_execution_env(self):
        client = MockLLMClient([_text_resp("ok")])
        env = object()  # sentinel
        parent = Session(profile=BaseProfile(), llm_client=client, execution_env=env)
        mgr = SubAgentManager(parent)

        agent_id = await mgr.spawn("task")
        handle = mgr.get(agent_id)
        assert handle.session.execution_env is env


class TestSubAgentTools:
    async def test_tool_definitions(self):
        parent = Session(profile=BaseProfile(), llm_client=MockLLMClient([]))
        mgr = SubAgentManager(parent)
        tools = make_subagent_tools(mgr)
        names = {t.name for t in tools}
        assert names == {"spawn_agent", "send_input", "wait", "close_agent"}

    async def test_spawn_tool(self):
        client = MockLLMClient([_text_resp("completed")])
        parent = Session(profile=BaseProfile(id="t", model="t"), llm_client=client)
        mgr = SubAgentManager(parent)
        tools = make_subagent_tools(mgr)
        spawn = next(t for t in tools if t.name == "spawn_agent")
        result = await spawn.execute(task="do thing")
        assert "Spawned agent" in result
