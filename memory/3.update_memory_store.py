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

# Update memory store properties
updated_store = client.memory_stores.update(
    name="my_memory_store",
    description="Updated description"
)

print(f"Updated: {updated_store.description}")