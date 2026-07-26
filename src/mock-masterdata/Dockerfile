# Repo-root build context required -- services read RFQ_ROOT-relative repo
# paths (identity/, systems/, authorization/, business/, agents/, themes/,
# interfaces/), not just their own src/<service> + the sibling rfq_common
# editable path-dependency (pyproject.toml's [tool.uv.sources]). .dockerignore
# trims the irrelevant rest (other services' .venv, vendor/, tmp/, .git).
# Build: docker build -f src/mock-masterdata/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

COPY . /app
WORKDIR /app/src/mock-masterdata

# --mount=type=cache: BuildKit-internal package cache, NOT baked into the
# final image layer -- persists across builds/rebuilds of this service
# (and any other service reusing the same id), so a slow/flaky path to
# pypi.org only has to succeed once per package, not once per build.
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
    pip install uv && uv sync --frozen

# SERVICE_PORT is a bind-only detail (GATEWAY-FIRST: external identity is a
# hostname, not this port) -- baked in as the default, override via compose
# environment: if ever needed. No HOST port published here; Caddy (or
# compose's internal DNS for peer traffic) is what reaches this container.
ENV SERVICE_PORT=8003
EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"SERVICE_PORT\"]}/healthz', timeout=3)"

CMD ["uv", "run", "mock-masterdata", "serve", "--host", "0.0.0.0"]
