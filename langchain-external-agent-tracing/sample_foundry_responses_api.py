# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""
Foundry Responses API sample.

For an Azure AI Foundry deployment called via LangChain's ``ChatOpenAI`` with
the Responses API, set ``include_response_headers=True``. Foundry only reports
the served model snapshot in the ``x-ms-served-model`` response header, so this
flag is what lets the distro's LangChain instrumentation record the correct
``gen_ai.response.model`` on the span.
"""

import os

from microsoft.opentelemetry import use_microsoft_opentelemetry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("AZURE_OPENAI_ENDPOINT")
MODEL_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

credential = DefaultAzureCredential()
aad_token_provider = get_bearer_token_provider(
    credential,
    "https://cognitiveservices.azure.com/.default",
)

def main() -> None:
    use_microsoft_opentelemetry(
        enable_azure_monitor=True,
        sampling_ratio=1.0,
        enable_sensitive_data=True,
    )

    llm = ChatOpenAI(
        model=MODEL_NAME,
        base_url=BASE_URL,
        api_key=aad_token_provider,
        use_responses_api=True,
        # Required so gen_ai.response.model reflects the served model.
        # Langchain documentation - https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/include_response_headers # pylint: disable=line-too-long
        include_response_headers=True,
    )

    result = llm.invoke(
        [
            SystemMessage(content="You are a concise, helpful assistant."),
            HumanMessage(content="In one sentence, what is OpenTelemetry?"),
        ]
    )
    print(result.content)


if __name__ == "__main__":
    main()