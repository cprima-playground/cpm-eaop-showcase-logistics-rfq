"""Generate the non-technical role exposition from canonical business data."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


RESPONSIBILITY_BRIDGES = {
    "transport-planner": [
        ("Evaluate route alternatives and check capacity", "Lane Evaluation Agent"),
        ("Prepare a route recommendation", "Route Decision Agent"),
    ],
    "commercial-pricing-specialist": [
        ("Normalize route costs and calculate commercial variance", "Commercial Normalization Agent"),
        ("Prepare a quote for approval", "Commercial Normalization Agent"),
    ],
    "pricing-manager": [
        ("Approve commercial deviations and exceptions", "Human authority retained"),
    ],
}


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    departments = {
        item["department_id"]: item for item in load("business/departments.yaml")["departments"]
    }
    titles = load("business/job-titles.yaml")["job_titles"]
    # Load the catalog as an input dependency so a missing or malformed agent
    # catalog fails the generation rather than silently producing stale prose.
    load("agents/catalog.yaml")

    lines = [
        "# Logistics roles and agent responsibilities",
        "",
        "This page is generated from `business/departments.yaml`,",
        "`business/job-titles.yaml`, and `agents/catalog.yaml`.",
        "",
        "The agent mapping is deliberately narrow: it illustrates selected",
        "responsibilities, not whole-job replacement.",
        "",
    ]
    for title in titles:
        department = departments.get(title.get("department_id"), {})
        status = "modeled today" if title.get("exists_today") else "organizationally recognized; not yet modeled"
        lines += [f"## {title['title']}", "", f"**Department:** {department.get('name', 'Platform / outside the logistics spine')}  ", f"**Status:** {status}", ""]
        responsibilities = title.get("responsibilities") or []
        if responsibilities:
            lines += ["**Responsibilities in the canonical data:**", ""]
            lines += [f"- {item}" for item in responsibilities]
            lines += [""]
        bridge = RESPONSIBILITY_BRIDGES.get(title["job_title_id"])
        if bridge:
            lines += ["**Showcase bridge — selected responsibilities:**", ""]
            for responsibility, agent in bridge:
                lines.append(f"- {responsibility} → **{agent}**")
            lines += ["", "The surrounding role, judgment, and accountability remain human.", ""]
    output = ROOT / "docs/story/roles.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
