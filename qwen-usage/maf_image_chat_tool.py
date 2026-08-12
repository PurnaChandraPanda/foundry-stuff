# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import os
from io import BytesIO
from urllib.request import urlopen

from PIL import Image
from agent_framework import Agent, Content
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

IMAGE_URL = "https://suanli.cn/assets/QucgbCSISoA7XCxlEI9cVQSOnbd.png"

# Default region to zoom into as [x1, y1, x2, y2], normalized 0-1000.
DEFAULT_BBOX = [685.0, 24.0, 790.0, 242.0]


load_dotenv()


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


def parse_args() -> tuple[list[float], str]:
    parser = argparse.ArgumentParser(
        description="Zoom into a user-supplied region of the image and describe it."
    )
    parser.add_argument(
        "bbox",
        nargs="*",
        type=float,
        help="Region as x1 y1 x2 y2, normalized 0-1000 (origin at top-left).",
    )
    parser.add_argument(
        "--label",
        default="region",
        help="Short label for the region of interest.",
    )
    args = parser.parse_args()

    if not args.bbox:
        return DEFAULT_BBOX, args.label
    if len(args.bbox) != 4:
        parser.error("bbox must have exactly 4 values: x1 y1 x2 y2")
    return args.bbox, args.label


async def main():
    print("=== User-Supplied Coordinate Zoom (user gives bbox, code crops, model inspects) ===")

    bbox_2d, label = parse_args()
    print(f"Requested region: label={label} bbox_2d={bbox_2d}")

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

    client = OpenAIChatCompletionClient(
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ["FOUNDRY_MODELS_ENDPOINT"],
        credential=token_provider,
    )

    image_data = download_image(IMAGE_URL)

    # Crop the user-supplied region in code.
    crop_bytes = crop_region(image_data, bbox_2d)

    # Send the cropped pixels and ask for a description.
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
