# Attractor

Attractor executes software pipelines defined as DOT digraphs. Each node represents a stage — an LLM call, a human review, a shell command, or a parallel fan-out — and edges define the flow between them.

## Quick Start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gutelius/attractor.git
cd attractor
uv sync --all-packages --all-extras
```

Write a pipeline (`my-pipeline.dot`):

```dot
digraph MyPipeline {
    goal = "Build a REST API"

    Start [shape=Mdiamond]
    Plan [label="Plan the implementation"]
    Implement [label="Write the code"]
    Review [shape=hexagon, label="Human review"]
    Exit [shape=Msquare]

    Start -> Plan -> Implement -> Review -> Exit
}
```

Validate and run:

```bash
uv run attractor validate my-pipeline.dot
uv run attractor run my-pipeline.dot --dry-run
```

## Packages

| Package | Purpose |
|---------|---------|
| **attractor** | DOT parser, graph engine, CLI, HTTP server |
| **attractor-llm** | Unified LLM client (OpenAI, Anthropic, Gemini) |
| **attractor-agent** | Coding agent loop with tool execution |

## Documentation

- **[User Guide](./docs/user-guide.md)** — installation, CLI reference, pipeline authoring, programmatic API, HTTP server
- **[Attractor Spec](./attractor-spec.md)** — NLSpec for the pipeline engine
- **[Coding Agent Loop Spec](./coding-agent-loop-spec.md)** — NLSpec for the agent loop
- **[Unified LLM Client Spec](./unified-llm-spec.md)** — NLSpec for the LLM client

## Building Your Own Attractor

This repository contains [NLSpecs](#terminology) for building your own version of Attractor. Supply the following prompt to a modern coding agent (Claude Code, Codex, OpenCode, Amp, Cursor, etc):

```
codeagent> Implement Attractor as described by https://github.com/strongdm/attractor
```

## Terminology

- **NLSpec** (Natural Language Spec): a human-readable spec intended to be directly usable by coding agents to implement and validate behavior.
