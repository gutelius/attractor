# Attractor Reference

Lookup tables for pipeline authoring. For explanations, see [Concepts](./concepts.md). For examples, see the [Cookbook](./cookbook.md).

---

## 1. CLI Commands

### `attractor run <dotfile>`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--goal` | str | `""` | Override pipeline goal |
| `--model` | str | `""` | Default LLM model |
| `--log-dir` | str | `.attractor-runs/{name}` | Log directory |
| `--dry-run` | flag | `false` | Simulate without calling LLM backends |
| `--max-steps` | int | `1000` | Maximum execution steps |

### `attractor validate <dotfile>`

No options. Parses, transforms, and validates the DOT file. Exits 0 on success, 1 on error.

### `attractor resume <checkpoint_path> <dotfile>`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--log-dir` | str | `""` | Log directory |

### `attractor serve`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--host` | str | `0.0.0.0` | Host to bind |
| `--port` | int | `8000` | Port to bind |

---

## 2. Node Shapes

Every node's handler type resolves from its `shape` attribute via `SHAPE_HANDLER_MAP`. Set `type` explicitly to override.

| Shape | Handler Type | Purpose |
|-------|-------------|---------|
| `Mdiamond` | `start` | Pipeline entry point |
| `Msquare` | `exit` | Pipeline terminal |
| `box` | `codergen` | LLM generation (default) |
| `hexagon` | `wait.human` | Human-in-the-loop gate |
| `diamond` | `conditional` | Condition-based routing |
| `component` | `parallel` | Parallel fan-out |
| `tripleoctagon` | `parallel.fan_in` | Parallel fan-in / join |
| `parallelogram` | `tool` | Tool execution |
| `house` | `stack.manager_loop` | Manager loop with sub-stack |

Any unrecognized shape defaults to `codergen`.

---

## 3. Node Attributes

All fields from the `Node` dataclass. Set these as DOT node attributes.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | str | `""` | Node identifier (set from DOT node name) |
| `label` | str | `""` | Display label; doubles as prompt if `prompt` is empty |
| `shape` | str | `"box"` | Graphviz shape; determines handler type |
| `type` | str | `""` | Explicit handler type override |
| `prompt` | str | `""` | Prompt text sent to the LLM |
| `max_retries` | int | `0` | Maximum retry attempts for this node |
| `goal_gate` | bool | `False` | Require success before pipeline exit |
| `retry_target` | str | `""` | Node ID to jump to on goal-gate failure |
| `fallback_retry_target` | str | `""` | Fallback if `retry_target` is absent |
| `fidelity` | str | `""` | Context fidelity mode for this node |
| `thread_id` | str | `""` | Thread ID for full-fidelity session reuse |
| `classes` | list[str] | `[]` | CSS-like classes for stylesheet matching |
| `timeout` | str | `""` | Execution timeout |
| `llm_model` | str | `""` | LLM model override |
| `llm_provider` | str | `""` | LLM provider override |
| `reasoning_effort` | str | `"high"` | Reasoning effort level |
| `auto_status` | bool | `False` | Automatically set status from handler |
| `allow_partial` | bool | `False` | Accept partial success as passing |
| `subgraph` | str | `""` | Containing subgraph name (set by parser) |
| `extra` | dict | `{}` | Arbitrary extra attributes |

---

## 4. Edge Attributes

All fields from the `Edge` dataclass. Set these as DOT edge attributes.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `source` | str | `""` | Source node ID |
| `target` | str | `""` | Target node ID |
| `label` | str | `""` | Display label |
| `condition` | str | `""` | Condition expression for routing |
| `weight` | int | `0` | Edge weight for priority (higher wins) |
| `fidelity` | str | `""` | Override fidelity for this transition |
| `thread_id` | str | `""` | Override thread ID for this transition |
| `loop_restart` | bool | `False` | Reset pipeline state on traversal |
| `extra` | dict | `{}` | Arbitrary extra attributes |

---

## 5. Graph Attributes

Pipeline-level settings. Set these as DOT graph attributes.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | `""` | Pipeline name |
| `goal` | str | `""` | Pipeline goal (mirrored to context) |
| `label` | str | `""` | Display label |
| `model_stylesheet` | str | `""` | CSS-like model assignment rules |
| `default_max_retry` | int | `50` | Default max retries for all nodes |
| `retry_target` | str | `""` | Default retry target for goal gates |
| `fallback_retry_target` | str | `""` | Default fallback retry target |
| `default_fidelity` | str | `""` | Default fidelity mode for all nodes |

---

## 6. Condition Expression Syntax

Edge conditions control routing. The engine evaluates them against the current outcome and context.

### Operators

| Operator | Syntax | Meaning |
|----------|--------|---------|
| Equality | `key=value` | True if resolved key equals value |
| Inequality | `key!=value` | True if resolved key does not equal value |
| AND | `clause && clause` | True if all clauses are true |
| Truthiness | `key` | True if resolved key is non-empty |

### Special keys

| Key | Resolves to |
|-----|-------------|
| `outcome` | Current `StageStatus` value (e.g., `success`, `fail`) |
| `preferred_label` | The `preferred_label` field from the outcome |

### Context key resolution

| Syntax | Lookup |
|--------|--------|
| `context.KEY` | `context["context.KEY"]`, then `context["KEY"]` |
| `KEY` (bare) | `context["KEY"]` |

Missing keys resolve to empty string. An empty condition always evaluates to true.

### Examples

| Condition | Meaning |
|-----------|---------|
| `outcome=success` | Last node succeeded |
| `outcome=fail` | Last node failed |
| `outcome!=retry` | Last node did not request retry |
| `preferred_label=option_a` | LLM chose "option_a" |
| `context.ready` | Context key "ready" is non-empty |
| `outcome=success && context.approved` | Succeeded and "approved" is set |

---

## 7. Model Stylesheet Syntax

Assign LLM models to nodes without editing each node. Set the `model_stylesheet` graph attribute.

### Selectors

| Selector | Specificity | Matches |
|----------|-------------|---------|
| `*` | 0 | All nodes |
| `.classname` | 1 | Nodes with `classname` in their `classes` list |
| `#nodeid` | 2 | Node with exact `id` |

### Properties

| Property | Effect |
|----------|--------|
| `llm_model` | Sets the LLM model |
| `llm_provider` | Sets the LLM provider |
| `reasoning_effort` | Sets reasoning effort level |

### Resolution rules

1. Higher specificity wins.
2. Equal specificity: later declaration wins.
3. Explicit node attributes always override stylesheet values.
4. `reasoning_effort` overrides only when the node still has the default value (`"high"`).

### Subgraph class derivation

Nodes inside a subgraph inherit a class derived from the subgraph label: lowercased, spaces replaced with hyphens, non-alphanumeric characters stripped. A subgraph labeled `"Code Review"` produces class `code-review`.

### Example

```
* { llm_model: gpt-4o; }
.draft { llm_model: claude-sonnet-4-20250514; reasoning_effort: medium; }
#final_review { llm_model: claude-opus-4-0-20250115; reasoning_effort: high; }
```

---

## 8. Fidelity Modes

Fidelity controls how much context each node receives.

### Modes

| Mode | What the node receives |
|------|----------------------|
| `full` | Complete conversation history (session reuse via thread ID) |
| `truncate` | Truncated context to fit token limits |
| `compact` | Key-value summary of context (default) |
| `summary:low` | Brief summary of prior work |
| `summary:medium` | Moderate summary of prior work |
| `summary:high` | Detailed summary of prior work |

### Precedence chain

The engine resolves fidelity in this order (first non-empty valid value wins):

1. **Edge** `fidelity` attribute
2. **Node** `fidelity` attribute
3. **Graph** `default_fidelity` attribute
4. **Hardcoded default**: `compact`

---

## 9. Outcome Statuses

Every node execution produces an `Outcome` with one of these statuses.

| Status | Value | Routing behavior |
|--------|-------|-----------------|
| `SUCCESS` | `"success"` | Advance along `outcome=success` edges |
| `FAIL` | `"fail"` | Advance along `outcome=fail` edges; pipeline errors if no fail edge exists |
| `PARTIAL_SUCCESS` | `"partial_success"` | Treated as success for `is_success` checks; routes via `outcome=partial_success` |
| `RETRY` | `"retry"` | Re-execute the node (counts against `max_retries`) |
| `SKIPPED` | `"skipped"` | Advance along `outcome=skipped` edges |

---

## 10. Interviewer Types

Interviewers handle human-in-the-loop interactions at `wait.human` nodes.

### Implementations

| Class | Behavior | Use case |
|-------|----------|----------|
| `AutoApproveInterviewer` | Always selects first option / YES | CI/CD, testing |
| `QueueInterviewer` | Pops answers from a pre-filled queue | Deterministic testing |
| `CallbackInterviewer` | Delegates to a callback function | Custom integrations |
| `RecordingInterviewer` | Wraps another interviewer, records all Q&A pairs | Auditing, replay |

### QuestionType enum

| Value | String | Description |
|-------|--------|-------------|
| `YES_NO` | `"yes_no"` | Binary yes/no question |
| `MULTIPLE_CHOICE` | `"multiple_choice"` | Pick from a list of options |
| `FREEFORM` | `"freeform"` | Open text input |
| `CONFIRMATION` | `"confirmation"` | Confirm an action |

### AnswerValue enum

| Value | String | Description |
|-------|--------|-------------|
| `YES` | `"yes"` | Affirmative |
| `NO` | `"no"` | Negative |
| `SKIPPED` | `"skipped"` | Question skipped |
| `TIMEOUT` | `"timeout"` | No answer within timeout |

### Accelerator key formats

The `parse_accelerator_key` function extracts shortcut keys from option labels:

| Format | Example | Extracted key |
|--------|---------|--------------|
| `[K] Label` | `[A] Approve` | `A` |
| `K) Label` | `R) Reject` | `R` |
| `K - Label` | `S - Skip` | `S` |
| *(fallback)* | `Proceed` | `P` (first character) |

---

## 11. Validation Rules

The validator runs these 10 rules against every pipeline. Errors block execution; warnings are advisory.

| Rule | Severity | Description | Fix |
|------|----------|-------------|-----|
| `start_node` | ERROR | Pipeline must have exactly one start node (`Mdiamond`) | Add or remove start nodes until exactly one remains |
| `terminal_node` | ERROR | Pipeline must have at least one terminal node (`Msquare`) | Add a node with `shape=Msquare` |
| `reachability` | ERROR | All nodes must be reachable from the start node | Add edges to unreachable nodes or remove them |
| `edge_target_exists` | ERROR | Every edge source and target must refer to an existing node | Fix the node ID in the edge definition |
| `start_no_incoming` | ERROR | Start node must have no incoming edges | Remove edges that point to the start node |
| `exit_no_outgoing` | ERROR | Exit node must have no outgoing edges | Remove edges that leave the exit node |
| `fidelity_valid` | WARNING | Node fidelity must be a recognized mode | Use one of: `compact`, `full`, `truncate`, `summary:low`, `summary:medium`, `summary:high` |
| `retry_target_exists` | WARNING | `retry_target` and `fallback_retry_target` must refer to existing nodes | Fix the target node ID |
| `goal_gate_has_retry` | WARNING | Nodes with `goal_gate=true` should have a `retry_target` or `fallback_retry_target` | Add a `retry_target` attribute |
| `prompt_on_llm_nodes` | WARNING | Codergen nodes should have a `prompt` or `label` | Add a `prompt` or `label` attribute |

---

## 12. Pipeline Events

The engine emits these events during execution. Subscribe via `engine.events` or the SSE endpoint.

| Event | `node_id` | Data fields | When emitted |
|-------|-----------|-------------|-------------|
| `pipeline.start` | — | `name`, `goal` | Pipeline begins |
| `pipeline.complete` | exit node | — | Pipeline reaches exit node and all goal gates pass |
| `pipeline.error` | failing node | `error` | Unrecoverable failure (no fail edge, unsatisfied goal gate) |
| `pipeline.finalize` | — | — | After the main loop ends, regardless of outcome |
| `node.start` | current node | — | Before handler execution |
| `node.complete` | current node | `status` | After handler returns an outcome |
| `node.retry` | current node | `attempt`, `reason` | Handler raised an exception or returned RETRY |
| `goal_gate.retry` | failed gate node | `target` | Goal gate unsatisfied; retrying from target node |
| `loop.restart` | current node | `target` | Edge with `loop_restart=true` traversed; state reset |

---

## 13. HTTP Server Endpoints

Start the server with `attractor serve`. All endpoints are under the base URL.

### POST /pipelines

Submit a DOT source and start execution.

| Field | Details |
|-------|---------|
| **Request body** | `{"dot_source": "...", "goal": "", "log_dir": ""}` |
| **Response** | `{"id": "<pipeline_id>", "status": "running"}` |
| **Error** | 400 on parse or validation failure |

```bash
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{"dot_source": "digraph { start [shape=Mdiamond]; end [shape=Msquare]; start -> end; }"}'
```

### GET /pipelines/{id}

Get pipeline status.

| Field | Details |
|-------|---------|
| **Response** | `{"id": "...", "status": "running\|completed\|failed\|error", "event_count": N}` |
| **When complete** | Adds `"outcome"` and `"notes"` fields |
| **Error** | 404 if pipeline not found |

```bash
curl http://localhost:8000/pipelines/abc12345
```

### GET /pipelines/{id}/events

SSE stream of pipeline events.

| Field | Details |
|-------|---------|
| **Response** | `text/event-stream` with `data: {"kind": "...", "node_id": "...", "data": {...}}` |
| **Terminal message** | `data: {"kind": "done", "status": "..."}` |
| **Error** | 404 if pipeline not found |

```bash
curl -N http://localhost:8000/pipelines/abc12345/events
```

### POST /pipelines/{id}/cancel

Cancel a running pipeline.

| Field | Details |
|-------|---------|
| **Response** | `{"id": "...", "status": "cancelled"}` |
| **Error** | 404 if pipeline not found |

```bash
curl -X POST http://localhost:8000/pipelines/abc12345/cancel
```

### GET /pipelines/{id}/context

Get current pipeline context.

| Field | Details |
|-------|---------|
| **Response** | `{"pipeline_id": "...", "event_count": N}` |
| **Error** | 404 if pipeline not found |

```bash
curl http://localhost:8000/pipelines/abc12345/context
```

### GET /pipelines/{id}/graph

Get pipeline graph structure.

| Field | Details |
|-------|---------|
| **Response** | `{"name": "...", "goal": "...", "nodes": [...], "edges": [{"source", "target", "label"}]}` |
| **Error** | 404 if pipeline not found |

```bash
curl http://localhost:8000/pipelines/abc12345/graph
```

---

## 14. Context Namespace Conventions

The engine and handlers write these keys to the shared context automatically.

### Auto-set keys

| Key | Set by | Value |
|-----|--------|-------|
| `pipeline.name` | Engine (startup) | `graph.name` |
| `pipeline.goal` | Engine (startup) | `graph.goal` |
| `goal` | Engine (startup) | `graph.goal` (if non-empty) |
| `outcome` | Engine (after each node) | Last `StageStatus` value (e.g., `"success"`) |
| `preferred_label` | Engine (after each node) | `outcome.preferred_label` (if non-empty) |
| `last_stage` | Codergen handler | ID of the node that just executed |
| `last_response` | Codergen handler | First 200 characters of the LLM response |

### Custom key naming advice

- Use dot notation for namespacing: `review.score`, `draft.content`.
- Avoid collisions with auto-set keys listed above.
- Keys are strings; values can be any serializable type.
- Access in conditions with `context.KEY` or bare `KEY`.
