# Publishing toolchain -- pandoc + mermaid-filter (pre-renders ```mermaid
# code blocks to images before pandoc runs) + uv (repo convention: always
# use uv for Python execution). Containerized so the toolchain version is
# pinned and reproducible, not whatever happens to be on the host -- same
# reasoning as infra/a2a-inspector, infra/mcp-inspector.
FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    curl ca-certificates \
    # mermaid-filter's puppeteer/Chromium runtime deps
    chromium \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    libcups2 libdrm2 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g mermaid-filter
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# mermaid-filter shells out to mmdc, which launches Chromium via Puppeteer --
# refuses to run as root (this container's default user) without an explicit
# --no-sandbox flag. Found live ("Running as root without --no-sandbox is
# not supported"). mermaid-filter reads Puppeteer launch args from
# MERMAID_FILTER_PUPPETEER_CONFIG (an env var, NOT a pandoc --metadata key --
# confirmed by reading mermaid-filter's own source inside this image; the
# --metadata=puppeteerConfig:... approach silently did nothing).
COPY infra/publishing/puppeteer-config.json /opt/puppeteer-config.json
ENV MERMAID_FILTER_PUPPETEER_CONFIG=/opt/puppeteer-config.json

WORKDIR /repo
# "uv run <script>.py" (not "uv run python <script>.py") -- only the direct
# script-path form makes uv parse the PEP 723 inline `# /// script` block
# and install its declared deps (pyyaml). Routing through an explicit
# `python` argument bypasses that detection entirely; found live
# ("ModuleNotFoundError: No module named 'yaml'" despite the script
# declaring pyyaml as a dependency).
ENTRYPOINT ["uv", "run", "tools/docs/export_docx.py"]
