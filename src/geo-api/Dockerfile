# Repo-root build context required -- reads RFQ_ROOT-relative repo paths
# (identity/) same as every other service, PLUS this service's own
# maritime_graph.yaml/keepout_zones.yaml (packaged inside geo_api/ itself)
# and data/vendor/naturalearth (D11: baked into the image, not bind-mounted
# -- routing inputs are immutable and versioned with the code that consumes
# them, so they belong in the workload artifact regardless of deployment
# environment; .dockerignore's data/vendor exclusion is lifted for this).
# Build: docker build -f src/geo-api/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

COPY . /app
WORKDIR /app/src/geo-api

# --mount=type=cache: BuildKit-internal package cache, NOT baked into the
# final image layer -- persists across builds/rebuilds of this service
# (and any other service reusing the same id), so a slow/flaky path to
# pypi.org only has to succeed once per package, not once per build.
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
    pip install uv && uv sync --frozen

# SERVICE_HOST/SERVICE_PORT are bind-only details (GATEWAY-FIRST: external
# identity is a hostname via SERVICE_PUBLIC_URL, not this port) -- main()
# already reads both from env (with A2A_HOST/A2A_PORT legacy fallback). No
# HOST port published here; Caddy (or compose's internal DNS for peer
# service traffic) is what reaches this container.
ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=8400
EXPOSE 8400
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"SERVICE_PORT\"]}/healthz', timeout=3)"

CMD ["uv", "run", "geo-api"]
