# Not vendored (no submodule) -- built directly from cprima-forks'
# modelcontextprotocol-inspector fork, never the upstream
# modelcontextprotocol/inspector repo. Ref overridable via build arg.
FROM alpine/git:latest AS source
ARG MCP_INSPECTOR_REPO=https://github.com/cprima-forks/modelcontextprotocol-inspector.git
ARG MCP_INSPECTOR_REF=main
RUN git clone --branch ${MCP_INSPECTOR_REF} --depth 1 ${MCP_INSPECTOR_REPO} /src

FROM node:current-alpine3.22 AS builder
WORKDIR /app
COPY --from=source /src/package*.json ./
COPY --from=source /src/.npmrc ./
COPY --from=source /src/client/package*.json ./client/
COPY --from=source /src/server/package*.json ./server/
COPY --from=source /src/cli/package*.json ./cli/
RUN --mount=type=cache,target=/root/.npm,id=mcp-inspector-npm-cache \
    npm ci --ignore-scripts
COPY --from=source /src/. .
RUN npm run build

FROM node:24-slim
WORKDIR /app
COPY --from=source /src/package*.json ./
COPY --from=source /src/.npmrc ./
COPY --from=source /src/client/package*.json ./client/
COPY --from=source /src/server/package*.json ./server/
COPY --from=source /src/cli/package*.json ./cli/
RUN --mount=type=cache,target=/root/.npm,id=mcp-inspector-npm-cache \
    npm ci --omit=dev --ignore-scripts
COPY --from=builder /app/client/dist ./client/dist
COPY --from=builder /app/client/bin ./client/bin
COPY --from=builder /app/server/build ./server/build
COPY --from=builder /app/cli/build ./cli/build

ENV CLIENT_PORT=6274
ENV SERVER_PORT=6277
EXPOSE ${CLIENT_PORT} ${SERVER_PORT}

ENTRYPOINT ["npm", "start"]
