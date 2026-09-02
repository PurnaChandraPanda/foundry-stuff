"""Sequential workflow over the Fabric data agent, exposed as a single agent.

Follows the public sample:
https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/agents/sequential_workflow_as_agent.py

Two participants run in order:

    analyst (Fabric tool) -> reviewer (no tool)

`analyst` is the same agent as fabric_local_agent.py - it carries the Fabric data
agent tool and produces the grounded numbers. `reviewer` sees the analyst's reply
as its input and turns it into a short brief. Only the analyst touches Fabric;
the reviewer works purely from what the analyst returned, which is what makes the
chain useful: the review cannot invent data it was not given.

Run:
    python fabric_sequential_workflow_agent.py
    python fabric_sequential_workflow_agent.py --stream
    python fabric_sequential_workflow_agent.py --query "what is the average trip distance"
"""

import argparse
import asyncio
import os
import sys

from agent_framework import Agent, WorkflowAgent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
FABRIC_CONNECTION_NAME = os.environ.get("FABRIC_CONNECTION_NAME")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")

DEFAULT_QUERY = "which month had highest travel rides and which month had lowest"


async def run_streaming(agent: WorkflowAgent, query: str) -> None:
    """Print each participant's output as it is produced.

    The workflow forwards every participant's chunks as `AgentResponseUpdate`s,
    each tagged with `author_name` (falling back to the executor id). Chunks
    arrive in participant order, so a header is printed whenever the author
    changes rather than buffering per agent.

    Non-text contents (tool calls, tool results) are announced by type instead of
    printed - that is where the Fabric round trip becomes visible, and its
    payload is far too large for a console.
    """
    print("\n===== Streaming =====")
    current_author: str | None = None

    async for update in agent.run(query, stream=True):
        author = update.author_name or "workflow"
        if author != current_author:
            print(f"\n{'-' * 60}\n[{author}]")
            current_author = author

        for content in update.contents or []:
            if content.type in ("text", "text_reasoning"):
                # text_reasoning carries intermediate participants' output, which
                # is why intermediate_output_from is set on the builder in main().
                print(getattr(content, "text", ""), end="", flush=True)
            else:
                print(f"\n<{content.type}>", end="", flush=True)

    print("\n")


async def main(query: str, stream: bool) -> None:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )
    if not FABRIC_CONNECTION_NAME:
        raise ValueError("FABRIC_CONNECTION_NAME is required.")

    # AzureCliCredential intermittently fails on a 10s subprocess timeout.
    credential = AzureCliCredential(process_timeout=60)

    project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
    connection_id = project.connections.get(FABRIC_CONNECTION_NAME).id

    # Pass the tool as a plain dict. agent_framework_foundry sanitizes hosted
    # tools with a shallow dict(), which leaves the nested
    # FabricDataAgentToolParameters as an Azure model object and fails with
    # "Object of type FabricDataAgentToolParameters is not JSON serializable".
    # as_dict() serializes the whole tree.
    fabric_tool = FoundryChatClient.get_fabric_tool(connection_id=connection_id).as_dict()

    # FoundryChatClient resolves the model at construction time, so model= must
    # be passed here (or via FOUNDRY_MODEL); setting it only on Agent raises
    # "Model is required."
    # project_endpoint must be passed explicitly: the client only reads the
    # FOUNDRY_PROJECT_ENDPOINT env var, not AZURE_AI_PROJECT_ENDPOINT.
    client = FoundryChatClient(
        project_endpoint=PROJECT_ENDPOINT,
        model=MODEL_DEPLOYMENT_NAME,
        credential=credential,
        allow_preview=True,
    )

    analyst = Agent(
        client=client,
        name="analyst",
        instructions=(
            "You are a data analyst. Use the connected Microsoft Fabric data agent "
            "to answer the question about enterprise data. Always ground your answer "
            "in the data the tool returns and state the exact numbers you used."
        ),
        tools=[fabric_tool],
    )

    reviewer = Agent(
        client=client,
        name="reviewer",
        instructions=(
            "You are a reporting reviewer. Turn the previous assistant message into "
            "a two-sentence executive brief. Reuse its numbers verbatim. If a figure "
            "you need is missing, say so instead of estimating it."
        ),
    )

    # intermediate_output_from=[analyst] keeps the analyst's grounded reply on the
    # response. Without it, as_agent() returns ONLY the last participant's message
    # and the numbers the review is based on are invisible.
    workflow = SequentialBuilder(
        participants=[analyst, reviewer],
        intermediate_output_from=[analyst],
    ).build()

    agent = workflow.as_agent(name="fabric-sequential")

    if stream:
        await run_streaming(agent, query)
        return

    agent_response = await agent.run(query)

    if agent_response.messages:
        print("\n===== Conversation =====")
        for i, msg in enumerate(agent_response.messages, start=1):
            name = msg.author_name or msg.role
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

    print(f"\n===== Final =====\n{agent_response.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Question to ask.")
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream each participant's output as it is produced.",
    )
    args = parser.parse_args()

    asyncio.run(main(args.query, args.stream))
