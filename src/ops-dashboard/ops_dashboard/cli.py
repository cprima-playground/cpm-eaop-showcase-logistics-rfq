"""ops-dashboard CLI -- serve on rfq_common's base Typer app."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

from . import api

app = create_cli("ops-dashboard", version="0.1.0")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8006) -> None:
    """Run the dashboard (login at /login, Swagger UI at /docs)."""
    import uvicorn

    uvicorn.run(api.build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
