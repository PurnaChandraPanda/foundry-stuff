## Agent run in local code
- Clone samples repo - https://github.com/microsoft-foundry/foundry-samples.git.
- In local, navigate to directory - `hosted-agents/agent-framework/responses/01-basic-dockerf`.

- Navigate to env file: `src/agent-framework-agent-basic-responses/.env`. Update the enviornment key-value pair details.

```
# ARM resource id till foundry project level
FOUNDRY_PROJECT_ID=""
# Foundry project endpoint
FOUNDRY_PROJECT_ENDPOINT="https://{foundry-name}.services.ai.azure.com/api/projects/{project-name}"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME=""
```

- Validate agent code runs fine (it can be developed using any sdk)

```
python src/agent-framework-agent-basic-responses/main.py
```

- Test the local agent hosted code to see if everything is fine

```
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{ "input": "Hi" }'
```

(OR)

```bash
azd ai agent invoke --local "Hi"
```

(same in bash or powershell)

## Install azd if not already

```
# install azd
winget install microsoft.azd

# install azd ai agents extension
azd ext install azure.ai.agents

# list the installed azd extensions
azd extension list --installed

# upgrade the azd ai agents extension if already installed
azd extension upgrade azure.ai.agents
```

```
azd auth login
```

## Get the azure.yaml ready for dev/ test

- Prepare the azure.yaml (follow this even if same file already exists).
- Update the `azure.yaml` - use existing Foundry project and model deployment.

```bash
# Load .env into current bash session
set -a
source src/agent-framework-agent-basic-responses/.env
set +a

# Check if any of env key-value pairs could not be read
: "${FOUNDRY_PROJECT_ID:?FOUNDRY_PROJECT_ID is missing}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?AZURE_AI_MODEL_DEPLOYMENT_NAME is missing}"
: "${AZURE_CONTAINER_REGISTRY_NAME:?AZURE_CONTAINER_REGISTRY_NAME is missing}"
: "${AZURE_CONTAINER_REGISTRY_ENDPOINT:?AZURE_CONTAINER_REGISTRY_ENDPOINT is missing}"

# Build image and store in ACR - avoiding local docker need (for fresh run: go for different version)
IMAGE_NAME="agent-framework-agent-basicdf-responses"
IMAGE_TAG="v2"
IMAGE="$AZURE_CONTAINER_REGISTRY_ENDPOINT/$IMAGE_NAME:$IMAGE_TAG"

# will look for Dockerfile in the path specified in build command
az acr build \
  --registry "$AZURE_CONTAINER_REGISTRY_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  ./src/agent-framework-agent-basic-responses

# Set the env name for azd agent to follow
ENV_NAME="basicdf-agent-dev"

# Option 2: azd will read the ACR image and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-framework-agent-basicdf-responses \
  -e "$ENV_NAME" \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --image "$IMAGE"

# For image specified, it seems to create a new folder that is passed in `--agent-name`
cd agent-framework-agent-basicdf-responses

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $FOUNDRY_PROJECT_ENDPOINT|endpoint: \${FOUNDRY_PROJECT_ENDPOINT}|" azure.yaml

# Replace hardcoded image with env placeholder in `azure.yaml`
sed -i "s|image: $IMAGE|image: \${IMAGE}|" azure.yaml

# Manually modify the generated azure.yaml to include required environment variables (if required)

azd ai agent doctor --local-only
```

## Deploy the hosted agent

- Generated azure.yaml won't have env var key-value pairs generated. Modify env vars section if needed.
- Other practice could be let your docker image itself having the .env - to read from.

- Navigate back to project directory.

```bash
cd ..
```

- Pull the image first that is recently built (will use logged in userid for AcrPull)

```bash
az acr login --name "$AZURE_CONTAINER_REGISTRY_NAME"
docker pull "$IMAGE"
```

- Deploy the agent to Microsoft Foundry (from the project directory).

```bash
azd -C ./agent-framework-agent-basicdf-responses deploy \
  agent-framework-agent-basicdf-responses \
  --from-package "$IMAGE" \
  -e "$ENV_NAME"
```

- Invoke the deployed agent

```bash
# verify agent is running
azd -C ./agent-framework-agent-basicdf-responses ai agent show agent-framework-agent-basicdf-responses

# test the deployed agent
azd -C ./agent-framework-agent-basicdf-responses ai agent invoke agent-framework-agent-basicdf-responses "Hi"

# view session verbose logs
azd -C ./agent-framework-agent-basicdf-responses ai agent monitor --follow
```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

