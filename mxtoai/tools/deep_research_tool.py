import base64
import json
import mimetypes
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.tools.mock_jina_service import MockJinaService

# Configure logger
logger = get_logger("research_tool")


class DeepResearchTool(Tool):
    """
    Tool for conducting deep research based on email content using Jina AI's DeepSearch API.
    """

    name = "deep_research"
    description = "Conducts deep research based on email content and attachments to provide comprehensive answers with sources. Use medium reasoning effort for all queries unless user's intent is explicitly requesting for low or high effort."

    # Define output type for the tool
    output_type = "object"  # Returns a dictionary with research findings and sources

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
            "attachments": {
                "type": "array",
                "description": "List of file attachments to include in research",
                "nullable": True,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "type": {"type": "string"},
                        "filename": {"type": "string"},
                    },
                    "required": ["path", "type", "filename"],
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

    def _encode_file(self, file_path: str) -> Optional[dict[str, Any]]:
        """
        Encode a file to base64 data URI format for Jina API.

        Args:
            file_path: Path to the file

        Returns:
            Dict containing file data in Jina API format or None if file is too large/invalid

        """
        try:
            # Check file size
            file_size = Path(file_path).stat().st_size
            if file_size > self.max_file_size:
                logger.warning(f"File {file_path} exceeds 10MB limit, skipping")
                return None

            # Get mime type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            # Read and encode file
            with Path(file_path).open("rb") as f:
                file_data = f.read()
                encoded = base64.b64encode(file_data).decode("utf-8")

        except Exception as e:
            logger.error(f"Error encoding file {file_path}: {e!s}")
            return None
        else:
            return {"type": "file", "data": f"data:{mime_type};base64,{encoded}", "mimeType": mime_type}

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
        attachments: Optional[list[dict[str, Any]]] = None,
        thread_messages: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, Any]]:
        """
        Prepare messages for Jina API including files and context.

        Args:
            query: The research query
            context: Additional context
            attachments: List of file attachments
            thread_messages: Previous messages in thread

        Returns:
            List of messages in Jina API format with a single message containing all content

        """
        # Ensure array parameters are properly initialized
        attachments = attachments if isinstance(attachments, list) else []
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

        # Add encoded files
        if attachments:
            for attachment in attachments:
                file_data = self._encode_file(attachment["path"])
                if file_data:
                    message_content.append(file_data)

        # Return a single message with all content
        return [{"role": "user", "content": message_content}]

    def _process_delta_in_stream(
        self, delta: dict, current_type_holder: list[Optional[str]], findings: list[str], annotations: list[dict[str, Any]]
    ) -> None:
        """Processes the 'delta' part of a stream message."""
        # Handle role change - typically skip these
        if "role" in delta:
            return

        # Handle content type change (e.g., think, text)
        if "type" in delta:
            current_type_holder[0] = delta["type"]
            # Skip specific content markers like <think> or </think> if they are part of type change signal
            if "content" in delta and delta["content"] in ("<think>", "</think>"):
                return # Or continue, depending on desired behavior for these markers

        # Handle actual content, append if not in 'think' mode
        if delta.get("content") and current_type_holder[0] != "think":
            findings.append(delta["content"])

        # Handle annotations
        if "annotations" in delta:
            annotations.extend(delta["annotations"])

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
                            # Use a list to pass current_type by reference to be modifiable by the helper
                            current_type_holder = [current_type]
                            self._process_delta_in_stream(choice["delta"], current_type_holder, findings, annotations)
                            current_type = current_type_holder[0] # Update current_type from the holder

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

    def _build_url_citation_map(self, read_urls: list[str], visited_urls: list[str]) -> dict[str, int]:
        """Builds a map of URLs to citation numbers."""
        url_citations: dict[str, int] = {}
        citation_counter = 1
        # Prioritize read URLs for citation numbering
        for url in read_urls:
            if url not in url_citations:
                url_citations[url] = citation_counter
                citation_counter += 1
        # Add other visited URLs
        for url in visited_urls:
            if url not in url_citations:
                url_citations[url] = citation_counter
                citation_counter += 1
        return url_citations

    def _apply_annotations_to_section(
        self, section_text: str, annotations: list[dict[str, Any]], url_citations_map: dict[str, int]
    ) -> str:
        """Applies URL citations to a single section of text based on annotations."""
        formatted_section = section_text
        for annotation in annotations:
            if annotation.get("type") == "url_citation":
                url_info = annotation.get("url_citation", {})
                url = url_info.get("url", "")
                original_citation_id = url_info.get("id", "")
                if url in url_citations_map:
                    citation_num = url_citations_map[url]
                    # Ensure the original citation pattern is specific enough to avoid wrong replacements
                    # The pattern looked for was |^id], e.g., |^abc-123]
                    formatted_section = formatted_section.replace(f"|^{original_citation_id}]", f"[{citation_num}]")
        return formatted_section

    def _generate_references_markdown(self, url_citations_map: dict[str, int]) -> str:
        """Generates the markdown for the references section."""
        if not url_citations_map:
            return ""

        references_md_parts = ["\n\n## References:"]
        # Sort by citation number for ordered references
        for url, num in sorted(url_citations_map.items(), key=lambda item: item[1]):
            references_md_parts.append(f"{num}. {url}")
        return "\n".join(references_md_parts)

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
            url_citations = self._build_url_citation_map(read_urls, visited_urls)

            # Format the content sections
            sections = content.split("\n\n")
            formatted_sections = []

            # Process each section
            for section in sections:
                if not section.strip():
                    continue
                formatted_section = self._apply_annotations_to_section(section, annotations, url_citations)
                formatted_sections.append(formatted_section)

            # Combine formatted sections
            main_formatted_content = "\n\n".join(formatted_sections)

            # Add references section
            references_md = self._generate_references_markdown(url_citations)

            final_content = main_formatted_content + references_md

            # Ensure all links in the final content are valid markdown links
            # This step might be complex and depends on Jina's output format.
            # For now, assuming Jina produces markdown-compatible links or the citation replacement handles it.
            # If Jina links are like `[text](|^id])`, the replacement above handles it.
            # If Jina links are just bare URLs that need to be linkified, that's another step.

            return final_content.strip()
        except Exception as e:
            logger.error(f"Error formatting research content: {e!s}")
            # Fallback to raw content if formatting fails
            return content

    def _validate_forward_params(self, reasoning_effort: str) -> Optional[dict[str, Any]]:
        """Validates parameters for the forward method."""
        if reasoning_effort not in ["low", "medium", "high"]:
            logger.error(f"Invalid reasoning_effort: {reasoning_effort}")
            return {
                "status": "error",
                "error": "Invalid reasoning_effort parameter. Must be one of 'low', 'medium', 'high'.",
                "findings": None,
                "sources": [],
            }
        return None

    def _handle_mock_service_forward(
        self,
        query: str,
        context: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        thread_messages: Optional[list[dict[str, str]]] = None,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """Handles the forward pass using the mock service."""
        logger.info(f"Using mock research service for query: {query}")
        mock_data = self.mock_service.search(
            query,
            context=context,
            attachments=attachments,
            thread_messages=thread_messages,
            reasoning_effort=reasoning_effort,
        )
        # Format mock data similar to real response for consistency
        return {
            "status": "success",
            "findings": mock_data.get("response", "Mock response not fully available."),
            "sources": mock_data.get("sources", []),
            "query": query,
            "annotations": mock_data.get("annotations", []),
            "visited_urls": mock_data.get("visited_urls", []),
            "read_urls": mock_data.get("read_urls", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usage": mock_data.get("usage", {}),
        }

    def _execute_jina_stream_request(self, messages: list, reasoning_effort: str, query: str) -> dict[str, Any]:
        """Executes a streaming Jina research request and processes the response."""
        response_stream = self._jina_research_request(messages, stream=True, reasoning_effort=reasoning_effort)
        if not response_stream: # Should not happen if _jina_research_request handles its errors by raising or returning error dict
            logger.error("Stream request to Jina returned no response object.")
            return {"status": "error", "error": "Failed to initiate stream with Jina API", "findings": None, "sources": []}

        processed_stream = self._process_stream_response(response_stream)
        if "error" in processed_stream:
            return {
                "status": "error",
                "error": processed_stream["error"],
                "findings": f"An error occurred during research: {processed_stream['error']}",
                "sources": []
            }

        # Stream processing already gives findings, annotations, urls etc.
        # The _format_research_content step is applied after the stream is fully processed.
        formatted_content = self._format_research_content(
            content=processed_stream.get("findings", ""),
            annotations=processed_stream.get("annotations", []),
            visited_urls=processed_stream.get("visited_urls", []),
            read_urls=processed_stream.get("read_urls", []),
        )
        return {"status": "success", "query": query, "findings": formatted_content, **processed_stream}

    def _execute_jina_non_stream_request(self, messages: list, reasoning_effort: str, query: str) -> dict[str, Any]:
        """Executes a non-streaming Jina research request and processes the response."""
        response_data = self._jina_research_request(messages, stream=False, reasoning_effort=reasoning_effort)
        if not response_data or "error" in response_data:
            error_msg = response_data.get("error") if response_data else "No response from Jina API"
            logger.error(f"Jina non-stream request failed: {error_msg}")
            return {"status": "error", "error": error_msg, "findings": None, "sources": []}

        try:
            # Assuming the structure based on original code for non-streaming mock/actual Jina
            choice = response_data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            annotations = message.get("annotations", [])

            if not content:
                 return {"status": "error", "error": "Empty content in Jina response", "findings": None, "sources": []}

            formatted_content = self._format_research_content(
                content=content,
                annotations=annotations,
                visited_urls=response_data.get("visitedURLs", response_data.get("visited_urls", [])), # Adapt to potential key name differences
                read_urls=response_data.get("readURLs", response_data.get("read_urls", [])),
            )
            # Include other relevant fields from response_data
            return {
                "status": "success",
                "query": query,
                "findings": formatted_content,
                "annotations": annotations,
                "visited_urls": response_data.get("visitedURLs", response_data.get("visited_urls", [])),
                "read_urls": response_data.get("readURLs", response_data.get("read_urls", [])),
                "timestamp": response_data.get("timestamp"), # Ensure this comes from Jina if available
                "usage": response_data.get("usage", {}),
                "num_urls": response_data.get("numURLs", response_data.get("num_urls", 0)),
            }
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Error parsing non-stream Jina response: {e!s} - Response: {response_data}")
            return {"status": "error", "error": f"Invalid response structure from Jina API: {e!s}", "findings": None, "sources": []}

    def forward(
        self,
        query: str,
        context: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        thread_messages: Optional[list[dict[str, str]]] = None,
        *,
        stream: bool = False,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """Main method to perform deep research."""
        if self.use_mock_service:
            return self._handle_mock_service_forward(
                query, context, attachments, thread_messages, reasoning_effort
            )

        if not self.api_key:
            logger.error("JINA_API_KEY is not set. Deep research tool is disabled.")
            return {
                "status": "error",
                "error": "JINA_API_KEY not configured. Deep research unavailable.",
                "findings": None,
                "sources": [],
            }

        if error_response := self._validate_forward_params(reasoning_effort):
            return error_response

        if not self.deep_research_enabled:
            logger.info("Deep research is disabled. Enable it explicitly before use.")
            return {
                "query": query,
                "findings": "Deep research functionality is currently disabled. Enable it explicitly before use.",
                "error": "Deep research disabled",
            }

        research_results: dict[str, Any] = {}
        try:
            messages = self._prepare_messages(query, context, attachments, thread_messages)

            try:
                if stream:
                    research_results = self._execute_jina_stream_request(messages, reasoning_effort, query)
                else:
                    research_results = self._execute_jina_non_stream_request(messages, reasoning_effort, query)

                # Logging based on status happens after assignment
                if research_results.get("status") == "success":
                    logger.info(f"Research complete for query: {query}. Findings length: {len(research_results.get('findings', ''))}")
                else:
                    logger.error(f"Research failed for query: {query}. Error: {research_results.get('error')}")

            except Exception as e: # Inner Jina call exception
                logger.exception("Error in Jina request execution")
                research_results = {
                    "status": "error",
                    "error": f"An unexpected error occurred during Jina request execution: {e!s}",
                    "findings": None,
                    "sources": [],
                }
            # Removed the else block and its return, research_results is now always assigned.

        except Exception as e: # Outer exception (e.g. message prep)
            logger.error(f"Error performing research (outer scope): {e!s}")
            research_results = {"query": query, "findings": f"An error occurred during research setup: {e!s}", "error": str(e), "status": "error"}

        return research_results # Single return point for the main logic path
