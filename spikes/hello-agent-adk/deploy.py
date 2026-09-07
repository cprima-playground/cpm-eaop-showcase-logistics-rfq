import os
import subprocess

import vertexai
from vertexai import agent_engines

from agent import root_agent

REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]==1.161.0",
    # Agent Engine has telemetry enabled by default; without these it logs
    # WARNING: "telemetry enabled but proceeding without X instrumentation"
    # for each - found in Cloud Logging on the first deploy of this spike.
    "opentelemetry-instrumentation-grpc",
    "opentelemetry-instrumentation-httpx",
    "opentelemetry-instrumentation-google-genai",
]


def _gcp_env() -> dict[str, str]:
    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    env: dict[str, str] = {}
    with open(os.path.join(repo_root, "spikes", "hello-agent-adk", "gcp.env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                env[key] = value
    return env


def main() -> None:
    cfg = _gcp_env()
    project_id = cfg["PROJECT_ID"]
    location = cfg["AGENT_REGION"]
    staging_bucket = cfg.get("STAGING_BUCKET") or f"gs://{project_id}-agent-engine-staging"

    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)

    remote_agent = agent_engines.create(
        agent_engine=root_agent,
        requirements=REQUIREMENTS,
        extra_packages=[],
        display_name="hello_agent_adk (showcase-rfq spike)",
        description="Minimal hello-world ADK agent spike, deployed from cpm-eaop-showcase-logistics-rfq.",
    )

    print(f"Created: {remote_agent.resource_name}")


if __name__ == "__main__":
    main()
