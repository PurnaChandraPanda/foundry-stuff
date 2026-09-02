Following doc https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric?pivots=python,

- Create a Foundry prompt agent with Fabric data agent tool: `create_fabric_prompt_agent.py`
- Run that created agent: `run_fabric_prompt_agent.py`
- Agent Framework local agent sample: `fabric_local_agent.py`
- Troubleshoot the Fabric wiring: `diagnose_fabric_connection.py`
- Foundry **hosted** agent (Responses protocol): [`hosted-agent/`](./hosted-agent/readme.md)

Use the active venv if it exists, and ensure dependencies are proper.

```bash
pip install -r requirements.txt
```

## Prerequisite: the Fabric connection must exist first

**These scripts do not create the Fabric connection.** They only look it up, by
name (`FABRIC_CONNECTION_NAME`). The
connection must already exist in the Foundry project before you create or run
any agent.

You also need a **published** Fabric data agent. Copy its `workspace_id` and
`artifact_id` from the data agent URL:

```
.../groups/<workspace_id>/aiskills/<artifact_id>...
```

## Configuration

Set the following environment variables before creating or running the samples:

```bash
export AZURE_AI_PROJECT_ID="/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
export AZURE_AI_PROJECT_ENDPOINT="https://<resource>.ai.azure.com/api/projects/<project_name>"
export FABRIC_CONNECTION_NAME="my-fabric-connection"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
export FABRIC_AGENT_NAME="MyFabricAgent"

# optional, used only by diagnose_fabric_connection.py
export FABRIC_WORKSPACE_ID="<workspace_id GUID>"
export FABRIC_ARTIFACT_ID="<artifact_id GUID>"
```

### Option A - create the connection in the Foundry portal (documented path)
1. Open your project in the Foundry portal.
2. Select **Manage** > **Project details** > **Connected resources**.
3. Create a connection of type **Microsoft Fabric**.
4. Enter the `workspace_id` and `artifact_id` values.
5. Save, then copy the connection **ID**.

### Option B - create the connection with the helper script

`create_fabric_connection.sh` reads your `.env`, derives the account and project
names from `AZURE_AI_PROJECT_ENDPOINT`, and looks up the resource group
automatically:

```bash
# Set the sys pathconv for git bash  - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

# create fabric connection in foundry
./create_fabric_connection.sh
```

Re-running it updates the existing connection. To remove it:

```bash
./create_fabric_connection.sh --delete
```

> **The credential key names must use hyphens: `workspace-id` and
> `artifact-id`.** This is what the Foundry portal sends. Underscores produce a
> connection that looks correct from every API - it is listed by
> `project.connections.list()` and `listSecrets` returns the keys - but every
> agent run fails with `Workspace ID and Artifact ID are required from
> connection details or additional_properties for Fabric operations`. The
> portal's own request body is:
>
> ```json
> "credentials": { "keys": {
>   "workspace-id": "<workspace_id GUID>",
>   "artifact-id":  "<artifact_id GUID>"
> } },
> "metadata": { "type": "fabric_dataagent_preview" }
> ```

There is no create API in the SDK - `ConnectionsOperations` exposes only
`get`, `get_default`, and `list` - so `az rest` is the only scripted route.

Diagnose the fabric connection

```bash
python diagnose_fabric_connection.py
```

## Create / run agents

Create the agent once:

```bash
python create_fabric_prompt_agent.py
```

Then run it:

```bash
python run_fabric_prompt_agent.py
```

Local Agent Framework sample:

```bash
python fabric_local_agent.py
```

## Foundry hosted agent

To deploy this agent as a Foundry hosted agent (Responses protocol), see
[`hosted-agent/`](./hosted-agent/readme.md). All of its artifacts - agent code,
`azure.yaml`, `.agentignore`, and the azd deploy runbook - live in that folder.

## Troubleshooting

If a run fails with `Create run failed: ... "Stage configuration not found."`, run:

```bash
python diagnose_fabric_connection.py
```

The Fabric tool uses identity passthrough (On-Behalf-Of), so the signed-in user
must be able to read the *published* Fabric data agent. The diagnostic checks:

1. the Foundry project connection resolves
2. the signed-in user can reach the Fabric workspace and artifact
3. the data agent actually has a **published** stage, not just a draft

Check 3 inspects the item definition. A data agent that was never published
contains only `Files/Config/draft/...` parts and no `Files/Config/published/...`
part, which is precisely what triggers `Stage configuration not found.`

Neither cause is fixable from this code. Both are fixed in Microsoft Fabric.
