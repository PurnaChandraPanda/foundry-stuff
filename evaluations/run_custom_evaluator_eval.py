import os
import time
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# OpenAI Evals types used by the Foundry Evals API
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
)

load_dotenv()

PROJECT_ENDPOINT = (
    os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    or os.environ["AZURE_AI_PROJECT_ENDPOINT"]
)

# For prompt-based (LLM-as-judge) evaluators, you typically pass deployment_name
MODEL_DEPLOYMENT = (
    os.environ.get("FOUNDRY_MODEL_NAME")
    or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
)

CUSTOM_EVALUATOR_CATALOG_NAME = "my_custom_evaluator_code"

POLL_INTERVAL_SECONDS = 5


def resolve_custom_evaluator_name(project_client: AIProjectClient, evaluator_name: str) -> str:
    """
    Resolves the evaluator name to whatever the catalog expects.
    Built-ins are referenced like 'builtin.coherence'. Custom evaluators are project-scoped. [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)

    Different SDK versions/experiences may surface custom evaluator names differently,
    so we list and match to be safe.
    """
    # List custom evaluators from the catalog (project scope)
    custom_evals = list(project_client.beta.evaluators.list(type="custom"))  # [1](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_eval_catalog.py)

    # Try exact match against catalog "name"
    for ev in custom_evals:
        # print(ev)
        if getattr(ev, "name", None) == evaluator_name:
            return ev.name

    # Try match against "display_name"
    for ev in custom_evals:
        if getattr(ev, "display_name", None) == evaluator_name:
            return ev.name

    # Fallback: many setups use "custom.<name>" in the Evals API.
    # If your run errors with "evaluator not found", print the list above and use the returned ev.name.
    if not evaluator_name.startswith("custom."):
        return f"custom.{evaluator_name}"

    return evaluator_name


def poll_run(client, eval_id: str, run_id: str):
    """
    Poll run status until terminal. The Evals API returns run objects you can poll. [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)
    """
    # The OpenAI SDK method names can differ slightly across versions; handle common ones.
    retrieve = getattr(client.evals.runs, "retrieve", None) or getattr(client.evals.runs, "get", None)
    if retrieve is None:
        raise RuntimeError("Couldn't find a runs.retrieve/get method on the OpenAI client.")

    while True:
        run = retrieve(eval_id=eval_id, run_id=run_id)
        status = getattr(run, "status", None) or getattr(run, "state", None)
        print(f"Run status: {status}")

        if status in ("completed", "failed", "cancelled"):
            return run

        time.sleep(POLL_INTERVAL_SECONDS)


def main():
    with DefaultAzureCredential() as cred, AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=cred) as project_client:
        # OpenAI-compatible client that exposes Evals APIs for cloud evaluation [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)
        client = project_client.get_openai_client()

        evaluator_name = resolve_custom_evaluator_name(project_client, CUSTOM_EVALUATOR_CATALOG_NAME)
        print(f"Using custom evaluator: {evaluator_name}")

        # 1) Define the dataset schema (must match your test items)
        data_source_config = DataSourceConfigCustom(
            type="custom",
            item_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "response": {"type": "string"},
                },
                "required": ["query", "response"],
            },
            # include_sample_schema only needed when using a *target* (model/agent) to generate output_text.
            include_sample_schema=False,
        )

        # 2) Provide test data inline (JSONL-like)
        source = SourceFileContent(
            type="file_content",
            content=[
                SourceFileContentContent(item={
                    "query": "What is the capital of France?",
                    "response": "Paris is the capital of France.",
                }),
                SourceFileContentContent(item={
                    "query": "Explain Kubernetes in one sentence.",
                    "response": "Kubernetes is a system for automating deployment and scaling of containerized apps.",
                }),
            ],
        )

        # 3) Configure testing criteria – reference the *catalog evaluator*
        # Built-ins look like "builtin.coherence"; custom evaluators come from your project's catalog. [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)[1](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_eval_catalog.py)
        testing_criteria = [
            {
                "type": "azure_ai_evaluator",
                "name": "my_custom_metric",             # alias in results
                "evaluator_name": evaluator_name,       # the catalog evaluator reference
                # For prompt-based evaluators, you typically pass the judge deployment in init params. [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)
                "initialization_parameters": {
                    "deployment_name": MODEL_DEPLOYMENT,
                    # Include any other init params your evaluator declared (e.g. threshold). [1](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_eval_catalog.py)
                    # "threshold": 0.7,
                },
                # Map your dataset fields to evaluator inputs.
                # These must match the evaluator's declared data schema (query/response here). [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)[1](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_eval_catalog.py)
                "data_mapping": {
                    "query": "{{item.query}}",
                    "response": "{{item.response}}",
                },
            }
        ]

        # 4) Create evaluation definition
        eval_obj = client.evals.create(
            name="custom-evaluator-dataset-eval",
            data_source_config=data_source_config,
            testing_criteria=testing_criteria,
        )

        # 5) Create evaluation run (jsonl source type) [2](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)
        run = client.evals.runs.create(
            eval_id=eval_obj.id,
            name="run-1",
            data_source=CreateEvalJSONLRunDataSourceParam(
                type="jsonl",
                source=source,
            ),
        )

        # 6) Poll until complete
        final_run = poll_run(client, eval_obj.id, run.id)

        # 7) Print basic run info
        print("\nFinal run object:")
        print(final_run)

        # Optional: Depending on your run object, you may receive output/result file ids.
        # If present, you can fetch those via client.files.content(file_id) and parse JSONL.


if __name__ == "__main__":
    main()