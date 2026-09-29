
Activties are planned for local or prompt agents into Fabric data agent via Fabric IQ MCP - for SP as authenticated user on client side. The authentication flow would be like following.

```
[for SP user local or prompt agent] -> [toolbox] -> [fabric iq mcp server] -> [fabric data agent]
```

As a pre-requisite, confirm that the SP user has `Foundry User` role on Foundry account/ project levels. Also, confirm that SP user has at least `reader` role at Fabric workspace level.

## 1. Create the Fabric IQ connection

```bash
# Git Bash rewrites values starting with /subscriptions/... into
# C:/Program Files/Git/subscriptions/... when launching a native Windows
# process. Set this before exporting AZURE_AI_PROJECT_ID.
export MSYS_NO_PATHCONV=1

./create_fabric_iq_connection.sh
```

## 2. Verify the wiring for Fabric IQ

```bash
python diagnose_fabric_iq_connection.py
```

The diagnostic uses `ClientSecretCredential` with `TENANT_ID`, `CLIENT_ID`,
and `CLIENT_SECRET` from the environment or `.env`. It reads the Foundry
connection and then calls Fabric MCP directly using the
`https://api.fabric.microsoft.com/.default` scope. It does not test the
Foundry agent/toolbox forwarding path or run a data query.

The connection creation script configures `UserEntraToken`; creating that
connection does not configure client-secret authentication on the connection.
A successful direct SP probe does not prove that this connection forwards an
app-only token through Foundry.

See [Data agent as an MCP server](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-mcp-server)
for MCP authentication and capacity prerequisites, and
[Service principal authentication](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-service-principal)
for SP setup and limitations. Use the MCP-specific scope above for this endpoint;
the general SP guide documents a different scope for the data agent query API.

## 3. Run a local agent directly against Fabric MCP

```bash
python local_fabriciq_direct_agent.py
```

This route uses the SP to call Fabric MCP directly and `FoundryChatClient` for
model inference. It does not use the Foundry connection or a toolbox. The SP
needs both model-invocation permission and access to the Fabric data sources.

Set `ALLOWED_TOOLS` to a JSON array of exact names from the diagnostic:

```bash
ALLOWED_TOOLS='["DataAgent_DA_DataAgent_WH"]'
```

## 4. Create Toolbox in Foundry

```bash
# Publish a toolbox version holding the Fabric IQ tool
python create_fabric_iq_toolbox.py

# See what is already published
python create_fabric_iq_toolbox.py --list
```

## 5. Local agent calling Foundry Toolbox

```bash
# Run a local agent against the latest published version
python local_fabriciq_toolbox_agent.py

# Ask something else, or pin an older version
python local_fabriciq_toolbox_agent.py --query "how many total trips are there"
python local_fabriciq_toolbox_agent.py --toolbox-version 1
```

## 6. Prompt agent calling Foundry Toolbox

```bash
# Create Fabric IQ prompt agent with SP in use
python create_fabric_iq_prompt_agent.py

# Run Fabric IQ prompt agent with SP in use
python run_fabric_iq_prompt_agent.py
```

