import os
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider 
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Replace placeholders with your resource, project, and app names
# BASE_URL = f"{os.getenv("FOUNDRY_PROJECT_ENDPOINT")}/applications/{os.getenv("FOUNDRY_AGENT_APPLICATION")}/protocols/openai"
BASE_URL = f"{os.getenv("FOUNDRY_PROJECT_ENDPOINT")}/agents/{os.getenv("FOUNDRY_AGENT_APPLICATION")}/endpoint/protocols/openai"

# Create OpenAI client authenticated with Azure credentials
openai = OpenAI(
    api_key=get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/"),
    base_url=BASE_URL,
    default_query={"api-version": "v1"}
    # default_query={"api-version": "2025-11-15-preview"}
)

## Non-stream mode: Send a request to the published agent
response = openai.responses.create( 
  input="Write a haiku", 
) 
print(f">> {response} <<")
print(f"Response output: {response.output_text}")

# ## For streamed output:
# stream = openai.responses.create(
#     input="Say hello",
#     stream=True,
# )

# for event in stream:
#     # OpenAI Responses streaming emits events like "response.output_text.delta"
#     # Print deltas as they arrive:
#     if event.type == "response.output_text.delta":
#         print(event.delta, end="", flush=True)

# print()  # newline at end
