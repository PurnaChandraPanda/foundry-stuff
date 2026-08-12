import os
import tempfile
from urllib.request import urlopen

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from qwen_agent.agents import Assistant
from qwen_agent.llm.schema import ContentItem, Message
from qwen_agent.tools.base import register_tool
from qwen_agent.tools.image_zoom_in_qwen3vl import ImageZoomInToolQwen3VL

IMAGE_URL = "https://suanli.cn/assets/QucgbCSISoA7XCxlEI9cVQSOnbd.png"
FOUNDRY_SCOPE = "https://ai.azure.com/.default"


@register_tool("custom_image_zoom_in_tool")
class CustomImageZoomInTool(ImageZoomInToolQwen3VL):
    name = ""


def download_image(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        image_data = response.read()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
        image_file.write(image_data)
        return image_file.name


def main() -> None:
    load_dotenv()

    access_token = DefaultAzureCredential().get_token(FOUNDRY_SCOPE).token
    image_path = download_image(IMAGE_URL)
    try:
        agent = Assistant(
            llm={
                "model_type": "qwenvl_oai",
                "model": os.environ["FOUNDRY_MODELS_ENDPOINT"],
                "model_server": os.environ["OPENAI_BASE_URL"],
                "api_key": access_token,
                # Enable native tool calls
                "generate_cfg": {"use_raw_api": True},
            },
            function_list=["custom_image_zoom_in_tool"],
            system_message=(
                "You analyze images. When the user provides zoom coordinates, "
                "call custom_image_zoom_in_tool before answering. Use the tool "
                "result as evidence and do not invent unreadable details."
            ),
            name="VisionAgent",
        )

        messages = [
            Message(
                role="user",
                content=[
                    ContentItem(image=image_path),

                    # The coordinates use a normalized 0–1000 coordinate system:
                    # - 850, 200: top-left
                    # - 980, 350: bottom-right
                    # - img_idx=0: first supplied image
                    # The origin (0, 0) is the top-left
                    # - X increases left → right
                    # - Y increases top → bottom
                    # Coordinates are normalized from 0 to 1000. Therefore (850, 200) means:
                    # - 85% across from the left
                    # - 20% down from the top
                    ContentItem(
                        text=(
                            "Inspect the bear in the upper-right area using img_idx=0 and "
                            "bbox_2d=[850, 200, 980, 350]. Describe what it contains."
                        )
                    ),
                ],
            )
        ]
        responses = agent.run_nonstream(messages)
        print(f"Agent: {responses[-1].content}")
    finally:
        os.unlink(image_path)


if __name__ == "__main__":
    main()
