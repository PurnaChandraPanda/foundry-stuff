"""Run a toolbox-backed prompt agent by name, handling every round of MCP approvals."""

import argparse
from collections.abc import Callable

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from openai import OpenAI
from openai.types.responses import Response
from openai.types.responses.response_input_param import McpApprovalResponse, ResponseInputParam

from config import https_url, load_environment, resource_name


def finish_response(
    client: OpenAI,
    response: Response,
    agent_reference: dict[str, str],
    approve: Callable[[str], str] = input,
) -> Response:
    for round_number in range(21):
        if response.error is not None or response.status in {"failed", "incomplete", "cancelled"}:
            raise RuntimeError(
                f"Foundry response {response.id}: {response.status}; "
                f"error={response.error}; incomplete={response.incomplete_details}"
            )
        approvals: ResponseInputParam = []
        for item in response.output:
            if item.type == "mcp_list_tools" and item.error is not None:
                raise RuntimeError(f"Toolbox MCP discovery failed: {item.error}")
            if item.type == "mcp_call":
                print(f"MCP call: {item.name}, server: {item.server_label}")
                if item.error is not None:
                    raise RuntimeError(f"Toolbox MCP call failed: {item.error}")
            elif item.type == "mcp_approval_request":
                if round_number == 20:
                    raise RuntimeError("Stopped after 20 approval rounds; inspect the agent and tool behavior.")
                print(f"Server: {item.server_label}\nTool: {item.name}\nArguments: {item.arguments}")
                approvals.append(
                    McpApprovalResponse(
                        type="mcp_approval_response",
                        approval_request_id=item.id,
                        approve=approve("Approve this call? [y/N] ").strip().lower() == "y",
                    )
                )
        if not approvals:
            if response.status != "completed":
                raise RuntimeError(f"Unexpected response status: {response.status}")
            return response
        response = client.responses.create(
            previous_response_id=response.id,
            input=approvals,
            extra_body={"agent_reference": agent_reference},
        )
    raise AssertionError("Approval loop exited without a response.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    load_environment()
    reference = {
        "type": "agent_reference",
        "name": resource_name("APIM_PROMPT_AGENT_NAME"),
    }
    with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=https_url("AZURE_AI_PROJECT_ENDPOINT"), credential=credential
        ) as project,
        project.get_openai_client() as client,
    ):
        response = client.responses.create(
            input=args.query, extra_body={"agent_reference": reference}
        )
        response = finish_response(client, response, reference)
        print(f"Response ID: {response.id}")
        print(response.output_text)
        if not response.output_text:
            print("No text returned; inspect this response in Foundry.")


if __name__ == "__main__":
    main()
