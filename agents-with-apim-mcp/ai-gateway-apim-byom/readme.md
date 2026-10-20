# APIM BYOM: Direct Calls vs. Agent AI Gateway Calls

On APIM service instance side, add `API`. Add `+ Foundry API` -> `foundry instance` -> `pick openai/v1` -> [Next] ... -> [Create].

## Direct APIM call

```text
Local Python -> APIM -> Model backend
```

- Rename the `.env.example` file as `.env`. Update all key:value pairs in it.
- `connect-byom-apim.py` reads `APIM_API_URL`, `APIM_MODEL`,
`APIM_SUBSCRIPTION_KEY_HEADER`, `APIM_SUBSCRIPTION_KEY`, and
`API_TIMEOUT_SECONDS` from `.env`.

- Set `APIM_API_URL` to `https://<apim-name>.azure-api.net/<api-suffix>`.
- The script appends `/openai/v1/chat/completions` and `/openai/v1/responses`.
- Both clients use the subscription header; the SDK check suppresses its default bearer header and disables retries BYOM model.

```bash
# HTTPX request only
python connect-byom-apim.py --client httpx

# OpenAI SDK only
python connect-byom-apim.py --client openai

# Compare HTTPX and OpenAI SDK (four requests)
python connect-byom-apim.py --client both

# Existing HTTPX behavior remains the default
python connect-byom-apim.py
```

## Agent call through an AI gateway model

```text
Local Python -> Foundry project -> Prompt agent -> Model gateway -> APIM -> Model backend
```

Register a connection under Foundry **Admin-connected models**:

| Setting | OpenAI-compatible v1 configuration |
| --- | --- |
| Base URL | `https://<apim-name>.azure-api.net/<api-suffix>/openai/v1` |
| Model name | Model/deployment name accepted by APIM |
| Include deployment name in URL path | Disabled |
| Authentication | Header and credentials expected by APIM |

Foundry appends the operation route, such as `chat/completions`.
Registration alone does not prove inference works.

Configure `.env`:

```dotenv
PROJECT_ENDPOINT=https://<foundry-name>.services.ai.azure.com/api/projects/<project-name>
BYOM_MODEL=<connection-name>/<model-name>
PROMPT_AGENT_NAME=<agent-name>
```

- `create_prompt_agent.py` creates an agent version using `BYOM_MODEL`.
- `run_prompt_agent.py` invokes the saved agent through the project's Responses API using `agent_reference`. 
- Both use `DefaultAzureCredential` with an identity
authorized for the project.

```bash
# If using Azure CLI credentials:
az login

# Create a version, then invoke the saved agent:
python create_prompt_agent.py
python run_prompt_agent.py
```

Changing local `BYOM_MODEL` does not update an existing agent version.
Changing local APIM settings does not update the Foundry connection.

## Troubleshooting Tips

- **Direct call works, agent fails:** compare the saved agent model reference, connection URL, authentication, and Foundry-to-APIM network access. The agent does not use your PC's network path or direct-call credentials.
- **404 / nested `DeploymentNotFound`:** inspect the actual route. Here, `/base1/chat/completions` returned 404 while `/base1/openai/v1/chat/completions` worked. Agent calls succeeded after the connection base URL was updated to include `/openai/v1`.
- **`BackendConnectionFailure` / `No such host is known`:** check APIM's effective backend hostname and private DNS. APIM's inbound private endpoint alone does not provide outbound VNet access to a private backend.
- **Correlation:** the diagnostic script reports an exposed `x-apim-request-id` or an error body's server-provided `activityId`. It generates no client IDs. To expose the gateway ID, set `x-apim-request-id` to `@(context.RequestId.ToString())` in APIM's existing outbound and on-error policies.

Reference: [Foundry BYOM gateway configuration](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/ai-gateway).
