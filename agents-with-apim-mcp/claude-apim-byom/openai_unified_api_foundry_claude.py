import os

from openai import OpenAI, omit
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

with OpenAI(
    base_url=os.getenv("APIM_UNIFIED_API_BASE_URL"),
    api_key="unused",
    default_headers={
        os.getenv("APIM_API_SUBSCRIPTION_KEY_NAME"): os.getenv("APIM_API_SUBSCRIPTION_KEY_VALUE"),
    },
) as client:
    response = client.chat.completions.create(
        model=os.getenv("APIM_UNIFIED_API_MODEL_ALIAS"),
        messages=[
            {"role": "user", "content": "Say hello in five words."}
        ],
        max_tokens=4096,
    )

    print(response.choices[0].message.content)