import base64
import json
import mimetypes
import os
import urllib.parse
from typing import Any, ClassVar, Optional

import requests
from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.tools.mock_jina_service import MockJinaService

# Configure logger
logger = get_logger("research_tool")


class DeepResearchTool(Tool):
    """
    Tool for conducting deep research based on email content using Jina AI's DeepSearch API.
    """

    name: ClassVar[str] = "deep_research"
    description: ClassVar[str] = (
        "Conducts deep research based on email content and attachments to provide comprehensive answers with sources. Use medium reasoning effort for all queries unless user's intent is explicitly requesting for low or high effort."
    )

    # Define output type for the tool
    output_type: ClassVar[str] = "object"  # Returns a dictionary with research findings and sources

    def __init__(self, *, use_mock_service: bool = False):
        """
        Initialize the deep research tool.

        Args:
            use_mock_service: Whether to use the mock service for load testing

        """
        # Log tool initialization
        logger.debug("Initializing DeepResearchTool")

        # Flag to enable URL encoding of messages
        self.should_encode_messages = True

        # Flag for using mock service
        self.use_mock_service = use_mock_service
        self.mock_service = MockJinaService() if use_mock_service else None

        # Define input schema before super().__init__() to ensure proper validation
        self.inputs = {
            "query": {"type": "string", "description": "The research query or question to investigate"},
            "context": {
                "type": "string",
                "description": "Additional context from email thread or other sources",
                "nullable": True,
            },
            "memory_attachments": {
                "type": "object",
                "description": "Dict mapping filename to (content, mime_type) tuples for in-memory files - preferred method for attachment processing",
                "nullable": True,
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "mime_type": {"type": "string"},
                    },
                    "required": ["content", "mime_type"],
                },
            },
            "thread_messages": {
                "type": "array",
                "description": "Previous messages in the email thread for context",
                "nullable": True,
                "items": {
                    "type": "object",
                    "properties": {"role": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["role", "content"],
                },
            },
            "stream": {
                "type": "boolean",
                "description": "Whether to stream the response",
                "default": False,
                "nullable": True,
            },
            "reasoning_effort": {
                "type": "string",
                "description": "Level of reasoning effort ('low', 'medium', 'high')",
                "enum": ["low", "medium", "high"],
                "default": "medium",
                "nullable": True,
            },
        }

        # Log schema before initialization
        logger.debug(f"Tool schema before initialization: {json.dumps(self.inputs, indent=2)}")

        try:
            super().__init__()
            logger.debug("Successfully initialized base Tool class")
        except Exception as e:
            logger.error(f"Error initializing base Tool class: {e!s}")
            raise

        # Check for JINA API key
        self.api_key = os.getenv("JINA_API_KEY")
        if not self.api_key:
            logger.warning("JINA_API_KEY not found. Research functionality will be limited.")

        # Jina AI DeepSearch API configuration
        self.api_url = "https://deepsearch.jina.ai/v1/chat/completions"
        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

        # Flag to track if deep research is explicitly requested
        self.deep_research_enabled = False

        # Maximum file size for attachments (10MB in bytes)
        self.max_file_size = 10 * 1024 * 1024

        # Log successful initialization
        logger.debug("DeepResearchTool initialization completed")

    def enable_deep_research(self):
        """Enable deep research functionality."""
        self.deep_research_enabled = True
        logger.info("Deep research functionality enabled")

    def disable_deep_research(self):
        """Disable deep research functionality."""
        self.deep_research_enabled = False
        logger.info("Deep research functionality disabled")

    def _encode_content_from_memory(
        self, content: bytes, filename: str, mime_type: str | None = None
    ) -> Optional[dict[str, Any]]:
        """
        Encode file content from memory to base64 data URI format for Jina API.

        Args:
            content: File content as bytes
            filename: Name of the file for context
            mime_type: MIME type of the content (will be guessed if not provided)

        Returns:
            Dict containing file data in Jina API format or None if content is too large/invalid

        """
        try:
            # Check content size
            if len(content) > self.max_file_size:
                logger.warning(f"Content for {filename} exceeds 10MB limit, skipping")
                return None

            # Use provided mime type or guess from filename
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(filename)
                if not mime_type:
                    mime_type = "application/octet-stream"

            # Encode content
            encoded = base64.b64encode(content).decode("utf-8")
            result = {"type": "file", "data": f"data:{mime_type};base64,{encoded}", "mimeType": mime_type}
        except Exception as e:
            logger.error(f"Error encoding content for {filename}: {e!s}")
            return None
        else:
            return result

    def _encode_file(self, file_path: str) -> Optional[dict[str, Any]]:
        """
        DEPRECATED: This method has been removed for security reasons.
        Use memory_attachments with _encode_content_from_memory instead.
        """
        logger.warning(f"_encode_file is deprecated and removed for security. Skipping file: {file_path}")
        return None

    def _encode_text(self, text: str) -> str:
        """
        URL encode text content to handle special characters.

        Args:
            text: Text content to encode

        Returns:
            URL encoded text

        """
        if self.should_encode_messages:
            return urllib.parse.quote(text)
        return text

    def _prepare_messages(
        self,
        query: str,
        context: Optional[str] = None,
        memory_attachments: Optional[dict[str, tuple[bytes, str]]] = None,
        thread_messages: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, Any]]:
        """
        Prepare messages for Jina API including files and context.

        Args:
            query: The research query
            context: Additional context
            memory_attachments: Dict mapping filename to (content, mime_type) tuples for in-memory files
            thread_messages: Previous messages in thread

        Returns:
            List of messages in Jina API format with a single message containing all content

        """
        # Ensure parameters are properly initialized
        memory_attachments = memory_attachments if isinstance(memory_attachments, dict) else {}
        thread_messages = thread_messages if isinstance(thread_messages, list) else []

        # Prepare content array for the single message
        message_content = []

        # Add query as text (encoded if enabled)
        message_content.append({"type": "text", "text": self._encode_text(query)})

        # Add thread messages content if available
        if thread_messages:
            thread_context = "\nPrevious Messages:\n" + "\n".join(
                f"{msg['role']}: {msg['content']}" for msg in thread_messages
            )
            message_content.append({"type": "text", "text": self._encode_text(thread_context)})

        # Add context if available
        if context:
            message_content.append({"type": "text", "text": self._encode_text(f"\nAdditional Context:\n{context}")})

        # Process memory attachments
        if memory_attachments:
            for filename, (content, mime_type) in memory_attachments.items():
                file_data = self._encode_content_from_memory(content, filename, mime_type)
                if file_data:
                    message_content.append(file_data)
                    logger.debug(f"Added attachment {filename} from memory for deep research")

        # Return a single message with all content
        return [{"role": "user", "content": message_content}]

    def _process_stream_response(self, response):
        """
        Process a streaming response from the API.

        Args:
            response: The streaming response object

        Returns:
            dict: Processed results containing findings and metadata

        """
        findings = []
        annotations = []
        visited_urls = set()
        read_urls = set()
        timestamp = response.headers.get("date")
        current_type = None  # Track current message type (think/text)

        try:
            for line in response.iter_lines():
                if not line:
                    continue

                try:
                    # Remove 'data: ' prefix if present and decode
                    line_str = line.decode("utf-8")
                    line_str = line_str.removeprefix("data: ")

                    # Skip empty messages
                    if line_str.strip() in ("", "[DONE]"):
                        continue

                    data = json.loads(line_str)

                    # Handle error messages
                    if "error" in data:
                        error_msg = data["error"].get("message", str(data["error"]))
                        logger.error(f"API returned error: {error_msg}")
                        return {"error": error_msg}

                    # Process choices
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "delta" in choice:
                            delta = choice["delta"]

                            # Handle role change
                            if "role" in delta:
                                continue  # Skip role messages

                            # Handle content type change
                            if "type" in delta:
                                current_type = delta["type"]
                                # Handle opening/closing think tags
                                if "content" in delta and delta["content"] in ("<think>", "</think>"):
                                    continue

                            # Handle content
                            if delta.get("content") and current_type != "think":
                                # Only append text content (ignore think content)
                                findings.append(delta["content"])

                            # Handle annotations
                            if "annotations" in delta:
                                annotations.extend(delta["annotations"])

                    # Handle URLs from the final chunk
                    if "visitedURLs" in data:
                        visited_urls.update(data["visitedURLs"])
                    if "readURLs" in data:
                        read_urls.update(data["readURLs"])

                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode streaming response line: {line_str}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing stream chunk: {e!s}")
                    continue

            # Combine all findings into a single string
            combined_findings = "".join(findings).strip()
            if not combined_findings:
                return {"error": "No content received in streaming response"}

            return {
                "findings": combined_findings,
                "annotations": annotations,
                "visited_urls": list(visited_urls),
                "read_urls": list(read_urls),
                "timestamp": timestamp,
            }

        except Exception as e:
            error_msg = f"Error processing streaming response: {e!s}"
            logger.error(error_msg)
            return {"error": error_msg}

    def _structure_research_content(self, content: str) -> str:
        """
        Pass through research content without adding extra structuring for now.
        Relies on Jina AI providing reasonably structured markdown.

        Args:
            content: Raw research content

        Returns:
            Original research content

        """
        logger.debug("Skipping TOC generation, returning raw content structure.")
        return content

    def _format_research_content(
        self, content: str, annotations: list[dict[str, Any]], visited_urls: list[str], read_urls: list[str]
    ) -> str:
        """
        Format research content with proper citations and structure.

        Args:
            content: Raw research content
            annotations: List of annotations with citations
            visited_urls: List of all URLs visited
            read_urls: List of URLs actually read

        Returns:
            Formatted research content with citations and references

        """
        try:
            # Create a mapping of URLs to citation numbers
            url_citations = {}
            citation_counter = 1

            # First process read URLs as they're more relevant
            for url in read_urls:
                if url not in url_citations:
                    url_citations[url] = citation_counter
                    citation_counter += 1

            # Then process visited URLs
            for url in visited_urls:
                if url not in url_citations:
                    url_citations[url] = citation_counter
                    citation_counter += 1

            # Format the content sections
            sections = content.split("\n\n")
            formatted_sections = []

            # Process each section
            for section in sections:
                if not section.strip():
                    continue

                # Format citations in the section
                formatted_section = section

                # Replace URL citations with numbered citations
                for annotation in annotations:
                    if annotation.get("type") == "url_citation":
                        url_info = annotation.get("url_citation", {})
                        url = url_info.get("url", "")
                        if url in url_citations:
                            citation_num = url_citations[url]
                            # Replace the citation in the text
                            formatted_section = formatted_section.replace(
                                f"|^{url_info.get('id', '')}]", f"[{citation_num}]"
                            )

                formatted_sections.append(formatted_section)

            # Join formatted sections
            formatted_content = "\n\n".join(formatted_sections)

            # Structure the content
            formatted_content = self._structure_research_content(formatted_content)

            # Add references section
            references = ["\n\n### References"]
            for url, citation_num in sorted(url_citations.items(), key=lambda x: x[1]):
                # Find annotation for this URL to get title and date
                url_annotation = next(
                    (
                        a
                        for a in annotations
                        if a.get("type") == "url_citation" and a.get("url_citation", {}).get("url") == url
                    ),
                    None,
                )

                if url_annotation:
                    url_info = url_annotation.get("url_citation", {})
                    title = url_info.get("title", url)  # Use URL as title if missing
                    date_str = url_info.get("dateTime", "")
                    retrieved_info = f" Retrieved on {date_str.split()[0]}" if date_str else ""  # Add date if available
                    # Corrected reference formatting to standard Markdown
                    references.append(f"{citation_num}. {title}.{retrieved_info} from [{url}]({url})")
                else:
                    # Fallback if no annotation found (less likely but safe)
                    # Corrected reference formatting to standard Markdown
                    references.append(f"{citation_num}. Retrieved from [{url}]({url})")

            # Add references to the content
            formatted_content += "\n".join(references)
            result = formatted_content
        except Exception as e:
            logger.error(f"Error formatting research content: {e!s}")
            # Return original content if formatting fails
            return content
        else:
            return result

    def forward(
        self,
        query: str,
        context: Optional[str] = None,
        memory_attachments: Optional[dict[str, tuple[bytes, str]]] = None,
        thread_messages: Optional[list[dict[str, str]]] = None,
        *,
        stream: bool = False,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """
        Perform deep research on a query with context and attachments.

        Args:
            query: The research query to investigate
            context: Optional additional context
            memory_attachments: Dict mapping filename to (content, mime_type) tuples for in-memory files
            thread_messages: Optional list of previous messages
            stream: Whether to stream the response (default False)
            reasoning_effort: Level of reasoning effort ("low", "medium", "high")

        Returns:
            Research results including findings, citations, and sources

        """
        # Ensure parameters are properly initialized
        memory_attachments = memory_attachments if isinstance(memory_attachments, dict) else {}
        thread_messages = thread_messages if isinstance(thread_messages, list) else []

        # Log memory attachment processing
        if memory_attachments:
            total_size = sum(len(content) for content, _ in memory_attachments.values())
            logger.info(f"Processing {len(memory_attachments)} memory attachments, total size: {total_size} bytes")

        result = {}

        if not self.api_key and not self.use_mock_service:
            result = {
                "query": query,
                "findings": "Research functionality is not available. JINA_API_KEY is required.",
                "error": "API key not configured",
            }
        elif not self.deep_research_enabled:
            logger.info("Deep research is disabled. Enable it explicitly before use.")
            result = {
                "query": query,
                "findings": "Deep research functionality is currently disabled. Enable it explicitly before use.",
                "error": "Deep research disabled",
            }
        else:
            try:
                if self.use_mock_service:
                    logger.info("Using mock Jina service for load testing")
                    response_data = self.mock_service.process_request(
                        query=query, stream=stream, reasoning_effort=reasoning_effort
                    )

                    if stream:
                        # Process streaming response from mock service
                        stream_results = self._process_stream_response(response_data)
                        if "error" in stream_results:
                            result = {
                                "query": query,
                                "findings": f"An error occurred during research: {stream_results['error']}",
                                "error": stream_results["error"],
                            }
                        else:
                            result = {"query": query, **stream_results}
                    else:
                        # Process non-streaming response from mock service
                        content = response_data["choices"][0]["message"]["content"]
                        annotations = response_data["choices"][0]["message"]["annotations"]

                        # Format content with proper citations
                        formatted_content = self._format_research_content(
                            content=content,
                            annotations=annotations,
                            visited_urls=response_data.get("visitedURLs", []),
                            read_urls=response_data.get("readURLs", []),
                        )

                        result = {
                            "query": query,
                            "findings": formatted_content,
                            "annotations": annotations,
                            "visited_urls": response_data.get("visitedURLs", []),
                            "read_urls": response_data.get("readURLs", []),
                            "timestamp": response_data.get("timestamp"),
                            "usage": response_data.get("usage", {}),
                            "num_urls": response_data.get("numURLs", 0),
                        }
                else:
                    # Prepare messages including files and context
                    messages = self._prepare_messages(
                        query=query, context=context, memory_attachments=memory_attachments, thread_messages=thread_messages
                    )

                    # Prepare request data
                    data = {
                        "model": "jina-deepsearch-v1",
                        "messages": messages,
                        "stream": stream,
                        "reasoning_effort": reasoning_effort,
                        "no_direct_answer": False,
                    }

                    # Log the complete request data
                    logger.info("Request data being sent to Jina AI:")
                    logger.info(f"URL: {self.api_url}")
                    logger.info(f"Headers: {json.dumps({k: v for k, v in self.headers.items() if k != 'Authorization'})}")
                    logger.info(f"Request Body: {json.dumps(data, indent=2)}")

                    logger.info(f"Sending research query to Jina AI: {query}")

                    # Make API request
                    response = requests.post(
                        self.api_url,
                        headers=self.headers,
                        data=json.dumps(data),
                        stream=stream,
                        timeout=600,  # 10 minute timeout
                    )

                    logger.debug(f"Response status: {response.status_code}")

                    if not response.ok:
                        error_msg = f"API request failed with status {response.status_code}"
                        logger.error(error_msg)
                        result = {
                            "query": query,
                            "findings": f"An error occurred during research: {error_msg}",
                            "error": error_msg,
                        }
                    else:
                        try:
                            if not stream:
                                # Process non-streaming response
                                response_data = response.json()
                                logger.debug(f"Non-streaming response data: {json.dumps(response_data, indent=2)}")

                                # Check for error in the response content
                                if (
                                    response_data.get("choices")
                                    and response_data["choices"][0].get("message", {}).get("type") == "error"
                                ):
                                    error_msg = response_data["choices"][0]["message"].get("content", "Unknown error from API")
                                    logger.error(f"API returned error in response: {error_msg}")
                                    result = {
                                        "query": query,
                                        "findings": f"An error occurred during research: {error_msg}",
                                        "error": error_msg,
                                    }
                                elif not response_data.get("choices") or not response_data["choices"][0].get("message"):
                                    error_msg = "Invalid response format from API"
                                    logger.error(error_msg)
                                    result = {
                                        "query": query,
                                        "findings": f"An error occurred during research: {error_msg}",
                                        "error": error_msg,
                                    }
                                else:
                                    # Extract message content and annotations
                                    message = response_data["choices"][0]["message"]
                                    content = message.get("content", "")
                                    annotations = message.get("annotations", [])

                                    # Format content with proper citations
                                    formatted_content = self._format_research_content(
                                        content=content,
                                        annotations=annotations,
                                        visited_urls=response_data.get("visitedURLs", []),
                                        read_urls=response_data.get("readURLs", []),
                                    )

                                    result = {
                                        "query": query,
                                        "findings": formatted_content,
                                        "annotations": annotations,
                                        "visited_urls": response_data.get("visitedURLs", []),
                                        "read_urls": response_data.get("readURLs", []),
                                        "timestamp": response.headers.get("date"),
                                        "usage": response_data.get("usage", {}),
                                        "num_urls": response_data.get("numURLs", len(response_data.get("visitedURLs", []))),
                                    }
                            else:
                                # Process streaming response
                                stream_results = self._process_stream_response(response)
                                if "error" in stream_results:
                                    result = {
                                        "query": query,
                                        "findings": f"An error occurred during research: {stream_results['error']}",
                                        "error": stream_results["error"],
                                    }
                                else:
                                    result = {
                                        "query": query,
                                        "findings": stream_results["findings"],
                                        "annotations": stream_results.get("annotations", []),
                                        "visited_urls": stream_results.get("visited_urls", []),
                                        "read_urls": stream_results.get("read_urls", []),
                                        "timestamp": stream_results.get("timestamp") or response.headers.get("date"),
                                    }
                        except Exception as e:
                            error_msg = f"Error processing response: {e}"
                            logger.error(error_msg)
                            result = {
                                "query": query,
                                "findings": f"An error occurred during research: {error_msg}",
                                "error": error_msg,
                            }
            except Exception as e:
                error_msg = f"Unexpected error during research: {e}"
                logger.error(error_msg)
                result = {
                    "query": query,
                    "findings": f"An error occurred during research: {error_msg}",
                    "error": error_msg,
                }

        return result
