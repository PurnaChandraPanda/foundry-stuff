import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ResponsesUserMessageItemParam
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

user_message = ResponsesUserMessageItemParam(
    content="I prefer dark roast coffee and usually drink it in the morning"
)

update_poller = client.memory_stores.begin_update_memories(
    name="my_memory_store",
    scope=scope,
    items=[user_message],  # Pass conversation items that you want to add to memory
    update_delay=0,  # Trigger update immediately without waiting for inactivity
)

# Wait for the update operation to complete, but can also fire and forget
update_result = update_poller.result()
print(f"Updated with {len(update_result.memory_operations)} memory operations")
for operation in update_result.memory_operations:
    print(
        f"  - Operation: {operation.kind}, Memory ID: {operation.memory_item.memory_id}, Content: {operation.memory_item.content}"
    )

# Extend the previous update with another update and more messages
new_message = ResponsesUserMessageItemParam(content="I also like cappuccinos in the afternoon")
new_update_poller = client.memory_stores.begin_update_memories(
    name="my_memory_store",
    scope=scope,
    items=[new_message],
    previous_update_id=update_poller.update_id,  # Extend from previous update ID
    update_delay=0,  # Trigger update immediately without waiting for inactivity
)
new_update_result = new_update_poller.result()
for operation in new_update_result.memory_operations:
    print(
        f"  - Operation: {operation.kind}, Memory ID: {operation.memory_item.memory_id}, Content: {operation.memory_item.content}"
    )