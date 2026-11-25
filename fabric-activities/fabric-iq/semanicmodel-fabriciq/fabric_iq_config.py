"""Build the Fabric IQ MCP endpoint URL from the item type and Fabric GUIDs.

Each Fabric IQ item type is exposed at a differently shaped MCP URL, so the
sample keeps the identifiers in `.env` and derives the URL here rather than
asking you to paste a long URL and keep it in sync with the GUIDs.

Environment variables:
    FABRIC_IQ_ITEM_TYPE   dataagent | ontology | semanticmodel  (default dataagent)
    FABRIC_WORKSPACE_ID   GUID from the Fabric portal URL
    FABRIC_ARTIFACT_ID    GUID of the item within that workspace
    FABRIC_IQ_SERVER_URL  optional escape hatch; wins over everything above
"""

import os

FABRIC_HOST = "https://api.fabric.microsoft.com"

DATA_AGENT = "dataagent"
ONTOLOGY = "ontology"
SEMANTIC_MODEL = "semanticmodel"

# Accept the spellings people actually reach for, so a reasonable value in .env
# does not fail on a hyphen or a plural.
_ALIASES = {
    "dataagent": DATA_AGENT,
    "data-agent": DATA_AGENT,
    "data_agent": DATA_AGENT,
    "ontology": ONTOLOGY,
    "semanticmodel": SEMANTIC_MODEL,
    "semantic-model": SEMANTIC_MODEL,
    "semantic_model": SEMANTIC_MODEL,
    "powerbi": SEMANTIC_MODEL,
    "pbi": SEMANTIC_MODEL,
}

# The Power BI semantic model endpoint is a single tenant-wide hub, so unlike the
# other two it carries no workspace or item GUID.
_NEEDS_GUIDS = {DATA_AGENT, ONTOLOGY}


def normalize_item_type(raw: str | None) -> str:
    if not raw:
        return DATA_AGENT
    key = raw.strip().lower()
    if key not in _ALIASES:
        raise ValueError(
            f"FABRIC_IQ_ITEM_TYPE='{raw}' is not recognized. "
            f"Use one of: {DATA_AGENT}, {ONTOLOGY}, {SEMANTIC_MODEL}."
        )
    return _ALIASES[key]


def build_server_url(item_type: str, workspace_id: str | None, artifact_id: str | None) -> str:
    """Return the MCP endpoint for one Fabric IQ item."""
    item_type = normalize_item_type(item_type)

    if item_type in _NEEDS_GUIDS:
        missing = [
            name
            for name, value in (
                ("FABRIC_WORKSPACE_ID", workspace_id),
                ("FABRIC_ARTIFACT_ID", artifact_id),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"{' and '.join(missing)} must be set to build the "
                f"'{item_type}' server URL."
            )

    if item_type == DATA_AGENT:
        return f"{FABRIC_HOST}/v1/mcp/workspaces/{workspace_id}/dataagents/{artifact_id}/agent"
    if item_type == ONTOLOGY:
        return (
            f"{FABRIC_HOST}/v1/mcp/dataPlane/workspaces/{workspace_id}"
            f"/items/{artifact_id}/ontologyEndpoint"
        )
    return f"{FABRIC_HOST}/v1/mcp/fabricaihub/integrations/m365"


def resolve_server_url() -> str:
    """Read the environment and produce the MCP endpoint URL.

    An explicit FABRIC_IQ_SERVER_URL wins, so an endpoint shape this sample does
    not know about can still be used without editing code.
    """
    explicit = os.environ.get("FABRIC_IQ_SERVER_URL")
    if explicit:
        return explicit

    return build_server_url(
        os.environ.get("FABRIC_IQ_ITEM_TYPE"),
        os.environ.get("FABRIC_WORKSPACE_ID"),
        os.environ.get("FABRIC_ARTIFACT_ID"),
    )


def resolve_item_type() -> str:
    return normalize_item_type(os.environ.get("FABRIC_IQ_ITEM_TYPE"))


def toolbox_mcp_url(project_endpoint: str, toolbox_name: str, version: str) -> str:
    """MCP endpoint a published toolbox version is served at.

    Shared so the create and run scripts cannot print or attach different URLs.
    """
    return f"{project_endpoint}/toolboxes/{toolbox_name}/versions/{version}/mcp?api-version=v1"
