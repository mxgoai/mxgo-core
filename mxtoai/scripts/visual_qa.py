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
from litellm import completion
from PIL import Image
from smolagents import Tool, tool

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


# Function to encode the image
def encode_image(image_path):
    if image_path.startswith("http"):
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        request_kwargs = {
            "headers": {"User-Agent": user_agent},
            "stream": True,
        }

        # Send a HTTP request to the URL
        response = requests.get(image_path, **request_kwargs)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")

        extension = mimetypes.guess_extension(content_type)
        if extension is None:
            extension = ".download"

        fname = str(uuid.uuid4()) + extension
        download_path = os.path.abspath(os.path.join("downloads", fname))

        with open(download_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=512):
                fh.write(chunk)

        image_path = download_path

    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


headers = {"Content-Type": "application/json", "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}


def resize_image(image_path):
    img = Image.open(image_path)
    width, height = img.size
    img = img.resize((int(width / 2), int(height / 2)))
    new_image_path = f"resized_{image_path}"
    img.save(new_image_path)
    return new_image_path


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


@tool
def visualizer(image_path: str, question: Optional[str] = None) -> str:
    """
    A tool that can answer questions about attached images.

    Args:
        image_path: The path to the image on which to answer the question. This should be a local path to downloaded image.
        question: The question to answer.

    """
    add_note = False
    if not question:
        add_note = True
        question = "Please write a detailed caption for this image."
    if not isinstance(image_path, str):
        msg = "You should provide at least `image_path` string argument to this tool!"
        raise Exception(msg)

    mime_type, _ = mimetypes.guess_type(image_path)
    base64_image = encode_image(image_path)

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
def azure_visualizer(image_path: str, question: Optional[str] = None) -> str:
    """
    A tool that can answer questions about attached images using Azure OpenAI.

    Args:
        image_path: The path to the image on which to answer the question. This should be a local path to downloaded image.
        question: The question to answer.

    """
    add_note = False
    if not question:
        add_note = True
        question = "Please write a detailed caption for this image."

    try:
        # Get image MIME type
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"  # Default to JPEG if can't determine

        # Encode the image to base64
        base64_image = encode_image(image_path)

        # Format the content for the Azure OpenAI API
        content = [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
        ]

        # Get Azure OpenAI configuration
        model = f"azure/{os.getenv('MODEL_NAME', 'gpt-4o')}"
        api_key = os.getenv("MODEL_API_KEY")
        api_base = os.getenv("MODEL_ENDPOINT")
        api_version = os.getenv("MODEL_API_VERSION")

        logger.info(f"Sending image to Azure OpenAI model: {model}")
        # Call Azure OpenAI using litellm
        response = completion(
            model=model,
            messages=[{"role": "user", "content": content}],
            api_key=api_key,
            api_base=api_base,
            api_version=api_version,
            max_tokens=1000,
        )

        # Extract content from response
        if hasattr(response, "choices") and response.choices:
            if hasattr(response.choices[0], "message") and hasattr(response.choices[0].message, "content"):
                output = response.choices[0].message.content
            else:
                # Fallback if direct access doesn't work
                output = response.choices[0].get("message", {}).get("content", "")
        else:
            # Handle unusual response format
            output = str(response)

        if not output:
            msg = "Empty response from Azure OpenAI"
            raise Exception(msg)

        # Add note if no question was provided
        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

        return output

    except Exception as e:
        logger.error(f"Error in azure_visualizer: {e!s}")

        # Try resizing the image if it might be too large
        if "too large" in str(e).lower() or "payload" in str(e).lower():
            try:
                new_image_path = resize_image(image_path)
                return azure_visualizer(new_image_path, question)
            except Exception as resize_error:
                logger.error(f"Error resizing image: {resize_error!s}")

        return f"Error processing image: {e!s}"
