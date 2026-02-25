# Attractor Tutorial

Attractor is a pipeline engine that turns DOT graph files into executable workflows. You describe what to build as a directed graph -- nodes for tasks, edges for order -- and Attractor drives an LLM through each step. This tutorial teaches you Attractor by building one project from scratch: a task management API.

Each chapter introduces one concept. By the end, you will have a complete pipeline that plans, implements, tests, and iterates on a real codebase.

**What you need to follow along:** a terminal, Python 3.12 or later, and the `uv` package manager. No prior experience with DOT graphs or pipeline tools is required.

---

## Chapter 1: Installation & Setup

This chapter gets Attractor running on your machine and explains what each package does.

### Prerequisites

You need three things installed before you start:

- **Python 3.12+** -- Attractor uses modern Python features that require 3.12 or later. Check your version with `python3 --version`.
- **uv** -- A fast Python package manager. Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` or see [uv's documentation](https://docs.astral.sh/uv/getting-started/installation/).
- **Graphviz** (optional) -- If you want to render your pipeline graphs as SVG diagrams, install Graphviz. On macOS: `brew install graphviz`. On Ubuntu: `sudo apt install graphviz`. This is not required to run pipelines.

### Clone and sync

Clone the Attractor repository and install all dependencies:

```bash
git clone https://github.com/attractorproject/attractor.git
cd attractor
uv sync
```

`uv sync` reads the workspace configuration and installs all three packages in development mode. Verify the installation by running:

```bash
uv run attractor --help
```

You should see output listing the available commands: `run`, `validate`, `resume`, and `serve`.

### Render a graph (optional)

If you installed Graphviz, you can turn any `.dot` file into an SVG image:

```bash
dot -Tsvg file.dot -o file.svg
```

This is useful for visualizing your pipeline, but Attractor itself does not require Graphviz. Attractor parses DOT files directly with its own parser.

### What each package does

Attractor is split into three packages, each with a specific role:

| Package | Purpose |
|---|---|
| **attractor-llm** | Low-level LLM client. Sends prompts to language model APIs (Claude, OpenAI, etc.) and returns responses. Handles HTTP, retries, and response parsing. |
| **attractor-agent** | Agent layer built on top of attractor-llm. Manages multi-turn conversations, tool use, and structured output. |
| **attractor** | The pipeline engine itself. Parses DOT files, validates graphs, executes nodes in order, and writes logs. Depends on both packages above. Provides the `attractor` CLI. |

You interact with the `attractor` CLI. The other two packages work behind the scenes when the engine calls an LLM backend.

---

## Chapter 2: Your First Pipeline

This chapter builds a minimal pipeline, validates it, and runs it in dry-run mode.

### The DOT file

Create a file named `task-manager.dot` with the following contents:

```dot
// A minimal 3-node pipeline: Start -> Plan -> Exit

digraph task_manager {
    // The goal attribute is a one-sentence summary of what this pipeline builds.
    // Every node can reference it via $goal in prompts.
    goal = "Build a task management API"

    // Start node: shape=Mdiamond marks the pipeline entry point.
    // The engine begins execution here.
    Start [shape=Mdiamond label="Start"]

    // Plan node: shape=box (the default) marks an LLM task node.
    // The label serves as both the display name and the default prompt
    // sent to the LLM backend.
    Plan [shape=box label="Plan the task management API"]

    // Exit node: shape=Msquare marks the pipeline exit point.
    // The engine stops here and reports the final outcome.
    Exit [shape=Msquare label="Exit"]

    // Edges define execution order. The engine follows these arrows
    // from Start through every node until it reaches Exit.
    Start -> Plan
    Plan -> Exit
}
```

This file lives at [`docs/examples/ch02-first-pipeline.dot`](examples/ch02-first-pipeline.dot) in the repository.

### DOT syntax explained

**`digraph task_manager`** declares a directed graph named `task_manager`. The `digraph` keyword tells the parser that edges have direction (A -> B means A runs before B, not the reverse). The graph name becomes the pipeline's identifier in logs and output.

**`goal`** is a graph-level attribute. It holds a one-sentence summary of what the pipeline builds. Nodes can reference this value in their prompts using `$goal`, so you define the project's purpose once and reuse it throughout.

**Node shapes** tell Attractor what kind of handler to use for each node:

| Shape | Meaning | Handler |
|---|---|---|
| `Mdiamond` | Pipeline entry point | start |
| `Msquare` | Pipeline exit point | exit |
| `box` | LLM task (default shape) | codergen |

A node with `shape=box` is handled by the **codergen** handler, which sends a prompt to the LLM backend and writes the response to disk. You will see this handler in detail in Chapter 3.

**`label`** sets the node's display name. For LLM task nodes (`box` shape), the label also serves as the default prompt -- the text sent to the LLM backend when no explicit `prompt` attribute is set.

**Edges** (`Start -> Plan`, `Plan -> Exit`) define execution order. The engine walks these edges one at a time, executing each node before moving to the next.

### Validate the pipeline

Run the validator to check your DOT file for structural errors:

```bash
uv run attractor validate task-manager.dot
```

Expected output:

```
Pipeline 'task_manager' is valid (3 nodes, 2 edges)
```

The validator checks that the graph has exactly one start node, at least one exit node, all edges reference existing nodes, and the graph is connected. If anything is wrong, it prints specific error messages with the rule that failed.

### Run in dry-run mode

Run the pipeline without calling any LLM backend:

```bash
uv run attractor run --dry-run task-manager.dot
```

Expected output:

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Plan
```

**What `--dry-run` does:** the engine walks the entire graph, visiting each node in order, but skips the LLM call. Every node returns an immediate success with the note `[dry-run] <node_id>`. This lets you verify that your graph structure, edge routing, and node ordering work before spending time and money on real LLM calls.

**What a real run does:** without `--dry-run`, the engine calls the configured LLM backend at each `box` node. The codergen handler sends the node's prompt (or label) to the LLM, writes the prompt and response to disk, and returns the outcome. A real run produces actual generated content -- plans, code, tests -- in the log directory.

---

## Chapter 3: Adding Real Work

This chapter expands the pipeline with a second LLM node, introduces the `prompt` attribute, and explains what the codergen handler writes to disk.

### Expand the pipeline

Create a new file named `task-manager-v2.dot`:

```dot
digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    // The prompt attribute overrides the label as the text sent to the LLM.
    // $goal expands to the graph's goal attribute at runtime.
    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
    ]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> Exit
}
```

This file lives at [`docs/examples/ch03-adding-work.dot`](examples/ch03-adding-work.dot) in the repository.

### Label vs. prompt

In Chapter 2, the Plan node used its `label` as the prompt: `"Plan the task management API"`. That works for simple cases, but real pipelines need more specific instructions.

The **`label`** attribute sets the node's display name. It appears in logs, validation output, and rendered diagrams. Keep it short -- a word or two that identifies the step.

The **`prompt`** attribute sets the text sent to the LLM backend. When present, it overrides the label for LLM purposes. Use it to give the LLM detailed, specific instructions.

The **`$goal`** variable expands to the graph's `goal` attribute at runtime. This keeps your prompts DRY -- you define the project's purpose once in the graph header, and every node that references `$goal` gets the current value. If you change the goal, every prompt updates automatically.

### The codergen handler

Every `box`-shaped node is handled by the **codergen** handler. Here is what it does, step by step:

1. **Build the prompt.** The handler takes the node's `prompt` attribute (or `label` if no prompt is set) and expands any variables like `$goal`.
2. **Write `prompt.md`.** The expanded prompt is written to `<log-dir>/<node-id>/prompt.md` so you can inspect exactly what was sent to the LLM.
3. **Call the LLM backend.** The prompt is sent to the configured language model. The backend returns a response.
4. **Write `response.md`.** The LLM's response is written to `<log-dir>/<node-id>/response.md`.
5. **Write `status.json`.** A structured status file records whether the node succeeded or failed, any notes, and context updates for downstream nodes.

After execution, the log directory for each node contains three files:

```
<log-dir>/
  Plan/
    prompt.md       # What was sent to the LLM
    response.md     # What came back
    status.json     # Outcome metadata
  Implement/
    prompt.md
    response.md
    status.json
```

This audit trail lets you review every step of the pipeline after it finishes. You can read `prompt.md` to verify the LLM received the right instructions, check `response.md` to see what it produced, and inspect `status.json` for structured outcome data.

### Run the expanded pipeline

Validate first:

```bash
uv run attractor validate task-manager-v2.dot
```

```
Pipeline 'task_manager' is valid (4 nodes, 3 edges)
```

Then run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v2.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Implement
```

The notes show the last node that completed before Exit. In dry-run mode, the engine walks Start, Plan, Implement, Exit -- but only Plan and Implement are "real" work nodes. The output confirms the engine traversed the full graph in order.

### Pipeline events

During execution, the engine emits events that trace the pipeline's progress. In a dry run, the event sequence for this pipeline is:

1. **`pipeline.start`** -- The engine begins. Logs the pipeline name and goal.
2. **`node.start`** (Start) -- The Start node is visited.
3. **`node.complete`** (Start) -- The Start handler returns success immediately.
4. **`node.start`** (Plan) -- The Plan node begins.
5. **`node.complete`** (Plan) -- In dry-run: instant success. In a real run: after the LLM responds.
6. **`node.start`** (Implement) -- The Implement node begins.
7. **`node.complete`** (Implement) -- Same as above.
8. **`pipeline.finalize`** -- The engine has reached Exit and the pipeline is done.

These events are useful for monitoring, debugging, and building integrations. The HTTP server (covered in a later chapter) streams these events to clients in real time.

### The `--log-dir` flag

By default, pipeline logs are written to `.attractor-runs/<graph-name>/`. You can override this with `--log-dir`:

```bash
uv run attractor run --dry-run --log-dir ./my-logs task-manager-v2.dot
```

This writes all output to `./my-logs/` instead of the default location. Use this when you want to keep logs for different runs separate, or when you want to inspect the output in a specific directory.

In dry-run mode, the log directory contains only a `checkpoint.json` file (no `prompt.md` or `response.md`, since no LLM calls are made). In a real run, you will find the full set of files described above for each work node.

---

## Chapter 4: Branching and Decisions

This chapter adds conditional branching to the pipeline. Instead of a single path from start to finish, the engine chooses between edges based on the outcome of each node.

### Add a Review node

Until now, the pipeline has been a straight line: Start, Plan, Implement, Exit. Real workflows branch. After implementation, you want a review step that either passes the work through or sends it back for revision.

Create a new file named `task-manager-v3.dot`:

```dot
digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
    ]

    // Diamond shape = conditional node.
    // The engine evaluates outgoing edge conditions against this node's outcome.
    Review [shape=diamond label="Review"]

    Revise [
        shape=box
        label="Revise"
        prompt="The review found issues. Revise the implementation to address the feedback."
    ]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> Review

    // Conditional edges: the engine picks the edge whose condition matches.
    Review -> Exit [condition="outcome=success" label="pass"]
    Review -> Revise [condition="outcome=fail" label="fail"]
    Revise -> Exit
}
```

This file lives at [`docs/examples/ch04-branching.dot`](examples/ch04-branching.dot) in the repository.

### The diamond shape

The `diamond` shape tells Attractor to use the **conditional** handler. A conditional node evaluates its outgoing edges and picks the one whose condition matches the node's outcome. This is how you build if/else logic in a pipeline.

Here is the updated shape table:

| Shape | Meaning | Handler |
|---|---|---|
| `Mdiamond` | Pipeline entry point | start |
| `Msquare` | Pipeline exit point | exit |
| `box` | LLM task (default) | codergen |
| `diamond` | Conditional branch | conditional |

### Condition expressions

Each outgoing edge from a conditional node can carry a `condition` attribute. The condition is a simple expression of the form `key=value`.

```
Review -> Exit [condition="outcome=success"]
Review -> Revise [condition="outcome=fail"]
```

The key `outcome` is special. After the engine executes a node, it records whether the node succeeded or failed. The value is either `success` or `fail`. The condition `outcome=success` matches when the preceding node completed without errors.

You can also use `!=` for negation (`outcome!=success`) and `&&` to combine clauses (`outcome=success && context.coverage>80`). For most pipelines, simple `outcome=success` and `outcome=fail` conditions cover what you need.

### How the engine selects an edge

When the engine finishes a node, it must decide which outgoing edge to follow. The selection algorithm works in priority order:

1. **Condition match.** The engine evaluates every outgoing edge that has a `condition` attribute. If one or more conditions match, it picks the matching edge with the highest `weight` (ties broken alphabetically by target node ID).
2. **Unconditional fallback.** If no condition matches, the engine looks for edges without a `condition` attribute. Among those, it picks the one with the highest `weight` (ties broken alphabetically).
3. **Any edge.** If there are no unconditional edges either, the engine falls back to the highest-weight edge regardless of condition.

In plain language: the engine checks each edge's condition. If one matches, it follows that edge. If none match, it picks the unconditional edge with the highest weight.

### The weight attribute

When multiple edges have matching conditions (or multiple unconditional edges exist), the `weight` attribute breaks the tie. Higher weight wins.

```
Review -> Exit [condition="outcome=success" weight=10]
Review -> Revise [condition="outcome=success" weight=5]
```

In this example, both edges match on `outcome=success`, but the edge to Exit has weight 10 and the edge to Revise has weight 5. The engine follows the edge to Exit. If you omit `weight`, it defaults to 0.

### Run the branching pipeline

Validate:

```bash
uv run attractor validate task-manager-v3.dot
```

```
Pipeline 'task_manager' is valid (6 nodes, 6 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v3.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Review
```

In dry-run mode, every node succeeds. The Review node's outcome is `success`, so the engine follows the `outcome=success` edge to Exit. The Revise node is never visited. To test the failure path, you need a real LLM run where the review actually fails -- or you can use the human review gate introduced in the next chapter.

---

## Chapter 5: Human Review Gates

This chapter replaces the automatic conditional review with a human decision point. The pipeline pauses, presents choices, and waits for a person to decide what happens next.

### Replace diamond with hexagon

The `diamond` shape routes automatically based on outcome. The `hexagon` shape does something different: it pauses the pipeline and asks a human to choose. Change the Review node's shape from `diamond` to `hexagon`, and replace condition-based edges with labeled edges that become selectable options.

Create a new file named `task-manager-v4.dot`:

```dot
digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
    ]

    // Hexagon shape = wait.human handler.
    // The pipeline pauses here and presents outgoing edge labels as options.
    Review [shape=hexagon label="Review"]

    Revise [
        shape=box
        label="Revise"
        prompt="The reviewer rejected the implementation. Revise the code to address the feedback."
    ]

    Escalate [
        shape=box
        label="Escalate"
        prompt="The reviewer escalated this item. Prepare a summary of the current state for a senior engineer."
    ]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> Review

    // Edge labels become selectable options in the human review prompt.
    // Accelerator keys let the reviewer type a single character to choose.
    Review -> Exit [label="[A] Approve"]
    Review -> Revise [label="R) Reject"]
    Review -> Escalate [label="E - Escalate"]
    Revise -> Exit
    Escalate -> Exit
}
```

This file lives at [`docs/examples/ch05-human-review.dot`](examples/ch05-human-review.dot) in the repository.

### The hexagon shape

The `hexagon` shape tells Attractor to use the **wait.human** handler. This handler pauses the pipeline and presents the outgoing edge labels as a multiple-choice prompt. The pipeline resumes only after a person (or an automated interviewer) selects an option.

| Shape | Meaning | Handler |
|---|---|---|
| `Mdiamond` | Pipeline entry point | start |
| `Msquare` | Pipeline exit point | exit |
| `box` | LLM task (default) | codergen |
| `diamond` | Conditional branch | conditional |
| `hexagon` | Human review gate | wait.human |

### Edge labels become options

Every outgoing edge from a hexagon node becomes a selectable option. The edge's `label` attribute is the text the reviewer sees. In this example, the Review node has three outgoing edges, so the reviewer sees three choices:

- `[A] Approve` -- follow the edge to Exit
- `R) Reject` -- follow the edge to Revise
- `E - Escalate` -- follow the edge to Escalate

The reviewer types their choice, and the engine follows the selected edge.

### Accelerator keys

Accelerator keys let the reviewer type a single character instead of the full label. Attractor recognizes three patterns:

| Pattern | Example | Key |
|---|---|---|
| `[K] Label` | `[A] Approve` | A |
| `K) Label` | `R) Reject` | R |
| `K - Label` | `E - Escalate` | E |

If you do not use any of these patterns, the accelerator key defaults to the first character of the label. Use explicit accelerator keys when two labels start with the same letter.

### What the reviewer sees

When the pipeline reaches the Review node, it pauses and displays a prompt like this:

```
Review: Review

Choose an action:
  [A] Approve
  [R] Reject
  [E] Escalate

Your choice:
```

The reviewer types `A`, `R`, or `E` and presses Enter. The engine matches the input to the corresponding edge and resumes execution. If the reviewer types `A`, the pipeline follows the edge to Exit and completes. If they type `R`, it follows the edge to Revise, which runs the LLM to fix the code, and then continues to Exit.

### Interviewer types

The person or system that answers human review prompts is called an **interviewer**. Attractor provides four interviewer implementations:

| Interviewer | Purpose |
|---|---|
| **AutoApprove** | Always picks the first option. Use in CI/CD pipelines where you want the pipeline to run unattended. |
| **Queue** | Reads from a pre-filled list of answers. Use in automated tests where you need deterministic, repeatable behavior. |
| **Callback** | Delegates to a custom function you provide. Use when you want to integrate with external systems (Slack, email, webhooks). |
| **Recording** | Wraps another interviewer and records every question-answer pair. Use for audit trails and compliance. |

In interactive mode (the default), the CLI prompts the user directly in the terminal. The interviewer types listed above are used when you run pipelines programmatically or through the HTTP server.

### Run with a human gate

Validate:

```bash
uv run attractor validate task-manager-v4.dot
```

```
Pipeline 'task_manager' is valid (7 nodes, 8 edges)
```

In dry-run mode, the engine uses the AutoApprove interviewer by default. It always selects the first option:

```bash
uv run attractor run --dry-run task-manager-v4.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Review
```

The AutoApprove interviewer selected `[A] Approve`, so the engine followed the edge to Exit. To test other paths, you can run without `--dry-run` and answer the prompt interactively, or use the Queue interviewer programmatically.

---

## Chapter 6: Iteration Loops

This chapter adds a loop to the pipeline. When the reviewer rejects the work, the pipeline goes back to an earlier step and tries again. This is one of Attractor's most powerful features: the pipeline keeps iterating until the human approves.

### The revise loop

Instead of routing rejected work to a separate Revise node that then exits, you can send it back to Plan. The pipeline re-plans, re-implements, and presents the work for review again. This creates a cycle in the graph.

Create a new file named `task-manager-v5.dot`:

```dot
digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
        max_retries=3
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
        retry_target="Plan"
    ]

    // Human review gate with a loop-back edge.
    Review [shape=hexagon label="Review"]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> Review

    Review -> Exit [label="[A] Approve"]
    // This edge creates a loop: rejection sends the pipeline back to Plan.
    Review -> Plan [label="R) Revise"]
}
```

This file lives at [`docs/examples/ch06-loops.dot`](examples/ch06-loops.dot) in the repository.

### Why loops are powerful

Without loops, a failed review means the pipeline exits with partial results. You would have to fix the issues manually and re-run the whole pipeline from scratch. With a loop, the pipeline handles iteration for you. The reviewer rejects, the LLM re-plans and re-implements, and the reviewer checks again. This cycle continues until the reviewer approves or the retry limit is reached.

This matches how real teams work: plan, build, review, revise, repeat.

### Preventing infinite loops with max_retries

A loop without a limit can run forever. The `max_retries` attribute on a node sets the maximum number of times that node can execute in a single pipeline run.

```
Plan [shape=box label="Plan" max_retries=3]
```

With `max_retries=3`, the Plan node can execute up to 3 times. If the reviewer rejects a third time and the loop would send execution back to Plan, the engine stops the pipeline and reports a failure. Without `max_retries`, the graph-level default applies (50 retries).

Set `max_retries` on the node where the loop re-enters the graph. In this pipeline, that is Plan, because the revise edge points back to Plan.

### The retry_target attribute

The `retry_target` attribute tells the engine where to jump back to when a node fails. Instead of following the normal edges, the engine sends execution directly to the named node.

```
Implement [shape=box label="Implement" retry_target="Plan"]
```

With `retry_target="Plan"`, if the Implement node fails (the LLM produces invalid code, for example), the engine jumps back to Plan without waiting for the Review step. This is different from the review loop: `retry_target` handles automatic failure recovery, while the review loop handles human-directed revision.

The key difference: `retry_target` keeps all completed work in context. When the engine jumps back to Plan, the LLM sees what happened in the previous attempt and can adjust. Previous log files and context values remain available.

### The loop_restart attribute

For cases where you want a clean slate, edges can carry the `loop_restart` attribute:

```
Review -> Plan [label="R) Restart" loop_restart=true]
```

When the engine follows a `loop_restart` edge, it clears all pipeline state -- context values, node outcomes, accumulated logs -- and restarts from the target node as if the pipeline had just begun. This is useful when previous attempts produced so much noise that starting fresh gives better results.

The difference between the two approaches:

| Attribute | Keeps previous work | When to use |
|---|---|---|
| `retry_target` | Yes -- previous context, logs, and outcomes remain | Incremental fixes. The LLM learns from past attempts. |
| `loop_restart` | No -- clears all state and starts fresh | Complete do-overs. Previous attempts caused more confusion than help. |

Most pipelines use `retry_target` for automatic retries and normal loop-back edges for human-directed revision. Reserve `loop_restart` for situations where accumulated state actively hinders progress.

### Run the loop pipeline

Validate:

```bash
uv run attractor validate task-manager-v5.dot
```

```
Pipeline 'task_manager' is valid (5 nodes, 5 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v5.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Review
```

As before, dry-run mode uses the AutoApprove interviewer, which selects the first option (`[A] Approve`). The loop is never triggered. To exercise the loop, run without `--dry-run` and choose `R) Revise` at the review prompt. The pipeline will loop back to Plan, re-execute Plan and Implement, and present the Review prompt again -- up to 3 times before it gives up.

Note: the validator accepts this graph despite the back-edge from Review to Plan. Attractor explicitly supports cycles in the graph. The `max_retries` attribute is the safety mechanism that prevents infinite execution.

---

## Chapter 7: Quality Gates and Evaluation

The loop from Chapter 6 catches problems when a human reviewer rejects work. But what about problems the engine can detect on its own? Quality gates let you mark nodes whose success is required before the pipeline can exit. If a gate fails, the engine retries automatically -- no human intervention needed.

### Mark a node as a goal gate

Add `goal_gate=true` to the Implement node:

```
Implement [
    shape=box
    label="Implement"
    prompt="Implement the plan from the previous step for: $goal."
    goal_gate=true
    retry_target="Plan"
]
```

Two attributes work together here:

- **`goal_gate=true`** tells the engine that this node must succeed for the pipeline to pass.
- **`retry_target="Plan"`** tells the engine where to jump if the gate fails.

### When gates are checked

The engine does not check goal gates when a gate node runs. It checks them at the exit node, after the pipeline has attempted the full workflow. This matters: the pipeline runs Plan, Implement, Evaluate, and Review in sequence. Only when execution reaches the Exit node does the engine look back and ask, "Did every goal gate succeed?"

If any goal gate recorded a failure, the engine jumps to that gate's `retry_target` instead of exiting. Execution resumes from the retry target, preserving all context from previous attempts.

### The retry target chain

The engine resolves retry targets in priority order:

1. The failed gate node's own `retry_target` attribute.
2. The failed gate node's `fallback_retry_target` attribute.
3. The graph-level `retry_target` attribute.
4. The graph-level `fallback_retry_target` attribute.

If none of these exist, the pipeline fails with an error. Always set a `retry_target` on goal gate nodes to avoid this.

### LLM-as-judge: a separate evaluation node

A goal gate on Implement checks whether the LLM reported success. But LLMs are optimistic -- they often report success even when the output has problems. A stronger pattern uses a separate evaluation node with a different (often stronger) model to judge the output.

Add an Evaluate node between Implement and Review:

```
Evaluate [
    shape=box
    label="Evaluate"
    prompt="Review the implementation for correctness, completeness, and code quality. Return success if the code meets the plan requirements, or fail with specific feedback."
    llm_model="claude-sonnet-4-20250514"
    goal_gate=true
    retry_target="Plan"
]
```

The `llm_model` attribute overrides the default model for this node. Use a strong model for evaluation -- the evaluator reads the output, not the codebase, so it processes less context and runs fast even with a capable model.

This creates two goal gates: Implement must succeed (the code was generated) and Evaluate must succeed (the code passed review). If either fails, the engine loops back to Plan.

### Multi-stage validation

For production pipelines, chain multiple validation steps. Each step is a separate node:

```
Implement -> Lint -> Test -> Evaluate -> Review
```

- **Lint** runs a linter (a tool node -- covered in Chapter 9).
- **Test** runs the test suite (another tool node).
- **Evaluate** is the LLM-as-judge node described above.
- **Review** is the human gate from Chapter 5.

Mark each validation node with `goal_gate=true` and `retry_target="Plan"`. If linting fails, the pipeline loops back and tries again. If tests fail, same result. Each gate checks one concern.

### Accepting partial success with allow_partial

Sometimes retries are exhausted but the output is still useful. The `allow_partial` attribute accepts partial success when a node's retries run out:

```
Implement [
    shape=box
    label="Implement"
    goal_gate=true
    retry_target="Plan"
    allow_partial=true
]
```

Without `allow_partial`, a node that exhausts its retries reports a hard failure. With `allow_partial=true`, the engine records `partial_success` instead. A partial success satisfies a goal gate -- the pipeline can still exit normally.

Use `allow_partial` when some output is better than no output. For example, an implementation that covers 4 of 5 endpoints is more useful than a failure that produces nothing.

### The complete quality gates pipeline

Create a file named `task-manager-v6.dot`:

```dot
// ch07-quality-gates.dot
// Adds goal gates and an LLM-as-judge evaluation node.
// The engine checks goal gates at the exit node. If Implement
// failed, execution jumps back to Plan automatically.

digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
        max_retries=3
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
        goal_gate=true
        retry_target="Plan"
    ]

    Evaluate [
        shape=box
        label="Evaluate"
        prompt="Review the implementation for correctness, completeness, and code quality. Return success if the code meets the plan requirements, or fail with specific feedback."
        llm_model="claude-sonnet-4-20250514"
        goal_gate=true
        retry_target="Plan"
    ]

    Review [shape=hexagon label="Review"]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> Evaluate
    Evaluate -> Review

    Review -> Exit [label="[A] Approve"]
    Review -> Plan [label="R) Revise"]
}
```

This file lives at [`docs/examples/ch07-quality-gates.dot`](examples/ch07-quality-gates.dot) in the repository.

The flow: Start leads to Plan, Plan leads to Implement, Implement leads to Evaluate, Evaluate leads to Review. The reviewer can approve (exit) or revise (loop back). If execution reaches Exit but either Implement or Evaluate recorded a failure, the engine jumps back to Plan and tries again.

### Run the quality gates pipeline

Validate:

```bash
uv run attractor validate task-manager-v6.dot
```

```
Pipeline 'task_manager' is valid (6 nodes, 6 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v6.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Evaluate
```

In dry-run mode, every node succeeds, so both goal gates pass. The engine exits normally. To exercise the retry loop, run without `--dry-run` and observe what happens when the evaluator returns a failure: the engine jumps back to Plan instead of proceeding to the human review.

---

## Chapter 8: Parallel Work

So far, every pipeline executes one node at a time. This chapter splits work into parallel branches that run concurrently and merge back together.

### The fan-out / fan-in pattern

Parallel execution uses two special node shapes:

| Shape | Handler | Purpose |
|---|---|---|
| `component` | ParallelHandler | Fan-out: launches branches concurrently |
| `tripleoctagon` | FanInHandler | Fan-in: collects results and picks the best |

The pattern looks like this: a single node fans out to multiple branches, each branch does its work independently, and a merge node collects all results.

### Split implementation into parallel branches

Replace the single Implement node with three parallel branches -- API, Frontend, and Tests:

```dot
Parallel [
    shape=component
    label="Parallel"
    join_policy="wait_all"
    error_policy="continue"
]

API [
    shape=box
    label="API"
    prompt="Implement the FastAPI endpoints and data models from the plan."
]

Frontend [
    shape=box
    label="Frontend"
    prompt="Implement the frontend components from the plan."
]

Tests [
    shape=box
    label="Tests"
    prompt="Write pytest test cases covering the API endpoints from the plan."
]

Merge [
    shape=tripleoctagon
    label="Merge"
]
```

Connect them:

```
Plan -> Parallel

Parallel -> API
Parallel -> Frontend
Parallel -> Tests

API -> Merge
Frontend -> Merge
Tests -> Merge

Merge -> Review
```

The Parallel node (shape `component`) triggers the ParallelHandler. The engine launches API, Frontend, and Tests concurrently. When all three finish, execution continues to the Merge node (shape `tripleoctagon`), which consolidates results.

### Context isolation

Each parallel branch receives a clone of the pipeline context at the moment the Parallel node executes. Changes made in one branch do not affect other branches. If the API branch sets `context.api_ready = true`, the Frontend and Tests branches never see that value.

After all branches complete, the engine stores a JSON summary of branch results in `parallel.results`. The Merge node reads this summary, ranks the results, and records the best branch in `parallel.fan_in.best_id` and `parallel.fan_in.best_outcome`.

### Join policies

The `join_policy` attribute on the fan-out node controls when the parallel group reports success. Set it in the node's extra attributes:

| Policy | Behavior |
|---|---|
| `wait_all` (default) | Succeed only if every branch succeeds. If any branch fails, report partial success. |
| `first_success` | Succeed as soon as one branch succeeds. Other branches may still be running. |
| `k_of_n` | Succeed when at least *k* branches succeed. Set `k` as a separate attribute (e.g., `k=2`). |

Examples:

```
// All branches must pass
Parallel [shape=component join_policy="wait_all"]

// Any one branch passing is enough
Parallel [shape=component join_policy="first_success"]

// At least 2 of 3 branches must pass
Parallel [shape=component join_policy="k_of_n" k=2]
```

### Error policies

The `error_policy` attribute controls what happens when a branch fails:

| Policy | Behavior |
|---|---|
| `continue` (default) | Keep running other branches. Report the failure in the results. |
| `fail_fast` | Cancel all remaining branches as soon as one fails. |
| `ignore` | Treat failures as if they did not happen. |

Use `fail_fast` when branches share a resource and one failure invalidates the others. Use `continue` (the default) when branches are independent and you want as many results as possible.

### The complete parallel pipeline

Create a file named `task-manager-v7.dot`:

```dot
// ch08-parallel.dot
// Splits implementation into three parallel branches: API, Frontend, Tests.
// The component shape triggers the ParallelHandler (fan-out).
// The tripleoctagon shape triggers the FanInHandler (fan-in).

digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. Define the API endpoints, frontend components, and test cases."
        max_retries=3
    ]

    Parallel [
        shape=component
        label="Parallel"
        join_policy="wait_all"
        error_policy="continue"
    ]

    API [
        shape=box
        label="API"
        prompt="Implement the FastAPI endpoints and data models from the plan."
    ]

    Frontend [
        shape=box
        label="Frontend"
        prompt="Implement the frontend components from the plan."
    ]

    Tests [
        shape=box
        label="Tests"
        prompt="Write pytest test cases covering the API endpoints from the plan."
    ]

    Merge [
        shape=tripleoctagon
        label="Merge"
    ]

    Review [shape=hexagon label="Review"]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Parallel

    Parallel -> API
    Parallel -> Frontend
    Parallel -> Tests

    API -> Merge
    Frontend -> Merge
    Tests -> Merge

    Merge -> Review

    Review -> Exit [label="[A] Approve"]
    Review -> Plan [label="R) Revise"]
}
```

This file lives at [`docs/examples/ch08-parallel.dot`](examples/ch08-parallel.dot) in the repository.

The topology: Start leads to Plan, Plan leads to Parallel. Parallel fans out to API, Frontend, and Tests. All three converge on Merge. Merge leads to Review, which can approve (exit) or revise (loop back to Plan).

### Run the parallel pipeline

Validate:

```bash
uv run attractor validate task-manager-v7.dot
```

```
Pipeline 'task_manager' is valid (9 nodes, 11 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v7.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] Merge
```

In dry-run mode, all three branches succeed immediately. The Merge node consolidates results and the pipeline exits through Review. In a real run, the three LLM calls execute concurrently -- the total time is the duration of the slowest branch, not the sum of all three.

---

## Chapter 9: Tool Nodes

LLM nodes generate code, but they cannot run it. Tool nodes bridge that gap. A tool node executes a shell command -- a test suite, a linter, a build script -- and feeds the output back into the pipeline context.

### Add a test runner

Add a node with the `parallelogram` shape after Implement:

```dot
RunTests [
    shape=parallelogram
    label="Run Tests"
    tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
    timeout="60s"
]
```

Three attributes matter:

- **`shape=parallelogram`** tells the engine to use the ToolHandler instead of the default LLM handler.
- **`tool_command`** is the shell command to execute. The engine runs it with `asyncio.create_subprocess_shell`, so standard shell features (pipes, `&&`, `cd`) work.
- **`timeout`** sets the maximum execution time. Accepts `s` (seconds) or `m` (minutes). If the command runs longer, the engine kills it and records a failure. The default is 30 seconds.

### How tool output flows into context

When a tool node finishes, the engine stores the command's stdout in the context key `tool.output`. Subsequent nodes can reference this value. If a tool node fails (non-zero exit code), the engine still captures the output -- test failures, compiler errors, linter warnings -- so downstream nodes can use the error details.

The engine also writes the full output (stdout and stderr) to `<logs_root>/<node_id>/tool_output.txt` for inspection after the run.

### Tool node outcomes

The ToolHandler maps exit codes to outcomes:

| Exit code | Outcome | Meaning |
|---|---|---|
| 0 | success | Command completed without errors. |
| Non-zero | fail | Command reported errors. The failure reason includes the exit code. |
| (timeout) | fail | Command exceeded the timeout. The failure reason says "timed out." |

A failed tool node behaves like any other failed node. If it has `goal_gate=true`, the engine checks it at exit time. If it has `retry_target`, the engine can loop back on failure.

### Combining tools with goal gates

Tool nodes pair well with goal gates. Mark the RunTests node as a goal gate so the pipeline cannot exit until tests pass:

```
RunTests [
    shape=parallelogram
    label="Run Tests"
    tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
    timeout="60s"
    goal_gate=true
    retry_target="Implement"
]
```

Now if tests fail, the engine loops back to Implement. The LLM sees the test output in context (via `tool.output`) and can fix the code accordingly.

### The complete tool node pipeline

Create a file named `task-manager-v8.dot`:

```dot
// ch09-tool-nodes.dot
// Adds a tool node that runs pytest after implementation.
// The parallelogram shape triggers the ToolHandler,
// which executes the shell command in tool_command.

digraph task_manager {
    goal = "Build a task management API"

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
        max_retries=3
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
        goal_gate=true
        retry_target="Plan"
    ]

    RunTests [
        shape=parallelogram
        label="Run Tests"
        tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
        timeout="60s"
    ]

    Review [shape=hexagon label="Review"]

    Exit [shape=Msquare label="Exit"]

    Start -> Plan
    Plan -> Implement
    Implement -> RunTests
    RunTests -> Review

    Review -> Exit [label="[A] Approve"]
    Review -> Plan [label="R) Revise"]
}
```

This file lives at [`docs/examples/ch09-tool-nodes.dot`](examples/ch09-tool-nodes.dot) in the repository.

The flow: Start leads to Plan, Plan leads to Implement, Implement leads to RunTests. The test runner executes `pytest`, captures the output, and records success or failure. Then Review presents the results to a human. The reviewer can approve or send the pipeline back to Plan.

### Run the tool node pipeline

Validate:

```bash
uv run attractor validate task-manager-v8.dot
```

```
Pipeline 'task_manager' is valid (6 nodes, 6 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v8.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] RunTests
```

In dry-run mode, the tool node is simulated -- no shell command executes. To see the tool in action, run without `--dry-run` in a project directory that has a `tests/` folder and `pytest` installed. The engine will execute the command, capture the output, and store it in context for the Review step.

Note: tool nodes require that the command exists on the host machine. If `pytest` is not installed or the `workspace` directory does not exist, the tool node fails with an appropriate error message.

---

## Chapter 10: Model Stylesheet

The pipeline now has eight nodes. Setting `llm_model` on each one is tedious and error-prone. The model stylesheet solves this: one block of CSS-like rules that assigns models, providers, and reasoning effort across the entire graph.

### The problem with per-node configuration

Without a stylesheet, you repeat yourself:

```dot
Plan [shape=box llm_model="claude-haiku-3-5" ...]
Implement [shape=box llm_model="claude-haiku-3-5" ...]
Evaluate [shape=box llm_model="claude-opus-4-20250514" ...]
FinalReview [shape=box llm_model="claude-sonnet-4-20250514" ...]
```

Four nodes, three different models, and the default is scattered across the file. Change your mind about the default model and you touch every node. A stylesheet centralizes these decisions.

### Add a model_stylesheet

Add a `model_stylesheet` attribute to the graph:

```dot
digraph task_manager {
    goal = "Build a task management API"

    model_stylesheet = "
        * {
            llm_model: claude-haiku-3-5;
            reasoning_effort: low;
        }
        .critical {
            llm_model: claude-sonnet-4-20250514;
            reasoning_effort: high;
        }
        #Evaluate {
            llm_model: claude-opus-4-20250514;
        }
    "
    ...
}
```

The syntax mirrors CSS. Each rule has a selector, a pair of braces, and semicolon-terminated declarations.

### Selectors and specificity

Three selector types control which nodes a rule matches:

| Selector | Example | Specificity | Matches |
|----------|---------|-------------|---------|
| `*` | `*` | 0 | All nodes |
| `.classname` | `.critical` | 1 | Nodes in a subgraph named `classname` or with that class |
| `#NodeId` | `#Evaluate` | 2 | A single node by ID |

Higher specificity wins. When two rules have equal specificity, the later rule wins. Explicit node attributes (set directly on the node) always override the stylesheet.

In the example above, the `*` rule sets every node to `claude-haiku-3-5` with low reasoning effort. The `.critical` rule overrides that for nodes in the `critical` class. The `#Evaluate` rule overrides the model (but not reasoning effort) for the Evaluate node alone.

### Properties

The stylesheet supports three properties:

- **`llm_model`** -- the model identifier (e.g., `claude-sonnet-4-20250514`)
- **`llm_provider`** -- the provider name (e.g., `anthropic`, `openai`)
- **`reasoning_effort`** -- `low`, `medium`, or `high`

Any other property names are ignored.

### Subgraphs as classes

Subgraphs in DOT create classes. Declare a subgraph and list the nodes that belong to it:

```dot
subgraph critical {
    Evaluate
    FinalReview
}
```

Nodes listed inside `subgraph critical` receive the class `critical`. They match the `.critical` selector in the stylesheet. A node can belong to only one subgraph, but that subgraph name acts as its class for selector matching.

### Resolution rules

The engine resolves stylesheet properties in this order:

1. Parse all rules from the `model_stylesheet` string.
2. For each node, collect every rule whose selector matches.
3. Sort matching rules by specificity (ascending), then by declaration order.
4. The last rule standing for each property wins.
5. If the node has an explicit attribute (e.g., `llm_model="..."` set directly on the node), that attribute overrides the stylesheet.

Step 5 is the escape hatch. If one node needs a model that does not fit any class, set it directly and the stylesheet will not touch it.

### The full DOT file

```dot
// ch10-stylesheet.dot
digraph task_manager {
    goal = "Build a task management API"

    model_stylesheet = "
        * {
            llm_model: claude-haiku-3-5;
            reasoning_effort: low;
        }
        .critical {
            llm_model: claude-sonnet-4-20250514;
            reasoning_effort: high;
        }
        #Evaluate {
            llm_model: claude-opus-4-20250514;
        }
    "

    Start [shape=Mdiamond label="Start"]

    Plan [
        shape=box
        label="Plan"
        prompt="Create a detailed project plan for: $goal. List the endpoints, data models, and implementation steps."
        max_retries=3
    ]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the plan from the previous step for: $goal. Write the Python code with FastAPI endpoints and Pydantic models."
        goal_gate=true
        retry_target="Plan"
    ]

    Evaluate [
        shape=box
        label="Evaluate"
        prompt="Review the implementation for correctness, completeness, and code quality. Return success if the code meets the plan requirements, or fail with specific feedback."
        goal_gate=true
        retry_target="Plan"
    ]

    RunTests [
        shape=parallelogram
        label="Run Tests"
        tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
        timeout="60s"
    ]

    Review [shape=hexagon label="Review"]

    FinalReview [
        shape=box
        label="Final Review"
        prompt="Perform a final quality check on the complete implementation. Verify all endpoints work, models are correct, and tests pass."
        goal_gate=true
        retry_target="Implement"
    ]

    Exit [shape=Msquare label="Exit"]

    subgraph critical {
        Evaluate
        FinalReview
    }

    Start -> Plan
    Plan -> Implement
    Implement -> Evaluate
    Evaluate -> RunTests
    RunTests -> FinalReview
    FinalReview -> Review

    Review -> Exit [label="[A] Approve"]
    Review -> Plan [label="R) Revise"]
}
```

This file lives at [`docs/examples/ch10-stylesheet.dot`](examples/ch10-stylesheet.dot) in the repository.

The result: Plan and Implement use `claude-haiku-3-5` (the `*` default). Evaluate uses `claude-opus-4-20250514` (the `#Evaluate` override). FinalReview uses `claude-sonnet-4-20250514` (the `.critical` class). All critical nodes reason at high effort; everything else reasons at low effort.

### Run the stylesheet pipeline

Validate:

```bash
uv run attractor validate task-manager-v9.dot
```

```
Pipeline 'task_manager' is valid (8 nodes, 9 edges)
```

Run in dry-run mode:

```bash
uv run attractor run --dry-run task-manager-v9.dot
```

```
Pipeline 'task_manager' completed: success
Notes: [dry-run] RunTests
```

The engine applies the stylesheet before execution. Each node receives its resolved model, provider, and reasoning effort. You can verify the resolution by running with `--verbose` -- the log shows which model each node uses.

---

## Chapter 11: Context and Fidelity

Every pipeline carries a context store -- a bag of key-value pairs that flows from node to node. Nodes read context through prompt templates and write context through outcome updates. Fidelity controls how much of that context the engine passes forward.

### The context store

Context is a thread-safe key-value store. The engine creates it at pipeline start and threads it through every node. Each node can read existing values and write new ones.

Nodes read context through variable references in prompts. When a prompt contains `$goal`, the engine substitutes the value of the `goal` key from context. Nodes write context through `context_updates` in their outcome -- a dictionary of keys and values the engine merges into the store after the node completes.

### Auto-set variables

The engine sets several context variables automatically:

| Variable | Value | Set when |
|----------|-------|----------|
| `pipeline.name` | The graph's `name` attribute | Pipeline start |
| `pipeline.goal` | The graph's `goal` attribute | Pipeline start |
| `goal` | Same as `pipeline.goal` | Pipeline start |
| `outcome` | The previous node's outcome label | After each node |
| `preferred_label` | The label the LLM chose for its response | After each node |

You never need to set these manually. They are always available in prompts.

### Custom context variables

Nodes can set arbitrary keys. When a node's outcome includes `context_updates`, those key-value pairs merge into the store:

```
context_updates = {
    "api_endpoints": ["GET /tasks", "POST /tasks", "DELETE /tasks/{id}"],
    "test_count": 12,
    "coverage": "87%"
}
```

Subsequent nodes can reference these values. The context accumulates as the pipeline progresses -- each node sees everything prior nodes have written.

### Fidelity modes

Context grows as the pipeline runs. A 15-node pipeline with detailed outputs at each step produces a large context. Passing all of it to every node wastes tokens and can confuse the model. Fidelity modes control how much context the engine includes in each node's preamble.

Six modes are available:

| Mode | What the node sees |
|------|-------------------|
| `full` | Everything: pipeline name, goal, all completed nodes with outcomes, all context variables. Expensive. Use for nodes that need the complete picture. |
| `truncate` | Pipeline name and goal only. The cheapest option. Use for nodes that need no prior context. |
| `compact` | Pipeline name, goal, all completed nodes with outcomes, and the first 20 context variables. The default. |
| `summary:low` | Pipeline name, goal, and "Completed N stages." No details. |
| `summary:medium` | Pipeline name, goal, and the last 5 completed nodes with outcomes. |
| `summary:high` | Pipeline name, goal, the last 10 completed nodes with outcomes, and the first 30 context variables. |

### Setting fidelity

Set fidelity at three levels. The engine resolves them in precedence order:

1. **Edge fidelity** -- set on a specific edge. Highest priority.
2. **Node fidelity** -- set on the target node.
3. **Graph default_fidelity** -- set on the graph.
4. **Built-in default** -- `compact`.

Edge fidelity:

```dot
Plan -> Implement [fidelity="full"]
```

Node fidelity:

```dot
Implement [shape=box fidelity="summary:medium" ...]
```

Graph default:

```dot
digraph task_manager {
    default_fidelity = "compact"
    ...
}
```

If none of these are set, the engine uses `compact`.

### When to use each mode

- **`full`** -- Final review nodes, merge nodes that synthesize output from multiple branches.
- **`truncate`** -- Start nodes, nodes that generate fresh content with no dependency on prior steps.
- **`compact`** -- Most nodes. The default strikes a good balance between context and cost.
- **`summary:low`** -- Nodes deep in a long pipeline where only the goal matters.
- **`summary:medium`** -- Mid-pipeline nodes that need recent history but not the full trail.
- **`summary:high`** -- Evaluation nodes that need substantial context but not everything.

### Thread IDs

When fidelity is `full`, the engine can reuse the same LLM conversation thread across nodes. Set `thread_id` on a node or edge to group related nodes into one thread:

```dot
Plan [shape=box thread_id="planning" ...]
Implement [shape=box thread_id="planning" ...]
```

Both nodes share the `planning` thread. The LLM sees Plan's full conversation history when it executes Implement. This avoids re-sending context and preserves conversational continuity.

Nodes in the same subgraph share a thread ID by default (derived from the subgraph name). You can override this with an explicit `thread_id` attribute.

Thread IDs only matter when fidelity is `full`. Other fidelity modes build a fresh preamble for each node.

---

## Chapter 12: Checkpoints and Recovery

Long-running pipelines fail. The LLM returns an error, the network drops, or the host machine restarts. Without checkpoints, you start over from the beginning. Checkpoints save the pipeline's state after each node so you can resume from where it stopped.

### Enable checkpoints

Checkpoints are enabled by default when you use a log directory. Pass `--log-dir` to save logs and checkpoints:

```bash
uv run attractor run task-manager-v9.dot --log-dir ./logs
```

The engine saves a checkpoint after each node completes. The checkpoint file lives at `{logs_root}/checkpoint.json`.

### What gets saved

The checkpoint captures five pieces of state:

| Field | Contents |
|-------|----------|
| `current_node` | The node that just completed |
| `completed_nodes` | Ordered list of all completed node IDs |
| `node_retries` | Retry counts per node |
| `context` | All context key-value pairs at the time of the checkpoint |
| `logs` | The full log trail up to this point |

### What does not get saved

- **In-flight LLM calls** -- if the engine crashes mid-call, that call is lost. The engine re-executes the next node on resume.
- **Handler internal state** -- custom handlers that maintain their own state must re-initialize on resume.

### Examine a checkpoint

After running a pipeline, inspect the checkpoint file:

```bash
cat logs/checkpoint.json | python -m json.tool
```

```json
{
  "timestamp": 1706300000.123,
  "current_node": "Evaluate",
  "completed_nodes": ["Start", "Plan", "Implement", "Evaluate"],
  "node_retries": {
    "Plan": 0,
    "Implement": 1,
    "Evaluate": 0
  },
  "context": {
    "pipeline.name": "task_manager",
    "pipeline.goal": "Build a task management API",
    "goal": "Build a task management API",
    "outcome": "success",
    "api_endpoints": ["GET /tasks", "POST /tasks", "DELETE /tasks/{id}"]
  },
  "logs": [
    "Start: passed",
    "Plan: success",
    "Implement: success (retry 1)",
    "Evaluate: success"
  ]
}
```

The `current_node` field tells you the last node that completed. The `completed_nodes` list shows the full execution path. The `context` object holds every key-value pair the pipeline accumulated.

### Resume from a checkpoint

If the pipeline crashes or you stop it, resume with:

```bash
uv run attractor resume logs/checkpoint.json task-manager-v9.dot --log-dir ./logs
```

The engine loads the checkpoint, restores context and completed node history, and picks up from the node after `current_node`. If the checkpoint shows `current_node: "Evaluate"`, the engine resumes at the next node in the graph (RunTests, in the Chapter 10 pipeline).

The resumed run appends to the existing logs. The checkpoint file is overwritten after each subsequent node.

### When to use checkpoints

Use checkpoints for:

- **Long-running pipelines** -- pipelines with 10+ nodes or slow LLM calls. A crash at node 12 of 15 is painful without recovery.
- **Expensive pipelines** -- pipelines that use strong models (Opus, GPT-4) where re-running from scratch wastes money.
- **Production pipelines** -- any pipeline that runs unattended. Crashes are inevitable; recovery should be automatic.

Skip checkpoints for:

- **Quick iterations during development** -- dry-run mode is faster and does not need recovery.
- **Pipelines under 5 nodes** -- re-running from scratch takes seconds.

---

## Chapter 13: Running the HTTP Server

Every chapter so far used the CLI. The CLI is the right tool when you sit at a terminal and run pipelines interactively. But pipelines also need to run from other software: dashboards, CI/CD systems, monitoring tools, Slack bots. The HTTP server exposes the same engine over a REST API with real-time event streaming.

### Start the server

```bash
uv run attractor serve --port 8000
```

The server binds to `0.0.0.0:8000` by default. You see Uvicorn's startup log:

```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

The `--host` flag controls the bind address if you need to restrict it:

```bash
uv run attractor serve --host 127.0.0.1 --port 8000
```

### Submit a pipeline

POST the DOT source and a goal to `/pipelines`:

```bash
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "dot_source": "digraph t { goal=\"Build a task API\" Start [shape=Mdiamond] Plan [shape=box prompt=\"Plan: $goal\"] Exit [shape=Msquare] Start -> Plan -> Exit }",
    "goal": "Build a task management API",
    "log_dir": "/tmp/my-run"
  }'
```

The server parses the DOT, validates the graph, and starts execution in the background. It returns immediately:

```json
{"id": "a1b2c3d4", "status": "running"}
```

The `id` is your handle for every subsequent request. The `log_dir` field is optional -- if omitted, logs go to `/tmp/attractor-server/<id>`.

If the DOT source has a parse error or fails validation, the server returns a 400:

```json
{"detail": "Parse error: unexpected token at line 3"}
```

### Check status

GET `/pipelines/{id}` to poll the current state:

```bash
curl http://localhost:8000/pipelines/a1b2c3d4
```

```json
{
  "id": "a1b2c3d4",
  "status": "running",
  "event_count": 3
}
```

The `status` field moves through these values:

| Status | Meaning |
|--------|---------|
| `running` | Pipeline is executing |
| `completed` | All nodes finished, goal gates passed |
| `failed` | A node failed and the pipeline could not recover |
| `error` | An unexpected exception occurred |
| `cancelled` | You cancelled it |

When the pipeline finishes, the response includes the outcome:

```json
{
  "id": "a1b2c3d4",
  "status": "completed",
  "event_count": 8,
  "outcome": "success",
  "notes": "All goal gates passed"
}
```

### Stream events

Polling works, but streaming is better. The `/pipelines/{id}/events` endpoint sends Server-Sent Events (SSE) as nodes execute:

```bash
curl -N http://localhost:8000/pipelines/a1b2c3d4/events
```

The `-N` flag disables curl's output buffering so events appear in real time. Each event is a JSON object on a `data:` line:

```
data: {"kind": "pipeline.start", "node_id": "", "data": {"name": "task_manager", "goal": "Build a task management API"}}

data: {"kind": "node.start", "node_id": "Plan", "data": {}}

data: {"kind": "node.complete", "node_id": "Plan", "data": {"status": "success"}}

data: {"kind": "node.start", "node_id": "Implement", "data": {}}

data: {"kind": "node.complete", "node_id": "Implement", "data": {"status": "success"}}

data: {"kind": "node.retry", "node_id": "Implement", "data": {"attempt": 1, "reason": "retry requested"}}

data: {"kind": "goal_gate.retry", "node_id": "Evaluate", "data": {"target": "Plan", "reason": "goal gate failed"}}

data: {"kind": "pipeline.complete", "node_id": "Exit", "data": {}}

data: {"kind": "done", "status": "completed"}
```

The event kinds map directly to engine actions:

| Event kind | When it fires |
|------------|---------------|
| `pipeline.start` | Pipeline begins. Data includes name and goal. |
| `node.start` | A node begins execution. |
| `node.complete` | A node finishes. Data includes status (`success` or `fail`). |
| `node.retry` | A node is retrying. Data includes attempt number and reason. |
| `goal_gate.retry` | A goal gate failed and the engine loops back. Data includes the retry target. |
| `loop.restart` | An edge sends execution back to an earlier node. |
| `pipeline.complete` | Pipeline finished normally. |
| `pipeline.error` | Pipeline hit an unrecoverable error. |
| `done` | Terminal event. The stream closes after this. |

The `done` event always comes last. When you receive it, close the connection.

### Cancel a pipeline

POST to `/pipelines/{id}/cancel` to stop a running pipeline:

```bash
curl -X POST http://localhost:8000/pipelines/a1b2c3d4/cancel
```

```json
{"id": "a1b2c3d4", "status": "cancelled"}
```

Cancellation sets the status to `cancelled`. Any in-flight LLM call finishes but the engine does not advance to the next node.

### Get the graph structure

GET `/pipelines/{id}/graph` returns the parsed graph as JSON:

```bash
curl http://localhost:8000/pipelines/a1b2c3d4/graph
```

```json
{
  "name": "task_manager",
  "goal": "Build a task management API",
  "nodes": ["Start", "Plan", "Implement", "Evaluate", "RunTests", "Review", "Exit"],
  "edges": [
    {"source": "Start", "target": "Plan", "label": ""},
    {"source": "Plan", "target": "Implement", "label": ""},
    {"source": "Implement", "target": "Evaluate", "label": ""},
    {"source": "Review", "target": "Exit", "label": "[A] Approve"},
    {"source": "Review", "target": "Plan", "label": "R) Revise"}
  ]
}
```

This is useful for building visual pipeline displays. A dashboard can fetch the graph once, render the node layout, then use SSE events to highlight the active node.

### Get pipeline context

GET `/pipelines/{id}/context` returns the current event count:

```bash
curl http://localhost:8000/pipelines/a1b2c3d4/context
```

```json
{"pipeline_id": "a1b2c3d4", "event_count": 5}
```

### When to use the server vs. the CLI

**Use the CLI when:**
- You run pipelines interactively from a terminal
- You iterate on DOT files during development
- You need dry-run mode to test graph structure
- You want checkpoint-based resume

**Use the server when:**
- Another program needs to trigger pipelines (CI/CD, Slack bots, cron jobs)
- You build a dashboard that displays pipeline progress in real time
- Multiple users submit pipelines concurrently
- You need a stable API contract for integration testing

The server and CLI share the same engine. A pipeline that works with `attractor run` works identically when submitted to the server.

---

## Chapter 14: From PRD to Product

The pipelines so far build one thing: a task management API. But in practice, the interesting question is not "how do I run a pipeline" -- it is "how do I go from an idea to a shipped product?" This chapter shows the full lifecycle: idea, PRD, design, implementation, validation, and sign-off.

### Two patterns for PRD input

A PRD (product requirements document) can enter the pipeline two ways.

**Pattern 1: External PRD.** A PM writes a PRD in a markdown file. The pipeline prompt references it directly:

```dot
Implement [
    shape=box
    prompt="Read the PRD at ./prd.md and implement the requirements for $goal"
]
```

This works when the PRD already exists and you want the pipeline to execute against a fixed spec. The LLM reads the file through its tool-use capabilities.

**Pattern 2: Generated PRD.** A node early in the pipeline generates the PRD from the goal. Later nodes read it from context. This is what we build here -- the pipeline creates its own spec, gets human approval, then implements against that spec.

### The lifecycle pipeline

The full pipeline has ten nodes arranged in five phases:

1. **Generate** -- the LLM writes a PRD from the goal
2. **Review** -- a human approves or rejects the PRD
3. **Design** -- the LLM creates an architecture spec
4. **Build** -- the LLM implements the code, then tests validate it
5. **Evaluate** -- a stronger model judges the output against the PRD

Here is the complete DOT file:

```dot
// ch14-prd-to-product.dot
digraph prd_to_product {
    goal = "Build a task management API with CRUD endpoints, authentication, and pagination"

    model_stylesheet = "
        * {
            llm_model: claude-haiku-3-5;
            reasoning_effort: low;
        }
        .review {
            llm_model: claude-sonnet-4-20250514;
            reasoning_effort: high;
        }
        #EvalPRD {
            llm_model: claude-opus-4-20250514;
            reasoning_effort: high;
        }
    "

    Start [shape=Mdiamond label="Start"]

    WritePRD [
        shape=box
        label="Write PRD"
        prompt="Write a product requirements document for: $goal. Include user stories, acceptance criteria, API contract, data models, error handling requirements, and non-functional requirements (performance, security). Output the PRD as structured markdown."
    ]

    ReviewPRD [shape=hexagon label="Review PRD"]

    DesignArch [
        shape=box
        label="Design Architecture"
        prompt="Based on the PRD from the previous step, create a technical design document for: $goal. Cover: project structure, module decomposition, API route definitions, database schema, authentication flow, error handling strategy, and test plan."
    ]

    ReviewDesign [shape=hexagon label="Review Design"]

    Implement [
        shape=box
        label="Implement"
        prompt="Implement the system described in the design document. Write production-ready Python code using FastAPI, Pydantic models, and SQLite. Follow the architecture exactly. Include all endpoints, models, middleware, and configuration."
        goal_gate=true
        retry_target="DesignArch"
    ]

    RunTests [
        shape=parallelogram
        label="Run Tests"
        tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
        timeout="120s"
    ]

    EvalPRD [
        shape=box
        label="Evaluate Against PRD"
        prompt="You are a quality auditor. Compare the implementation against the original PRD requirements. Check every user story and acceptance criterion. Return success only if all requirements are met. If any requirement is missing or incorrect, return fail with a detailed list of gaps."
        goal_gate=true
        retry_target="Implement"
    ]

    FinalReview [shape=hexagon label="Final Review"]

    Exit [shape=Msquare label="Exit"]

    subgraph review {
        EvalPRD
        DesignArch
    }

    Start -> WritePRD
    WritePRD -> ReviewPRD

    ReviewPRD -> DesignArch [label="[A] Approve"]
    ReviewPRD -> WritePRD [label="R) Revise"]

    DesignArch -> ReviewDesign
    ReviewDesign -> Implement [label="[A] Approve"]
    ReviewDesign -> DesignArch [label="R) Revise"]

    Implement -> RunTests
    RunTests -> EvalPRD
    EvalPRD -> FinalReview

    FinalReview -> Exit [label="[A] Ship it"]
    FinalReview -> Implement [label="R) Rework"]
}
```

This file lives at [`docs/examples/ch14-prd-to-product.dot`](examples/ch14-prd-to-product.dot) in the repository.

### Walk-through

**WritePRD** (box / codergen). The LLM takes the goal and produces a full PRD: user stories, acceptance criteria, API contracts, data models. The output goes into context for every subsequent node to read.

**ReviewPRD** (hexagon / wait.human). The pipeline pauses. You read the generated PRD, then choose Approve or Revise. If you reject it, the pipeline loops back to WritePRD with your feedback.

**DesignArch** (box / codergen). Given the approved PRD, the LLM creates a technical design: project layout, module boundaries, database schema, auth flow. The `.review` class in the stylesheet assigns a stronger model here -- architecture decisions warrant better reasoning.

**ReviewDesign** (hexagon / wait.human). Another human checkpoint. Approve the design or send it back for revision.

**Implement** (box / codergen, `goal_gate=true`, `retry_target="DesignArch"`). The LLM writes the code. The goal gate means the exit handler will check this node. If the downstream evaluation fails, the engine loops back to DesignArch to revise the design before trying again.

**RunTests** (parallelogram / tool). Executes `pytest` against the generated code. The 120-second timeout gives large test suites room to run. Test output flows into context so the evaluation node can reference specific failures.

**EvalPRD** (box / codergen, `goal_gate=true`, `retry_target="Implement"`). This is the judge. The `#EvalPRD` stylesheet rule assigns `claude-opus-4-20250514` -- the strongest available model. It compares every PRD requirement against the implementation. If anything is missing, it returns fail with a gap list, and the engine loops back to Implement.

**FinalReview** (hexagon / wait.human). The last gate. A human reviews the implementation, test results, and evaluation report. Ship it or send it back.

### The model stylesheet strategy

The stylesheet assigns models by role:

| Selector | Model | Reasoning | Why |
|----------|-------|-----------|-----|
| `*` | claude-haiku-3-5 | low | Fast drafting for most nodes |
| `.review` | claude-sonnet-4-20250514 | high | Architecture and evaluation need stronger reasoning |
| `#EvalPRD` | claude-opus-4-20250514 | high | Final judgment against PRD demands the best model |

The WritePRD node uses the default (Haiku). Writing a first draft is fast work -- the human review catches problems. But the evaluation node needs to reason carefully about whether every requirement is satisfied, so it gets Opus.

### The retry loop

Two goal gates create two retry loops:

1. **EvalPRD fails** -> loops to Implement. The implementation did not satisfy the PRD. The LLM re-implements with the gap list in context.
2. **Implement fails** (after retries) -> loops to DesignArch. The design itself was flawed. The LLM revises the architecture.

This two-tier retry separates "bad code" from "bad design." Most failures resolve at the Implement level. If the same implementation keeps failing, the problem is upstream in the design.

---

## Chapter 15: The Complete Pipeline

This chapter brings everything together. The pipeline below combines every concept from chapters 1 through 14: entry and exit nodes, codergen nodes, human gates, goal gates, tool nodes, parallel branches, a model stylesheet, and retry loops. It is the task management API pipeline in its final form.

### The full DOT file

```dot
// ch15-complete-pipeline.dot
digraph task_manager {
    // --- Graph-level attributes ---
    // The goal is the north star. Every goal_gate node is judged against it.
    goal = "Build a task management API with CRUD endpoints, authentication, and pagination"

    // --- Model stylesheet ---
    // Fast default for drafting. Stronger models for critical evaluation.
    // The #EvalPRD override uses the strongest model for final judgment.
    model_stylesheet = "
        * {
            llm_model: claude-haiku-3-5;
            reasoning_effort: low;
        }
        .critical {
            llm_model: claude-sonnet-4-20250514;
            reasoning_effort: high;
        }
        #EvalPRD {
            llm_model: claude-opus-4-20250514;
            reasoning_effort: high;
        }
    "

    // --- Entry point ---
    // Mdiamond = start handler. Every pipeline begins here.
    Start [shape=Mdiamond label="Start"]

    // --- PRD phase ---
    // box = codergen handler. The LLM generates a PRD from the goal.
    WritePRD [
        shape=box
        label="Write PRD"
        prompt="Write a product requirements document for: $goal. Include user stories, acceptance criteria, API contract, data models, error handling requirements, and non-functional requirements."
    ]

    // hexagon = wait.human handler. Pauses for a person to approve or reject.
    ReviewPRD [shape=hexagon label="Review PRD"]

    // --- Design phase ---
    DesignArch [
        shape=box
        label="Design Architecture"
        prompt="Based on the PRD, create a technical design document for: $goal. Cover project structure, module decomposition, API routes, database schema, authentication flow, error handling, and test plan."
    ]

    ReviewDesign [shape=hexagon label="Review Design"]

    // --- Implementation phase ---
    // goal_gate=true means the exit handler checks this node's outcome.
    // retry_target="DesignArch" means failure loops back to redesign.
    Implement [
        shape=box
        label="Implement"
        prompt="Implement the system described in the design document. Write production-ready Python code using FastAPI, Pydantic, and SQLite. Follow the architecture exactly."
        goal_gate=true
        retry_target="DesignArch"
        max_retries=3
    ]

    // --- Parallel validation branches ---
    // parallel shape = fan-out. Runs both branches concurrently.
    ValidationFork [shape=parallel label="Validation Fork"]

    // parallelogram = tool handler. Runs a shell command.
    RunTests [
        shape=parallelogram
        label="Run Tests"
        tool_command="cd workspace && uv run pytest tests/ -v --tb=short"
        timeout="120s"
    ]

    LintCheck [
        shape=parallelogram
        label="Lint Check"
        tool_command="cd workspace && uv run ruff check . --output-format=concise"
        timeout="30s"
    ]

    // parallel.fan_in shape = fan-in. Waits for both branches, picks best.
    ValidationJoin [shape=parallel_fan_in label="Validation Join"]

    // --- Evaluation phase ---
    // Uses the strongest model (set by #EvalPRD in the stylesheet).
    // goal_gate=true + retry_target="Implement" forces a rework loop
    // if the evaluation finds gaps against the PRD.
    EvalPRD [
        shape=box
        label="Evaluate Against PRD"
        prompt="You are a quality auditor. Compare the implementation against the original PRD. Check every user story and acceptance criterion. Return success only if all requirements are met. Return fail with a detailed gap list otherwise."
        goal_gate=true
        retry_target="Implement"
    ]

    // --- Final human gate ---
    FinalReview [shape=hexagon label="Final Review"]

    // --- Exit point ---
    // Msquare = exit handler. Checks all goal_gate nodes before completing.
    Exit [shape=Msquare label="Exit"]

    // --- Subgraph classes for stylesheet targeting ---
    subgraph critical {
        EvalPRD
        DesignArch
        Implement
    }

    // --- Edges: the execution order ---

    // PRD phase
    Start -> WritePRD
    WritePRD -> ReviewPRD
    ReviewPRD -> DesignArch [label="[A] Approve"]
    ReviewPRD -> WritePRD [label="R) Revise"]

    // Design phase
    DesignArch -> ReviewDesign
    ReviewDesign -> Implement [label="[A] Approve"]
    ReviewDesign -> DesignArch [label="R) Revise"]

    // Implementation -> parallel validation
    Implement -> ValidationFork
    ValidationFork -> RunTests
    ValidationFork -> LintCheck
    RunTests -> ValidationJoin
    LintCheck -> ValidationJoin

    // Evaluation and sign-off
    ValidationJoin -> EvalPRD
    EvalPRD -> FinalReview
    FinalReview -> Exit [label="[A] Ship it"]
    FinalReview -> Implement [label="R) Rework"]
}
```

This file lives at [`docs/examples/ch15-complete-pipeline.dot`](examples/ch15-complete-pipeline.dot) in the repository.

### Section-by-section breakdown

**Graph attributes.** Two lines set the stage. `goal` declares what the pipeline builds. `model_stylesheet` assigns models by tier so you never touch per-node model attributes.

**Start node** (`Mdiamond`). The entry point. The start handler initializes the pipeline context with the goal and passes control to the first real node.

**PRD phase** (WritePRD + ReviewPRD). The LLM generates a product requirements document from the goal. A human reviews it. Rejection loops back to regeneration. This is the "Generated PRD" pattern from Chapter 14.

**Design phase** (DesignArch + ReviewDesign). The LLM translates the approved PRD into a technical design. Another human gate. Two approval checkpoints before any code is written.

**Implementation** (Implement). The LLM writes the code. Three attributes control its behavior: `goal_gate=true` ensures the exit handler checks it, `retry_target="DesignArch"` loops back to redesign on persistent failure, and `max_retries=3` caps the retry count.

**Parallel validation** (ValidationFork + RunTests + LintCheck + ValidationJoin). After implementation, two tool nodes run concurrently: pytest for correctness and ruff for code quality. The fan-in node waits for both to finish. This is the parallel pattern from Chapter 8 combined with tool nodes from Chapter 9.

**Evaluation** (EvalPRD). The strongest model compares the implementation against the PRD. The `#EvalPRD` stylesheet rule overrides the model to Opus. If the evaluation fails, the engine loops back to Implement -- not to DesignArch -- because evaluation failures are usually code-level gaps, not design flaws.

**Final review** (FinalReview). One last human gate. Ship it or rework.

**Exit** (`Msquare`). The exit handler collects outcomes from all goal_gate nodes (Implement and EvalPRD). If any failed, the engine retries using their `retry_target`. Only when all gates pass does the pipeline exit with success.

**Subgraph** (`critical`). Groups EvalPRD, DesignArch, and Implement into the `.critical` class. The stylesheet assigns `claude-sonnet-4-20250514` with high reasoning effort to these nodes. EvalPRD gets a further override to Opus.

### Render the graph

If you have Graphviz installed, render the pipeline as an SVG:

```bash
dot -Tsvg docs/examples/ch15-complete-pipeline.dot -o pipeline.svg
```

Open `pipeline.svg` in a browser to see the full graph with all nodes, edges, and labels. The visual layout makes the retry loops and parallel branches obvious in a way that reading the DOT source does not.

### Run it

Validate first:

```bash
uv run attractor validate docs/examples/ch15-complete-pipeline.dot
```

Dry-run to verify the execution path:

```bash
uv run attractor run --dry-run docs/examples/ch15-complete-pipeline.dot
```

Or submit it to the server:

```bash
uv run attractor serve --port 8000 &

curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d "{\"dot_source\": \"$(cat docs/examples/ch15-complete-pipeline.dot | sed 's/"/\\"/g')\", \"goal\": \"Build a task management API\"}"
```

### What you have learned

Over fifteen chapters, you built a pipeline from a two-node skeleton to a production-grade workflow. Here is what you covered:

| Chapter | Concept | Shape / Feature |
|---------|---------|-----------------|
| 1 | Installation | `uv sync`, CLI commands |
| 2 | First pipeline | `Mdiamond` (start), `Msquare` (exit) |
| 3 | Adding work | `box` (codergen), `prompt`, `goal` |
| 4 | Branching | `diamond` (conditional), `outcome=` edges |
| 5 | Human gates | `hexagon` (wait.human), labeled edges as options |
| 6 | Loops | Backward edges, `max_retries` |
| 7 | Quality gates | `goal_gate=true`, `retry_target` |
| 8 | Parallel branches | `parallel` (fan-out), `parallel_fan_in` (fan-in) |
| 9 | Tool nodes | `parallelogram` (tool), `tool_command`, `timeout` |
| 10 | Model stylesheet | `model_stylesheet`, CSS selectors, subgraph classes |
| 11 | Context and fidelity | Context keys, fidelity settings, thread management |
| 12 | Checkpoints | `checkpoint_enabled`, resume from crash |
| 13 | HTTP server | `attractor serve`, REST API, SSE streaming |
| 14 | PRD to product | Generated PRD, multi-phase review, evaluation loops |
| 15 | Complete pipeline | All concepts combined |

### Where to go next

- **Cookbook** -- ready-made patterns for common workflows. Copy a pattern, adapt the prompts, run it.
- **Concepts** -- deeper explanations of how the engine, handlers, context, and fidelity system work under the hood.
- **Reference** -- every node attribute, edge attribute, graph attribute, CLI flag, and API endpoint in one place.
