import base64
import json
import mimetypes
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar, Optional

import requests
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from PIL import Image
from smolagents import Tool

from mxtoai._logging import get_logger

load_dotenv(override=True)

# Configure logger
logger = get_logger("azure_visualizer")

DEFAULT_REQUEST_TIMEOUT = 30


# Define custom exceptions
class VisualQAError(Exception):
    pass


class InvalidImagePathError(TypeError):
    pass


class OpenAIResponseError(VisualQAError):
    pass


class AzureAIResponseError(VisualQAError):
    pass


def process_images_and_text(image_path, query, client):
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

    # load images from local directory

    # encode images to strings which can be sent to the endpoint
    def encode_local_image(image_path):
        # load image
        image = Image.open(image_path).convert("RGB")

        # Convert the image to a base64 string
        buffer = BytesIO()
        image.save(buffer, format="JPEG")  # Use the appropriate format (e.g., JPEG, PNG)
        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # add string formatting required by the endpoint
        return f"data:image/jpeg;base64,{base64_image}"

    image_string = encode_local_image(image_path)
    prompt_with_images = prompt_with_template.replace("<image>", "![]({}) ").format(image_string)

    payload = {
        "inputs": prompt_with_images,
        "parameters": {
            "return_full_text": False,
            "max_new_tokens": 200,
        },
    }

    return json.loads(client.post(json=payload).decode())[0]


headers = {"Content-Type": "application/json", "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}


class VisualQATool(Tool):
    """
    A tool that can answer questions about images using OpenAI's GPT-4 Vision model or Azure Computer Vision.
    """

    name = "visualizer"
    description = "A tool that can answer questions about attached images."
    inputs: ClassVar[dict] = {
        "image_path": {
            "description": "The path to the image on which to answer the question",
            "type": "string",
        },
        "question": {"description": "the question to answer", "type": "string", "nullable": True},
    }
    output_type = "string"

    client = InferenceClient("HuggingFaceM4/idefics2-8b-chatty")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("MODEL_NAME", "gpt-4o")

    def __init__(self):
        self.client = InferenceClient(self.model_name)

    def forward(self, image_path: str, question: Optional[str] = None) -> str:
        add_note = False
        if not question:
            question = "Describe this image in detail, as if you were describing it to someone who cannot see it. Be specific about any text, logos, or objects present."
            add_note = True
        if not isinstance(image_path, str):
            msg = "You should provide at least `image_path` string argument to this tool!"
            raise InvalidImagePathError(msg)

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type or not mime_type.startswith("image"):
            # Try to get from URL if it's a URL and not obviously an image
            if image_path.startswith("http"):
                try:
                    response = requests.head(image_path, allow_redirects=True, timeout=DEFAULT_REQUEST_TIMEOUT)
                    content_type = response.headers.get("content-type")
                    if content_type and content_type.startswith("image"):
                        mime_type = content_type
                    else:
                        msg = f"URL does not appear to be an image. Content-Type: {content_type}"
                        raise VisualQAError(msg)
                except requests.RequestException as e:
                    msg = f"Could not determine content type from URL {image_path}: {e!s}"
                    raise VisualQAError(msg) from e
            else:
                msg = f"File {image_path} does not appear to be an image. Mime type: {mime_type}"
                raise VisualQAError(msg)

        base64_image = self.get_image_from_url(image_path, self.openai_api_key)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                        },
                    ],
                }
            ],
            "max_tokens": 1000,
        }
        response = requests.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        try:
            response.raise_for_status()
            output = response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as http_err:
            msg = f"HTTP error occurred: {http_err} - {response.text}"
            raise OpenAIResponseError(msg) from http_err
        except (KeyError, IndexError, TypeError) as e:
            msg = f"Response format unexpected: {response.json()}"
            raise OpenAIResponseError(msg) from e

        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"
        return output

    def get_image_from_url(self, image_path: str, openai_api_key: Optional[str] = None) -> str:
        """Helper function to get image data from a URL or local path."""
        if image_path.startswith(("http://", "https://")):
            request_kwargs: dict[str, Any] = {}
            if openai_api_key:
                request_kwargs["headers"] = {"Authorization": f"Bearer {openai_api_key}"}
            # Send a HTTP request to the URL
            response = requests.get(image_path, timeout=DEFAULT_REQUEST_TIMEOUT, **request_kwargs)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            extension = mimetypes.guess_extension(content_type) or ""

            # Create downloads directory if it doesn't exist
            downloads_dir = Path("downloads")
            downloads_dir.mkdir(parents=True, exist_ok=True)

            fname = str(uuid.uuid4()) + extension
            download_path = downloads_dir / fname

            with download_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=512):
                    fh.write(chunk)
            logger.info(f"Image downloaded from URL to: {download_path}")
            image_path = str(download_path.resolve())

        with Path(image_path).open("rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _azure_vision_request(self, image_path: str, question: Optional[str] = None) -> str:
        _ = image_path # Acknowledge to satisfy ARG002 for placeholder
        _ = question
        # Placeholder for Azure logic based on common patterns
        # Ensure to handle exceptions and return structure similar to OpenAI part
        try:
            # ... Azure API call logic ...
            # Example:
            # if not self.azure_vision_client:
            #     msg = "Azure Vision client not initialized."
            #     raise VisualQAError(msg)
            #
            # result = self.azure_vision_client.analyze(...) # Placeholder
            # output = result.caption.text if result.caption else "No caption generated by Azure."
            output = "Placeholder Azure output"  # Replace with actual call and result extraction

            if not output:
                msg = "Empty response from Azure OpenAI"  # Or Azure Vision
                raise AzureAIResponseError(msg)

            # Add note if no question was provided (assuming similar logic to OpenAI path)
            if (
                question is None
                or question
                == "Describe this image in detail, as if you were describing it to someone who cannot see it. Be specific about any text, logos, or objects present."
            ):  # check against the default prompt
                output = (
                    f"You did not provide a particular question, so here is a detailed caption for the image: {output}"
                )
            # return output # Moved to else block for TRY300

        except AzureAIResponseError:  # Catch specific Azure error
            raise  # Re-raise if already handled
        except Exception as e:  # Catch other potential errors during Azure processing
            logger.error(f"Error during Azure vision request: {e!s}")
            # It's often better to raise a specific custom error here
            msg = f"Azure vision request failed: {e!s}"
            raise VisualQAError(msg) from e
        else:
            return output  # Moved to else block for TRY300
