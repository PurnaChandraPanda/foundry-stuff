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
- Now, navigate into directory - `hosted-agents/agent-framework/responses/12-foundry-skills`. 

- Navigate to env file: `src/agent-framework-agent-foundry-skills-responses/.env` (create if not already). Update the enviornment key-value pair details.

```
# ARM resource id till foundry project level
FOUNDRY_PROJECT_ID=""
# Foundry project endpoint
FOUNDRY_PROJECT_ENDPOINT="https://{foundry-name}.services.ai.azure.com/api/projects/{project-name}"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME=""

# Comma-separated list of Foundry skill names to download at startup.
SKILL_NAMES="support-style,escalation-policy"
# Hosted deployments load packaged skills so startup does not wait on a network download.
SKILL_SOURCE="bundled"
```

- Load .env into current bash session and read/ write azd env values

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/agent-framework-agent-foundry-skills-responses/.env
set +a
```

- Major code modification on the `provision_skills.py` file - use `create_from_files()` API to upload the foundry skill.

```python
            imported = await project.beta.skills.create_from_files(
                name=name,
                content=CreateSkillVersionFromFilesBody(
                    files=[(f"{name}.zip", _zip_skill_md(skill_md), "application/zip")],
                    default=True,
                ),
            )
            print(
                f"  Imported skill '{imported.name}' "
                f"(skill_id={imported.skill_id}, version={imported.version}, version_id={imported.id})."
            )
```

- Provision the skills in foundry

```bash
az login

python src/agent-framework-agent-foundry-skills-responses/provision_skills.py
```

- Validate agent code runs fine (it can be developed using any sdk)

The downloaded skills are stored under `foundry-skills/downloaded_skills` in the operating system's temporary directory. Hosted-agent deployments mount `/app` read-only, so runtime downloads must not be written next to `main.py`.

```bash
python src/agent-framework-agent-foundry-skills-responses/main.py
```

- Test the local agent hosted code to see if everything is fine (open another terminal)

```bash

## 1) start request with a conversation id - for order return
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"conversation": {"id": "alex-return-121"}, "input": "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."}'

## 1) grab the mcpr_** approval ID to continue
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "alex-return-121"},
    "input": [
      {
        "type": "mcp_approval_response",
        "approval_request_id": "mcpr_e30f1aa17cff4e7200t31UuvlsRro4jnhZieTFdgywgydbSKiJ",
        "approve": true
      }
    ]
  }'

## 2) start request with a conversation id - for order refund
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"conversation": {"id": "alex-return-123"}, "input": "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."}'

## 2) grab the mcpr_** approval ID to continue
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "alex-return-123"},
    "input": [
      {
        "type": "mcp_approval_response",
        "approval_request_id": "mcpr_faf46ef3f2213bc600Hs5VoDG14114c761pSMXASqKBa1OCz96",
        "approve": true
      }
    ]
  }'

## 2) grab the mcpr_** approval ID to continue
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "conversation": {"id": "alex-return-123"},
    "input": [
      {
        "type": "mcp_approval_response",
        "approval_request_id": "mcpr_c1deca412b6e3e0300dsEAv38it6T5J7GiiDqjiY8epdScv5yB",
        "approve": true
      }
    ]
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
source ./src/agent-framework-agent-foundry-skills-responses/.env
set +a

# Check if any of env key-value pairs could not be read
: "${FOUNDRY_PROJECT_ID:?FOUNDRY_PROJECT_ID is missing}"
: "${FOUNDRY_PROJECT_ENDPOINT:?FOUNDRY_PROJECT_ENDPOINT is missing}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?AZURE_AI_MODEL_DEPLOYMENT_NAME is missing}"
: "${SKILL_NAMES:?SKILL_NAMES is missing}"
: "${SKILL_SOURCE:?SKILL_SOURCE is missing}"


# set the azd ai project
azd ai project set "$FOUNDRY_PROJECT_ENDPOINT"

# Set the env name for azd agent to follow
export AZD_ENV_NAME="fskills-agent-dev"

# remove existing azure.yaml
rm -rf azure.yaml

# azd will will package local code and try agent init
# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-framework-agent-foundry-skills-responses \
  -e "$AZD_ENV_NAME" \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/agent-framework-agent-foundry-skills-responses \
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
env:
  AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  SKILL_NAMES: ${SKILL_NAMES}
  SKILL_SOURCE: ${SKILL_SOURCE}

# # Set the environment variable for azd project scope
azd env set SKILL_NAMES "$SKILL_NAMES" -e "$AZD_ENV_NAME"
azd env set SKILL_SOURCE "$SKILL_SOURCE" -e "$AZD_ENV_NAME"

# Validate environment variable is properly set in azd project scope
azd env get-value SKILL_NAMES -e "$AZD_ENV_NAME"

# doctor validation
azd ai agent doctor --local-only
```

- Sample azure.yaml with remote_build

```
# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

name: 12-foundry-skills
services:
    agent-framework-agent-foundry-skills-responses:
        project: ./src/agent-framework-agent-foundry-skills-responses
        host: azure.ai.agent
        language: python
        uses:
            - proj-default
        env:
            AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
            SKILL_NAMES: ${SKILL_NAMES}
            SKILL_SOURCE: ${SKILL_SOURCE}
        codeConfiguration:
            dependencyResolution: remote_build
            entryPoint: main.py
            runtime: python_3_13
        container:
            resources:
                cpu: "0.5"
                memory: 1Gi
        kind: hosted
        name: agent-framework-agent-foundry-skills-responses
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

azd ai agent invoke --local "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."
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
azd ai agent show agent-framework-agent-foundry-skills-responses

# test the deployed agent
azd ai agent invoke agent-framework-agent-foundry-skills-responses "Hi"

azd ai agent invoke agent-framework-agent-foundry-skills-responses "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."

azd ai agent invoke agent-framework-agent-foundry-skills-responses "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."

## With azd, not possible to follow approval control. 
## Follow foundry playground alone to play with such approve/ deny requests kind.
## Otherwise, need to use curl for public agent endpoint host like its being done for localhost.

# view session verbose logs
azd ai agent monitor --follow

# view session verbose logs for a session id
azd ai agent monitor --follow --session-id fa5d7b17722d259244fbd8430c5544ede3801ba07773ef9fb6744771d1f7526

```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

## Deploy prompt agents

- Follow the steps in [./tests/prompt_agents_skill/](./tests/prompt_agents_skill/) for foundry skills interaction in prompt agents.
