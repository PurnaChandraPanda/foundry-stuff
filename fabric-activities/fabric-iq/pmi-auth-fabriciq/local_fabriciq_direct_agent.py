import asyncio
import json
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from fabric_iq_config import resolve_server_url

load_dotenv()


def parse_allowed_tools(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    try:
        names = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ALLOWED_TOOLS must be a JSON array of tool names.") from exc
    if not isinstance(names, list) or not all(
        isinstance(name, str) and name.strip() for name in names
    ):
        raise ValueError("ALLOWED_TOOLS must be a JSON array of non-empty tool names.")
    return [name.strip() for name in names]


async def main() -> None:
    allowed_tools = parse_allowed_tools(os.environ.get("ALLOWED_TOOLS"))
    with DefaultAzureCredential() as credential:
        
        def fabric_headers(_: dict) -> dict[str, str]:
            token = credential.get_token(
                "https://api.fabric.microsoft.com/.default"
            ).token
            return {"Authorization": f"Bearer {token}"}

        async with MCPStreamableHTTPTool(
            name="fabric_iq",
            url=resolve_server_url(),
            header_provider=fabric_headers,
            load_prompts=False,
            allowed_tools=allowed_tools,
            approval_mode="never_require",
            request_timeout=180,
        ) as fabric_tool:
            tool_names = [tool.name for tool in fabric_tool.functions]
            if not tool_names:
                raise RuntimeError(
                    "No Fabric MCP tools are available to the agent. "
                    "Check ALLOWED_TOOLS against the names printed by "
                    "diagnose_fabric_iq_connection.py."
                )
            print(f"Available Fabric tools: {', '.join(tool_names)}")

            async with Agent(
                name="LocalFabricIQAgent",
                client=FoundryChatClient(
                    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                    credential=credential,
                ),
                instructions=(
                    "For business-data questions, call a Fabric data tool before "
                    "answering and pass the user's full question. "
                    "Ground answers only in the returned data. For monthly "
                    "comparisons, include year-month, totals, and any ties. "
                    "If the tool returns an error, report the actual error and "
                    "do not invent results or claim the tool was unavailable. "
                    "If the data is insufficient, explain what is missing."
                ),
                tools=[fabric_tool],
            ) as agent:
                result = await agent.run(
                    "Which month had the highest travel rides, "
                    "and which month had the lowest?"
                )
                print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
