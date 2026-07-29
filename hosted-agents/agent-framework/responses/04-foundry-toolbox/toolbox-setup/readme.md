

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

export AZD_ENV_NAME="toolbox-agent-dev"
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

azd env set AZURE_SUBSCRIPTION_ID "$SUBSCRIPTION_ID"
azd env set AZURE_TENANT_ID "$TENANT_ID"
azd env set FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT"
azd env set FOUNDRY_PROJECT_ID "$FOUNDRY_PROJECT_ID"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME"
azd env set FOUNDRY_MCP_SERVER_URL "$FOUNDRY_MCP_SERVER_URL"

azd ai connection create foundry-mcp-conn \
  --kind remote-tool \
  --target "$FOUNDRY_MCP_SERVER_URL" \
  --auth-type project-managed-identity \
  --audience "$FOUNDRY_MCP_SERVER_URL" \
  -p "$FOUNDRY_PROJECT_ENDPOINT"

export TOOLBOX_NAME="toolbox_basic"
export USE_EXISTING_FOUNDRY_MCP_CONNECTION=true
export FOUNDRY_MCP_CONNECTION_NAME="foundry-mcp-conn"
export CREATE_FOUNDRY_MCP_CONNECTION=false

./create-foundry-toolbox-rest.sh
```


## test the toolbox endpoint

```
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

chmod +x test_toolbox_endpoint.sh

# before running this, cross check if TOOLBOX_ENDPOINT is already updated in .env; 
## otherwise, update .env first and export it
./test_toolbox_endpoint.sh "$TOOLBOX_ENDPOINT"
```

