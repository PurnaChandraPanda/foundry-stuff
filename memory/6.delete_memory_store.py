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

# Delete the entire memory store
delete_response = client.memory_stores.delete("my_memory_store")

print(delete_response)
print(f"Deleted memory store: {delete_response.deleted}")

