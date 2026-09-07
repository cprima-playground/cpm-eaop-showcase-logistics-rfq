# Standalone spike, no repo-root build context needed (unlike src/*/Dockerfile
# services, which need RFQ_ROOT-relative paths). Build: docker build -f
# spikes/hello-mcp/Dockerfile spikes/hello-mcp
#
# No --mount=type=cache here (unlike src/*/Dockerfile services) -- Cloud
# Build's default `gcr.io/cloud-builders/docker` builder doesn't run with
# BuildKit enabled, and --mount requires it.
FROM python:3.12-slim
WORKDIR /app
COPY . /app

RUN pip install uv && uv sync --no-dev

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "hello-mcp"]
