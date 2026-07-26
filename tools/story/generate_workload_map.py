"""Generate the job-to-implemented-workload projection."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

MCP_RUNTIME = {
    "workload.tms-mcp": ("TMS MCP", "src/tms-mcp", "mcp", ["system.tms-api"]),
    "workload.rate-mcp": ("Rate MCP", "src/rate-mcp", "mcp", ["system.rate-api"]),
    "workload.qms-mcp": ("QMS MCP", "src/qms-mcp", "mcp", ["system.qms-api"]),
    "workload.approval-mcp": ("Approval MCP", "src/approval-mcp", "mcp", ["system.qms-api"]),
}

AGENT_RUNTIME = {
    "agent.lane-evaluation": ("Lane Evaluation Agent", "src/lane-evaluation-agent", "a2a", ["workload.tms-mcp", "workload.rate-mcp"]),
    "agent.commercial-normalization": ("Commercial Normalization Agent", "src/commercial-normalization-agent", "a2a", ["workload.qms-mcp", "system.fx-api"]),
    "agent.route-decision": ("Route Decision Agent", "src/route-decision-agent", "a2a", ["workload.approval-mcp", "agent.lane-evaluation"]),
}

SYSTEM_RUNTIME = {
    "system.tms-api": ("TMS API", "src/mock-tms", "http", "TMS"),
    "system.rate-api": ("Rate API", "src/mock-rate", "http", "Rate management"),
    "system.qms-api": ("QMS API", "src/mock-qms", "http", "Quotation / QMS"),
    "system.fx-api": ("FX API", "src/mock-fx", "http", "Exchange rates"),
    "system.masterdata-api": ("Masterdata API", "src/mock-masterdata", "http", "Master data"),
}

POLICY_RUNTIME = {
    "policy.control-panel-pep": ("Control-panel PEP / Cedar PDP", "src/rfq_common", "policy", "Authorization and obligations"),
}


def load(relative: str):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def implementation_status(source: str) -> str:
    return "implemented" if (ROOT / source).exists() else "planned"


def main() -> None:
    jobs = load("business/job-titles.yaml")["job_titles"]
    bridge = load("business/job-workload-mappings.yaml")["mappings"]
    agents = {item["id"]: item for item in load("agents/catalog.yaml")["agents"]}
    actors = load("identity/actors.yaml")["actors"]
    actors_by_id = {item["id"]: item for item in actors}
    groups = {item["group_id"]: item for item in load("identity/groups.yaml")["groups"]}

    job_by_id = {item["job_title_id"]: item for item in jobs}
    directory_by_job = {}
    for actor in actors:
        job_title_id = actor.get("job_title_id")
        if not job_title_id or actor.get("kind") != "human":
            continue
        directory_by_job.setdefault(job_title_id, {"actors": [], "groups": []})["actors"].append(actor["id"])
        for group_id in actor.get("member_of", []):
            if group_id not in groups:
                raise ValueError(f"Unknown directory group: {group_id}")
            if group_id not in directory_by_job[job_title_id]["groups"]:
                directory_by_job[job_title_id]["groups"].append(group_id)
    for item in bridge:
        job = job_by_id.get(item["job_title_id"])
        if not job:
            raise ValueError(f"Unknown job_title_id: {item['job_title_id']}")
        if item["responsibility"] not in (job.get("responsibilities") or []):
            raise ValueError(f"Responsibility not found for {item['job_title_id']}: {item['responsibility']}")

    workloads = {}

    def add(workload_id: str, name: str, kind: str, source: str, protocol: str, dependencies=None, description=None):
        workloads[workload_id] = {
            "workload_id": workload_id,
            "name": name,
            "kind": kind,
            "implementation_status": implementation_status(source),
            "protocol": protocol,
            "source": source,
            "dependencies": dependencies or [],
        }
        if description:
            workloads[workload_id]["description"] = description
        directory_identity = actors_by_id.get(workload_id)
        if directory_identity:
            workloads[workload_id]["directory_identity"] = {
                "kind": directory_identity["kind"],
                "persona": directory_identity.get("persona"),
                "trust_domain": directory_identity.get("trust_domain"),
                "member_of": directory_identity.get("member_of", []),
            }

    for workload_id, (name, source, protocol, dependencies) in AGENT_RUNTIME.items():
        catalog_id = workload_id.removeprefix("agent.")
        catalog = agents.get(catalog_id)
        add(workload_id, name, "agent", source, protocol, dependencies, catalog.get("description") if catalog else None)
    for workload_id, (name, source, protocol, dependencies) in MCP_RUNTIME.items():
        add(workload_id, name, "mcp_server", source, protocol, dependencies)
    for workload_id, (name, source, protocol, domain) in SYSTEM_RUNTIME.items():
        add(workload_id, name, "system_api", source, protocol, [], domain)
    for workload_id, (name, source, protocol, domain) in POLICY_RUNTIME.items():
        add(workload_id, name, "policy_enforcement", source, protocol, [], domain)

    mappings = []
    for item in bridge:
        entry = {
            "job_title_id": item["job_title_id"],
            "job_title": job_by_id[item["job_title_id"]]["title"],
            "responsibility": item["responsibility"],
            "workloads": [],
        }
        for relation in item["workloads"]:
            workload_id = relation["workload_id"]
            if workload_id not in workloads:
                raise ValueError(f"Unknown workload_id: {workload_id}")
            entry["workloads"].append({**relation, "name": workloads[workload_id]["name"], "implementation_status": workloads[workload_id]["implementation_status"]})
        mappings.append(entry)

    policy_text = (ROOT / "authorization/policies.cedar").read_text(encoding="utf-8")
    policy_groups = [group_id for group_id in groups if f'Group::"{group_id}"' in policy_text]

    output = {
        "schema_version": 1,
        "generated_from": [
            "business/job-titles.yaml",
            "business/job-workload-mappings.yaml",
            "agents/catalog.yaml",
            "identity/actors.yaml",
            "identity/groups.yaml",
            "authorization/policies.cedar",
            "tools/story/generate_workload_map.py",
        ],
        "note": (
            "Current scope: this projection covers selected responsibilities from "
            "the Transport Planner, Commercial Pricing Specialist, and Pricing "
            "Manager job descriptions within the cross-currency lane repricing "
            "and approval subprocess. It connects those responsibilities to "
            "the showcase's implemented agent, MCP, system-API, and policy "
            "enforcement workloads, and includes the directory hierarchy used "
            "for AuthZ. It is not a claim that an entire job, role, or "
            "department is automated or replaced."
        ),
        "directory": {
            "sources": ["identity/actors.yaml", "identity/groups.yaml", "authorization/authz-projection.yaml"],
            "identity_service_targets": ["keycloak", "entra_id"],
            "hierarchy_relation": "actor.member_of -> group.path -> policy principal in Group",
            "policy_relevant_groups": policy_groups,
            "groups": list(groups.values()),
        },
        "workloads": list(workloads.values()),
        "job_responsibility_mappings": mappings,
    }
    for entry in output["job_responsibility_mappings"]:
        entry["directory"] = directory_by_job.get(entry["job_title_id"], {"actors": [], "groups": []})
    output_path = ROOT / "data/story/workload-to-jobs.yaml"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(yaml.safe_dump(output, sort_keys=False, allow_unicode=False), encoding="utf-8")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
