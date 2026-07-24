"""Base Typer app factory -- every mock system's CLI builds on this (ADR-006).
Ships `whoami` (deterministic env introspection, useful for a coding agent driving
the CLI) and `version`; each system adds its own commands (e.g. `reset`, `serve`)."""

from __future__ import annotations

import typer

from .clock import now, seed


def create_cli(name: str, *, version: str = "0.1.0") -> typer.Typer:
    app = typer.Typer(name=name, help=f"{name} CLI")

    @app.command()
    def whoami() -> None:
        """Print deterministic run context (NOW/SEED) -- for scripted/agent use."""
        typer.echo(f"system={name} version={version} now={now().isoformat()} seed={seed()}")

    @app.command(name="version")
    def version_cmd() -> None:
        """Print the CLI version."""
        typer.echo(version)

    return app
