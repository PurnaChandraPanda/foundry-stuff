# Fabric ontology through Foundry managed user authentication

Activties are planned for local or prompt agents into Fabric Ontology via Fabric IQ MCP - with Managed UserEntraToken as remote tool auth type. Any authenticated user would start agent on client side. The authentication flow would be like following.

```text
Azure CLI user -> local agent -> Foundry toolbox -> UserEntraToken -> Fabric ontology
Azure CLI user -> Foundry prompt agent -> Fabric IQ tool -> UserEntraToken -> Fabric ontology
```

## 1. Configure the local user and environment

Copy [.env.example](.env.example) to `.env` if needed and populate the existing
project/model and Fabric workspace/item IDs. The separate resource names are:

```dotenv
FABRIC_IQ_CONNECTION_NAME="fabric-iq-managed-oauth-ontology"
FABRIC_IQ_TOOLBOX_NAME="fabric-iq-managed-oauth-toolbox"
FABRIC_IQ_AGENT_NAME="MyFabricIQManagedOAuthOntologyAgent"
FABRIC_IQ_SERVER_LABEL="fabriciq-managed-oauth-ontology"
FABRIC_IQ_ITEM_TYPE="ontology"
```

The provisioning caller needs connection write permissions on the project 
(for example, Foundry Project Manager); verification needs connection-read access.
Developers need the appropriate Foundry project roles to publish agents/toolboxes. Runtime users need Foundry
access and access to the Fabric ontology and any data sources they query.
See [OAuth identity passthrough prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/mcp-authentication#oauth-identity-passthrough).

## 2. Create the connection with Azure CLI (`az rest`)

No connector identifier is needed. The script provisions a `UserEntraToken`
connection using the Fabric API audience. It uses `AZURE_AI_PROJECT_ID` directly, so connection creation does
not depend on Foundry data-plane discovery, an `azd` project/environment, or an
`azd` sign-in. No Azure Developer CLI extension is required.

```bash
# In Git Bash, export this explicitly before running the script.
export MSYS_NO_PATHCONV=1

# Sign in to TENANT_ID, then create or update the connection.
./create_fabric_iq_connection.sh
```

The PUT URL is:

```text
https://management.azure.com{AZURE_AI_PROJECT_ID}/connections/{FABRIC_IQ_CONNECTION_NAME}?api-version=2025-10-01-preview
```

## 3. Publish and test a toolbox

```bash
python create_fabric_iq_toolbox.py
python create_fabric_iq_toolbox.py --list
```

The publisher verifies the UserEntraToken connection before creating a new toolbox version.
It continues to use `FabricIQPreviewToolboxTool`; there is no separate OAuth tool
class and no Fabric token is passed from the local agent.

Use the version printed by the publisher (the examples assume version 1):

```bash
python diagnose_fabric_iq_connection.py --tool-source toolbox --toolbox-version 1
python diagnose_fabric_iq_connection.py --tool-source toolbox --toolbox-version 1 --entity-name MovieRating
```

The diagnostic defaults to `--tool-source toolbox`, which goes **through Foundry**.
It verifies
that the published version references the configured connection, lists all MCP tool
pages, and optionally calls `list_ontology_entities` without an LLM. Entity names
are exact matches. Tool results and errors are printed rather than summarized by
the model. Metadata success does not prove access to backing-table rows.

Choose the source whose tool names you need:

| Flag | Names returned | Use |
| --- | --- | --- |
| `--tool-source toolbox` | Actual toolbox names, such as `fabriciq-managed-oauth-ontology___list_ontology_entities` | Foundry toolbox calls |
| `--tool-source direct` | Actual Fabric names, such as `list_ontology_entities` | Direct-client `ALLOWED_TOOLS` |

Direct mode queries Fabric itself; it does not merely remove a prefix. It skips
Foundry connection and toolbox checks and ignores `ALLOWED_TOOLS` so a stale
allowlist cannot hide tools. Neither diagnostic mode filters the discovered list.
Do not combine direct mode with `--toolbox-version`, `--connection-only`, or
`--setup`. The toolbox runner does not use the direct client's `ALLOWED_TOOLS`.

```bash
python local_fabriciq_toolbox_agent.py --toolbox-version 1 --query "Describe MovieRating and its properties."
python local_fabriciq_toolbox_agent.py --toolbox-version 1 --query "List movies from MovieRating by rating descending."

python local_fabriciq_toolbox_agent.py --toolbox-version 1 --query "Return the top 10 movies from MovieRating's backing table, movies_table. Show FILM, YEAR, and RATING. Convert RATING from text to a numeric value, exclude invalid or missing ratings, and sort numerically descending. Execute the query and return actual rows."
```

The runner prints the tools available to the model. If the endpoint still exposes
only `list_ontology_entities` and `list_ontology_rules`, changing authentication has not added a
row-query engine. Do not confuse ontology metadata with movie records. 

## 4. Alternatively, publish and invoke a prompt agent

```bash
python create_fabric_iq_prompt_agent.py
python run_fabric_iq_prompt_agent.py --query "Describe MovieRating and its properties."
```

This path attaches `FabricIQPreviewTool` **directly** to the prompt agent; it does
not use the toolbox. The agent references the same UserEntraToken connection.
`require_approval="never"` disables tool-call approvals, **not OAuth consent**.

If the service returns `oauth_consent_request` response items, the runner prints their
`consent_link`, and exits with code 2 (authorization is still pending). Complete
consent, then use the printed command with `--previous-response-id` to resume the
same response and question. Failed/incomplete responses exit with code 1.
Successful answers exit with code 0.

## 5. Direct-client comparison only

```bash
# Discover raw names and print a ready-to-copy ALLOWED_TOOLS assignment `in .env`.
python diagnose_fabric_iq_connection.py --tool-source direct

# Optionally execute the entity metadata tool directly.
python diagnose_fabric_iq_connection.py --tool-source direct --entity-name MovieRating

python local_fabriciq_direct_agent.py
```

This script bypasses the Foundry connection and requests a Fabric bearer token
for the Azure CLI user. It does **not test the Foundry UserEntraToken connection**. `ALLOWED_TOOLS` applies
only to this direct-client comparison, not to the toolbox or prompt agent.

## References

- [Fabric IQ integration and authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq)
- [Managed vs custom OAuth and prompt-agent consent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/mcp-authentication#oauth-identity-passthrough)
- [Toolbox OAuth consent errors](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Ontology MCP server](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-mcp-server)
