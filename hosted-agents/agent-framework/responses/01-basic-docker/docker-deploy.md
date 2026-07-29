## Agent run in local code
- Clone samples repo - https://github.com/microsoft-foundry/foundry-samples.git.
- In local, navigate to directory - `hosted-agents/agent-framework/responses/01-basic-docker`.

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
- Update the `azure.yaml` - use existing Foundry project and model deployment.

- Prepare the azure.yaml (follow this even if same file already exists)

```bash
# Load .env into current bash session
set -a
source src/agent-framework-agent-basicd-responses/.env
set +a

# Run azd init
azd ai agent init \
  --no-prompt --force \
  --agent-name agent-framework-agent-basicd-responses \
  -e basicd-agent-dev \
  --project-id "$FOUNDRY_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/agent-framework-agent-basic-responses \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
sed -i "s|endpoint: $FOUNDRY_PROJECT_ENDPOINT|endpoint: \${FOUNDRY_PROJECT_ENDPOINT}|" azure.yaml

azd ai agent doctor --local-only
```

(OR)

```powershell
# Load .env into current PowerShell session
Get-Content .\src\agent-framework-agent-basic-responses\.env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $value
    }
}

# Run azd init
azd ai agent init `
  --no-prompt --force `
  --agent-name agent-framework-agent-basic-responses `
  -e basic-agent-dev `
  --project-id "$env:FOUNDRY_PROJECT_ID" `
  --model-deployment "$env:AZURE_AI_MODEL_DEPLOYMENT_NAME" `
  --src .\src\agent-framework-agent-basic-responses `
  --deploy-mode code `
  --runtime python_3_13 `
  --entry-point main.py

# Replace hardcoded endpoint with env placeholder in `azure.yaml`
(Get-Content .\azure.yaml) | ForEach-Object { if ($_ -match '^(\s*)endpoint:\s*') { "$($Matches[1])endpoint: `${FOUNDRY_PROJECT_ENDPOINT}" } else { $_ } } | Set-Content .\azure.yaml
```

- Run the agent locally

```bash
set -a
source src/agent-framework-agent-basic-responses/.env
set +a

azd ai agent run
```

(OR)

```powershell
Get-Content .\src\agent-framework-agent-basic-responses\.env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $value
    }
}

azd ai agent run
```


The agent host will start on `http://localhost:8088`.

- You would find a localhost 8087 port browser page opened with chat interface, where same conversation testing activities can be carried too.

- Test the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "Hi"
```

## Deploy the hosted agent

- Once tested agent locally, deploy to Microsoft Foundry.

```bash
set -a
source src/agent-framework-agent-basic-responses/.env
set +a

azd deploy
```

(OR)

```powershell
Get-Content .\src\agent-framework-agent-basic-responses\.env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $value
    }
}

azd deploy
```

- Invoke the deployed agent

```bash
# verify agent is running
azd ai agent show agent-framework-agent-1basic-responses

# test the deployed agent
azd ai agent invoke agent-framework-agent-1basic-responses "Hi"

# view session verbose logs
azd ai agent monitor --follow
```

(OR)

```powershell
# verify agent is running
azd ai agent show agent-framework-agent-basic-responses

# test the deployed agent
azd ai agent invoke agent-framework-agent-basic-responses "Hi"

# view session verbose logs
azd ai agent monitor --follow
```

- After deployment, invoke the agent in the Agent Playground and stream live logs from the **Log Stream**. Navigate to **Traces** tab and watch the sequential execution happened in specification conversation session.

