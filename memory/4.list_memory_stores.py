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

# List all memory stores
stores_list = client.memory_stores.list()

# Convert the iterable to a list
stores = list(stores_list)

print(f"Found {len(stores)} memory stores")
for store in stores:
    print(f"- {store.name} ({store.description})")