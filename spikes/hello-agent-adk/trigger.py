import os
import subprocess
import sys

import vertexai
from vertexai import agent_engines


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
    if len(sys.argv) < 2:
        print("usage: uv run trigger.py <resource_name> [message]", file=sys.stderr)
        raise SystemExit(1)

    resource_name = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else "2+2? one word."

    cfg = _gcp_env()
    vertexai.init(project=cfg["PROJECT_ID"], location=cfg["AGENT_REGION"])

    agent = agent_engines.get(resource_name)
    for event in agent.stream_query(message=message, user_id="u1"):
        print(event)


if __name__ == "__main__":
    main()
