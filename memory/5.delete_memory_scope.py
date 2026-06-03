import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the client
client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential()
)

# Delete memories for a specific scope
delete_scope_response = client.memory_stores.delete_scope(
    name="my_memory_store",
    scope="user_123"
)

print(delete_scope_response)
print(f"Deleted memories for scope: user_123")
