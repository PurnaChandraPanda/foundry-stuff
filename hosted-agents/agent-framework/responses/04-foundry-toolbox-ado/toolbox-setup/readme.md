

## pre-requisite
- install jq if not already in git bash
```
winget install jqlang.jq

jq --version
```


```
cd toolbox-setup
```

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

chmod +x create-foundry-toolbox-rest.sh

export TENANT_ID="16b3c013-d300-468d-ac64-7eda0820b6d3"
export SUBSCRIPTION_ID="6977e295-0d7c-4557-8e0b-26e2f6532103"

az login
az account set --subscription "$SUBSCRIPTION_ID"

set -a
source ../src/agent-framework-agent-with-foundry-toolbox-responses/.env
set +a

azd ai project set "$FOUNDRY_PROJECT_ENDPOINT"

export AZD_ENV_NAME="toolbox-ado-dev"
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

azd env set AZURE_SUBSCRIPTION_ID "$SUBSCRIPTION_ID"
azd env set AZURE_TENANT_ID "$TENANT_ID"
azd env set FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT"
azd env set FOUNDRY_PROJECT_ID "$FOUNDRY_PROJECT_ID"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME"

# ADO's Entra resource ID
# export ADO_AUDIENCE="https://mcp.dev.azure.com"
export ADO_AUDIENCE="api://2a72489c-aab2-4b65-b93a-a91edccf33b8"
export ADO_MCP_SERVER_URL="https://mcp.dev.azure.com/cssdevs"

azd ai connection create ado-mcp-conn \
  --kind remote-tool \
  --target "$ADO_MCP_SERVER_URL" \
  --auth-type user-entra-token \
  --audience "$ADO_AUDIENCE" \
  -p "$FOUNDRY_PROJECT_ENDPOINT"


# Create the toolbox with ADO MCP tool
export TOOLBOX_NAME="toolbox_ado"
export FOUNDRY_MCP_SERVER_URL="$ADO_MCP_SERVER_URL"
export USE_EXISTING_FOUNDRY_MCP_CONNECTION=true
export FOUNDRY_MCP_CONNECTION_NAME="ado-mcp-conn"
export CREATE_FOUNDRY_MCP_CONNECTION=false

./create-foundry-toolbox-rest.sh
```


## test the toolbox endpoint

```
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

chmod +x test_toolbox_endpoint.sh

# export toolbox endpoint
export TOOLBOX_ENDPOINT='https://foundryeus2tst.services.ai.azure.com/api/projects/proj-default/toolboxes/toolbox_ado/mcp?api-version=v1'

# before running this, cross check if TOOLBOX_ENDPOINT is already updated in .env; 
## otherwise, update .env first and export it
./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"

TOKEN_SCOPE="https://ai.azure.com" ./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"
TOKEN_SCOPE="https://mcp.dev.azure.com" ./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"
TOKEN_SCOPE="https://mcp.ai.azure.com" ./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"
TOKEN_SCOPE="api://2a72489c-aab2-4b65-b93a-a91edccf33b8" ./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"

# local validation for ado mcp
ADO_TOKEN=$(az account get-access-token --resource https://mcp.dev.azure.com --query accessToken -o tsv)

curl -i -X POST "https://mcp.dev.azure.com/cssdevs" \
  -H "Authorization: Bearer $ADO_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```





