import os
import json
from datetime import datetime, timezone

from anthropic import AnthropicFoundry
from anthropic.types import MessageParam, ToolParam
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("FOUNDRY_ANTHROPIC_ENDPOINT")
deployment_name = os.getenv("FOUNDRY_ANTHROPIC_DEPLOYMENT")

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://ai.azure.com/.default",
)

client = AnthropicFoundry(
    azure_ad_token_provider=token_provider,
    base_url=endpoint,
)

tools: list[ToolParam] = [
    {
        "name": "get_current_utc_time",
        "description": (
            "Get the actual current UTC date and time. "
            "Use this whenever the user asks for the current time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }
]


def run_agent(task: str) -> str:
    messages: list[MessageParam] = [
        {"role": "user", "content": task}
    ]

    for _ in range(8):
        response = client.messages.create(
            model=deployment_name,
            max_tokens=1024,
            system=(
                "You are a helpful assistant with access to tools. "
                "Use tools when you need live information. "
                "Never invent tool results."
            ),
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "\n".join(
                block.text
                for block in response.content
                if block.type == "text"
            )

        if response.stop_reason != "tool_use":
            raise RuntimeError(
                f"Agent stopped unexpectedly: {response.stop_reason}"
            )

        # Keep every block, including tool calls, in conversation history.
        messages.append(
            {
                "role": "assistant",
                "content": response.model_dump()["content"],
            }
        )

        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "get_current_utc_time" and block.input == {}:
                result = json.dumps(
                    {"utc_time": datetime.now(timezone.utc).isoformat()}
                )
                is_error = False
            else:
                result = "Unknown tool or invalid tool arguments."
                is_error = True

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                    "is_error": is_error,
                }
            )

        if not tool_results:
            raise RuntimeError("Claude requested tools but provided no calls.")

        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Agent exceeded the maximum of 8 model calls.")


if __name__ == "__main__":
    answer = run_agent(
        "Check the current UTC time and tell me what time it is in India."
    )
    print(answer)
