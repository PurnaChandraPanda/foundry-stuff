## Claude message from Foundry

```bash
# Basic foundry claude model interaction
python foundry_claude.py

# Foundry claude model interaction with tool call
python foundry_claude_tools.py

# Using agent-framework, Foundry claude model interaction with tool call
python maf_foundry_claude.py
```

## APIM maps to Claude Foundry for messages API

On APIM level, create a new Foundry API. Pick the Foundry account name, set base path. On options, pick "Azure OpenAI" client compatibility option. 

```bash
# Invoke APIM API that points to Fondry claude model messages api
python apim_api_foundry_claude.py

# Using agent-framework, invoke APIM API that points to Fondry claude model messages api
python maf_apim_api_foundry_claude.py
```

## BYOM: OpenAI client -> APIM handles automatic spec translation

- APIM can handle the API translation automatically through its Unified model API (preview) feature. 
- It needs to handle automatic translation between an OpenAI-compatible frontend and an Anthropic Messages backend.

Archicture on API spec translation:

```text
Foundry prompt agent
    → Admin-connected model
        → APIM Unified model API
            → Automatic OpenAI ↔ Anthropic translation
                → Foundry Claude deployment
```

Add your Claude backend

| Setting | Value |
|---|---|
| Backend model | Your actual deployment name, such as `claude-opus-5` |
| Backend API format | Anthropic Messages API |
| Backend URL | Your Foundry Claude endpoint, as required by the wizard `https://{foundry-account-name}.services.ai.azure.com/anthropic` |
| Backend authentication | Supported Foundry credential or APIM managed identity (For system MSI, pass resource URI scope as `https://ai.azure.com`. Confirm APIM MSI has Foundry User role on Foundry account.) |
| Client-facing alias | For example, `claude-byom` |

Auth flow:

```text
Python OpenAI chat completion client
    │ APIM subscription key
    ▼
APIM Unified model API
    │ Obtains an Entra token using its managed identity
    │ Sends Authorization: Bearer <token>
    | OpenAI to Anthropic translation
    ▼
Foundry Claude
    │ Validates token and checks the identity's assigned roles
    ▼
Model response
```

```bash
python openai_unified_api_foundry_claude.py
```

## BYOM: Prompt agent -> admin connected model

At the moment, per design, the AI Gateway just have `POST /chat/completions` API exposed. AI Gatway can't directly converse with `/v1/messages` nor `/v1/responses` APIs.

Bring up admin connected model.

| Field | Value |
| --- | --- |
| Model configuration |	Static model list |
| Name |	claude-byom |
| Display name |	Any descriptive label, e.g. Claude Opus 5 via APIM |
| Version |	Leave blank |
| Format |	OpenAI |

OpenAI is correct here, even though the backend is Claude. Foundry talks to APIM's OpenAI-compatible frontend, and APIM translates it to Anthropic Messages.

```
Foundry sends model="claude-byom"
    → APIM resolves alias
        → Backend deployment "claude-opus-5"
```

Challenge noticed:

| Layer |	Verified finding |
| --- | --- |
| `run_prompt_agent.py` and SDK serialization |	No top_p sent in the Responses request |
| Saved prompt-agent definition |	No top_p configured |
| Foundry → APIM request |	Contains top_p: 1.0 |
| Claude backend |	Rejects top_p as deprecated |

This locates the insertion inside the Foundry service-side agent/model-gateway path. 

As Foundry platform is supplying `top_p` param at the moment, workaround to follow is like: remove top_p in APIM's inbound policy, scoped to `claude-byom`, before translation.

Steps to add an inbound policy to the Unified model API (that removes `top_p` only for `claude-byom`, before APIM translates the request to Anthropic format):

1. Open the Unified API policy
In Azure portal:
```
APIM → APIs → your Unified model API (model-api, path llm/v1) → All operations → Inbound processing → Policy code editor
```

2. Insert this inside the existing <inbound> section
Place it after <base />. Keep your existing <set-backend-service ... /> and all other policies unchanged.

```xml
<choose>
    <when condition='@(context.Operation.Id == "createChatCompletion")'>
        <set-body>@{
            var body = context.Request.Body.As<JObject>(
                preserveContent: true
            );

            if ((string)body["model"] == "claude-byom")
            {
                body.Remove("top_p");
            }

            return body.ToString(Newtonsoft.Json.Formatting.None);
        }</set-body>
    </when>
</choose>
```

3. Save the policy

For the affected model, the effective transformation is like following.

Arriving from Foundry:
```
{
  "model": "claude-byom",
  "top_p": 1.0,
  "messages": ["..."]
}
```

After the inbound policy:
```
{
  "model": "claude-byom",
  "messages": ["..."]
}
```

```bash
# Create foundry prompt agent
python create_prompt_agent.py

# Run foundry prompt agent
python run_prompt_agent.py
```

Here is the current prompt agent flow in working like:

```
Your Python code (Foundry Prompt Agent)
    │
    │ client.responses.create(...)
    │ agent_reference = your saved agent
    ▼
Foundry Agent Service — Responses API
    │
    │ Loads the saved agent definition:
    │ model = Model-API/claude-byom
    │
    │ Calls the connected model using Chat Completions
    ▼
APIM: POST /llm/v1/chat/completions
    │
    │ Removes top_p through your policy
    │ Translates OpenAI format → Anthropic format
    ▼
Foundry Claude: POST /anthropic/v1/messages
```

The agent_reference tells Foundry to execute the saved agent. Foundry's service-side runtime makes the downstream model request using the OpenAI-compatible connection you registered.

Reference:
- [APIM Unified Model API](https://learn.microsoft.com/en-us/azure/api-management/unified-model-api)
- [BYOM with AI Gateways](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/ai-gateway?tabs=api-management&pivots=foundry-portal)
- [APIM Unified Model API format transformation](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities)

## BYOM Claude model (litellm way)
```
Foundry prompt agent
    → Admin-connected model
        → APIM OpenAI-compatible route
            → Adapter
                → Foundry Claude Messages API
```

Target architecture

```
Your application
    │ Entra authentication
    ▼
Foundry prompt agent
    ▼
Admin-connected model
    │ APIM subscription key stored in the connection
    ▼
NEW APIM OpenAI-compatible API
    ▼
LiteLLM proxy
    │ Foundry backend authentication
    ▼
Foundry Claude /anthropic/v1/messages
```



