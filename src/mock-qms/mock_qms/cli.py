"""mock-qms CLI -- serve only, on rfq_common's base Typer app. No business
commands yet (see api.py's module docstring)."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

app = create_cli("mock-qms", version="0.1.0")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8007) -> None:
    """Run the REST API (Swagger UI at /swagger)."""
    import uvicorn

    from .api import app as fastapi_app
    uvicorn.run(fastapi_app, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
