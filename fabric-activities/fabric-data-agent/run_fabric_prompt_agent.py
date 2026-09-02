import os
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import BadRequestError

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# load environment variables from .env file
load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
AGENT_NAME = os.environ.get("FABRIC_AGENT_NAME")
QUERY = "which month had highest travel rides and which month had lowest"


def _explain_fabric_error(error: BadRequestError) -> None:
    message = str(error)
    print(f"\nFabric tool call failed:\n  {message}\n", file=sys.stderr)

    lowered = message.lower()
    if "configuration not found" in lowered or "cannot find the requested item" in lowered:
        print(
            "Cause: the Fabric data agent is not published, or its configuration changed\n"
            "after the connection was created. The Foundry Fabric tool calls the\n"
            "*published* stage of the data agent, and that stage does not exist yet.\n\n"
            "Fix (in Microsoft Fabric, not in this code):\n"
            "  1. Open your data agent in Fabric.\n"
            "  2. Confirm its data sources are attached and valid.\n"
            "  3. Select Publish and wait for publishing to complete.\n"
            "  4. Re-run this script.\n\n"
            "Verify the connection wiring with:\n"
            "  python diagnose_fabric_connection.py",
            file=sys.stderr,
        )
    elif "unauthorized" in lowered:
        print(
            "Cause: the signed-in user lacks access to the Fabric data agent or its\n"
            "underlying data sources. Grant that user READ access in Fabric. Service\n"
            "principal authentication is not supported for the Fabric data agent.",
            file=sys.stderr,
        )
    elif "artifact id" in lowered or "workspace id" in lowered:
        print(
            "Cause: the Fabric connection has an invalid workspace_id or artifact_id.\n"
            "Recreate the connection using the GUIDs from the data agent URL path:\n"
            "  .../groups/<workspace_id>/aiskills/<artifact_id>...",
            file=sys.stderr,
        )


def main() -> int:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    if not AGENT_NAME:
        raise ValueError("FABRIC_AGENT_NAME is required. Run create_fabric_prompt_agent.py first.")

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    openai_client = project.get_openai_client()

    try:
        # Optional Step: Create a conversation to use with the agent
        conversation = openai_client.conversations.create()
        print(f"Created conversation (id: {conversation.id})")

        # Create a conversation to use with the agent
        response = openai_client.responses.create(
            tool_choice="required",
            input=QUERY,
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": AGENT_NAME, "type": "agent_reference"}},
        )
    except BadRequestError as error:
        _explain_fabric_error(error)
        return 1

    print(f"Response output: {response.output_text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
