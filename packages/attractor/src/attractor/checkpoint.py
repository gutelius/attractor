"""Checkpoint for crash recovery and resume."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from attractor.context import Context


@dataclass
class Checkpoint:
    timestamp: float = 0.0
    current_node: str = ""
    completed_nodes: list[str] = field(default_factory=list)
    node_retries: dict[str, int] = field(default_factory=dict)
    context_values: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def save(self, path: str) -> None:
        """Serialize checkpoint to JSON file."""
        data = {
            "timestamp": self.timestamp or time.time(),
            "current_node": self.current_node,
            "completed_nodes": self.completed_nodes,
            "node_retries": self.node_retries,
            "context": self.context_values,
            "logs": self.logs,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> Checkpoint:
        """Deserialize checkpoint from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            timestamp=data.get("timestamp", 0.0),
            current_node=data.get("current_node", ""),
            completed_nodes=data.get("completed_nodes", []),
            node_retries=data.get("node_retries", {}),
            context_values=data.get("context", {}),
            logs=data.get("logs", []),
        )

    @classmethod
    def from_context(cls, context: Context, current_node: str, completed_nodes: list[str],
                     node_retries: dict[str, int]) -> Checkpoint:
        """Create checkpoint from current execution state."""
        return cls(
            timestamp=time.time(),
            current_node=current_node,
            completed_nodes=list(completed_nodes),
            node_retries=dict(node_retries),
            context_values=context.snapshot(),
            logs=context.logs,
        )

    def restore_context(self) -> Context:
        """Restore a Context from this checkpoint."""
        return Context(values=dict(self.context_values), logs=list(self.logs))
