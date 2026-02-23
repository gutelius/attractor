# Attractor Implementation Design

## Summary

Attractor is a DOT-graph pipeline runner that orchestrates multi-stage AI workflows. It comprises three layers: a unified LLM client, a coding agent loop, and a pipeline engine. This document describes the Python implementation.

## Decisions

- **Language:** Python 3.12+
- **Packaging:** uv + pyproject.toml, monorepo with three packages
- **Providers:** OpenAI, Anthropic, Gemini (all three from the start)
- **Interface:** Library, CLI, and HTTP server with SSE

## Architecture

Three packages, built bottom-up:

```
attractor-llm     (Unified LLM Client)
       |
attractor-agent   (Coding Agent Loop)
       |
attractor         (Pipeline Engine + CLI + HTTP Server)
```

Each package is independently installable. The pipeline engine depends on both lower layers.

## Package 1: attractor-llm

Provider-agnostic LLM client wrapping OpenAI, Anthropic, and Gemini APIs behind a single interface.

### Modules

| Module | Responsibility |
|--------|---------------|
| `client.py` | `Client` class, `from_env()`, provider routing, middleware chain |
| `types.py` | `Message`, `ContentPart`, `Request`, `Response`, `StreamEvent`, enums |
| `errors.py` | `SDKError` hierarchy with provider-specific subtypes |
| `retry.py` | `RetryPolicy`, exponential backoff with jitter |
| `middleware.py` | Middleware registration and chain execution |
| `catalog.py` | `ModelInfo` records, lookup functions |
| `generate.py` | `generate()`, `generate_object()` high-level functions |
| `stream.py` | `stream()`, `stream_object()`, `StreamAccumulator` |
| `providers/base.py` | `ProviderAdapter` interface |
| `providers/openai.py` | OpenAI Responses API adapter |
| `providers/anthropic.py` | Anthropic Messages API adapter |
| `providers/gemini.py` | Gemini native API adapter |
| `providers/openai_compat.py` | OpenAI-compatible endpoint adapter |

### Key Design Points

- **Async-first** using `httpx.AsyncClient` for all HTTP calls.
- **Two methods, not a flag:** `complete()` returns `Response`; `stream()` returns `AsyncIterator[StreamEvent]`.
- **Native APIs only:** OpenAI uses Responses API, Anthropic uses Messages API, Gemini uses native generateContent. No compatibility shims.
- **Anthropic cache injection:** Adapter auto-injects `cache_control` breakpoints on system and long user messages.
- **Gemini synthetic IDs:** Adapter generates UUIDs for tool calls since Gemini lacks native call IDs.
- **Retry at Layer 4 only:** `Client.complete()`/`stream()` never retry. `generate()`/`stream()` retry per-step with configurable policy.

### Dependencies

`httpx`, `pydantic`, `jsonschema`

## Package 2: attractor-agent

Coding agent loop that pairs an LLM with developer tools through an iterative execute-observe cycle.

### Modules

| Module | Responsibility |
|--------|---------------|
| `session.py` | `Session`, `SessionConfig`, state machine |
| `loop.py` | `process_input()`, core agentic loop |
| `types.py` | `Turn` variants, `SubAgentResult`, `ExecResult` |
| `profiles/base.py` | `ProviderProfile` interface |
| `profiles/openai.py` | OpenAI profile with `apply_patch` |
| `profiles/anthropic.py` | Anthropic profile with `edit_file` |
| `profiles/gemini.py` | Gemini profile with extended tools |
| `tools/registry.py` | `ToolRegistry`, dispatch, validation |
| `tools/core.py` | `read_file`, `write_file`, `edit_file`, `shell`, `grep`, `glob` |
| `tools/patch.py` | `apply_patch` v4a format parser and applier |
| `tools/truncation.py` | Character-first, then line-based truncation |
| `environments/base.py` | `ExecutionEnvironment` interface |
| `environments/local.py` | `LocalExecutionEnvironment` |
| `subagent.py` | Subagent spawning, depth limiting |
| `prompt.py` | 5-layer system prompt construction |
| `events.py` | `EventEmitter`, 12 `EventKind` variants |
| `detection.py` | Loop detection within sliding window |

### Core Loop

1. Append user turn, drain steering queue.
2. Build request: system prompt + history + tool definitions.
3. Call `client.complete()` (single-shot, no SDK-level tool loop).
4. If tool calls: execute via registry, append results, continue loop.
5. If text-only response: break.
6. Process follow-up queue after completion.

### Tool Output Truncation

Character-based truncation runs first (catches pathological single-line outputs). Line-based truncation runs second. Default limits per spec (shell: 30K chars / 256 lines, grep: 20K / 200 lines, etc.).

### Execution Environment

`LocalExecutionEnvironment` runs commands in new process groups. Timeout handling: SIGTERM, wait 2s, SIGKILL. Environment variable filtering excludes secrets by pattern (`*_API_KEY`, `*_SECRET`, etc.).

### Dependencies

`attractor-llm`

## Package 3: attractor (Pipeline Engine)

DOT-graph pipeline runner that orchestrates multi-stage workflows.

### Modules

| Module | Responsibility |
|--------|---------------|
| `cli.py` | CLI entry point (`attractor run`, `attractor validate`, etc.) |
| `parser.py` | DOT file parser (using `pyparsing`) |
| `graph.py` | `Graph`, `Node`, `Edge` data structures |
| `validator.py` | Lint rules, structural validation |
| `engine.py` | Core execution loop, edge selection, goal gates |
| `context.py` | Thread-safe KV store with `ReadWriteLock` |
| `outcome.py` | `Outcome`, `StageStatus` enum |
| `checkpoint.py` | JSON serialization, save/restore |
| `fidelity.py` | Context fidelity modes and resolution |
| `conditions.py` | Condition expression parser and evaluator |
| `stylesheet.py` | CSS-like model stylesheet parser/resolver |
| `transforms.py` | Variable expansion, stylesheet application, preamble |
| `artifacts.py` | `ArtifactStore` with file-backing above 100KB |
| `interviewer.py` | `Interviewer` interface + 5 implementations |
| `handlers/base.py` | `Handler` interface, `HandlerRegistry` |
| `handlers/start_exit.py` | No-op start/exit handlers |
| `handlers/codergen.py` | LLM task handler + `CodergenBackend` interface |
| `handlers/human.py` | Human-in-the-loop gate |
| `handlers/conditional.py` | Conditional routing (no-op, engine handles edges) |
| `handlers/parallel.py` | Fan-out with join policies, fan-in with ranking |
| `handlers/tool.py` | Shell command execution |
| `handlers/manager.py` | Supervisor loop over child pipeline |
| `server.py` | FastAPI HTTP server with SSE events |
| `events.py` | Pipeline observability events |

### Execution Flow

1. **Parse:** Read DOT file into in-memory `Graph`.
2. **Validate:** Check structural rules (one start, one exit, reachability).
3. **Initialize:** Create run directory, seed context from graph attributes, apply transforms.
4. **Execute:** Traverse from start node. At each node: resolve handler, execute with retry, select next edge (5-step deterministic algorithm), checkpoint.
5. **Finalize:** Write final checkpoint, emit completion event, clean up.

### Edge Selection (5-step priority)

1. Condition-matching edges (evaluate expressions, pick by weight then lexical).
2. Preferred label match (normalize and compare).
3. Suggested next IDs from outcome.
4. Highest weight among unconditional edges.
5. Lexical tiebreak on target node ID.

### Human-in-the-Loop

`WaitForHumanHandler` derives choices from outgoing edge labels. Presents multiple-choice question via `Interviewer.ask()`. Five implementations: `AutoApproveInterviewer` (CI), `ConsoleInterviewer` (CLI), `CallbackInterviewer`, `QueueInterviewer` (testing), `RecordingInterviewer`.

### HTTP Server Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/pipelines` | Submit DOT, start execution |
| GET | `/pipelines/{id}` | Status and progress |
| GET | `/pipelines/{id}/events` | SSE event stream |
| POST | `/pipelines/{id}/cancel` | Cancel pipeline |
| GET | `/pipelines/{id}/graph` | Rendered SVG |
| GET | `/pipelines/{id}/questions` | Pending human questions |
| POST | `/pipelines/{id}/questions/{qid}/answer` | Submit answer |
| GET | `/pipelines/{id}/checkpoint` | Current checkpoint |
| GET | `/pipelines/{id}/context` | Context store |

### CLI Commands

- `attractor run <file.dot>` — Execute a pipeline
- `attractor validate <file.dot>` — Validate without executing
- `attractor serve` — Start HTTP server
- `attractor resume <checkpoint>` — Resume from checkpoint

### Dependencies

`attractor-llm`, `attractor-agent`, `fastapi`, `uvicorn`, `sse-starlette`, `pyparsing`, `click`

## Build Order

1. `attractor-llm` types and errors
2. `attractor-llm` provider adapters
3. `attractor-llm` client, middleware, retry
4. `attractor-llm` high-level API (generate, stream)
5. `attractor-agent` execution environment
6. `attractor-agent` tool registry and core tools
7. `attractor-agent` provider profiles
8. `attractor-agent` session and core loop
9. `attractor` DOT parser and graph types
10. `attractor` context, outcome, conditions
11. `attractor` handlers
12. `attractor` engine (execution loop, edge selection, checkpointing)
13. `attractor` CLI
14. `attractor` HTTP server
15. Integration tests across all layers
