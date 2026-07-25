"""Shared HTTP-CLI response handling -- every mock system's Typer CLI talks
to its OWN running server now (never a throwaway local store, which can't
see what the live process actually holds -- a CLI and a `serve` process are
separate OS processes with separate memory; HTTP is the only channel that
reaches into the running process's actual state, same reasoning as ADR-010's
"consume masterdata via the API, never a duplicated file"). This is the one
genuinely identical bit across every system's CLI: print JSON on success,
print the error body and exit 1 on failure. Base-URL/API-key resolution
stays per-system (env var names and `.auth._expected_key()` differ)."""

from __future__ import annotations

import json

import httpx
import typer


def print_response(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(code=1)
    body = resp.json()
    typer.echo(json.dumps(body, indent=2) if isinstance(body, (dict, list)) else str(body))
