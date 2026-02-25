# How Attractor Works

This document explains how Attractor thinks. Read it when you need to understand why pipelines behave the way they do. For copy-paste patterns, see the [Cookbook](./cookbook.md). For exact attribute values, see the [Reference](./reference.md).

---

## 1. Pipelines Are Graphs

An Attractor pipeline is a directed graph. Nodes are stages of work. Edges are transitions between stages. Execution flows from a single Start node to a single Exit node, following edges selected at each step.

Why graphs? Three reasons. First, graphs are visual — you can render a `.dot` file and see every path your pipeline can take. Second, graphs are version-controllable — a pipeline is a text file, diffable and mergeable like code. Third, every path is explicit. There are no hidden transitions, no implicit fallbacks, no magic. If a path exists, you drew it. If a path doesn't exist, the pipeline cannot take it.

One `.dot` file equals one workflow. The graph IS the program.

---

## 2. Node Types and Handlers

Each node has a shape, and each shape maps to a handler. When the engine reaches a node, it looks up the handler for that node's shape and calls `execute`, which returns an Outcome. This interface is uniform — every handler, regardless of what it does internally, produces the same output type.

Handlers are pluggable. The engine doesn't care whether a `box` node calls Claude, GPT-4, or a local model. It calls the handler, gets an Outcome, and moves on. You can swap backends without changing a single edge in your pipeline.

| Shape | Handler | What It Does |
|---|---|---|
| `Mdiamond` | start | Entry point — initializes context, begins execution |
| `Msquare` | exit | Terminal — checks goal gates, ends pipeline |
| `box` | codergen | Sends prompt to an LLM, returns generated content |
| `hexagon` | wait.human | Pauses for human input, routes on the answer |
| `diamond` | conditional | Evaluates conditions, routes without producing content |
| `component` | parallel | Fans out to multiple branches concurrently |
| `tripleoctagon` | parallel.fan_in | Collects and ranks parallel branch results |
| `parallelogram` | tool | Executes an external tool or command |
| `house` | stack.manager_loop | Manages iterative sub-workflows |

If a node specifies `type` explicitly, that overrides the shape-based lookup. This lets you use custom handlers without inventing new shapes.

---

## 3. Edge Routing

After a node executes, the engine must pick the next edge. It uses a five-step selection algorithm, evaluated in strict order. The first step that produces a match wins.

**Step 1: Condition matching.** The engine evaluates every edge that has a `condition` attribute. Conditions are simple expressions — `outcome=success`, `preferred_label=approve`, or compound checks joined by `&&`. If one or more conditional edges evaluate to true, the engine picks the one with the highest weight (ties broken alphabetically by target node ID).

**Step 2: Preferred label.** If the Outcome carries a `preferred_label` (say, `"revise"`), the engine looks for an edge whose label matches. Labels are compared case-insensitively with accelerator prefixes stripped, so `[R] Revise` matches `revise`.

**Step 3: Suggested next IDs.** The Outcome can suggest specific target node IDs. The engine checks outgoing edges for those targets, in order.

**Step 4: Weight on unconditional edges.** Among edges with no condition, the engine picks the one with the highest `weight`.

**Step 5: Lexical tiebreak.** If weights are equal, the engine sorts alphabetically by target node ID and picks the first.

Why put conditions on edges instead of nodes? Because it separates two concerns. The node decides *what to do* — generate code, review a document, run a test. The edge decides *where to go next* — route to revision if the review failed, advance if it passed. This separation means you can reuse nodes in different routing contexts without modification.

---

## 4. Outcomes and Status

Every node produces an Outcome. This is the engine's universal language for "what happened."

An Outcome carries a `status` — one of five values:

- **SUCCESS** — the node completed its work satisfactorily.
- **FAIL** — the node could not complete. The pipeline may retry or halt.
- **PARTIAL_SUCCESS** — the node finished but with caveats. Treated as success for goal gate checks.
- **RETRY** — the node wants another attempt.
- **SKIPPED** — the node chose not to act.

Beyond status, an Outcome carries routing hints (`preferred_label`, `suggested_next_ids`), a `context_updates` dictionary that the engine merges into the context store, free-text `notes`, and a `failure_reason` for diagnostics.

The engine uses the Outcome twice: first to update context (applying `context_updates` and setting the `outcome` and `preferred_label` keys), then to select the next edge via the routing algorithm. Outcomes are also stored per-node, so goal gate checks can inspect them at exit time.

---

## 5. The Context Store

Context is a thread-safe key-value store that flows through the pipeline. Every node can read from it and write to it. It is how stages communicate.

The engine auto-sets several keys. Before execution begins, it writes `pipeline.name`, `pipeline.goal`, and `goal` from the graph's metadata. After each node completes, it writes `outcome` (the status string) and `preferred_label` (if the Outcome provided one). Handlers add their own keys through `context_updates` in the Outcome.

You use custom context keys for stage-to-stage communication. An early node might set `architecture_decision=microservices`, and a later node's prompt can reference that value. The [Tutorial](./tutorial.md) walks through this pattern. The [Cookbook](./cookbook.md) shows advanced uses like accumulating review feedback across iterations.

Context supports `clone()` for parallel execution — each branch gets an independent copy so branches cannot interfere with each other. It supports `snapshot()` for checkpointing — the engine serializes all values to disk after each step.

---

## 6. Fidelity

LLMs have limited context windows. Sending the full execution history to every node wastes tokens and can exceed limits. Fidelity controls how much context the engine carries forward.

Six modes, from most to least information:

| Mode | What the LLM sees |
|---|---|
| `full` | Complete conversation history from the session thread |
| `compact` | Pipeline name, goal, list of completed stages with statuses, current context keys (default) |
| `truncate` | Pipeline name and goal only |
| `summary:high` | Goal, last 10 stages, up to 30 context keys |
| `summary:medium` | Goal, last 5 stages |
| `summary:low` | Goal and a count of completed stages |

The engine resolves fidelity through a four-level precedence chain: edge fidelity overrides node fidelity, which overrides the graph's `default_fidelity`, which falls back to `compact`. This means you can set a global default and override it precisely where needed — full fidelity for a critical review step, truncate for a quick formatting pass.

Think of fidelity as a zoom lens. `full` shows every detail but costs the most. `summary:low` is cheap but the LLM may miss context. `compact` is the pragmatic middle ground, which is why it's the default.

---

## 7. Human-in-the-Loop

The hexagon node implements the interviewer pattern. When the engine reaches a hexagon, it pauses execution, derives a set of choices from the outgoing edge labels, and presents them to an interviewer (a human at a terminal, or a programmatic stand-in). The interviewer picks one. The engine routes along the matching edge.

Why derive choices from edges? Because the graph structure already defines every possible next step. The hexagon doesn't need a hardcoded list of options — it reads them from the topology. Add an edge labeled "Reject" and the human sees a "Reject" option. Remove it and the option disappears. The graph is the single source of truth.

This pattern turns any decision point into a human gate. Place a hexagon between "Generate Draft" and "Publish" and you have a review step. Place one between "Plan" and "Execute" and you have a sign-off gate. The [Tutorial](./tutorial.md) builds both patterns step by step.

---

## 8. Goal Gates

Mark a node with `goal_gate=true` to declare that its success is required for the pipeline to finish. The engine does not check gates at the node itself — it waits until execution reaches the Exit node.

At the exit, the engine inspects the stored Outcome for every goal-gated node. If any gated node's Outcome is not a success (neither SUCCESS nor PARTIAL_SUCCESS), the pipeline does not exit. Instead, the engine looks up the `retry_target` — a node ID to jump back to. If a retry target exists, the engine redirects there and re-executes from that point. If no retry target exists, the pipeline fails.

Why deferred enforcement? Because a pipeline should attempt the full workflow before judging quality. A code-review node might fail on the first pass, but if the next node fixes the issues and re-reviews successfully, the gate is satisfied. Checking gates only at exit lets the pipeline self-correct through its normal flow before triggering a costly retry loop.

---

## 9. Evaluation and Validation

Attractor separates two kinds of quality assurance, and they operate at different times.

**Static validation** runs before execution begins. It checks graph structure: does a start node exist? Is there at least one exit node? Are all nodes reachable from start? Do all edge targets point to real nodes? Does the start node have no incoming edges? Are all shapes recognized? Are fidelity values valid? Static validation catches authoring errors — typos in node IDs, orphaned nodes, missing entry points. If validation fails, the engine refuses to run.

**Runtime evaluation** happens during execution. This is where you assess the quality of generated work. Goal gates are one mechanism — they check Outcome statuses at exit. Condition expressions on edges are another — they route based on results like `outcome=fail`. The most powerful approach is the LLM-as-judge pattern: dedicate a node to evaluation, feed it the output plus requirements, and let a strong model decide whether the work passes. Route on its judgment.

To build an evaluation node, create a `box` node whose prompt asks the LLM to assess output against criteria. Use the model stylesheet to assign a stronger model to this node (see [section 13](#13-model-stylesheet)). Have it set `preferred_label` to "approve" or "revise" and let edge routing handle the rest. The [Cookbook](./cookbook.md) has a complete example.

---

## 10. PRDs, Design Specs, and Pipeline Inputs

A pipeline's `goal` attribute is a lightweight PRD — a sentence or two describing what the pipeline should produce. For many workflows, this suffices.

For richer input, two patterns work well.

**Pattern 1: External PRD.** The PM writes a detailed requirements document. Early nodes reference it in their prompts, either by including the content in context or by pointing to a file path. The pipeline implements the requirements as specified.

**Pattern 2: Generated PRD.** The PM provides a brief goal. An early stage generates a full PRD from that goal. A hexagon node presents it to the PM for review. If approved, subsequent stages implement it. If rejected, the pipeline revises.

Pattern 2 is powerful because it keeps the PM in control while letting the LLM handle the tedious work of writing structured requirements. The pipeline becomes a conversation: human intent in, structured spec out, human approval, then implementation.

---

## 11. Checkpoints and Recovery

After each node completes, the engine saves a checkpoint to disk. If a pipeline crashes — process killed, API timeout, power failure — you resume from the last checkpoint instead of starting over.

A checkpoint captures:

- **completed_nodes** — the ordered list of nodes already executed.
- **context_values** — the full context store snapshot.
- **node_retries** — retry counts per node.
- **current_node** — the node that just finished.
- **logs** — accumulated log entries.

What the checkpoint does not capture: in-flight LLM calls. If the process dies mid-generation, that call is lost. On resume, the engine picks up at the next node after the checkpoint, so the interrupted node's work must be re-executed. This is a deliberate tradeoff — checkpointing partial LLM responses would add complexity for little benefit, since most calls complete in seconds.

---

## 12. Parallel Execution

The `component` shape triggers the parallel handler. It fans out to all outgoing edges concurrently, giving each branch an isolated clone of the context store. Branches execute independently — one branch cannot read or write another's context.

A `tripleoctagon` fan-in node collects the results. It ranks branches by outcome status (SUCCESS > PARTIAL_SUCCESS > RETRY > FAIL > SKIPPED), then by score, then alphabetically. The best candidate's ID flows into context for downstream nodes.

Three join policies control when parallel execution succeeds:

- **wait_all** — all branches must complete; any failure yields PARTIAL_SUCCESS.
- **first_success** — the first branch to succeed ends the wait.
- **k_of_n** — at least *k* branches must succeed (you set *k*).

Three error policies control how failures propagate:

- **fail_fast** — cancel remaining branches on first failure.
- **continue** — let all branches finish regardless.
- **ignore** — treat failures as non-fatal.

Why isolated context clones? Without isolation, concurrent branches writing to the same context key would race. One branch's "architecture_decision=monolith" would overwrite another's "architecture_decision=microservices" unpredictably. Cloning eliminates the problem at the cost of requiring explicit fan-in to merge results.

---

## 13. Model Stylesheet

Hardcoding `llm_model` on every node doesn't scale. If you want to switch from Claude to GPT-4 across thirty nodes, you'd edit thirty attributes.

The model stylesheet solves this with CSS-like syntax. Declare rules in the graph's `model_stylesheet` attribute:

```
* { llm_model: claude-sonnet-4-20250514 }
.review { llm_model: claude-opus-4-20250514; reasoning_effort: high }
#final_check { llm_model: o1; llm_provider: openai }
```

Three selectors: `*` matches all nodes. `.class` matches nodes in a subgraph whose derived class name matches (or nodes with explicit `classes`). `#id` matches one specific node.

Three properties: `llm_model`, `llm_provider`, `reasoning_effort`.

Specificity follows CSS conventions: `#id` (2) beats `.class` (1) beats `*` (0). Equal specificity: the later rule wins. Explicit node attributes always override stylesheet rules — if a node sets `llm_model` directly, the stylesheet won't touch it.

The stylesheet is applied as a transform before execution (see [section 14](#14-transforms)). This means you can inspect the resolved configuration of every node after transforms run but before the pipeline starts.

---

## 14. Transforms

Transforms are pre-processing steps that modify the graph between parsing and execution. The lifecycle is:

1. **Parse** — read the `.dot` file into an in-memory Graph.
2. **Apply transforms** — each transform receives the Graph and returns a (possibly modified) Graph.
3. **Validate** — check the transformed graph for structural errors.
4. **Execute** — run the pipeline.

Two transforms are built in:

- **VariableExpansionTransform** — replaces `$goal` in node prompts with the graph's `goal` value. Write `$goal` in a prompt and it expands before execution.
- **StylesheetTransform** — applies the model stylesheet rules to resolve `llm_model`, `llm_provider`, and `reasoning_effort` on every node.

Custom transforms implement a simple protocol: a class with an `apply(graph: Graph) -> Graph` method. You can use them to inject nodes, rewrite prompts, enforce naming conventions, or any other structural modification. Register custom transforms via `EngineConfig.extra_transforms`.

Transforms run in order: built-in first, then custom. Since validation runs after all transforms, your custom transforms can create nodes and edges freely — the validator will catch any structural problems they introduce.

---

## 15. The Event Stream

The engine is headless. It prints nothing. Instead, every action emits an event.

An event carries four fields:

- **kind** — what happened (`pipeline.start`, `node.start`, `node.complete`, `goal_gate.retry`, `pipeline.complete`, `pipeline.error`, `loop.restart`).
- **node_id** — the node involved, if any.
- **data** — a dictionary of additional details (status, error messages, retry targets).
- **timestamp** — when it happened.

This design separates execution from presentation. The engine doesn't know whether you're running in a terminal, a web UI, or a CI pipeline. It produces events. Consumers decide what to do with them.

In practice, the HTTP server forwards events as Server-Sent Events (SSE) for real-time progress display. A logging consumer writes them to disk. A monitoring system aggregates them for dashboards. Your custom consumer can filter, transform, or react to events however you choose.

The event stream also makes testing straightforward. Assert on emitted events rather than parsing stdout. Check that `node.complete` fired with `status=success` for a specific node. Verify that `goal_gate.retry` appeared when a gate failed. Events are structured data, not formatted text, so assertions are precise.
