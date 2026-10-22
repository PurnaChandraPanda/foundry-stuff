# Hosted agent using the admin-connected Claude model

This sample uses Agent Framework's `FoundryChatClient` through the Foundry project, not a direct APIM client or the native Anthropic client.

```text
Caller
  -> Hosted agent's /responses endpoint
  -> Agent Framework agent running in the container
  -> Foundry project /openai/v1/responses, model=Model-API/claude-byom
  -> Admin-connected model
  -> APIM Unified API /llm/v1/chat/completions
  -> Foundry Claude /anthropic/v1/messages
```

From the hosted agent, the model is selected directly on the project-backed client. The existing APIM policy removing `top_p` for `claude-byom` remains in place.

## Configuration

Use the existing adjacent `.env` file or set these runtime environment variables:

```text
PROJECT_ENDPOINT=<your existing Foundry project endpoint>
BYOM_MODEL=Model-API/claude-byom
```

The sample loads `.env` relative to the entry point, regardless of the current
working directory. Environment variables take precedence over that file.
No APIM subscription key or Claude resource key is needed in this application:
the existing admin-connected model retains the gateway authentication settings.

## Local testing

From this directory, using your existing Python environment:

```bash
# Be in hosted agent directory if not already
cd hosted-agent-unified-byom

# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/claude-unified-byom/.env
set +a

az login

# run local server with hosted agent
python ./src/claude-unified-byom/main.py
```

This runs the same agent and model client used by the HTTP host, but does not start
the server. Local authentication uses `DefaultAzureCredential`, for example your
existing Azure CLI login. The signed-in identity must have project access.

To start the local Responses host instead:

```powershell
python .\main.py --port 8088
```

From another bash terminal:

```bash
## start request with a conversation id
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"conversation": {"id": "alex-return-121"}, "input": "hi"}'
```

## Get the azure.yaml ready for dev/ test

- Prepare the azure.yaml (follow this even if same file already exists).
- Update the azure.yaml - use existing Foundry project and model deployment.

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/claude-unified-byom/.env
set +a

# set the azd ai project
azd ai project set "$FOUNDRY_PROJECT_ENDPOINT"

# Set the env name for azd agent to follow
export AZD_ENV_NAME="claudebyom-agent-dev"

# remove existing azure.yaml
rm -rf azure.yaml

# azd will will package local code and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-claudebyom-responses \
  -e "$AZD_ENV_NAME" \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --src ./src/claude-unified-byom \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# select or create the env
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

# Read key-values already set at azd env level
azd env get-values

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $FOUNDRY_PROJECT_ENDPOINT|endpoint: \${FOUNDRY_PROJECT_ENDPOINT}|" azure.yaml

# Set the azd environment for BYOM_MODEL
azd env set BYOM_MODEL "$BYOM_MODEL"

# Manually modify the generated azure.yaml to include required environment variables after the `container.resources` section (if required)
env:
  BYOM_MODEL: ${BYOM_MODEL}

# doctor validation
azd ai agent doctor --local-only
```

## Deploy the hosted agent

- Be sure, you are in the project directory.
- Deploy the agent to Microsoft Foundry (from the project directory).

```bash
azd auth login
azd deploy -e "$ENV_NAME"
```

## Invoke the deployed hosted agent

```bash
# verify agent is running
azd ai agent show agent-claudebyom-responses

# test the deployed agent
azd ai agent invoke agent-claudebyom-responses "Hi"

# view session verbose logs
azd ai agent monitor --follow
```

## References

- [Foundry hosted agents](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent)
- [Admin-connected models / BYOM](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/ai-gateway)
