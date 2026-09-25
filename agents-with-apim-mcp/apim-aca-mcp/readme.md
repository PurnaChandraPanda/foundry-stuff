This sample is talking about bringing up MCP server proxy on APIM for existing ACA hosted MCP server (it can be considered for any internet exposed mcp server). Once MCP server is brought up, how the foundry or local agents side of interaction is going to work for destination mcp server.

## Bring up APIM instance with MCP
- Imagine the MCP server is already hosted in some ACA server and its URI is exposed.
- On private APIM, add [+ MCP servers]. But, same can be followed for public APIM too.

Steps to bring up the APIM API instance where it has to proxy in existing MCP server:
1. Azure Portal → API Management instance.
2. Left menu → APIs → MCP Servers → + Create MCP server.
3. Choose `Expose an existing MCP server`.
4. Backend MCP server:
    - MCP server base URL: https://xxxxxxxxxxxxx.eastus.azurecontainerapps.io/mcp.
5. New MCP server:
    - Name: e.g. aca-mcp
    - Base path: e.g. aca-mcp (route prefix)
    - Description: optional.
6. Products: optionally associate one (controls subscription/access).
7. `Create`. APIM discovers the backend's tools and lists the server; the Server URL column shows your new endpoint.

- Bring up the .env with following details. Follow `.env.example` for reference.

```bash
# Foundry resource details
AZURE_AI_PROJECT_ENDPOINT="https://{account}.services.ai.azure.com/api/projects/{project}"
AZURE_AI_PROJECT_ID="/subscriptions/-----------------------------/resourceGroups/{resourceGroup}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-xx"

# APIM connection details
APIM_SUBSCRIPTION_KEY="-------------------------"
APIM_SUBSCRIPTION_KEY_HEADER="api-key"

# APIM MCP server/ tools details
APIM_MCP_URL="https://{apim}.azure-api.net/{mcpPath}"
APIM_MCP_SERVER_LABEL="apim-aca-mcp"
APIM_ALLOWED_TOOLS="greet_user,add"

# APIM MCP connection name
APIM_MCP_CONNECTION_NAME="apim-aca-mcp-connection"

# Prompt agent name
APIM_PROMPT_AGENT_NAME="private-apim-aca-prompt"

# Tenant of the subscription containing the Foundry resource.
AZURE_TENANT_ID="16-------------------------------d3"
```

- Confirm the APIM MCP server exposes tools.

```bash
python diagnose_mcp.py
```

Output for reference example:
```text
Initialized: My Tools Server 1.26.0
  add
  subtract
  multiply
  divide
  greet_user
Discovered 5 tools. No tools were executed.
```

## Consume the APIM wrapped MCP server

- Run `agent-framework` based local agent in PC.

```bash
python local_agent.py --query "Use greet_user to greet the user named John Doe in a friendly style."
```

- Create MCP connection

```bash
# Git Bash on Windows
export MSYS_NO_PATHCONV=1

../create_mcp_connection.sh apim-aca-mcp
```

- Create prompt agent

```bash
python create_prompt_agent.py
```

- Run prompt agent

```bash
python run_prompt_agent.py --query "Use greet_user to greet the user named John Doe in a friendly style."
```

