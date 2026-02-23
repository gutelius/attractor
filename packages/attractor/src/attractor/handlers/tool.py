"""Tool handler — executes shell commands or external tools."""

from __future__ import annotations

import asyncio
import os

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus


class ToolHandler:
    """Executes an external tool configured via node attributes."""

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        command = node.extra.get("tool_command", "")
        if not command:
            return Outcome(status=StageStatus.FAIL, failure_reason="No tool_command specified")

        timeout_str = node.timeout or "30s"
        timeout = _parse_timeout(timeout_str)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")

            # Write output to logs
            stage_dir = os.path.join(logs_root, node.id)
            os.makedirs(stage_dir, exist_ok=True)
            with open(os.path.join(stage_dir, "tool_output.txt"), "w") as f:
                f.write(output)
                if stderr:
                    f.write("\n--- STDERR ---\n")
                    f.write(stderr.decode("utf-8", errors="replace"))

            if proc.returncode != 0:
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Command exited with code {proc.returncode}",
                    context_updates={"tool.output": output},
                )

            return Outcome(
                status=StageStatus.SUCCESS,
                context_updates={"tool.output": output},
                notes=f"Tool completed: {command}",
            )
        except asyncio.TimeoutError:
            return Outcome(status=StageStatus.FAIL, failure_reason=f"Command timed out after {timeout}s")
        except Exception as e:
            return Outcome(status=StageStatus.FAIL, failure_reason=str(e))


def _parse_timeout(s: str) -> float:
    """Parse a timeout string like '30s' or '5m' to seconds."""
    s = s.strip()
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) * 60
    try:
        return float(s)
    except ValueError:
        return 30.0
