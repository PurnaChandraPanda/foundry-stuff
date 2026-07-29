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
# login with current user id
azd auth login
```


## Agent run in local code
- Clone samples repo - https://github.com/microsoft-foundry/foundry-samples.git.

- In local, navigate to directory - `hosted-agents/agent-framework/responses`.
- Copy/ Paste the folder `01-basic` and rename to `01-basic-envdockerf`.
- Now, navigate into directory - `hosted-agents/agent-framework/responses/01-basic-envdockerf`. 

- Navigate to env file: `src/agent-framework-agent-basic-responses/.env` (create if not already). Update the enviornment key-value pair details.

```
# ARM resource id till foundry project level
FOUNDRY_PROJECT_ID=""
# Foundry project endpoint
FOUNDRY_PROJECT_ENDPOINT="https://{foundry-name}.services.ai.azure.com/api/projects/{project-name}"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME=""

# For ACR
AZURE_CONTAINER_REGISTRY_NAME={acr-name}
AZURE_CONTAINER_REGISTRY_ENDPOINT={acr-name}.azurecr.io
```

- Validate agent code runs fine (it can be developed using any sdk)

```
python src/agent-framework-agent-basic-responses/main.py
```

- Test the local agent hosted code to see if everything is fine (open another terminal)

```
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{ "input": "Hi" }'
```

(same in bash or powershell)


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
IMAGE_NAME="agent-framework-agent-basicedf-responses"
IMAGE_TAG="v3"
IMAGE="$AZURE_CONTAINER_REGISTRY_ENDPOINT/$IMAGE_NAME:$IMAGE_TAG"

# will look for Dockerfile in the path specified in build command
az acr build \
  --registry "$AZURE_CONTAINER_REGISTRY_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  ./src/agent-framework-agent-basic-responses

# Set the env name for azd agent to follow
ENV_NAME="basicedf-agent-dev"

# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

# Option 2: azd will read the ACR image and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-framework-agent-basicedf-responses \
  -e "$ENV_NAME" \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --image "$IMAGE" \
  --protocol responses

# For image specified, it seems to create a new folder that is passed in `--agent-name`
cd agent-framework-agent-basicedf-responses

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $FOUNDRY_PROJECT_ENDPOINT|endpoint: \${FOUNDRY_PROJECT_ENDPOINT}|" azure.yaml

# Replace hardcoded image with env placeholder in `azure.yaml`
sed -i "s|image: $IMAGE|image: \${IMAGE}|" azure.yaml

# Manually modify the generated azure.yaml to include required environment variables after the `container.resources` section (if required)
environmentVariables:
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}

# Set the environment variable for azd project scope
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME" -e "$ENV_NAME"

# Validate environment variable is properly set in azd project scope
azd env get-value AZURE_AI_MODEL_DEPLOYMENT_NAME -e "$ENV_NAME"

# doctor validation
azd ai agent doctor --local-only
```

- Sample azure.yaml with ACR image path mapping

```
# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

name: agent-framework-agent-basicedf-responses
services:
    agent-framework-agent-basicedf-responses:
        project: src/agent-framework-agent-basicedf-responses
        host: azure.ai.agent
        language: docker
        image: ${IMAGE}
        docker:
            remoteBuild: true
        uses:
            - proj-default
        container:
            resources:
                cpu: "0.5"
                memory: 1Gi
        environmentVariables:
            - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
              value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
        description: Hosted container agent using pre-built image
        kind: hosted
        name: agent-framework-agent-basicedf-responses
        protocols:
            - protocol: responses
              version: 2.0.0
    proj-default:
        host: azure.ai.project
        endpoint: ${FOUNDRY_PROJECT_ENDPOINT}
infra:
    provider: microsoft.foundry
```

**Note**: For docker image case, local test can be avoided as there's some authentication challenges noticed. You can authenticate yourself in host machine but not the container instance. The azd has issues too because `src` path mapping need to be modified to point to actual source folder in `azure.yaml`. For this exercise, trying the direct deploy instead.

## Deploy the hosted agent

- Generated azure.yaml won't have env var key-value pairs generated. Modify env vars section if needed.
- Other practice could be let your docker image itself having the .env - to read from (in this case, its not).

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
azd -C ./agent-framework-agent-basicedf-responses deploy \
  agent-framework-agent-basicedf-responses \
  --from-package "$IMAGE" \
  -e "$ENV_NAME"
```

- Invoke the deployed agent

```bash
# verify agent is running
azd -C ./agent-framework-agent-basicedf-responses ai agent show agent-framework-agent-basicedf-responses

# test the deployed agent
azd -C ./agent-framework-agent-basicedf-responses ai agent invoke agent-framework-agent-basicedf-responses "Hi"

# view session verbose logs
azd -C ./agent-framework-agent-basicedf-responses ai agent monitor --follow
```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

