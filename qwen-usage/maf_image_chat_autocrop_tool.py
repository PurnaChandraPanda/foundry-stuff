# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from io import BytesIO
from typing import Annotated
from urllib.request import urlopen

from PIL import Image
from agent_framework import Agent, Content, tool
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from pydantic import Field

IMAGE_URL = "https://suanli.cn/assets/QucgbCSISoA7XCxlEI9cVQSOnbd.png"


load_dotenv()


@tool(approval_mode="never_require")
def propose_zoom_region(
    bbox_2d: Annotated[list[float], Field(description="Region to zoom into as [x1, y1, x2, y2], normalized 0-1000.")],
    label: Annotated[str, Field(description="Short label for the region of interest.")] = "region",
) -> str:
    """Record the region the model wants to zoom into. The crop is produced in code afterwards."""
    return f"Recorded zoom region label={label} bbox_2d={bbox_2d}."


def download_image(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        return response.read()


def crop_region(image_bytes: bytes, bbox_2d: list[float]) -> bytes:
    """Crop a normalized (0-1000) region from the image and return PNG bytes."""
    image = Image.open(BytesIO(image_bytes))
    img_width, img_height = image.size
    x1, y1, x2, y2 = [float(v) for v in bbox_2d]

    left = max(0, int((x1 / 1000.0) * img_width))
    top = max(0, int((y1 / 1000.0) * img_height))
    right = min(img_width, int((x2 / 1000.0) * img_width))
    bottom = min(img_height, int((y2 / 1000.0) * img_height))

    if right <= left or bottom <= top:
        raise ValueError(f"Invalid bbox after conversion: {(left, top, right, bottom)}")

    crop = image.crop((left, top, right, bottom))
    buffer = BytesIO()
    crop.save(buffer, format="PNG")
    return buffer.getvalue()


def extract_proposed_region(result) -> tuple[list[float], str] | None:
    """Find the first propose_zoom_region tool call in the response and parse its arguments."""
    for message in result.messages:
        for content in message.contents or []:
            if content.type == "function_call" and content.name == "propose_zoom_region":
                args = content.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                bbox = [float(v) for v in args["bbox_2d"]]
                label = args.get("label", "region")
                return bbox, label
    return None


async def main():
    print("=== Coordinate-Driven Zoom (model proposes bbox, code crops, model inspects) ===")

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

    client = OpenAIChatCompletionClient(
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ["FOUNDRY_MODELS_ENDPOINT"],
        credential=token_provider,
    )

    image_data = download_image(IMAGE_URL)

    # Turn 1: the model looks at the full image and proposes a region via the tool.
    proposer = Agent(
        client=client,
        name="RegionProposer",
        instructions=(
            "You are a vision agent. Look at the image and pick the single most "
            "information-dense region worth zooming into. Call propose_zoom_region "
            "with its bbox_2d in normalized 0-1000 coordinates (origin at top-left). "
            "Do not describe the image yet."
        ),
        tools=[propose_zoom_region],
    )

    proposal = await proposer.run([
        Content.from_data(image_data, media_type="image/png"),
        Content.from_text("Choose one region to zoom into and call propose_zoom_region."),
    ])

    region = extract_proposed_region(proposal)
    if region is None:
        print("Model did not propose a zoom region.")
        return

    bbox_2d, label = region
    print(f"Proposed region: label={label} bbox_2d={bbox_2d}")

    # Crop the proposed region in code.
    crop_bytes = crop_region(image_data, bbox_2d)

    # Turn 2: send the cropped pixels back and ask for a description.
    inspector = Agent(
        client=client,
        name="RegionInspector",
        instructions=(
            "You are a vision agent. Describe only what is actually visible in the "
            "cropped region. Do not invent unreadable details."
        ),
    )

    result = await inspector.run([
        Content.from_data(crop_bytes, media_type="image/png"),
        Content.from_text(
            f"This is a zoomed crop of region '{label}' (bbox_2d={bbox_2d}, normalized 0-1000) "
            "from a larger image. Describe what this cropped region contains."
        ),
    ])

    if result.text and result.text.strip():
        print(f"Agent: {result.text.strip()}")
    else:
        print("Agent: No text response received.")


if __name__ == "__main__":
    asyncio.run(main())
