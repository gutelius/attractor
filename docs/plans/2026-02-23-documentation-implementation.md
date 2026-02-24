# Documentation Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the flat reference-style user guide with four progressive documents — Tutorial, Cookbook, Concepts, Reference — that teach a PM to author pipelines and build software products end-to-end.

**Architecture:** Four markdown files in `docs/`. Tutorial teaches by building one continuous project. Cookbook provides copy-paste patterns. Concepts explains the mental model. Reference is lookup tables. The README links to Tutorial as the entry point. The old `docs/user-guide.md` is removed.

**Tech Stack:** Markdown, DOT syntax examples, shell commands. Verify examples with `uv run attractor validate` where possible.

---

## Task 1: Tutorial — Chapters 1-3 (Installation, First Pipeline, Adding Work)

**Files:**
- Create: `docs/tutorial.md`

**Step 1: Write Tutorial chapters 1-3**

Write the opening of `docs/tutorial.md` with title, introduction, and chapters 1-3.

**Chapter 1: Installation & Setup** must cover:
- Prerequisites: Python 3.12+, uv, optionally Graphviz (for rendering)
- Clone, sync, verify `attractor --help`
- Optionally render a .dot file to SVG: `dot -Tsvg file.dot -o file.svg`
- Explain what each package does (attractor-llm, attractor-agent, attractor)

**Chapter 2: Your First Pipeline** must cover:
- Create a minimal 3-node pipeline: Start → Plan → Exit
- Full .dot file with comments explaining every line
- Explain `digraph` keyword, graph name, `shape=Mdiamond` (start), `shape=Msquare` (exit), `box` (default, LLM task)
- Explain `goal` graph attribute — the one-sentence summary of what the pipeline builds
- Explain `label` — the display name and default prompt for LLM nodes
- Run `attractor validate` and explain output
- Run `attractor run --dry-run` and explain output
- Show what `--dry-run` simulates vs. what a real backend does

**Chapter 3: Adding Real Work** must cover:
- Expand to Start → Plan → Implement → Exit
- Introduce the `prompt` attribute with `$goal` variable expansion
- Show how prompts guide the LLM: generic label vs. specific prompt
- Explain the codergen handler: what it does, how it calls the backend, what it writes to disk (prompt.md, response.md, status.json)
- Run dry-run, show 4 events (pipeline.start, node.start x2, node.complete x2, pipeline.finalize)
- Explain the `--log-dir` flag and what appears in the log directory

**Step 2: Create fixture DOT files for chapters 1-3**

Create `docs/examples/ch02-first-pipeline.dot` and `docs/examples/ch03-adding-work.dot` — complete, valid .dot files the reader can copy and run.

**Step 3: Validate fixture files**

Run: `uv run attractor validate docs/examples/ch02-first-pipeline.dot`
Expected: "Pipeline '...' is valid"

Run: `uv run attractor validate docs/examples/ch03-adding-work.dot`
Expected: "Pipeline '...' is valid"

**Step 4: Commit**

```bash
git add docs/tutorial.md docs/examples/
git commit -m "docs: add tutorial chapters 1-3 (installation, first pipeline, adding work)"
```

---

## Task 2: Tutorial — Chapters 4-6 (Branching, Human Gates, Loops)

**Files:**
- Modify: `docs/tutorial.md`

**Step 1: Write chapters 4-6**

**Chapter 4: Branching and Decisions** must cover:
- Add a `diamond` Review node after Implement with two outgoing edges
- Edge conditions: `condition="outcome=success"` and `condition="outcome=fail"`
- Explain condition expressions: `outcome` is a special key set by the engine after each node
- Explain the edge selection algorithm in plain language (not the 5-step technical version — save that for Concepts): "The engine checks each edge's condition. If one matches, it follows that edge. If none match, it picks the unconditional edge with the highest weight."
- Show the graph visually (ASCII or describe the SVG)
- Run dry-run — explain that in simulation all nodes succeed, so the success path is taken
- Introduce the `weight` attribute for tiebreaking

**Chapter 5: Human Review Gates** must cover:
- Replace diamond with `hexagon` shape (wait.human handler)
- Explain what happens: pipeline pauses, presents choices derived from outgoing edge labels, waits for input
- Edge labels become button text: `[label="approve"]` becomes an option
- Accelerator keys: `[A] Approve`, `R) Reject`, `E - Escalate` — explain the three patterns
- Walk through running interactively (what the PM sees, what they type, what happens next)
- Mention the four interviewer types briefly (AutoApprove for CI, Queue for testing, Callback for custom, Recording for audit)

**Chapter 6: Iteration Loops** must cover:
- The "revise" edge from Review goes back to Plan, creating a loop
- Explain why this is powerful: the pipeline keeps trying until the human approves
- Introduce `max_retries` on nodes to prevent infinite loops
- Introduce `retry_target` — where to jump back to when a node fails
- Explain `loop_restart` edges: clear all pipeline state and restart from target
- Show the difference: `retry_target` keeps completed work, `loop_restart` starts fresh
- Show a 5-node loop pipeline as a complete .dot file

**Step 2: Create fixture DOT files**

Create `docs/examples/ch04-branching.dot`, `docs/examples/ch05-human-review.dot`, `docs/examples/ch06-loops.dot`.

**Step 3: Validate fixture files**

Run: `uv run attractor validate docs/examples/ch04-branching.dot`
Run: `uv run attractor validate docs/examples/ch05-human-review.dot`

Note: `ch06-loops.dot` may fail validation due to `start_no_incoming` if it has loop-back edges to Start. This is expected — explain in the chapter that loops involving Start require `loop_restart` or targeting a non-Start node.

**Step 4: Commit**

```bash
git add docs/tutorial.md docs/examples/
git commit -m "docs: add tutorial chapters 4-6 (branching, human gates, loops)"
```

---

## Task 3: Tutorial — Chapters 7-9 (Quality Gates, Parallel, Tools)

**Files:**
- Modify: `docs/tutorial.md`

**Step 1: Write chapters 7-9**

**Chapter 7: Quality Gates and Evaluation** must cover:
- Add `goal_gate=true` to the Implement node
- Explain what happens: the engine checks all goal gates before exiting. If any failed, it jumps to `retry_target` automatically.
- Enforcement timing: gates are checked at the exit node, not when the gate node runs. The pipeline attempts the full workflow first.
- Add `retry_target="Plan"` so failure loops back to planning
- Introduce the LLM-as-judge pattern: a separate evaluation node (e.g., "Evaluate") that reviews the output of Implement. Use a stronger model (`llm_model` attribute) for the judge. The evaluator returns success/fail, which routes via conditions.
- Multi-stage validation: show a chain of lint → test → LLM review → human review, each as a separate node
- Explain `allow_partial=true` — accept partial success when retries are exhausted instead of failing
- Complete .dot file showing goal gate + evaluation

**Chapter 8: Parallel Work** must cover:
- Split Implement into three parallel branches: API, Frontend, Tests
- Use `component` shape for fan-out (ParallelHandler) and `tripleoctagon` for fan-in (FanInHandler)
- Explain context isolation: each branch gets a clone of the context. Changes in one branch don't affect others.
- Explain join policies via `extra` attributes:
  - `wait_all` (default) — wait for all branches
  - `first_success` — take the fastest successful branch
  - `k_of_n` — proceed when K of N branches succeed
- Explain error policies:
  - `fail_fast` — cancel remaining branches on first failure
  - `continue` (default) — let all branches complete
  - `ignore` — treat failures as successes
- Show the complete fan-out/fan-in pattern as a .dot file

**Chapter 9: Tool Nodes** must cover:
- Add a `parallelogram` shaped node that runs `pytest` after implementation
- Explain `tool_command` in the `extra` dict: the shell command to run
- Explain timeout handling
- Show how tool output flows into context (the `tool.output` key)
- Complete .dot file with a tool node running a test command

**Step 2: Create fixture DOT files**

Create `docs/examples/ch07-quality-gates.dot`, `docs/examples/ch08-parallel.dot`, `docs/examples/ch09-tool-nodes.dot`.

**Step 3: Validate fixture files**

Run validate on each. Note: the quality gate file may need `parse_dot` + `run` directly if it has retry edges — explain this in the chapter.

**Step 4: Commit**

```bash
git add docs/tutorial.md docs/examples/
git commit -m "docs: add tutorial chapters 7-9 (quality gates, parallel, tools)"
```

---

## Task 4: Tutorial — Chapters 10-12 (Stylesheet, Context/Fidelity, Checkpoints)

**Files:**
- Modify: `docs/tutorial.md`

**Step 1: Write chapters 10-12**

**Chapter 10: Model Stylesheet** must cover:
- The pipeline now has 8+ nodes. Setting `llm_model` on each is tedious.
- Introduce `model_stylesheet` graph attribute with CSS-like syntax
- Three selector types with specificity:
  - `*` (specificity 0) — matches all nodes
  - `.classname` (specificity 1) — matches nodes in a subgraph named `classname` or with that class
  - `#NodeId` (specificity 2) — matches a single node by ID
- Three properties: `llm_model`, `llm_provider`, `reasoning_effort`
- Resolution rules: higher specificity wins. Equal specificity: later rule wins. Explicit node attributes always override stylesheet.
- Show subgraphs as a way to create classes:
  ```dot
  subgraph critical {
      Evaluate
      FinalReview
  }
  ```
  Nodes in subgraph `critical` get class `critical`, matching `.critical` selector.
- Complete example with a stylesheet assigning different models to different tiers

**Chapter 11: Context and Fidelity** must cover:
- The Context store: key-value pairs that flow through the pipeline
- Nodes read context (via prompt templates) and write context (via `context_updates` in Outcome)
- Auto-set variables: `pipeline.name`, `pipeline.goal`, `goal`, `outcome`, `preferred_label`
- Custom variables: nodes can set arbitrary keys like `design_spec`, `test_results`, etc.
- Fidelity modes — how much context carries from one node to the next:
  - `full` — everything (expensive, full LLM context)
  - `truncate` — pipeline name + goal only
  - `compact` (default) — name + goal + recent completed nodes + first 20 context vars
  - `summary:low` — name + goal + "Completed N stages"
  - `summary:medium` — name + goal + last 5 completed nodes
  - `summary:high` — name + goal + last 10 completed nodes + first 30 context vars
- Fidelity precedence: edge > node > graph `default_fidelity` > "compact"
- When to use each: `full` for evaluation nodes that need complete history, `compact` for most work, `summary:low` for simple routing
- `thread_id` for keeping related nodes on the same conversation thread (relevant for OpenAI threads)

**Chapter 12: Checkpoints and Recovery** must cover:
- After each node completes, the engine saves a checkpoint (when `checkpoint_enabled=True`)
- Checkpoint location: `{logs_root}/checkpoint.json`
- What gets saved: current_node, completed_nodes, node_retries, context_values, logs
- What doesn't get saved: in-flight LLM calls, handler internal state
- Demo: run a pipeline, find the checkpoint file, examine its JSON structure
- Resume: `attractor resume checkpoint.json pipeline.dot --log-dir ./logs`
- The engine picks up from the node after the checkpoint's `current_node`
- When to use: long-running pipelines, recovering from crashes, continuing after human review

**Step 2: Create fixture DOT files**

Create `docs/examples/ch10-stylesheet.dot` with a full stylesheet example.

**Step 3: Validate fixture**

Run: `uv run attractor validate docs/examples/ch10-stylesheet.dot`

**Step 4: Commit**

```bash
git add docs/tutorial.md docs/examples/
git commit -m "docs: add tutorial chapters 10-12 (stylesheet, context, checkpoints)"
```

---

## Task 5: Tutorial — Chapters 13-15 (HTTP Server, PRD to Product, Complete Pipeline)

**Files:**
- Modify: `docs/tutorial.md`

**Step 1: Write chapters 13-15**

**Chapter 13: Running the HTTP Server** must cover:
- Start: `attractor serve --port 8000`
- Submit a pipeline via curl: POST `/pipelines` with `{"dot_source": "...", "goal": "..."}`
- Check status: GET `/pipelines/{id}`
- Stream events: `curl -N http://localhost:8000/pipelines/{id}/events`
- Show SSE event format with real examples
- Cancel: POST `/pipelines/{id}/cancel`
- Get graph structure: GET `/pipelines/{id}/graph`
- Get context: GET `/pipelines/{id}/context`
- Explain when to use the server vs. CLI: server for integration with other tools, dashboards, CI/CD; CLI for interactive use

**Chapter 14: From PRD to Product** must cover:
- The full lifecycle: idea → PRD → design → implement → validate → ship
- Two patterns for PRD input:
  - **External PRD**: PM writes a PRD.md file. Pipeline prompt references it: `prompt="Read the PRD at ./prd.md and implement the requirements for $goal"`
  - **Generated PRD**: A "Write PRD" node generates the PRD from the goal into context. Later nodes read it from context.
- Show a complete pipeline:
  1. Start
  2. "Write PRD" (codergen) — generates PRD from goal
  3. "Review PRD" (hexagon) — human reviews generated PRD
  4. "Design Architecture" (codergen) — creates design spec based on PRD
  5. "Review Design" (hexagon) — human reviews design
  6. "Implement" (codergen, goal_gate=true, retry_target="Design Architecture") — builds the product
  7. "Run Tests" (parallelogram, tool) — runs test suite
  8. "Evaluate Against PRD" (codergen) — LLM judge compares output to PRD requirements, uses stronger model
  9. "Final Review" (hexagon) — human sign-off
  10. Exit
- Show the `model_stylesheet` assigning a stronger model to the evaluation node
- Explain how goal_gate on Implement forces the pipeline to loop back to Design if evaluation fails
- This chapter ties everything together: shapes, conditions, human gates, goal gates, tool nodes, context, fidelity, stylesheet

**Chapter 15: The Complete Pipeline** must cover:
- Show the full .dot file for the task management API pipeline built across all chapters
- Every concept from chapters 1-14 in one working example
- Walk through each section of the file with inline comments
- Show how to render to SVG for visualization
- Recap: what the PM has learned, where to go next (Cookbook for patterns, Concepts for deeper understanding, Reference for lookup)

**Step 2: Create fixture DOT files**

Create `docs/examples/ch14-prd-to-product.dot` and `docs/examples/ch15-complete-pipeline.dot`.

**Step 3: Validate fixtures where possible**

Note: some may not validate due to loop edges. Document this.

**Step 4: Commit**

```bash
git add docs/tutorial.md docs/examples/
git commit -m "docs: add tutorial chapters 13-15 (HTTP server, PRD to product, complete pipeline)"
```

---

## Task 6: Cookbook — Basic Patterns, Branching, Human-in-the-Loop

**Files:**
- Create: `docs/cookbook.md`

**Step 1: Write cookbook introduction and first three sections**

Start with a brief introduction: "Each recipe is self-contained: a problem, a complete .dot file, an explanation, and a command to try it."

**Basic Patterns (3 recipes):**
- Linear pipeline — problem: simplest possible pipeline. Full .dot, explain, `attractor run --dry-run`.
- Pipeline with goal and prompt templates — problem: control what the LLM does. Show `$goal` expansion.
- Dry-run for testing structure — problem: validate pipeline logic without LLM costs.

**Branching & Routing (5 recipes):**
- Binary decision — success/fail condition edges from a diamond node.
- Multi-way branch — 3+ edges from a conditional with different conditions.
- Weighted edges — `weight=10` on the preferred edge for tiebreaking.
- Preferred label matching — LLM returns `preferred_label` in Outcome, engine matches against edge labels.
- Context-based conditions — `condition="context.approval=granted&&outcome=success"`.

**Human-in-the-Loop (4 recipes):**
- Single approval gate — hexagon with approve/reject edges.
- Multi-option review — 4 outgoing edges with labels: approve, revise, escalate, reject.
- Accelerator keys — `[A] Approve`, `R) Reject` label formats.
- Recording decisions — mention RecordingInterviewer wrapping for audit trails (programmatic, not DOT).

Each recipe: problem (1 sentence), complete .dot file, explanation (2-3 paragraphs), try-it command.

**Step 2: Commit**

```bash
git add docs/cookbook.md
git commit -m "docs: add cookbook — basic patterns, branching, human-in-the-loop"
```

---

## Task 7: Cookbook — Iteration, Evaluation, PRDs, Parallel, Configuration, Operations

**Files:**
- Modify: `docs/cookbook.md`

**Step 1: Write remaining cookbook sections**

**Iteration & Retry (5 recipes):**
- Revise-and-resubmit loop — review → revise → re-review cycle.
- Retry with max_retries — node retries on failure up to limit.
- Goal gate enforcement — must-pass quality check at exit.
- allow_partial — accept best effort when retries exhausted.
- loop_restart — full state reset and pipeline restart.

**Evaluation & Quality (5 recipes):**
- LLM-as-judge — separate evaluation node using stronger model, returns success/fail.
- Multi-stage validation chain — lint (tool) → test (tool) → LLM review (codergen) → human review (hexagon).
- Goal gate with retry loop — evaluation fails → jump back to implementation.
- Fidelity control for evaluation — give judge node `fidelity="full"` for complete context.
- Model stylesheet for evaluation — `.evaluator { llm_model: claude-opus-4-6; reasoning_effort: high; }`.

**PRDs & Design Specs (5 recipes):**
- External PRD — file reference in prompt.
- Generated PRD — early pipeline stage creates PRD into context.
- Full lifecycle — Goal → PRD → Design → Implement → Validate → Exit.
- Human review of generated PRD — hexagon after PRD generation.
- Design spec iteration — review → revise loop with goal gate on design quality.

**Parallel Execution (4 recipes):**
- Fan-out / fan-in — component + tripleoctagon shapes.
- K-of-N join — proceed when 2 of 3 succeed.
- First-success join — take fastest branch.
- Error policy — fail_fast vs. continue.

**Configuration & Scaling (4 recipes):**
- Model stylesheet — all three selector types in one pipeline.
- Subgraph classes — grouping nodes for stylesheet targeting.
- Context fidelity modes — show when to use each mode.
- Thread IDs — conversation continuity for related nodes.

**Operations (4 recipes):**
- Checkpoint and resume — save/load after crash.
- HTTP server with SSE — submit + stream events via curl.
- Custom codergen backend — Python snippet showing MyBackend class.
- Validation before execution — validate + fix cycle.

**Step 2: Commit**

```bash
git add docs/cookbook.md
git commit -m "docs: add cookbook — iteration, evaluation, PRDs, parallel, config, operations"
```

---

## Task 8: Concepts Document

**Files:**
- Create: `docs/concepts.md`

**Step 1: Write all 15 concepts sections**

Title: "How Attractor Works"

Introduction: "This document explains how Attractor thinks. Read it to understand why pipelines behave the way they do. For copy-paste patterns, see the Cookbook. For exact attribute values, see the Reference."

Write all 15 sections as described in the design doc:

1. **Pipelines Are Graphs** — nodes, edges, directed flow. Why graphs: visual, version-controllable, every path explicit. One .dot file = one workflow.

2. **Node Types and Handlers** — each shape triggers a handler. The engine calls handlers through a common interface. Handlers are pluggable — swap backends without changing the pipeline. Table of shapes → behaviors (not the API table — the conceptual explanation of what each type does).

3. **Edge Routing** — the 5-step selection algorithm explained in full:
   1. Condition matching (edges with conditions that evaluate true)
   2. Preferred label matching (outcome suggests an edge label)
   3. Suggested next IDs (outcome suggests specific node IDs)
   4. Weight on unconditional edges (higher weight wins)
   5. Lexical tiebreak (alphabetical by target node ID)
   Why conditions live on edges: the same node can route to different targets based on outcome. This separates "what to do" (node) from "where to go next" (edge).

4. **Outcomes and Status** — every node produces an Outcome. Five statuses: SUCCESS, FAIL, PARTIAL_SUCCESS, RETRY, SKIPPED. Outcomes carry context_updates (data to store), preferred_label (routing hint), suggested_next_ids (routing hint), notes, failure_reason. The engine uses outcome to drive routing and context updates.

5. **The Context Store** — a key-value dictionary that flows through the pipeline. Nodes read from context (in prompts) and write to context (via outcome.context_updates). Auto-set keys: pipeline.name, pipeline.goal, goal, outcome, preferred_label. Custom keys: any string. Context is the communication channel between stages.

6. **Fidelity** — controls how much context carries from one node to the next. Five modes: full, truncate, compact (default), summary:low/medium/high. Precedence chain: edge fidelity > node fidelity > graph default_fidelity > "compact". Why this matters: LLMs have limited context windows. Full fidelity is accurate but expensive. Summary is cheap but lossy. Choose based on what the next node needs.

7. **Human-in-the-Loop** — the interviewer pattern. When the engine reaches a hexagon node, it pauses. It derives choices from outgoing edge labels. It presents choices to the interviewer. The human (or automated interviewer) picks one. The engine follows the matching edge. Why choices come from edges: the graph structure defines what's possible. The human picks from those possibilities.

8. **Goal Gates** — nodes marked `goal_gate=true` must succeed for the pipeline to complete. Enforcement happens at the exit node: the engine checks all goal gates. If any failed, it jumps to that node's `retry_target`. If no retry_target exists, the pipeline fails. Why enforcement is deferred: the pipeline should attempt the full workflow before checking quality. Early enforcement would miss work that might fix the problem.

9. **Evaluation and Validation** — two kinds. Static validation runs before execution: checks graph structure (start node exists, all nodes reachable, edge targets valid). Runtime evaluation runs during execution: goal gates assess output quality, condition expressions route based on results, LLM-as-judge nodes review other nodes' work. How to build evaluation into pipeline design: use a dedicated evaluation node with a stronger model, feed it the output and the original requirements, route based on its judgment.

10. **PRDs, Design Specs, and Pipeline Inputs** — how external documents feed into pipelines. The `goal` attribute is the lightweight PRD — one sentence of intent. For richer input, reference external files in prompt templates. For generated documents, early pipeline stages produce specs into context that later stages consume. Two patterns: PM writes PRD → pipeline implements it. PM states goal → pipeline generates PRD → human reviews → pipeline implements.

11. **Checkpoints and Recovery** — after each node, the engine saves state to `{logs_root}/checkpoint.json`. If the process crashes, `attractor resume` picks up from the last completed node. What's saved: completed nodes, context values, retry counts, logs. What's lost: in-flight LLM calls restart from scratch.

12. **Parallel Execution** — fan-out (component shape) splits execution into parallel branches. Each branch gets an isolated clone of context. Fan-in (tripleoctagon shape) collects results. Join policies control when fan-in proceeds: wait_all, first_success, k_of_n. Error policies control failure handling: fail_fast, continue, ignore. Why context isolation: prevents branches from interfering with each other.

13. **Model Stylesheet** — CSS-like syntax for assigning LLM configuration to nodes. Three selectors: `*` (all nodes), `.class` (nodes in a named subgraph), `#id` (one node). Three properties: llm_model, llm_provider, reasoning_effort. Specificity rules: `#id` > `.class` > `*`. Equal specificity: later rule wins. Explicit node attributes always override. Why this exists: as pipelines grow, per-node configuration becomes tedious and error-prone.

14. **Transforms** — pre-processing steps between parsing and execution. The lifecycle: parse DOT → apply transforms → validate → execute. Built-in transforms: VariableExpansionTransform (replaces `$goal` in prompts), StylesheetTransform (applies model_stylesheet to nodes). Custom transforms can modify the graph before execution.

15. **The Event Stream** — every engine action emits an event (pipeline.start, node.start, node.complete, node.retry, goal_gate.retry, loop.restart, pipeline.complete, pipeline.error, pipeline.finalize). Events have a kind, node_id, data dict, and timestamp. The engine is headless — it doesn't print or display anything. Events power the SSE endpoint, logging, and monitoring. Frontends consume events to show progress.

**Step 2: Commit**

```bash
git add docs/concepts.md
git commit -m "docs: add concepts document — how Attractor works"
```

---

## Task 9: Reference Document

**Files:**
- Create: `docs/reference.md`

**Step 1: Write all 14 reference sections**

Title: "Attractor Reference"

Introduction: "Lookup tables for pipeline authoring. For explanations, see Concepts. For examples, see the Cookbook."

Write all 14 sections as lookup tables. Every value must match the actual codebase (use the API surface data gathered earlier).

1. **CLI Commands** — all 4 commands (run, validate, resume, serve) with every flag, type, default, description, and example invocation.

2. **Node Shapes** — shape → handler type → one-sentence purpose. All 9 shapes from SHAPE_HANDLER_MAP.

3. **Node Attributes** — all 20 fields from Node dataclass: attribute name, type, default, description. Include `extra` dict for arbitrary custom attributes.

4. **Edge Attributes** — all 9 fields from Edge dataclass: attribute name, type, default, description.

5. **Graph Attributes** — all fields from Graph dataclass relevant to pipeline authors: name, goal, label, model_stylesheet, default_max_retry (default 50), retry_target, fallback_retry_target, default_fidelity. Exclude internal fields (nodes, edges, subgraphs, node_defaults, edge_defaults).

6. **Condition Expression Syntax** — operators (=, !=, &&), special keys (outcome, preferred_label), context key resolution (context.KEY and bare KEY both work), truthiness for bare keys, empty condition = always true. Include 6+ examples.

7. **Model Stylesheet Syntax** — three selectors with specificity values. Three properties. Resolution rules. Show the `subgraph` → `.class` derivation. Include a complete example.

8. **Fidelity Modes** — table of all 6 modes (full, truncate, compact, summary:low, summary:medium, summary:high) with what each includes. Precedence chain. When to use each.

9. **Outcome Statuses** — all 5 StageStatus values with routing implications and when each occurs.

10. **Interviewer Types** — all 4 implementations with constructor parameters and behavior. Include AnswerValue and QuestionType enums. Include accelerator key formats.

11. **Validation Rules** — all 10 rules with rule name, severity, description, and how to fix.

12. **Pipeline Events** — all 9 event kinds with node_id presence, data fields, and when emitted.

13. **HTTP Server Endpoints** — all 6 endpoints with method, path, request body (if applicable), response body, and curl example.

14. **Context Namespace Conventions** — auto-set keys (pipeline.name, pipeline.goal, goal, outcome, preferred_label, last_stage, last_response), custom key naming advice.

**Step 2: Commit**

```bash
git add docs/reference.md
git commit -m "docs: add reference document — complete attribute and API lookup"
```

---

## Task 10: Update README, Remove Old User Guide, Final Verification

**Files:**
- Modify: `README.md`
- Delete: `docs/user-guide.md`

**Step 1: Update README**

Update `README.md` to:
- Keep the title and opening description
- Keep Quick Start section but link to Tutorial for the full walkthrough
- Update Documentation section to list all four new docs:
  - [Tutorial](./docs/tutorial.md) — learn by building a complete product
  - [Cookbook](./docs/cookbook.md) — copy-paste pipeline patterns
  - [Concepts](./docs/concepts.md) — understand how Attractor works
  - [Reference](./docs/reference.md) — look up attributes, operators, events
- Keep NLSpec links (attractor-spec.md, coding-agent-loop-spec.md, unified-llm-spec.md) in a separate "Specifications" section for implementors
- Keep "Building Your Own Attractor" and "Terminology" sections

**Step 2: Delete old user guide**

```bash
rm docs/user-guide.md
```

**Step 3: Validate all example .dot files**

```bash
for f in docs/examples/*.dot; do echo "=== $f ===" && uv run attractor validate "$f" 2>&1; done
```

Document any files that intentionally fail validation (loop edges, goal gate retries) with a comment at the top of those .dot files.

**Step 4: Verify all internal links**

Check that all cross-document links (`[Cookbook](./cookbook.md)`, etc.) use correct relative paths.

**Step 5: Commit**

```bash
git add README.md docs/
git rm docs/user-guide.md
git commit -m "docs: update README, remove old user guide, add example DOT files"
```

**Step 6: Push**

```bash
git push origin main
```

---

## Verification

After all tasks complete:

1. `ls docs/` shows: `tutorial.md`, `cookbook.md`, `concepts.md`, `reference.md`, `examples/`, `plans/`
2. `wc -l docs/tutorial.md` — should be 2000+ lines (15 chapters)
3. `wc -l docs/cookbook.md` — should be 1500+ lines (~30 recipes)
4. `wc -l docs/concepts.md` — should be 600+ lines (15 sections)
5. `wc -l docs/reference.md` — should be 800+ lines (14 sections)
6. All example .dot files in `docs/examples/` validate (or are documented as intentional failures)
7. README links to Tutorial as primary entry point
8. No broken internal links between documents
