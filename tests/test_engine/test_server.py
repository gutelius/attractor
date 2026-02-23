"""Tests for HTTP server."""

import pytest
from httpx import AsyncClient, ASGITransport

from attractor.server import app


@pytest.fixture
def simple_dot():
    return '''
    digraph G {
        Start [shape=Mdiamond]
        Task [label="Do work"]
        Exit [shape=Msquare]
        Start -> Task -> Exit
    }
    '''


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestPipelineSubmission:
    @pytest.mark.asyncio
    async def test_submit_pipeline(self, client, simple_dot):
        resp = await client.post("/pipelines", json={"dot_source": simple_dot})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_submit_invalid_dot(self, client):
        resp = await client.post("/pipelines", json={"dot_source": "not valid dot"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_submit_invalid_graph(self, client):
        dot = 'digraph G { A [label="no start or exit"] }'
        resp = await client.post("/pipelines", json={"dot_source": dot})
        assert resp.status_code == 400


class TestPipelineStatus:
    @pytest.mark.asyncio
    async def test_get_pipeline(self, client, simple_dot):
        submit = await client.post("/pipelines", json={"dot_source": simple_dot})
        pid = submit.json()["id"]

        # Allow some time for pipeline to run
        import asyncio
        await asyncio.sleep(0.5)

        resp = await client.get(f"/pipelines/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pid
        assert data["status"] in ("running", "completed", "failed", "error")

    @pytest.mark.asyncio
    async def test_get_nonexistent_pipeline(self, client):
        resp = await client.get("/pipelines/nonexistent")
        assert resp.status_code == 404


class TestPipelineCancel:
    @pytest.mark.asyncio
    async def test_cancel_pipeline(self, client, simple_dot):
        submit = await client.post("/pipelines", json={"dot_source": simple_dot})
        pid = submit.json()["id"]
        resp = await client.post(f"/pipelines/{pid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, client):
        resp = await client.post("/pipelines/nonexistent/cancel")
        assert resp.status_code == 404


class TestPipelineGraph:
    @pytest.mark.asyncio
    async def test_get_graph(self, client, simple_dot):
        submit = await client.post("/pipelines", json={"dot_source": simple_dot})
        pid = submit.json()["id"]
        resp = await client.get(f"/pipelines/{pid}/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_graph_nonexistent(self, client):
        resp = await client.get("/pipelines/nonexistent/graph")
        assert resp.status_code == 404


class TestPipelineContext:
    @pytest.mark.asyncio
    async def test_get_context(self, client, simple_dot):
        submit = await client.post("/pipelines", json={"dot_source": simple_dot})
        pid = submit.json()["id"]
        resp = await client.get(f"/pipelines/{pid}/context")
        assert resp.status_code == 200
        assert resp.json()["pipeline_id"] == pid


class TestPipelineEvents:
    @pytest.mark.asyncio
    async def test_events_sse(self, client, simple_dot):
        submit = await client.post("/pipelines", json={"dot_source": simple_dot})
        pid = submit.json()["id"]

        # Allow pipeline to complete
        import asyncio
        await asyncio.sleep(0.5)

        resp = await client.get(f"/pipelines/{pid}/events")
        assert resp.status_code == 200
        # SSE content type
        assert "text/event-stream" in resp.headers.get("content-type", "")
