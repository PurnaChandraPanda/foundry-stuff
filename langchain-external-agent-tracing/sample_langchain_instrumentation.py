# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from microsoft.opentelemetry import use_microsoft_opentelemetry
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
application_insights_connection_string = os.environ.get(
    "APPLICATIONINSIGHTS_CONNECTION_STRING"
)

credential = DefaultAzureCredential()
aad_token_provider = get_bearer_token_provider(
    credential,
    "https://cognitiveservices.azure.com/.default",
)

if not application_insights_connection_string:
    raise RuntimeError(
        "Set APPLICATIONINSIGHTS_CONNECTION_STRING for Azure Monitor telemetry."
    )

use_microsoft_opentelemetry(
    enable_azure_monitor=True,
    azure_monitor_connection_string=application_insights_connection_string,
    sampling_ratio=1.0,
    instrumentation_options={
        "langchain": {
            "enabled": True,
            # Optional: set static agent identity on all LangChain spans.
            # These appear as gen_ai.agent.* attributes in your telemetry.
            # If omitted, agent_name is inferred from LangChain's
            # runtime metadata when available.
            "agent_id": "travel-assistant-001",
            "agent_name": "Travel_Assistant",
        },
    },
)


def main():
    if not endpoint or not deployment_name:
        raise RuntimeError(
            "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME."
        )

    llm = ChatOpenAI(
        model=deployment_name,
        api_key=aad_token_provider,
        base_url=endpoint,
        temperature=0.1,
        max_tokens=100,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        seed=100,
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = llm.invoke(messages)
    print("LLM output:\n", result)

    @tool
    def get_population(city: str) -> str:
        """Get the population of a city."""
        populations = {
            "paris": "2.1 million",
            "london": "8.9 million",
            "tokyo": "14 million",
            "new york": "8.3 million",
        }
        return populations.get(city.lower(), f"Population data not available for {city}.")

    @tool
    def get_famous_landmark(city: str) -> str:
        """Get the most famous landmark in a city."""
        landmarks = {
            "paris": "Eiffel Tower",
            "london": "Big Ben",
            "tokyo": "Tokyo Tower",
            "new york": "Statue of Liberty",
        }
        return landmarks.get(city.lower(), f"No landmark info for {city}.")

    agent = create_agent(
        llm,
        tools=[get_population, get_famous_landmark],
        system_prompt="You are a helpful travel assistant. Use the tools to answer questions about cities.",
        name="Travel_Assistant",
    )

    print("\n--- Agent run ---")
    user_input = "What is the population of Paris and what is its most famous landmark?"
    agent_result = agent.invoke({"messages": [("human", user_input)]})
    output = agent_result["messages"][-1].content
    print("Agent output:\n", output)


if __name__ == "__main__":
    main()
