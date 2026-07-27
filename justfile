# Explicit -p on every recipe -- project identity must never depend on
# which directory `docker compose` happened to be invoked from (bit us
# once: containers created via a run from infra/ became untouchable by
# `down` run from repo root, same project name, different working_dir
# label). `just` always runs recipes from the justfile's own directory
# (repo root), so paths below are root-relative.

# Without this, `just` picks up git-bash's sh on PATH, which mangles the
# docker.exe path into a /cygdrive form that then fails to execute
# (found live: "cannot execute: required file not found").
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]

# `just` with no recipe name runs the FIRST recipe in the file by default --
# that must never be an action (bit us live: bare `just` silently built and
# started the whole stack). List instead; every real action needs an
# explicit name.
# List available recipes.
default:
    @just --list

# docker compose's own .env auto-lookup uses the FIRST -f file's directory
# as "project directory", not the invocation cwd -- with infra/compose.support.yaml
# listed first, it looks for infra/.env, not repo-root .env, silently. Found
# live: DOCKER_BUILDCACHE_DIR went unresolved, cache_from/cache_to fell back
# to a relative default that landed a 6.5GB .buildcache/ inside the Docker
# build context. --env-file makes the lookup explicit regardless of -f order.
# showcase_files is compose.showcase.yaml ALONE -- it's self-contained (own
# yaml anchors, network referenced as `external: true` by literal name, no
# content from compose.support.yaml needed to resolve). Including support's
# file here too (as this used to) merges its profile-less services
# (gateway/keycloak/vault/inspectors/web) into this SAME `up` call --
# --profile core doesn't filter them out, so they get recreated a second
# time under project eaop-logistics, colliding on host ports with the
# eaop-infra copies from the first `up` step. Found live: "Bind for
# 0.0.0.0:8081 failed: port is already allocated" from an
# eaop-logistics-keycloak-1 that should never have been created.
env_file := "--env-file .env"
support_files := "-f infra/compose.support.yaml"
showcase_files := "-f infra/compose.showcase.yaml"
otel_files := "-f infra/observability/docker-compose.yml"

# Bring up support (gateway/keycloak/vault/inspectors/web) then showcase (agents/mocks).
up:
    docker compose {{env_file}} -p eaop-infra {{support_files}} up -d --build
    docker compose {{env_file}} -p eaop-logistics {{showcase_files}} --profile core up -d --build

# Stop both stacks (containers kept, not removed).
down:
    docker compose {{env_file}} -p eaop-logistics {{showcase_files}} down
    docker compose {{env_file}} -p eaop-infra {{support_files}} down

# Status of both stacks.
ps:
    docker compose {{env_file}} -p eaop-infra {{support_files}} ps -a
    docker compose {{env_file}} -p eaop-logistics {{showcase_files}} ps -a

# Observability (OTel/Tempo/Prometheus/Grafana) -- separate lifecycle, boots independently.
otel-up:
    docker compose {{env_file}} -p eaop-infra {{otel_files}} up -d

otel-down:
    docker compose {{env_file}} -p eaop-infra {{otel_files}} down

# Export web/slides/*.html reveal.js decks to PDF (data/slides/pdf/) via decktape.
slides-pdf:
    pwsh -NoLogo -File tools/slides/export-pdf.ps1

# Build the publishing toolchain image (pandoc + mermaid-filter + uv).
docs-image:
    docker build -t eaop-publishing -f infra/publishing/Dockerfile .

# Export combined .docx documents (data/publishing/manifests.yaml). No args = every document.
docs-export *KEYS:
    docker run --rm -v "{{justfile_directory()}}:/repo" -w /repo eaop-publishing {{KEYS}}

# Generate SPDX SBOMs (built images + repo source manifests) via containerized syft.
sbom:
    pwsh -NoLogo -File tools/sbom/generate.ps1

# Generate the runtime manifest (services/ports/volumes/networks) from `docker compose config`.
runtime-manifest:
    pwsh -NoLogo -File tools/runtime-manifest/generate.ps1
