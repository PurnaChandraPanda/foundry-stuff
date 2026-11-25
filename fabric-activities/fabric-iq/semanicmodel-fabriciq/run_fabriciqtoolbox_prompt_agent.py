"""Query a prompt agent created through a published Fabric IQ toolbox."""

import argparse
import os
import shlex
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from openai import APIStatusError
from openai.types.responses import Response

from fabric_iq_oauth import CONSENT_GUIDANCE, load_environment, required_env

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_environment()

DEFAULT_QUERY = "What are the total sales based on customer categories?"


def report_response(response: Response, query: str) -> int:
    needs_consent = False
    for item in response.output:
        data = item.model_dump()
        if data.get("type") == "oauth_consent_request":
            link = data.get("consent_link")
            if not isinstance(link, str) or not link.startswith("https://"):
                raise ValueError(
                    "Foundry returned an OAuth consent request without a valid HTTPS link."
                )
            print(f"Review and open this consent URL as the Azure CLI user:\n{link}")
            needs_consent = True
    if needs_consent:
        print("After completing consent, resume with:")
        print(
            shlex.join(
                [
                    "python",
                    "run_fabriciqtoolbox_prompt_agent.py",
                    "--previous-response-id",
                    response.id,
                    "--query",
                    query,
                ]
            )
        )
        return 2
    if response.error is not None or response.status != "completed":
        print(
            f"Response did not complete: status={response.status}, "
            f"error={response.error}, incomplete_details={response.incomplete_details}",
            file=sys.stderr,
        )
        return 1
    if not response.output_text:
        print("Response completed without answer text.", file=sys.stderr)
        print(response.model_dump_json(indent=2), file=sys.stderr)
        return 1
    print(f"Response output: {response.output_text}")
    return 0


def mcp_approval_requests(response: Response) -> list[str]:
    return [
        data["id"]
        for item in response.output
        if (data := item.model_dump()).get("type") == "mcp_approval_request"
        and isinstance(data.get("id"), str)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument(
        "--previous-response-id",
        help="Resume the response after completing OAuth consent.",
    )
    args = parser.parse_args()

    endpoint = required_env("AZURE_AI_PROJECT_ENDPOINT")
    agent_name = os.getenv("FABRIC_IQ_TOOLBOX_AGENT_NAME")

    try:
        with (
            AzureCliCredential(tenant_id=required_env("TENANT_ID")) as credential,
            AIProjectClient(endpoint=endpoint, credential=credential) as project,
            project.get_openai_client() as openai_client,
        ):
            if args.previous_response_id:
                approval_input = [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": approval_request_id,
                        "approve": True,
                    }
                    for approval_request_id in args.approval_request_id
                ]
                response = openai_client.responses.create(
                    input=approval_input or args.query,
                    previous_response_id=args.previous_response_id,
                    tool_choice="required",
                    extra_body={
                        "agent_reference": {"name": agent_name, "type": "agent_reference"}
                    },
                )
                for _ in range(10):
                    approval_requests = mcp_approval_requests(response)
                    if not approval_requests:
                        break
                    approval_input = [
                        {
                            "type": "mcp_approval_response",
                            "approval_request_id": approval_request_id,
                            "approve": True,
                        }
                        for approval_request_id in approval_requests
                    ]
                    response = openai_client.responses.create(
                        input=approval_input,
                        previous_response_id=response.id,
                        tool_choice="required",
                        extra_body={
                            "agent_reference": {
                                "name": agent_name,
                                "type": "agent_reference",
                            }
                        },
                    )
            else:
                conversation_id = openai_client.conversations.create().id
                response = openai_client.responses.create(
                    input=args.query,
                    tool_choice="required",
                    conversation=conversation_id,
                    extra_body={
                        "agent_reference": {"name": agent_name, "type": "agent_reference"}
                    },
                )
                for _ in range(10):
                    approval_requests = mcp_approval_requests(response)
                    if not approval_requests:
                        break
                    approval_input = [
                        {
                            "type": "mcp_approval_response",
                            "approval_request_id": approval_request_id,
                            "approve": True,
                        }
                        for approval_request_id in approval_requests
                    ]
                    response = openai_client.responses.create(
                        input=approval_input,
                        previous_response_id=response.id,
                        tool_choice="required",
                        extra_body={
                            "agent_reference": {
                                "name": agent_name,
                                "type": "agent_reference",
                            }
                        },
                    )
    except APIStatusError as error:
        print(f"\nFabric IQ toolbox prompt-agent call failed:\n{error}\n", file=sys.stderr)
        lowered = str(error).lower()
        if "consent_required" in lowered or "consent" in lowered or "-32006" in lowered:
            print(CONSENT_GUIDANCE, file=sys.stderr)
        elif error.status_code in (401, 403):
            print(
                "Check the signed-in tenant, Foundry permissions, OAuth consent, "
                "and Fabric semantic-model access.",
                file=sys.stderr,
            )
        return 1

    return report_response(response, args.query)


if __name__ == "__main__":
    sys.exit(main())
