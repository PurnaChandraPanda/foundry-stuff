import os
from anthropic import AnthropicFoundry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

endpoint = os.getenv("APIM_API_FOUNDRY_ANTHROPIC_ENDPOINT")
deployment_name = os.getenv("APIM_API_FOUNDRY_ANTHROPIC_DEPLOYMENT")
token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

client = AnthropicFoundry(
    azure_ad_token_provider=token_provider,
    base_url=endpoint,
    default_headers={
        os.getenv("APIM_API_SUBSCRIPTION_KEY_NAME"): os.getenv("APIM_API_SUBSCRIPTION_KEY_VALUE")
    }
)

message = client.messages.create(
    model=deployment_name,
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    max_tokens=1024,
)

# print(message)
print(message.content)