# Public APIM MCP through a toolbox as a Foundry hosted agent

Deploy the MAF toolbox agent as a **Foundry hosted agent** speaking the Responses
protocol. This folder contains a standalone hosted implementation for the
**public** APIM toolbox. For the private route, use
[toolbox-mcp-private/hosted-agent](../../toolbox-mcp-private/hosted-agent/readme.md).

## Prerequisites

Complete the [parent setup](../readme.md) first:

1. Ensure Foundry toolbox execution can reach the public APIM gateway and its
   policies permit the call.
2. Create or reuse the public APIM subscription-key project connection.
3. Publish a reviewed, read-only toolbox and note its exact version:

   ```bash
   cd ..
   python create_toolbox.py --allow-unattended
   # Update APIM_TOOLBOX_VERSION in the parent .env.
   python local_agent.py --query "Your question"
   cd hosted-agent
   ```

The toolbox runs without per-call approval. Do not include write/destructive
tools. The APIM key stays in the **Foundry connection**, not this code or its
environment. A successful local direct call does not prove that
the Foundry toolbox can reach APIM.

Keep using your existing `.maf_venv`. Only if hosted dependencies are missing:

```bash
python -m pip install -r src/private-apim-responses/requirements.txt
```

## How this differs from the local agent

- Uses `DefaultAzureCredential`, so the deployed process uses its platform
  identity rather than relying on the developer's Azure CLI login.
- Always uses `FoundryToolbox`, not direct MCP with a local subscription key.
- Uses the same model instructions and version-pinned toolbox behavior as the
  parent local toolbox agent.
- Is self-contained: it does not import the parent configuration or agent
  factory, because those files are outside the uploaded source folder.
- Resolves configuration and checks the pinned toolbox version at startup.
  A missing version or authorization failure stops startup.
- Passes the MCP tool unconnected to the agent. The connection opens within the
  server's event loop, avoiding a session bound to a temporary loop.

The toolbox metadata check is not a live APIM invocation. Verify a real tool
result and correlate it with APIM logs.

## 1. Configure

From this `hosted-agent` folder:

```bash
cp src/private-apim-responses/.env.example src/private-apim-responses/.env
```

Edit the copied configuration with:

```bash
AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="<model-deployment-name>"
APIM_TOOLBOX_NAME="public-apim-toolbox"
APIM_TOOLBOX_VERSION="<published-version>"
MCP_TIMEOUT_SECONDS="120"
PORT="8088"
```

Do not copy the parent's subscription key into this configuration.
`--local` loads `.env` beside [main.py](./src/private-apim-responses/main.py).
Existing exported variables take precedence, so refresh them after changing
the configuration if you previously sourced it.

## 2. Run the Responses server locally

```bash
python src/public-apim-responses/main.py --local
```

The local server binds to `127.0.0.1:8088` by default. From another Git Bash
terminal:

```bash
curl --fail-with-body http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"conversation":{"id":"apim-local-1"},"input":"Use the configured tool to answer your question"}'
```

This local development endpoint is not an authenticated public service.
Do not expose it through a public tunnel. Foundry handles authentication on the
deployed endpoint; hosted startup binds to `0.0.0.0` as required by the platform.

## 3. Configure azd

[azure.yaml](./azure.yaml) is already provided. Do not delete it or rerun `init`
unless you intend to regenerate the configuration. Use current Azure Developer
CLI with `azd ai` support.

```bash
# Set manually in your Git Bash terminal.
export MSYS_NO_PATHCONV=1  

set -a
source src/public-apim-responses/.env
set +a

azd auth login

# remove old azure.yaml
rm -rf azure.yaml

# set the azd ai project
azd ai project set "$AZURE_AI_PROJECT_ENDPOINT"

# Set the env name for azd agent to follow
export AZD_ENV_NAME="apim-toolbox-public-dev"

# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name public-apim-toolbox-hosted \
  -e "$AZD_ENV_NAME" \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/public-apim-responses \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# select the azd env
azd env select "$AZD_ENV_NAME"

# Only nonsecret settings are deployed.
azd env set AZURE_AI_PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME"
azd env set APIM_TOOLBOX_NAME "$APIM_TOOLBOX_NAME"
azd env set APIM_TOOLBOX_VERSION "$APIM_TOOLBOX_VERSION"
azd env set MCP_TIMEOUT_SECONDS "$MCP_TIMEOUT_SECONDS"

# doctor validation
azd ai agent doctor --local-only
```

# in azure.yaml, apply change for environment variables
```bash
        env:
            AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
            AZURE_AI_PROJECT_ENDPOINT: ${AZURE_AI_PROJECT_ENDPOINT}
            APIM_TOOLBOX_NAME: ${APIM_TOOLBOX_NAME}
            MCP_TIMEOUT_SECONDS: ${MCP_TIMEOUT_SECONDS}
```

The manifest uses source-code deployment with remote dependency build, Python
3.13, and Responses protocol 2.0.0. The entry point is `main.py` relative to
the service's source directory, not the parent sample directory.

If you previously initialized azd in the parent sample folder, its `.azure`
state is not automatically transferred. Configure/select the environment in
this folder before deployment; do not delete unrelated parent state.

## 4. Deploy

```bash
azd deploy public-apim-toolbox-hosted -e "$ENV_NAME"
azd ai agent show public-apim-toolbox-hosted
```

## 5. Invoke and inspect

```bash
azd ai agent invoke public-apim-toolbox-hosted --new-conversation "hi"

# Grab the conv_xxxxx ID and use in following
azd ai agent invoke public-apim-toolbox-hosted --conversation-id conv_xxxxxxxxxxxxxxxxxxxxx "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."

azd ai agent monitor --follow
```
