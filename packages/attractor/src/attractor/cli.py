"""CLI entry point for Attractor pipeline runner."""

from __future__ import annotations

import asyncio
import sys

import click

from attractor.engine import EngineConfig, PipelineEngine
from attractor.parser import parse_dot
from attractor.validator import validate, validate_or_raise, Severity, ValidationError
from attractor.transforms import VariableExpansionTransform, StylesheetTransform
from attractor.checkpoint import Checkpoint


@click.group()
def main():
    """Attractor — DOT-graph pipeline runner."""
    pass


@main.command()
@click.argument("dotfile", type=click.Path(exists=True))
@click.option("--goal", default="", help="Override pipeline goal")
@click.option("--model", default="", help="Default LLM model")
@click.option("--log-dir", default="", help="Log directory")
@click.option("--dry-run", is_flag=True, help="Simulate without calling LLM backends")
@click.option("--max-steps", default=1000, type=int, help="Maximum execution steps")
def run(dotfile: str, goal: str, model: str, log_dir: str, dry_run: bool, max_steps: int):
    """Run a pipeline from a DOT file."""
    with open(dotfile) as f:
        dot_source = f.read()

    graph = parse_dot(dot_source)
    graph = VariableExpansionTransform().apply(graph)
    graph = StylesheetTransform().apply(graph)

    if goal:
        graph.goal = goal

    try:
        validate_or_raise(graph)
    except ValidationError as e:
        click.echo(f"Validation failed: {e}", err=True)
        sys.exit(1)

    logs_root = log_dir or f".attractor-runs/{graph.name}"
    config = EngineConfig(
        logs_root=logs_root,
        dry_run=dry_run,
        max_steps=max_steps,
    )
    engine = PipelineEngine(config)
    outcome = asyncio.run(engine.run(graph))

    click.echo(f"Pipeline '{graph.name}' completed: {outcome.status.value}")
    if outcome.notes:
        click.echo(f"Notes: {outcome.notes}")
    if outcome.failure_reason:
        click.echo(f"Failure: {outcome.failure_reason}", err=True)
        sys.exit(1)


@main.command()
@click.argument("dotfile", type=click.Path(exists=True))
def validate_cmd(dotfile: str):
    """Validate a DOT file without executing."""
    with open(dotfile) as f:
        dot_source = f.read()

    graph = parse_dot(dot_source)
    graph = VariableExpansionTransform().apply(graph)
    graph = StylesheetTransform().apply(graph)
    diags = validate(graph)

    errors = [d for d in diags if d.severity == Severity.ERROR]
    warnings = [d for d in diags if d.severity == Severity.WARNING]

    if errors:
        click.echo(f"{len(errors)} error(s):")
        for d in errors:
            click.echo(f"  ERROR [{d.rule}]: {d.message}")
    if warnings:
        click.echo(f"{len(warnings)} warning(s):")
        for d in warnings:
            click.echo(f"  WARN  [{d.rule}]: {d.message}")
    if not errors and not warnings:
        click.echo(f"Pipeline '{graph.name}' is valid ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")

    if errors:
        sys.exit(1)


# Register as "validate" command name
validate_cmd.name = "validate"


@main.command()
@click.argument("checkpoint_path", type=click.Path(exists=True))
@click.argument("dotfile", type=click.Path(exists=True))
@click.option("--log-dir", default="", help="Log directory")
def resume(checkpoint_path: str, dotfile: str, log_dir: str):
    """Resume a pipeline from a checkpoint."""
    cp = Checkpoint.load(checkpoint_path)

    with open(dotfile) as f:
        dot_source = f.read()

    graph = parse_dot(dot_source)
    graph = VariableExpansionTransform().apply(graph)
    graph = StylesheetTransform().apply(graph)

    try:
        validate_or_raise(graph)
    except ValidationError as e:
        click.echo(f"Validation failed: {e}", err=True)
        sys.exit(1)

    logs_root = log_dir or f".attractor-runs/{graph.name}"
    config = EngineConfig(logs_root=logs_root)
    engine = PipelineEngine(config)
    outcome = asyncio.run(engine.run(graph, resume_from=cp))

    click.echo(f"Pipeline resumed and completed: {outcome.status.value}")
    if outcome.failure_reason:
        click.echo(f"Failure: {outcome.failure_reason}", err=True)
        sys.exit(1)


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind")
@click.option("--port", default=8000, type=int, help="Port to bind")
def serve(host: str, port: int):
    """Start the HTTP server."""
    try:
        import uvicorn
        from attractor.server import app
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        click.echo("uvicorn not installed. Run: pip install uvicorn", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
