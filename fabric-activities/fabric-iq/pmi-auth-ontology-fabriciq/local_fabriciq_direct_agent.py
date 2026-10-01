import asyncio
import json
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from fabric_iq_config import resolve_server_url

load_dotenv()

USER_PROMPT = (
    # "Call list_ontology_entities without a name filter, if its schema allows that. "
    # "Report every returned entity's name, identifier, properties, and backing-table bindings. "
    # "If the call fails, report the actual error. Do not infer that the ontology is empty."

    # "Call list_ontology_entities and list_ontology_rules. Describe the MovieRating entity: its "
    # "properties, types, keys, backing-table bindings, and any explicitly linked business rules or "
    # "relationships. Report only what the tools return. Do not infer movie records, rating values, or "
    # "undocumented relationships."
    
    # "Which entity in this ontology represents movies? Identify its backing table and the properties "
    # "relevant to movie titles, release years, and ratings. Use the available tools and report only returned metadata. "
    # "Explain whether that metadata alone is enough to identify the highest-rated movies."

    # "Before choosing an entityName filter, call list_ontology_entities without a name filter, when " "supported. Match the user's terminology to the returned names, descriptions, and synonyms. Use "
    # "only discovered canonical entity names for subsequent filters. An empty filtered result does "
    # "not mean the ontology lacks that entity; retry unfiltered discovery before concluding it is "
    # "absent. Construct arguments according to each tool's schema."

    # "Before choosing an entityName filter, call list_ontology_entities without a name filter, when "
    # "supported. Match the user's terminology to the returned names, descriptions, and synonyms. Use "
    # "only discovered canonical entity names for subsequent filters. An empty filtered result does "
    # "not mean the ontology lacks that entity; retry unfiltered discovery before concluding it is "
    # "absent. Construct arguments according to each tool's schema."

    "Describe the MovieRating entity in this ontology. "
    "First call list_ontology_entities without a name filter, when supported. "
    "Find the entity whose canonical name is MovieRating. "
    "Using the returned metadata, report its description, identifier, "
    "properties and types, keys, synonyms, and backing-table bindings. "
    "Call list_ontology_rules and report any rules explicitly linked to "
    "MovieRating; state if none are returned. "
    "Complete this task now rather than listing all entities or offering "
    "to perform another lookup. Do not invent movie records or rating values."
)

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
                    USER_PROMPT
                )
                print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
