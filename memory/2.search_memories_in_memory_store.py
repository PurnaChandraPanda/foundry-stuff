import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ResponsesUserMessageItemParam, MemorySearchOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the client
client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential()
)

# Set scope to associate the memories with
scope = "user_123"

# Search memories by a query
query_message = ResponsesUserMessageItemParam(content="What are my coffee preferences?")

search_response = client.memory_stores.search_memories(
    name="my_memory_store",
    scope=scope,
    items=[query_message],
    options=MemorySearchOptions(max_memories=5)
)
print(f"Found {len(search_response.memories)} memories")
for memory in search_response.memories:
    print(f"  - Memory ID: {memory.memory_item.memory_id}, Content: {memory.memory_item.content}")

