import logging
import sys
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

import os
from anthropic import AnthropicFoundry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

endpoint = os.getenv("FOUNDRY_ANTHROPIC_ENDPOINT")
deployment_name = os.getenv("FOUNDRY_ANTHROPIC_DEPLOYMENT")
token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

client = AnthropicFoundry(
    azure_ad_token_provider=token_provider,
    base_url=endpoint
)

message = client.messages.create(
    model=deployment_name,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    max_tokens=1024,
)

# print(message)
print(message.content)
# print(message.content[0].text)
