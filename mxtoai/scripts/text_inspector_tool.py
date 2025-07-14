from typing import ClassVar

from smolagents import Tool
from smolagents.models import MessageRole, Model

from .mdconvert import FileConversionException, MarkdownConverter, UnsupportedFormatException

# Constants
SHORT_CONTENT_THRESHOLD = 4000


class TextInspectorError(Exception):
    """Base exception for text inspector tool errors."""


class ImageFileError(TextInspectorError):
    """Exception raised when trying to process image files."""


class FileProcessingError(TextInspectorError):
    """Exception raised for general file processing errors."""


class TextInspectorTool(Tool):
    """
    Tool to inspect files as text and ask questions about them.
    """

    name: ClassVar[str] = "inspect_file_as_text"
    description: ClassVar[str] = """
You cannot load files yourself: instead call this tool to read a file as markdown text and ask questions about it.
This tool handles the following file extensions: [".html", ".htm", ".xlsx", ".pptx", ".wav", ".mp3", ".m4a", ".flac", ".pdf", ".docx"], and all other types of text files. IT DOES NOT HANDLE IMAGES."""

    inputs: ClassVar[dict] = {
        "file_path": {
            "description": "The path to the file you want to read as text. Must be a '.something' file, like '.pdf'. If it is an image, use the visualizer tool instead! DO NOT use this tool for an HTML webpage: use the web_search tool instead!",
            "type": "string",
        },
        "question": {
            "description": "[Optional]: Your question, as a natural language sentence. Provide as much context as possible. Do not pass this parameter if you just want to directly return the content of the file.",
            "type": "string",
            "nullable": True,
        },
    }
    output_type: ClassVar[str] = "string"
    md_converter: ClassVar[MarkdownConverter] = MarkdownConverter()

    def __init__(self, model: Model, text_limit: int):
        """
        Initialize the TextInspectorTool.

        Args:
            model: The model to use for processing the text.
            text_limit: The maximum number of characters to process from the file.

        """
        super().__init__()
        self.model = model
        self.text_limit = text_limit

    def forward_initial_exam_mode(self, file_path, question):
        """
        Process the file and return a short caption based on the content.

        Args:
            file_path: Path to the file to be processed.
            question: Optional question to guide the caption generation.

        Returns:
            str: The generated caption or the text content of the file.

        """
        result_text = ""
        try:
            if file_path[-4:] in [".png", ".jpg"]:
                msg = "Cannot use inspect_file_as_text tool with images: use visualizer instead!"
                raise ImageFileError(msg)

            result = self.md_converter.convert(file_path)

            if ".zip" in file_path or not question:
                result_text = result.text_content
            elif len(result.text_content) < SHORT_CONTENT_THRESHOLD:
                result_text = "Document content: " + result.text_content
            else:
                messages = [
                    {
                        "role": MessageRole.SYSTEM,
                        "content": [
                            {
                                "type": "text",
                                "text": "Here is a file:\n### "
                                + str(result.title)
                                + "\n\n"
                                + result.text_content[: self.text_limit],
                            }
                        ],
                    },
                    {
                        "role": MessageRole.USER,
                        "content": [
                            {
                                "type": "text",
                                "text": "Now please write a short, 5 sentence caption for this document, that could help someone asking this question: "
                                + question
                                + "\n\nDon't answer the question yourself! Just provide useful notes on the document",
                            }
                        ],
                    },
                ]
                result_text = self.model(messages).content
        except FileConversionException as e:
            result_text = f"Error converting file: {e!s}"
        except UnsupportedFormatException as e:
            return f"Unsupported file format: {e!s}"
        except ImageFileError as e:
            return f"Image file error: {e!s}"
        except FileProcessingError as e:
            return f"Error processing file: {e!s}"
        except Exception as e:
            return f"Unexpected error processing file: {e!s}"

        return result_text

    def forward(self, file_path, question: str | None = None) -> str:
        """
        Process the file and return a response based on the content and question.

        Args:
            file_path: Path to the file to be processed.
            question: Optional question to guide the response generation.

        Returns:
            str: The generated response or the text content of the file.

        """
        result_text = ""
        try:
            if file_path[-4:] in [".png", ".jpg"]:
                msg = "Cannot use inspect_file_as_text tool with images: use visualizer instead!"
                raise ImageFileError(msg)

            result = self.md_converter.convert(file_path)

            if ".zip" in file_path or not question:
                result_text = result.text_content
            else:
                messages = [
                    {
                        "role": MessageRole.SYSTEM,
                        "content": [
                            {
                                "type": "text",
                                "text": "You will have to write a short caption for this file, then answer this question:"
                                + question,
                            }
                        ],
                    },
                    {
                        "role": MessageRole.USER,
                        "content": [
                            {
                                "type": "text",
                                "text": "Here is the complete file:\n### "
                                + str(result.title)
                                + "\n\n"
                                + result.text_content[: self.text_limit],
                            }
                        ],
                    },
                    {
                        "role": MessageRole.USER,
                        "content": [
                            {
                                "type": "text",
                                "text": "Now answer the question below. Use these three headings: '1. Short answer', '2. Extremely detailed answer', '3. Additional Context on the document and question asked'."
                                + question,
                            }
                        ],
                    },
                ]
                result_text = self.model(messages).content
        except FileConversionException as e:
            result_text = f"Error converting file: {e!s}"
        except UnsupportedFormatException as e:
            return f"Unsupported file format: {e!s}"
        except ImageFileError as e:
            return f"Image file error: {e!s}"
        except FileProcessingError as e:
            return f"Error processing file: {e!s}"
        except Exception as e:
            return f"Unexpected error processing file: {e!s}"

        return result_text
