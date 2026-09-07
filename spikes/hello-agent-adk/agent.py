from google.adk.agents import Agent

root_agent = Agent(
    name="hello_agent_adk",
    model="gemini-2.5-flash-lite",
    description="Minimal hello-world ADK agent spike (this repo).",
    instruction=(
        "You are a terse hello-world agent running on Google ADK / Vertex AI "
        "Agent Engine, deployed from cpm-eaop-showcase-logistics-rfq. Always "
        "prefix your reply with '[ADK/Vertex AI - showcase] '. Reply in one "
        "short sentence."
    ),
    tools=[],
)
