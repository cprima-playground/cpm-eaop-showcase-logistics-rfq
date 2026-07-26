# Repo-root build context required -- services read RFQ_ROOT-relative repo
# paths (identity/, systems/, authorization/, business/, agents/, themes/,
# interfaces/), not just their own src/<service> + the sibling rfq_common
# editable path-dependency (pyproject.toml's [tool.uv.sources]). .dockerignore
# trims the irrelevant rest (other services' .venv, vendor/, tmp/, .git).
# Build: docker build -f src/approval-mcp/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

COPY . /app
WORKDIR /app/src/approval-mcp

RUN pip install --no-cache-dir uv && uv sync --frozen

# SERVICE_HOST/SERVICE_PORT are bind-only details (Caddy-first: external
# identity is a hostname via SERVICE_PUBLIC_URL, not this port) -- main()
# already reads both from env (with A2A_HOST/A2A_PORT legacy fallback). No
# HOST port published here; Caddy (or compose's internal DNS for peer
# agent-to-MCP traffic) is what reaches this container.
ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=8107
EXPOSE 8107
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"SERVICE_PORT\"]}/healthz', timeout=3)"

CMD ["uv", "run", "approval-mcp"]
