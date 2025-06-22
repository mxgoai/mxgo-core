import base64
import json
import os
from io import BytesIO
from typing import Optional

import requests
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from litellm import completion
from PIL import Image
from smolagents import Tool, tool

from mxtoai._logging import get_logger

load_dotenv(override=True)

# Configure logger
logger = get_logger("azure_visualizer")


def process_images_and_text_from_content(content: bytes, query: str, client: InferenceClient):
    """
    Process images and text using the IDEFICS model from memory content.

    Args:
        content: Image content as bytes.
        query: The question to ask about the image.
        client: Inference client for the model.

    """
    from transformers import AutoProcessor

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": query},
            ],
        },
    ]
    idefics_processor = AutoProcessor.from_pretrained("HuggingFaceM4/idefics2-8b-chatty")
    prompt_with_template = idefics_processor.apply_chat_template(messages, add_generation_prompt=True)

    def encode_content_image(content: bytes):
        image = Image.open(BytesIO(content)).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{base64_image}"

    image_string = encode_content_image(content)
    prompt_with_images = prompt_with_template.replace("<image>", "![]({}) ").format(image_string)

    payload = {
        "inputs": prompt_with_images,
        "parameters": {
            "return_full_text": False,
            "max_new_tokens": 200,
        },
    }

    return json.loads(client.post(json=payload).decode())[0]


def encode_image_from_content(content: bytes) -> str:
    """
    Encode image content to base64 format.

    Args:
        content: The image content as bytes.

    Returns:
        str: The base64 encoded string of the image.

    """
    return base64.b64encode(content).decode("utf-8")


def resize_image_from_content(content: bytes) -> bytes:
    """
    Resize image content to half its original size.

    Args:
        content: The image content as bytes.

    Returns:
        bytes: The resized image content as bytes.

    """
    img = Image.open(BytesIO(content))
    width, height = img.size
    img = img.resize((int(width / 2), int(height / 2)))
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


headers = {"Content-Type": "application/json", "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}


class VisualQATool(Tool):
    name = "visualizer"
    description = "A tool that can answer questions about attached images from memory content."
    inputs = {
        "content": {
            "description": "The image content as bytes",
            "type": "any",
        },
        "mime_type": {
            "description": "MIME type of the image",
            "type": "string",
        },
        "question": {"description": "the question to answer", "type": "string", "nullable": True},
    }
    output_type = "string"

    client = InferenceClient("HuggingFaceM4/idefics2-8b-chatty")

    def forward(self, content: bytes, mime_type: str, question: Optional[str] = None) -> str:
        """
        Process the image and return a short caption based on the content.

        Args:
            content: The image content as bytes.
            mime_type: MIME type of the image.
            question: The question to answer.

        Returns:
            str: The generated caption or the text content of the file.

        """
        output = ""
        add_note = False
        if not question:
            add_note = True
            question = "Please write a detailed caption for this image."
        try:
            output = process_images_and_text_from_content(content, question, self.client)
        except Exception as e:
            if "Payload Too Large" in str(e):
                resized_content = resize_image_from_content(content)
                output = process_images_and_text_from_content(resized_content, question, self.client)

        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

        return output


@tool
def visualizer_from_content(content: bytes, mime_type: str, question: Optional[str] = None) -> str:
    """
    A tool that can answer questions about image content.

    Args:
        content: The image content as bytes.
        mime_type: MIME type of the image.
        question: The question to answer.

    """
    add_note = False
    if not question:
        add_note = True
        question = "Please write a detailed caption for this image."

    if not mime_type:
        mime_type = "image/jpeg"

    base64_image = encode_image_from_content(content)

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                ],
            }
        ],
        "max_tokens": 1000,
    }
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    try:
        output = response.json()["choices"][0]["message"]["content"]
    except Exception:
        msg = f"Response format unexpected: {response.json()}"
        raise Exception(msg)

    if add_note:
        output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

    return output


@tool
def azure_visualizer_from_content(content: bytes, mime_type: str, question: Optional[str] = None) -> str:
    """
    A tool that can answer questions about image content using Azure OpenAI.

    Args:
        content: The image content as bytes.
        mime_type: MIME type of the image.
        question: The question to answer.

    """
    add_note = False
    if not question:
        add_note = True
        question = "Please write a detailed caption for this image."

    try:
        if not mime_type:
            mime_type = "image/jpeg"

        base64_image = encode_image_from_content(content)

        content_payload = [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
        ]

        model = f"azure/{os.getenv('MODEL_NAME', 'gpt-4o')}"
        api_key = os.getenv("MODEL_API_KEY")
        api_base = os.getenv("MODEL_ENDPOINT")
        api_version = os.getenv("MODEL_API_VERSION")

        logger.info(f"Sending image content to Azure OpenAI model: {model}")
        response = completion(
            model=model,
            messages=[{"role": "user", "content": content_payload}],
            api_key=api_key,
            api_base=api_base,
            api_version=api_version,
            max_tokens=1000,
        )

        if hasattr(response, "choices") and response.choices:
            if hasattr(response.choices[0], "message") and hasattr(response.choices[0].message, "content"):
                output = response.choices[0].message.content
            else:
                output = response.choices[0].get("message", {}).get("content", "")
        else:
            output = str(response)

        if not output:
            msg = "Empty response from Azure OpenAI"
            raise Exception(msg)

        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

        return output

    except Exception as e:
        logger.error(f"Error in azure_visualizer_from_content: {e!s}")

        try:
            resized_content = resize_image_from_content(content)
            base64_image = encode_image_from_content(resized_content)

            content_payload = [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
            ]

            response = completion(
                model=model,
                messages=[{"role": "user", "content": content_payload}],
                api_key=api_key,
                api_base=api_base,
                api_version=api_version,
                max_tokens=1000,
            )

            if hasattr(response, "choices") and response.choices:
                if hasattr(response.choices[0], "message") and hasattr(response.choices[0].message, "content"):
                    output = response.choices[0].message.content
                else:
                    output = response.choices[0].get("message", {}).get("content", "")
            else:
                output = str(response)

            if add_note:
                output = (
                    f"You did not provide a particular question, so here is a detailed caption for the image: {output}"
                )

            return output

        except Exception as retry_error:
            logger.error(f"Error in azure_visualizer_from_content retry: {retry_error!s}")
            msg = f"Failed to process image: {retry_error!s}"
            raise Exception(msg)
