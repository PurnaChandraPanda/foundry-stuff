#!/usr/bin/env python3
"""
Step 6 of the public BYOM golden path: create an agent that uses the model served
through the Azure API Management (APIM) AI Gateway.

IMPORTANT
---------
A BYOM (gateway-connected) model works ONLY with a *prompt agent* invoked through the
Responses API. The classic Assistants API (create_agent + threads + runs) CANNOT resolve
a "<connection>/<model>" reference and fails with:

    invalid_engine_error: Failed to resolve model info for: ai-gateway/gpt-4o

This script uses the correct path: agents.create_version(PromptAgentDefinition(...))
followed by responses.create(..., agent_reference=...).

Prerequisites
-------------
- The public-byom-apim.bicep template has been deployed (APIM + role assignment + the
  "<connectionName>" BYOM connection on the project).
- You are logged in with an identity that can call the project data plane:
    az login
- Packages:
    pip install "azure-ai-projects>=2.0.0" azure-identity

Arguments can also be supplied via environment variables:
    PROJECT_ENDPOINT, BYOM_MODEL
"""
import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    print("Create a BYOM prompt agent.")

    endpoint = os.environ.get("PROJECT_ENDPOINT")
    model = os.environ.get("BYOM_MODEL")
    agent_name = os.environ.get("PROMPT_AGENT_NAME")
    instructions = "You are a helpful assistant."
    
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    # 1) Create a PROMPT agent version bound to the gateway model.
    agent = project.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions=instructions,
        ),
    )
    print(f"Created prompt agent '{agent.name}' (version {getattr(agent, 'version', '?')}) "
          f"using model '{model}'.")
    

if __name__ == "__main__":
    main()