# Not vendored (no submodule) -- built directly from cprima-forks'
# a2a-inspector fork, never the upstream a2aproject/a2a-inspector repo.
# Default ref is our own fix branch (streaming=False against pinned
# a2a-sdk==0.3.10 -- a2aproject/a2a-inspector#153), overridable via build
# arg for testing other branches/commits without touching this file.
FROM alpine/git:latest AS source
ARG A2A_INSPECTOR_REPO=https://github.com/cprima-forks/a2aproject-a2a-inspector.git
ARG A2A_INSPECTOR_REF=fix/streaming-false-0.3.10
RUN git clone --branch ${A2A_INSPECTOR_REF} --depth 1 ${A2A_INSPECTOR_REPO} /src

FROM node:18-alpine AS frontend-builder
WORKDIR /app
COPY --from=source /src/frontend/package*.json ./
COPY --from=source /src/frontend/tsconfig.json ./
COPY --from=source /src/frontend/src ./src
RUN --mount=type=cache,target=/root/.npm,id=a2a-inspector-npm-cache \
    npm ci
COPY --from=source /src/frontend/ ./
RUN npm rebuild esbuild
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
    pip install uv
COPY --from=source /src/pyproject.toml /src/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
    uv sync && uv pip install validators
COPY --from=source /src/backend/ ./backend/
RUN mkdir -p /app/frontend
COPY --from=frontend-builder /app/public /app/frontend/public

WORKDIR /app/backend
EXPOSE 8080

# Not `uv run` -- the fork's own uv.lock/pyproject.toml drift ("Missing
# workspace member `a2a-inspector`", confirmed via --frozen) makes `uv run`
# try to self-heal over the network on every container start. The venv
# built above is already correct; invoke it directly, no runtime network
# dependency. TLS trust (gateway's local CA) is layered on top via
# infra/compose.support.yaml's command: override, not here -- this image
# has no opinion on which CA bundle it should trust, that's deployment
# config, not a build concern.
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
