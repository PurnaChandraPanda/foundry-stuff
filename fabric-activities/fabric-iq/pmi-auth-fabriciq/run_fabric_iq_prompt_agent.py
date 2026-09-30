"""Query the prompt agent created by `create_fabric_iq_prompt_agent.py`."""

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

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
AGENT_NAME = os.environ.get("FABRIC_IQ_AGENT_NAME")
QUERY = "which month had highest travel rides and which month had lowest"


def _explain_fabric_iq_error(error: BadRequestError) -> None:
    message = str(error)
    print(f"\nFabric IQ tool call failed:\n  {message}\n", file=sys.stderr)

    lowered = message.lower()
    if "not found" in lowered or "404" in lowered:
        print(
            "Cause: the server_url is wrong, or the Fabric item is not published.\n"
            "Verify the workspace and item GUIDs against the Fabric portal URL, and\n"
            "confirm the item is published. Check the endpoint directly with:\n"
            "  python diagnose_fabric_iq_connection.py",
            file=sys.stderr,
        )
    elif "consent_required" in lowered or "consent" in lowered:
        print(
            "Cause: the signed-in user has not completed the OAuth flow for this\n"
            "connection. Open the consent URL from the error in a browser, finish the\n"
            "flow, then re-run. This applies to managed OAuth / BYO Entra connections.",
            file=sys.stderr,
        )
    elif "unauthorized" in lowered or "401" in lowered:
        print(
            "Cause: the caller cannot reach the Fabric item. Fabric IQ runs under the\n"
            "*caller's* identity, so that user needs read access to the item and each\n"
            "underlying data source. For BYO Entra apps, confirm admin consent was\n"
            "granted for the required delegated permissions.",
            file=sys.stderr,
        )


def main() -> int:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    if not AGENT_NAME:
        raise ValueError(
            "FABRIC_IQ_AGENT_NAME is required. Run create_fabric_iq_prompt_agent.py first."
        )

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    openai_client = project.get_openai_client()

    try:
        conversation = openai_client.conversations.create()
        print(f"Created conversation (id: {conversation.id})")

        response = openai_client.responses.create(
            input=QUERY,
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": AGENT_NAME, "type": "agent_reference"}},
        )
    except BadRequestError as error:
        _explain_fabric_iq_error(error)
        return 1

    print(f"Response output: {response.output_text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
