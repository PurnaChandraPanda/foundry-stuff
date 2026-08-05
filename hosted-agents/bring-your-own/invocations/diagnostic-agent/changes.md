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


## Prepare agent in local
- Clone samples repo - https://github.com/microsoft-foundry/foundry-samples.git.

- Now, navigate into directory - `hosted-agents/bring-your-own/invocations/diagnostic-agent`. 

- Navigate to env file: `src/diagnostic-agent-python-invocations/.env` (create if not already). Update the enviornment key-value pair details.

```
# ARM resource id till foundry project level
AZURE_AI_PROJECT_ID=""
# Foundry project endpoint
AZURE_AI_PROJECT_ENDPOINT="https://{foundry-name}.services.ai.azure.com/api/projects/{project-name}"
# Subscription ID
AZURE_SUBSCRIPTION_ID=""
# Environment name for azd
AZURE_ENV_NAME=""
# Azure location
AZURE_LOCATION=""
```

- Load .env into current bash session and read/ write azd env values

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

# Read the current project env from src folder
set -a
source src/diagnostic-agent-python-invocations/.env
set +a

# Set project endpoint for azd
azd ai project set "$AZURE_AI_PROJECT_ENDPOINT"

# Create azd env, or read if existing
azd env new "$AZURE_ENV_NAME" 2>/dev/null || azd env select "$AZURE_ENV_NAME"

# Set the azd env
azd env set AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
azd env set AZURE_AI_PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"
azd env set AZURE_AI_PROJECT_ID "$AZURE_AI_PROJECT_ID"
azd env set AZURE_LOCATION "$AZURE_LOCATION"
```

- Get the azure.yaml ready

```
# delete existing azure.yaml manually
rm -rf azure.yaml

# azd will will package local code and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name diagnostic-agent-python-invocations \
  -e "$AZURE_ENV_NAME" \
  --protocol invocations \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --src ./src/diagnostic-agent-python-invocations \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# select or create the env
azd env new "$AZURE_ENV_NAME" 2>/dev/null || azd env select "$AZURE_ENV_NAME"

# Read key-values already set at azd env level
azd env get-values

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $AZURE_AI_PROJECT_ENDPOINT|endpoint: \${AZURE_AI_PROJECT_ENDPOINT}|" azure.yaml

# doctor validation
azd ai agent doctor --local-only
```

- Sample azure.yaml with remote_build

```
# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

name: diagnostic-agent
services:
    diagnostic-agent-python-invocations:
        project: ./src/diagnostic-agent-python-invocations
        host: azure.ai.agent
        language: python
        uses:
            - project3738
        codeConfiguration:
            dependencyResolution: remote_build
            entryPoint: main.py
            runtime: python_3_13
        container:
            resources:
                cpu: "0.5"
                memory: 1Gi
        kind: hosted
        name: diagnostic-agent-python-invocations
        protocols:
            - protocol: invocations
              version: 2.0.0
    project3738:
        host: azure.ai.project
        endpoint: ${AZURE_AI_PROJECT_ENDPOINT}
infra:
    provider: microsoft.foundry
```

## Deploy the hosted agent

- Be sure, you are in the project directory.

- Deploy the agent to Microsoft Foundry (from the project directory).

```bash
azd auth login

azd deploy -e "$AZURE_ENV_NAME"
```

- Invoke the deployed agent

```bash
# verify agent is running
azd ai agent show diagnostic-agent-python-invocations

# test the deployed agent
azd ai agent invoke diagnostic-agent-python-invocations '{"message": "Hi"}'

azd ai agent invoke diagnostic-agent-python-invocations '{"hosts":["aifoundry3738.services.ai.azure.com", "aifoundry3738.openai.azure.com", "aifoundry3738.cognitiveservices.azure.com", "aifoundry3738cosmosdb.documents.azure.com", "aifoundry3738storage.blob.core.windows.net", "aifoundry3738search.search.windows.net"],"public_hosts":["https://management.azure.com/metadata/endpoints?api-version=2020-09-01"],"resolvers": ["168.63.129.16"],"record_types": ["A", "AAAA"],"raw_dns": true,"include_container_info": true, "include_env_dump": true,"include_evidence": true,"stream": true,"tcp_timeout_sec": 5,"http_timeout_sec": 10,"dns_timeout_sec": 5}'


# view session verbose logs
azd ai agent monitor --follow
```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

- Review the container side logs that came out as `hosts` input supplied. This is live log that is actually running on docker container in the microVM managed in ADC computes in backend.
