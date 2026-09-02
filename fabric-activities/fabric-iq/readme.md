# Fabric IQ (MCP) with Foundry agents

Following doc - [/tools/fabric-iq/](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq?pivots=python)

- Create the Fabric IQ project connection: `create_fabric_iq_connection.sh`
- Troubleshoot the wiring: `diagnose_fabric_iq_connection.py`
- Create a Foundry prompt agent with the Fabric IQ tool: `create_fabric_iq_prompt_agent.py`
- Run that created agent: `run_fabric_iq_prompt_agent.py`
- Publish a toolbox holding the Fabric IQ tool: `create_fabric_iq_toolbox.py`
- Agent Framework local agent using that toolbox: `fabric_iq_local_agent.py`
- Foundry **hosted** agent (Responses protocol): [`hosted-agent/`](./hosted-agent/readme.md)

`fabric_iq_config.py` is a shared module, not a step - you never run it. It
builds the Fabric IQ MCP URL from `FABRIC_IQ_ITEM_TYPE` and the workspace/item
GUIDs, and is imported by every script above (and by the connection shell
script), so they cannot disagree about the endpoint.

Each step is its own script, so a failure points at one thing. The two shapes -
prompt agent and local agent - both follow the same create-then-run split.

## How this differs from `../fabric-data-agent`

Both folders answer the same questions over the same Fabric data, but they reach
it through different tools:

| | `fabric-data-agent` | `fabric-iq` (this folder) |
| --- | --- | --- |
| Tool type | `fabric_dataagent_preview` | `fabric_iq_preview` |
| Transport | Foundry-internal | **MCP** |
| Connection category | `CustomKeys` | `RemoteTool` |
| Connection auth | workspace-id / artifact-id keys | `UserEntraToken` (OBO) |
| Reaches | a published data agent only | ontology, data agent, or Power BI semantic model |
| Local agent wiring | tool passed straight to `Agent` | tool published in a **toolbox**, attached over MCP |

Fabric IQ is the broader surface: an ontology exposes your enterprise vocabulary
(entity types, relationships, and bindings to OneLake) and a Natural Language to
Ontology layer, so agents can ask in business terms. This sample targets the
**data agent** item because it is the only Fabric IQ item type that accepts a
plain user or service-principal token, which avoids the one-time Entra app
registration and Global Administrator consent the other item types require.

## Prerequisites

- A published Fabric item on F2+ capacity, and the capacity **resumed**. A paused
  capacity fails with `CapacityNotActive`.
- `Foundry User` on the Foundry project, plus `Foundry Project Manager` to create
  the connection.
- The signed-in user needs read access to the Fabric item and every data source
  behind it. Fabric IQ runs queries as the caller.
- `pip install -r requirements.txt`, and `az login`.

## Configuration

Copy `.env.example` to `.env` and fill it in.

```bash
# Foundry project ARM id till project level
AZURE_AI_PROJECT_ID="/subscriptions/.../projects/<project>"
AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"

# Connection name: alphanumerics, dashes and dots only - underscores are rejected
FABRIC_IQ_CONNECTION_NAME="fabric-iq-dataagent"
FABRIC_IQ_SERVER_LABEL="fabriciq-dataagent"
FABRIC_IQ_AUDIENCE="https://api.fabric.microsoft.com"

# Which Fabric item to talk to. The MCP URL is built from these three values.
FABRIC_IQ_ITEM_TYPE="dataagent"        # dataagent | ontology | semanticmodel
FABRIC_WORKSPACE_ID="640d864e-..."
FABRIC_ARTIFACT_ID="d1bea063-..."

FABRIC_IQ_AGENT_NAME="MyFabricIQAgent"
```

### How the server URL is built

You never write the MCP URL by hand. Set `FABRIC_IQ_ITEM_TYPE` plus the two
GUIDs, and `fabric_iq_config.py` assembles the endpoint. Every script - and the
connection shell script, which shells out to the same function - uses that one
resolver, so bash and Python cannot drift apart.

| `FABRIC_IQ_ITEM_TYPE` | Resulting `server_url` |
| --- | --- |
| `dataagent` (default) | `https://api.fabric.microsoft.com/v1/mcp/workspaces/{FABRIC_WORKSPACE_ID}/dataagents/{FABRIC_ARTIFACT_ID}/agent` |
| `ontology` | `https://api.fabric.microsoft.com/v1/mcp/dataPlane/workspaces/{FABRIC_WORKSPACE_ID}/items/{FABRIC_ARTIFACT_ID}/ontologyEndpoint` |
| `semanticmodel` | `https://api.fabric.microsoft.com/v1/mcp/fabricaihub/integrations/m365` |

Hyphens, underscores and a few synonyms (`data-agent`, `pbi`, `powerbi`) are
accepted. An unrecognized value fails immediately with the list of valid ones
rather than producing a URL that 404s later.

`semanticmodel` is a single tenant-wide hub endpoint, so it ignores both GUIDs.
The other two require them and say which one is missing if it is not set.

Setting `FABRIC_IQ_SERVER_URL` explicitly overrides all of this - an escape
hatch for an endpoint shape this sample does not know about.

Find the GUIDs in the Fabric portal: open the workspace, select the item, and
read them out of the browser URL.

## 1. Create the connection

```bash
# Git Bash rewrites values starting with /subscriptions/... into
# C:/Program Files/Git/subscriptions/... when launching a native Windows
# process. Set this before exporting AZURE_AI_PROJECT_ID.
export MSYS_NO_PATHCONV=1

./create_fabric_iq_connection.sh
```

This creates a `RemoteTool` connection with `authType: UserEntraToken`, so
Foundry forwards the signed-in user's Entra token to the Fabric MCP endpoint.

To remove it: `./create_fabric_iq_connection.sh --delete`

Ontology and Power BI semantic model items cannot use this connection type. They
need a BYO Entra app or managed OAuth connection, created in the Foundry portal
under **Settings > Connections > New connection > Fabric IQ**, because they
require a client secret and one-time tenant admin consent. See
[Set up your Entra app for ontology](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq#set-up-your-entra-app-for-ontology-one-time-per-organization).

## 2. Verify the wiring

```bash
python diagnose_fabric_iq_connection.py
```

It reads the project connection, then performs an MCP `initialize` and
`tools/list` against the Fabric endpoint using your identity, printing the tools
the item exposes. Expect something like:

```
  OK: connected to DataAgent MCP Server v1.0.0
  Tools exposed (1):
    - DataAgent_DA_DataAgent_WH: ...
```

## 3. Prompt agent

```bash
python create_fabric_iq_prompt_agent.py
python run_fabric_iq_prompt_agent.py
```

`create_...` registers a server-side agent whose definition carries the
`fabric_iq_preview` tool. `require_approval="never"` is set deliberately: the
default is `always`, which would stall a non-interactive script waiting for an
approval it can never receive.

## 4. Local agent through a toolbox

A toolbox registers a tool once and exposes it at an MCP endpoint that any agent
can attach to. Publishing and consuming are separate scripts because they have
different lifetimes: you publish when the tool definition changes, and run agents
against it many times in between.

```bash
# Publish a toolbox version holding the Fabric IQ tool
python create_fabric_iq_toolbox.py

# See what is already published
python create_fabric_iq_toolbox.py --list

# Run a local agent against the latest published version
python fabric_iq_local_agent.py

# Ask something else, or pin an older version
python fabric_iq_local_agent.py --query "how many total trips are there"
python fabric_iq_local_agent.py --toolbox-version 1
```

`fabric_iq_local_agent.py` resolves the highest published version by default, so
the common case takes no arguments. Toolbox versions persist across processes,
so `create_fabric_iq_toolbox.py` only needs re-running when the tool definition
changes.

Each run of `create_fabric_iq_toolbox.py` publishes a **new version** and leaves
earlier ones intact, so anything pinned with `--toolbox-version` keeps working.

If the toolbox has never been created, the local agent says so and exits non-zero
rather than failing later with an opaque 404 from the MCP endpoint.

