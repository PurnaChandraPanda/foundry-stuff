"""Query the prompt agent created by `create_fabric_iq_prompt_agent.py`."""

import argparse
import shlex
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from openai import APIStatusError
from openai.types.responses import Response

from fabric_iq_oauth import CONSENT_GUIDANCE, load_environment, required_env

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_environment()
DEFAULT_QUERY = "Describe MovieRating using the ontology entity metadata tool."


def _explain_fabric_iq_error(error: APIStatusError) -> None:
    message = str(error)
    print(f"\nFabric IQ tool call failed:\n  {message}\n", file=sys.stderr)

    lowered = message.lower()
    if "consent_required" in lowered or "consent" in lowered or "-32006" in lowered:
        print(CONSENT_GUIDANCE, file=sys.stderr)
    elif "not found" in lowered or "404" in lowered:
        print(
            "Check the agent name, connection, endpoint, workspace/item IDs, and publication.\n"
            "Inspect the UserEntraToken connection and toolbox with:\n"
            "  python diagnose_fabric_iq_connection.py",
            file=sys.stderr,
        )
    elif error.status_code in (401, 403):
        print(
            "Check the signed-in user's tenant, Foundry permissions, OAuth consent,\n"
            "and access to the Fabric ontology and each underlying source.",
            file=sys.stderr,
        )


def report_response(response: Response, query: str) -> int:
    needs_consent = False
    for item in response.output:
        # Foundry extends the OpenAI response union with OAuth output items.
        data = item.model_dump()
        if data.get("type") == "oauth_consent_request":
            link = data.get("consent_link")
            if not isinstance(link, str) or not link.startswith("https://"):
                raise ValueError("Foundry returned an OAuth consent request without a valid HTTPS link.")
            print(f"Review and open this consent URL as the Azure CLI user:\n{link}")
            needs_consent = True
    if needs_consent:
        print("After completing consent, resume with:")
        print(shlex.join([
            "python", "run_fabric_iq_prompt_agent.py",
            "--previous-response-id", response.id, "--query", query,
        ]))
        return 2
    if response.error is not None or response.status != "completed":
        print(
            f"Response did not complete: status={response.status}, "
            f"error={response.error}, incomplete_details={response.incomplete_details}",
            file=sys.stderr,
        )
        return 1
    if not response.output_text:
        print("Response completed without answer text. Inspect the agent/tool configuration.", file=sys.stderr)
        return 1
    print(f"Response output: {response.output_text}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--previous-response-id", help="Resume the response after completing OAuth consent.")
    args = parser.parse_args()
    endpoint = required_env("AZURE_AI_PROJECT_ENDPOINT")
    agent_name = required_env("FABRIC_IQ_AGENT_NAME")
    try:
        with (
            AzureCliCredential(tenant_id=required_env("TENANT_ID")) as credential,
            AIProjectClient(endpoint=endpoint, credential=credential) as project,
            project.get_openai_client() as openai_client,
        ):
            if args.previous_response_id:
                response = openai_client.responses.create(
                    input=args.query,
                    previous_response_id=args.previous_response_id,
                    tool_choice="required",
                    extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
                )
            else:
                response = openai_client.responses.create(
                    input=args.query,
                    tool_choice="required",
                    extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
                )
    except APIStatusError as error:
        _explain_fabric_iq_error(error)
        return 1
    return report_response(response, args.query)


if __name__ == "__main__":
    sys.exit(main())
