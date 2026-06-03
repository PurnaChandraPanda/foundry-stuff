import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the client
client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential()
)

# Create memory store
definition = MemoryStoreDefaultDefinition(
    chat_model="gpt-4.1",  # Your chat model deployment name
    embedding_model="text-embedding-3-small",  # Your embedding model deployment name
    options=MemoryStoreDefaultOptions(user_profile_enabled=True, chat_summary_enabled=True)
)

memory_store = client.memory_stores.create(
    name="my_memory_store",
    definition=definition,
    description="Memory store for customer support agent",
)

print(f"Created memory store: {memory_store.name}")