## Install azd if not already

```
# install azd
winget install microsoft.azd

# upgrade azd (if required)
winget upgrade microsoft.azd

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
- Now, navigate into directory - `hosted-agents/agent-framework/responses/07-skills-htl`. 

- Navigate to env file: `src/agent-framework-agent-with-skills-responses/.env` (create if not already). Update the enviornment key-value pair details.

```
# ARM resource id till foundry project level
FOUNDRY_PROJECT_ID=""
# Foundry project endpoint
FOUNDRY_PROJECT_ENDPOINT="https://{foundry-name}.services.ai.azure.com/api/projects/{project-name}"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME=""
```

- Load .env into current bash session and read/ write azd env values

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1
```

- Apply code changes in `main.py` to disable skill approval.

```python
    ## With skills approval enabled, agent will be popped up with approval dialogs \
    ## before executing the travel-guide skill when a user asks for a PDF travel guide, \
    ## city guide, itinerary, or trip-planning document.
    ### load_skill → run_skill_script → final PDF response
    skills_provider = SkillsProvider.from_paths(
        skill_paths=Path(__file__).parent / "skills",
        script_runner=run_local_skill_script,
        disable_load_skill_approval=False,
        disable_read_skill_resource_approval=False,
        disable_run_skill_script_approval=False,
    )
```

- Validate agent code runs fine (it can be developed using any sdk)

```bash
python src/agent-framework-agent-with-skills-responses/main.py
```

- Test the local agent hosted code to see if everything is fine (open another terminal)

```bash
# start request with a conversation id
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "lisbon-guide-1231"},
    "input": "Create a colorful 3-day PDF travel guide for Lisbon focused on food, viewpoints, and neighborhoods."
  }'

# watch for following section of output in the response
## "type":"mcp_approval_request","id":"mcpr_f9bbe209a54a3e7900kWLA8yylS3pWrBlzFijYh4TZDlvspbX1"
# use the mcpr_*** id to approve or deny request 
## if still gives some more mcpr_** id in response, approve/ deny accordingly
## in this sample, will get two mcpr id: 1) load_skill, 2) run_skill_script

# grab the approval request id, approve and continue
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "lisbon-guide-1231"},
    "input": [{
      "type": "mcp_approval_response",
      "approval_request_id": "mcpr_f9bbe209a54a3e7900kWLA8yylS3pWrBlzFijYh4TZDlvspbX1",
      "approve": true
    }]
  }'

curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "lisbon-guide-1231"},
    "input": [{
      "type": "mcp_approval_response",
      "approval_request_id": "mcpr_10db9bf7df40425a00Ntn6HHxnn5ojuZGVpAZaMCWJwobxG8uS",
      "approve": true
    }]
  }'


# grab the approval request id, deny and stop
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "lisbon-guide-1232"},
    "input": [{
      "type": "mcp_approval_response",
      "approval_request_id": "mcpr_5a3fa59e4df83c1f00qnzlUa8LjGZA4yil2HWxbi1xpwTuHSf3",
      "approve": false
    }]
  }'
```


(same in bash or powershell)


## Get the azure.yaml ready for dev/ test

- Prepare the azure.yaml (follow this even if same file already exists).
- Update the `azure.yaml` - use existing Foundry project and model deployment.

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/agent-framework-agent-with-skills-responses/.env
set +a

# Check if any of env key-value pairs could not be read
: "${FOUNDRY_PROJECT_ID:?FOUNDRY_PROJECT_ID is missing}"
: "${FOUNDRY_PROJECT_ENDPOINT:?FOUNDRY_PROJECT_ENDPOINT is missing}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?AZURE_AI_MODEL_DEPLOYMENT_NAME is missing}"


# set the azd ai project
azd ai project set "$FOUNDRY_PROJECT_ENDPOINT"

# Set the env name for azd agent to follow
export AZD_ENV_NAME="skillshtl-agent-dev"

# remove existing azure.yaml
rm -rf azure.yaml

# azd will will package local code and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-framework-agent-htl-skills-responses \
  -e "$AZD_ENV_NAME" \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/agent-framework-agent-with-skills-responses \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# select or create the env
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

# Read key-values already set at azd env level
azd env get-values

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $FOUNDRY_PROJECT_ENDPOINT|endpoint: \${FOUNDRY_PROJECT_ENDPOINT}|" azure.yaml

# Manually modify the generated azure.yaml to include required environment variables after the `container.resources` section (if required)
environmentVariables:
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}

# doctor validation
azd ai agent doctor --local-only
```

- Sample azure.yaml with remote_build

```
# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

name: 07-skills-htl
services:
    agent-framework-agent-htl-skills-responses:
        project: ./src/agent-framework-agent-with-skills-responses
        host: azure.ai.agent
        language: python
        uses:
            - proj-default
        env:
            AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
        codeConfiguration:
            dependencyResolution: remote_build
            entryPoint: main.py
            runtime: python_3_13
        container:
            resources:
                cpu: "0.5"
                memory: 1Gi
        kind: hosted
        name: agent-framework-agent-htl-skills-responses
        protocols:
            - protocol: responses
              version: 2.0.0
    proj-default:
        host: azure.ai.project
        endpoint: ${FOUNDRY_PROJECT_ENDPOINT}
infra:
    provider: microsoft.foundry
```

- Run it locally

```
azd auth login

azd ai agent run
```

The agent host will start on `http://localhost:8088`.

- You would find a localhost 8087 port browser page opened with chat interface, where same conversation testing activities can be carried too.

- Test the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "hi"

azd ai agent invoke --local "Create a colorful 3-day PDF travel guide for Lisbon focused on food, viewpoints, and neighborhoods."
```

**note**: For `azd ai agent invoke`, it won't be possible to continue with approval controls. With Agent Inspector, for some UI bugs, sometimes approval controls are not visible.

## Deploy the hosted agent

- Be sure, you are in the project directory.

- Deploy the agent to Microsoft Foundry (from the project directory).

```bash
az login
azd auth login

azd deploy -e "$AZD_ENV_NAME"
```

- Invoke the deployed agent

```bash
# verify agent is running
azd ai agent show agent-framework-agent-htl-skills-responses

# test the deployed agent
azd ai agent invoke agent-framework-agent-htl-skills-responses "Hi"

azd ai agent invoke agent-framework-agent-htl-skills-responses "Create a colorful 3-day PDF travel guide for Lisbon focused on food, viewpoints, and neighborhoods."

## With azd, not possible to follow approval control. 
## Follow foundry playground alone to play with such approve/ deny requests kind.
## Otherwise, need to use curl for public agent endpoint host like its being done for localhost.

# view session verbose logs
azd ai agent monitor --follow
```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

