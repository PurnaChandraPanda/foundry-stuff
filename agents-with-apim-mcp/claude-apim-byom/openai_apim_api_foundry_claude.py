import os

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

endpoint = os.environ["APIM_API_FOUNDRY_ANTHROPIC_ENDPOINT"].rstrip("/")
deployment_name = os.environ["APIM_API_FOUNDRY_ANTHROPIC_DEPLOYMENT"]

with DefaultAzureCredential() as credential:
    token = credential.get_token("https://ai.azure.com/.default").token

    with OpenAI(
        base_url=endpoint,
        api_key="unused",
        default_headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            os.environ["APIM_API_SUBSCRIPTION_KEY_NAME"]:
                os.environ["APIM_API_SUBSCRIPTION_KEY_VALUE"],
        },
        timeout=120.0,
        max_retries=0,
    ) as client:
        message = client.post(
            "/v1/messages",
            cast_to=dict,
            body={
                "model": deployment_name,
                "system": "You are a helpful assistant.",
                "messages": [
                    {
                        "role": "user",
                        "content": "What is the capital of France?",
                    }
                ],
                "max_tokens": 1024,
            },
        )

        for block in message["content"]:
            if block["type"] == "text":
                print(block["text"])