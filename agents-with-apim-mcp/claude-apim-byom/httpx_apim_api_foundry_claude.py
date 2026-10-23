import os

import httpx
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ["APIM_API_FOUNDRY_ANTHROPIC_ENDPOINT"].rstrip("/")
deployment_name = os.environ["APIM_API_FOUNDRY_ANTHROPIC_DEPLOYMENT"]

with DefaultAzureCredential() as credential:
    token = credential.get_token("https://ai.azure.com/.default").token

    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        os.environ["APIM_API_SUBSCRIPTION_KEY_NAME"]:
            os.environ["APIM_API_SUBSCRIPTION_KEY_VALUE"],
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{endpoint}/v1/messages",
            headers=headers,
            json={
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

        if response.is_error:
            print(response.text)

        response.raise_for_status()
        message = response.json()

        for block in message["content"]:
            if block["type"] == "text":
                print(block["text"])