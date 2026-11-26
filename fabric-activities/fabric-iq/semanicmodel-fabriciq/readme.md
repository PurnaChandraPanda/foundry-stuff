# Fabric ontology through Foundry managed user authentication

Activties are planned for local or prompt agents into Fabric Semantic Model via Fabric IQ MCP - with Managed UserEntraToken as remote tool auth type. Any authenticated user would start agent on client side. The authentication flow would be like following.

```text
Azure CLI user
  -> local agent using Foundry FabricIQPreviewTool
  -> Foundry project UserEntraToken connection
  -> delegated Fabric API token
  -> Fabric IQ MCP server: Semantic Model

Azure CLI user
  -> Foundry hosted prompt agent
  -> FabricIQPreviewTool
  -> same managed UserEntraToken connection
  -> delegated Fabric API token
  -> Fabric IQ MCP server: Semantic Model
```

## 1. Configure the local user and environment

Copy [.env.example](.env.example) to `.env` if needed and populate the existing
project/model and Fabric workspace/item IDs. 

The provisioning caller needs connection write permissions on the project (for example, Foundry Project Manager); verification needs connection-read access.
Developers need the appropriate Foundry project roles to publish agents/toolboxes. Runtime users need Foundry access and access to the Fabric ontology and any data sources they query.
See [OAuth identity passthrough prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/mcp-authentication#oauth-identity-passthrough).

In Dev environment, it has `Python-3.13` installed. The package `agent-framework` is needed for remainder local machine testing.

```
pip install agent-framework>=1.26.0
```


## 2. Create the connection with Azure CLI (`az rest`)

No connector identifier is needed. The script provisions a `UserEntraToken` connection using the Fabric API audience. It uses `AZURE_AI_PROJECT_ID` directly, so connection creation does not depend on Foundry data-plane discovery, an `azd` project/environment, or an `azd` sign-in. No Azure Developer CLI extension is required.

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

## 3. Direct-client comparison only

```bash
# Discover raw names and print a ready-to-copy ALLOWED_TOOLS assignment `in .env`.
python diagnose_fabric_iq_connection.py --tool-source direct

python local_fabriciq_direct_agent.py
```

This script bypasses the Foundry connection and requests a Fabric bearer token
for the Azure CLI user. It does **not test the Foundry UserEntraToken connection**. `ALLOWED_TOOLS` applies
only to this direct-client comparison, not to the toolbox or prompt agent.

## 4. Publish and invoke a prompt agent + Fabric IQ [tool]

```bash
python create_fabric_iq_prompt_agent.py

python run_fabric_iq_prompt_agent.py --query "what are the total sales based on customer categories"
```

This path attaches `FabricIQPreviewTool` **directly** to the prompt agent; it does
not use the toolbox. The agent references the same UserEntraToken connection.
`require_approval="never"` disables tool-call approvals, **not OAuth consent**.

If the service returns `oauth_consent_request` response items, the runner prints their
`consent_link`, and exits with code 2 (authorization is still pending). Complete
consent, then use the printed command with `--previous-response-id` to resume the
same response and question. Failed/incomplete responses exit with code 1.
Successful answers exit with code 0.

## 5. Publish and test a toolbox

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
```

The diagnostic defaults to `--tool-source toolbox`, which goes **through Foundry**.
It verifies that the published version references the configured connection, lists all MCP tool
pages without an LLM. Entity names are exact matches. Tool results and errors are printed rather than summarized by
the model. Metadata success does not prove access to backing-table rows.

Direct mode queries Fabric itself; it does not merely remove a prefix. It skips 
Foundry connection and toolbox checks and ignores `ALLOWED_TOOLS` so a stale
allowlist cannot hide tools. Neither diagnostic mode filters the discovered list.
Do not combine direct mode with `--toolbox-version`, `--connection-only`, or
`--setup`. The toolbox runner does not use the direct client's `ALLOWED_TOOLS`.

```bash
python local_fabriciq_toolbox_agent.py --toolbox-version 1 --query "what are the different customer categories"
python local_fabriciq_toolbox_agent.py --toolbox-version 1 --query "what are the total sales based on customer categories"

python local_fabriciq_toolbox_agent.py --query "what are the different customer categories"
```

## 6. Publish and invoke a prompt agent + Fabric IQ [Toolbox]

To publish a prompt agent that uses a published **toolbox**, use:

```bash
python create_fabriciqtoolbox_prompt_agent.py
python run_fabriciqtoolbox_prompt_agent.py --query "what are the total sales based on customer categories"
```

Set `FABRIC_IQ_TOOLBOX_AGENT_NAME` separately from `FABRIC_IQ_AGENT_NAME` so the
direct and toolbox prompt agents have independent names. The toolbox agent
attaches the published toolbox MCP endpoint to `MCPTool` and uses the same
`UserEntraToken` connection stored in the toolbox.

If the service returns `oauth_consent_request` response items, the runner prints their
`consent_link`, and exits with code 2 (authorization is still pending). Complete
consent, then use the printed command with `--previous-response-id` to resume the
same response and question. Failed/incomplete responses exit with code 1.
Successful answers exit with code 0.


## References

- [Fabric IQ integration and authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq)
- [Managed vs custom OAuth and prompt-agent consent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/mcp-authentication#oauth-identity-passthrough)
- [Toolbox OAuth consent errors](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Ontology MCP server](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-mcp-server)
