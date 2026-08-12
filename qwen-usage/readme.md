## Qwen Python Samples

Small examples for using a Qwen deployment (Foundry hosted - managed compute deployment) on Azure AI Foundry through its
OpenAI-compatible chat-completions endpoint.

## Setup

1. Sign in to Azure:

   ```powershell
   az login
   ```

2. Create a `.env` file:

   ```env
   OPENAI_BASE_URL=https://<your-endpoint>/openai/v1
   FOUNDRY_MODELS_ENDPOINT=<your-qwen-deployment-name>
   ```

   Follow `.env.example` and rename as `.env` otherwise with own resource details.

3. Install the packages needed by the sample you want to run. The
   `qwen-agent` examples use `requirement1.txt`.

    ```
    python --version

    # create vnev
    python -m venv .qw9

    # activate venv
    source .qw9/Scripts/activate
    ```

    ```
    pip install -r requirement1.txt
    ```

   The `agent-framework` examples require an environment with `agent-framework`. The zoom examples also need `Pillow` installed. Use `requirement2.txt` for venv setup.

    ```
    python --version

    # create vnev
    python -m venv .maf

    # activate venv
    source .maf/Scripts/activate
    ```

    ```
    pip install -r requirement2.txt
    ```

Authentication uses `DefaultAzureCredential` and the Azure AI scope
`https://ai.azure.com/.default`.

## Samples

| File | Purpose |
| --- | --- |
| `qwen_agent_image_chat.py` | Analyze an image with `qwen-agent` using a data URI. |
| `qwen_agent_text_chat.py` | Send a text prompt with `qwen-agent`. |
| `qwen_aget_image_chat_zoomintool.py` | Use Qwen's image zoom tool through native tool calling. |
| `qwen_agent_image_chat_basetool.py` | Demonstrate a custom image tool skeleton. Its crop logic is intentionally incomplete. |
| `maf_image_chat.py` | Analyze an image with `agent-framework`. |
| `maf_text_chat.py` | Send a text prompt and print token usage. |
| `maf_image_chat_autocrop_tool.py` | Let Qwen propose a zoom region, crop it locally, and inspect the crop. |
| `maf_image_chat_tool.py` | Accept zoom coordinates from the user, crop locally, and inspect the crop. |

## Basic usage

Run a sample from this directory with the Python environment containing its
dependencies:

```
python qwen_agent_text_chat.py

python qwen_agent_image_chat.py

python qwen_aget_image_chat_zoomintool.py

python qwen_agent_image_chat_basetool.py
```

```
python maf_text_chat.py

python maf_image_chat.py

# custom tool
python maf_image_chat_autocrop_tool.py

# Use the script's default region
python maf_image_chat_tool.py

# Inspect default region with co-ordinates
python maf_image_chat_tool.py 300 400 620 780

# Inspect a supplied region
python maf_image_chat_tool.py 300 400 620 780 --label "bear body"
```

## Critical Qwen configuration

For `qwen-agent`, use `oai` for text or `qwenvl_oai` for image input:

```python
access_token = DefaultAzureCredential().get_token(
    "https://ai.azure.com/.default"
).token

agent = Assistant(
    llm={
        "model_type": "qwenvl_oai",
        "model": os.environ["FOUNDRY_MODELS_ENDPOINT"],
        "model_server": os.environ["OPENAI_BASE_URL"],
        "api_key": access_token,
    },
    system_message="Analyze the provided image.",
)
```

For installed version `qwen-agent==0.0.34`, the registered types are:

- `oai` — text, OpenAI-compatible
- `qwenvl_oai` — vision, OpenAI-compatible
- `qwenomni_oai` — multimodal/omni, OpenAI-compatible
- `azure` — Azure OpenAI
- `qwen_dashscope`
- `qwenvl_dashscope`
- `qwenaudio_dashscope`
- `qwenvlo_dashscope`
- `transformers`
- `openvino`

The repo [qwen_agent/llm/](https://github.com/QwenLM/Qwen-Agent/blob/main/qwen_agent/llm/__init__.py#L20_) gives more idea about `model_type` support with `qwen-agent` caller library.


## Critical zoom technique

The key to the zoom objective is to crop the selected region in Python and
send the resulting pixels back to the vision model:

```python
def crop_region(image_bytes: bytes, bbox_2d: list[float]) -> bytes:
    image = Image.open(BytesIO(image_bytes))
    width, height = image.size
    x1, y1, x2, y2 = bbox_2d
    box = (
        int(x1 / 1000 * width),
        int(y1 / 1000 * height),
        int(x2 / 1000 * width),
        int(y2 / 1000 * height),
    )
    crop = image.crop(box)
    output = BytesIO()
    crop.save(output, format="PNG")
    return output.getvalue()

crop_bytes = crop_region(image_data, bbox_2d)
result = await inspector.run([
    Content.from_data(crop_bytes, media_type="image/png"),
    Content.from_text("Describe what this cropped region contains."),
])
```

This crop-and-resend flow is implemented in `maf_image_chat_autocrop_tool.py` and `maf_image_chat_tool.py` in `agent-framework` way.
