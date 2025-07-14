import base64
import mimetypes
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar

import requests
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from PIL import Image
from smolagents import Tool, tool

from mxtoai._logging import get_logger


# Lazy import for transformers to avoid torch import issues during test discovery
def _get_auto_processor():
    """Lazy import of AutoProcessor to avoid early torch imports."""
    try:
        from transformers import AutoProcessor  # NOQA: PLC0415
    except ImportError as e:
        msg = "transformers package is required for HuggingFace models"
        raise ImportError(msg) from e
    else:
        return AutoProcessor


load_dotenv(override=True)

# Configure logger
logger = get_logger("visual_qa")


def encode_image(image_path: str) -> str:
    """
    Encode an image to a base64 string.

    Args:
        image_path: Path to the image file or URL

    Returns:
        str: Base64 encoded image string

    """
    if image_path.startswith("http"):
        # Remote image
        response = requests.get(image_path, timeout=30)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")
    # Local image
    with Path(image_path).open("rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def resize_image(image_path: str, max_dimension: int = 1024) -> str:
    """
    Resize an image to fit within max_dimension while maintaining aspect ratio.

    Args:
        image_path: Path to the image file
        max_dimension: Maximum width or height in pixels

    Returns:
        str: Path to the resized image file

    """
    image = Image.open(image_path)

    # Calculate new dimensions
    width, height = image.size
    if width > height:
        new_width = min(width, max_dimension)
        new_height = int(height * (new_width / width))
    else:
        new_height = min(height, max_dimension)
        new_width = int(width * (new_height / height))

    # Resize image
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Save resized image
    resized_path = f"{image_path}_resized_{uuid.uuid4().hex}.jpg"
    resized_image.save(resized_path, "JPEG", quality=90)

    return resized_path


def process_images_and_text(image_path: str, query: str, client: InferenceClient):
    """
    Process images and text using the IDEFICS model.

    Args:
        image_path: Path to the image file.
        query: The question to ask about the image.
        client: Inference client for the model.

    """
    AutoProcessor = _get_auto_processor()  # NOQA: N806

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

    # Prepare the request
    message = {
        "role": "user",
        "content": prompt_with_images,
    }

    # Initialize the client
    response = client.chat_completion(
        messages=[message],
        max_tokens=1000,
        temperature=0.7,
    )

    # Extract the response
    if response and response.choices:
        return response.choices[0].message.content
    return "No response received from the model."


class AzureVisualizerTool(Tool):
    """Tool for analyzing images using Azure OpenAI vision models."""

    name: ClassVar[str] = "azure_visualizer"
    description: ClassVar[str] = (
        "A tool that can answer questions about attached images using Azure OpenAI vision models."
    )
    inputs: ClassVar[dict] = {
        "image_path": {
            "description": "The path to the image on which to answer the question. This should be a local path to downloaded image.",
            "type": "string",
        },
        "question": {"description": "The question to answer about the image", "type": "string", "nullable": True},
    }
    output_type: ClassVar[str] = "string"

    def __init__(self, model: Any):
        """
        Initialize the Azure Visualizer tool.

        Args:
            model: The model to use for image analysis (should be RoutedLiteLLMModel or similar)

        """
        super().__init__()
        self.model = model
        logger.debug("AzureVisualizerTool initialized with model")

    def forward(self, image_path: str, question: str | None = None) -> str:
        """
        Process the image and return analysis based on the question.

        Args:
            image_path: The path to the image on which to answer the question
            question: The question to answer about the image

        Returns:
            str: The analysis or caption of the image

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

            # Create messages for the model
            messages = [{"role": "user", "content": content}]

            logger.info("Sending image to Azure OpenAI for analysis")

            # Use the model to generate response
            response = self.model(messages, max_tokens=1000)

            # Extract content from response
            output = response.content if hasattr(response, "content") else str(response)

            if not output:
                msg = "Empty response from Azure OpenAI"
                raise ValueError(msg)

            # Add note if no question was provided
            if add_note:
                output = (
                    f"You did not provide a particular question, so here is a detailed caption for the image: {output}"
                )

        except Exception as e:
            # Handle image too large error by resizing and retrying
            if "image too large" in str(e).lower():
                try:
                    logger.info("Image too large, resizing and retrying...")
                    resized_image_path = resize_image(image_path)

                    # Retry with resized image
                    mime_type, _ = mimetypes.guess_type(resized_image_path)
                    if not mime_type:
                        mime_type = "image/jpeg"

                    base64_image = encode_image(resized_image_path)
                    content = [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                    ]

                    messages = [{"role": "user", "content": content}]

                    response = self.model(messages, max_tokens=1000)

                    output = response.content if hasattr(response, "content") else str(response)

                    if not output:
                        msg = "Empty response from Azure OpenAI after resize"
                        raise ValueError(msg)

                    if add_note:
                        output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

                except Exception as retry_e:
                    logger.error(f"Error in azure_visualizer retry: {retry_e}")
                    return f"Error processing image: {retry_e!s}"
                else:
                    return output

            logger.exception("Error in azure_visualizer")
            return f"Error processing image: {e!s}"
        else:
            return output


class HuggingFaceVisualizerTool(Tool):
    """Tool for visual question answering using HuggingFace models."""

    name: ClassVar[str] = "huggingface_visualizer"
    description: ClassVar[str] = (
        "A tool that can answer questions about attached images using HuggingFace vision models."
    )
    inputs: ClassVar[dict] = {
        "image_path": {
            "description": "The path to the image on which to answer the question",
            "type": "string",
        },
        "question": {"description": "the question to answer", "type": "string", "nullable": True},
    }
    output_type: ClassVar[str] = "string"

    def __init__(self, model_name: str = "HuggingFaceM4/idefics2-8b-chatty"):
        """
        Initialize the HuggingFace Visualizer tool.

        Args:
            model_name: The HuggingFace model to use for image analysis

        """
        super().__init__()
        self.client = InferenceClient(model_name)
        logger.debug(f"HuggingFaceVisualizerTool initialized with model: {model_name}")

    def forward(self, image_path: str, question: str | None = None) -> str:
        """
        Process the image and return a short caption based on the content.

        Args:
            image_path: The path to the image on which to answer the question
            question: The question to answer

        Returns:
            str: The generated caption or the text content of the file

        """
        add_note = False
        if not question:
            add_note = True
            question = "Please write a detailed caption for this image."

        try:
            output = process_images_and_text(image_path, question, self.client)
        except Exception as e:
            if "Payload Too Large" in str(e):
                new_image_path = resize_image(image_path)
                output = process_images_and_text(new_image_path, question, self.client)
            else:
                raise

        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

        return output


class OpenAIVisualizerTool(Tool):
    """Tool for analyzing images using OpenAI vision models via direct API calls."""

    name: ClassVar[str] = "openai_visualizer"
    description: ClassVar[str] = "A tool that can answer questions about attached images using OpenAI vision models."
    inputs: ClassVar[dict] = {
        "image_path": {
            "description": "The path to the image on which to answer the question",
            "type": "string",
        },
        "question": {"description": "the question to answer", "type": "string", "nullable": True},
    }
    output_type: ClassVar[str] = "string"

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        """
        Initialize the OpenAI Visualizer tool.

        Args:
            api_key: OpenAI API key (if None, will use OPENAI_API_KEY env var)
            model: OpenAI model to use for image analysis

        """
        super().__init__()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

        if not self.api_key:
            msg = "OpenAI API key is required"
            raise ValueError(msg)

        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        logger.debug(f"OpenAIVisualizerTool initialized with model: {model}")

    def forward(self, image_path: str, question: str | None = None) -> str:
        """
        Process the image and return analysis based on the question.

        Args:
            image_path: The path to the image on which to answer the question
            question: The question to answer

        Returns:
            str: The analysis or caption of the image

        """
        add_note = False
        if not question:
            add_note = True
            question = "Please write a detailed caption for this image."

        if not isinstance(image_path, str):
            msg = "You should provide at least `image_path` string argument to this tool!"
            raise TypeError(msg)

        mime_type, _ = mimetypes.guess_type(image_path)
        base64_image = encode_image(image_path)

        payload = {
            "model": self.model,
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

        response = requests.post(
            "https://api.openai.com/v1/chat/completions", headers=self.headers, json=payload, timeout=30
        )

        try:
            output = response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            msg = f"Response format unexpected: {response.json()}"
            raise ValueError(msg) from e

        if add_note:
            output = f"You did not provide a particular question, so here is a detailed caption for the image: {output}"

        return output


# Legacy function-based tools for backward compatibility
# These are now deprecated and will be removed in a future version


@tool
def visualizer(image_path: str, question: str | None = None) -> str:
    """
    A tool that can answer questions about attached images.

    DEPRECATED: Use OpenAIVisualizerTool instead.

    Args:
        image_path: The path to the image on which to answer the question. This should be a local path to downloaded image.
        question: The question to answer.

    """
    logger.warning("visualizer function is deprecated. Use OpenAIVisualizerTool instead.")

    # Create temporary instance for backward compatibility
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Error: OpenAI API key not found. Please set OPENAI_API_KEY environment variable."

    tool = OpenAIVisualizerTool(api_key=api_key)
    return tool.forward(image_path, question)


@tool
def azure_visualizer(_image_path: str, _question: str | None = None) -> str:
    """
    A tool that can answer questions about attached images using Azure OpenAI.

    DEPRECATED: Use AzureVisualizerTool instead.

    Args:
        _image_path: The path to the image on which to answer the question. This should be a local path to downloaded image.
        _question: The question to answer.

    """
    logger.warning("azure_visualizer function is deprecated. Use AzureVisualizerTool instead.")

    # This is a fallback implementation - in practice, the tool mapping should use AzureVisualizerTool
    return "Error: azure_visualizer function is deprecated. Please use AzureVisualizerTool with proper model initialization."


# Backward compatibility class alias
VisualQATool = HuggingFaceVisualizerTool
