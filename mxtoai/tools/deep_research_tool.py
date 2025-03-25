import os
import json
import base64
import logging
import mimetypes
import requests
from typing import Dict, List, Any, Optional, Generator
from smolagents import Tool

# Configure logger with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("research_tool")

class DeepResearchTool(Tool):
    """
    Tool for conducting deep research based on email content using Jina AI's DeepSearch API.
    """
    
    name = "deep_research"
    description = "Conducts deep research based on email content and attachments to provide comprehensive answers with sources."
    
    # Define output type for the tool
    output_type = "object"  # Returns a dictionary with research findings and sources
    
    def __init__(self):
        """Initialize the deep research tool."""
        # Log tool initialization
        logger.debug("Initializing DeepResearchTool")
        
        # Define input schema before super().__init__() to ensure proper validation
        self.inputs = {
            "query": {
                "type": "string",
                "description": "The research query or question to investigate"
            },
            "context": {
                "type": "string",
                "description": "Additional context from email thread or other sources",
                "required": False,
                "nullable": True
            },
            "attachments": {
                "type": "array",
                "description": "List of file attachments to include in research",
                "required": False,
                "nullable": True,
                "default": [],
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "type": {"type": "string"},
                        "filename": {"type": "string"}
                    }
                }
            },
            "thread_messages": {
                "type": "array",
                "description": "Previous messages in the email thread for context",
                "required": False,
                "nullable": True,
                "default": [],
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "content": {"type": "string"}
                    }
                }
            },
            "stream": {
                "type": "boolean",
                "description": "Whether to stream the response",
                "required": False,
                "nullable": True,
                "default": True
            },
            "reasoning_effort": {
                "type": "string",
                "description": "Level of reasoning effort ('low', 'medium', 'high')",
                "required": False,
                "nullable": True,
                "default": "medium",
                "enum": ["low", "medium", "high"]
            }
        }
        
        # Log schema before initialization
        logger.debug(f"Tool schema before initialization: {json.dumps(self.inputs, indent=2)}")
        
        try:
            super().__init__()
            logger.debug("Successfully initialized base Tool class")
        except Exception as e:
            logger.error(f"Error initializing base Tool class: {str(e)}")
            raise
        
        # Check for JINA API key
        self.api_key = os.getenv("JINA_API_KEY")
        if not self.api_key:
            logger.warning("JINA_API_KEY not found. Research functionality will be limited.")
            
        # Jina AI DeepSearch API configuration
        self.api_url = 'https://deepsearch.jina.ai/v1/chat/completions'
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
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
    
    def _encode_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Encode a file to base64 data URI format for Jina API.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dict containing file data in Jina API format or None if file is too large/invalid
        """
        try:
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                logger.warning(f"File {file_path} exceeds 10MB limit, skipping")
                return None
            
            # Get mime type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Read and encode file
            with open(file_path, 'rb') as f:
                file_data = f.read()
                encoded = base64.b64encode(file_data).decode('utf-8')
                
            return {
                "type": "file",
                "data": f"data:{mime_type};base64,{encoded}",
                "mimeType": mime_type
            }
            
        except Exception as e:
            logger.error(f"Error encoding file {file_path}: {str(e)}")
            return None
    
    def _prepare_messages(
        self,
        query: str,
        context: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        thread_messages: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Prepare messages for Jina API including files and context.
        
        Args:
            query: The research query
            context: Additional context
            attachments: List of file attachments
            thread_messages: Previous messages in thread
            
        Returns:
            List of messages in Jina API format
        """
        messages = []
        
        # Ensure array parameters are properly initialized
        attachments = attachments if isinstance(attachments, list) else []
        thread_messages = thread_messages if isinstance(thread_messages, list) else []
        
        # Add thread messages if available
        if thread_messages:
            messages.extend(thread_messages)
        
        # Prepare user message with query and files
        user_message_content = []
        
        # Add query as text
        user_message_content.append({
            "type": "text",
            "text": query
        })
        
        # Add context if available
        if context:
            user_message_content.append({
                "type": "text",
                "text": f"\nAdditional Context:\n{context}"
            })
        
        # Add encoded files
        if attachments:
            for attachment in attachments:
                file_data = self._encode_file(attachment["path"])
                if file_data:
                    user_message_content.append(file_data)
        
        # Add the complete user message
        messages.append({
            "role": "user",
            "content": user_message_content
        })
        
        return messages
    
    def _process_stream_response(self, response: requests.Response) -> Generator[Dict[str, Any], None, None]:
        """
        Process streaming response from Jina AI DeepSearch API.
        
        Args:
            response: Streaming response from the API
            
        Yields:
            Processed chunks of the response
        """
        buffer = ""
        for line in response.iter_lines():
            if line:
                try:
                    # Decode the line and remove 'data: ' prefix if present
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        decoded_line = decoded_line[6:]
                    
                    # Parse JSON response
                    chunk = json.loads(decoded_line)
                    
                    # Extract content and annotations
                    if 'choices' in chunk and chunk['choices']:
                        delta = chunk['choices'][0].get('delta', {})
                        content = delta.get('content', '')
                        annotations = delta.get('annotations', [])
                        
                        if content:
                            buffer += content
                        
                        # Yield accumulated content and annotations
                        yield {
                            'content': buffer,
                            'annotations': annotations,
                            'visited_urls': chunk.get('visitedURLs', []),
                            'read_urls': chunk.get('readURLs', [])
                        }
                        
                        # Clear buffer after yielding
                        buffer = ""
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON response: {e}")
                except Exception as e:
                    logger.error(f"Error processing stream response: {e}")
    
    def forward(
        self,
        query: str,
        context: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        thread_messages: Optional[List[Dict[str, str]]] = None,
        stream: bool = True,
        reasoning_effort: str = "medium"
    ) -> Dict[str, Any]:
        """
        Perform deep research on a query with context and attachments.
        
        Args:
            query: The research query to investigate
            context: Optional additional context
            attachments: Optional list of file attachments
            thread_messages: Optional list of previous messages
            stream: Whether to stream the response
            reasoning_effort: Level of reasoning effort ("low", "medium", "high")
            
        Returns:
            Research results including findings and sources
        """
        import ipdb; ipdb.set_trace()
        # Ensure array parameters are always treated as arrays
        attachments = attachments if isinstance(attachments, list) else []
        thread_messages = thread_messages if isinstance(thread_messages, list) else []
        
        if not self.api_key:
            return {
                "query": query,
                "findings": "Research functionality is not available. JINA_API_KEY is required.",
                "sources": [],
                "error": "API key not configured"
            }
        
        if not self.deep_research_enabled:
            logger.info("Deep research is disabled. Enable it explicitly before use.")
            return {
                "query": query,
                "findings": "Deep research functionality is currently disabled. Enable it explicitly before use.",
                "sources": [],
                "error": "Deep research disabled"
            }
        
        try:
            # Prepare messages including files and context
            messages = self._prepare_messages(
                query=query,
                context=context,
                attachments=attachments,
                thread_messages=thread_messages
            )
            
            # Prepare request data
            data = {
                "model": "jina-deepsearch-v1",
                "messages": messages,
                "stream": stream,
                "reasoning_effort": reasoning_effort,
                "no_direct_answer": False
            }
            
            logger.info(f"Sending research query to Jina AI: {query}")
            
            # Make API request
            response = requests.post(
                self.api_url,
                headers=self.headers,
                data=json.dumps(data),
                stream=stream
            )
            
            if not response.ok:
                error_msg = f"API request failed with status {response.status_code}"
                logger.error(error_msg)
                return {
                    "query": query,
                    "findings": f"An error occurred during research: {error_msg}",
                    "sources": [],
                    "error": error_msg
                }
            
            if stream:
                # Process streaming response
                full_content = ""
                all_annotations = []
                visited_urls = set()
                read_urls = set()
                
                for chunk in self._process_stream_response(response):
                    full_content = chunk['content']  # Always contains full content
                    all_annotations.extend(chunk.get('annotations', []))
                    visited_urls.update(chunk.get('visited_urls', []))
                    read_urls.update(chunk.get('read_urls', []))
                
                research_results = {
                    "query": query,
                    "findings": full_content,
                    "annotations": all_annotations,
                    "visited_urls": list(visited_urls),
                    "read_urls": list(read_urls),
                    "timestamp": response.headers.get('date')
                }
            else:
                # Process non-streaming response
                response_data = response.json()
                research_results = {
                    "query": query,
                    "findings": response_data['choices'][0]['message']['content'],
                    "annotations": response_data['choices'][0]['message'].get('annotations', []),
                    "visited_urls": response_data.get('visitedURLs', []),
                    "read_urls": response_data.get('readURLs', []),
                    "timestamp": response.headers.get('date')
                }
            
            logger.info(f"Research complete for query: {query}")
            return research_results
            
        except Exception as e:
            logger.error(f"Error performing research: {str(e)}")
            return {
                "query": query,
                "findings": f"An error occurred during research: {str(e)}",
                "sources": [],
                "error": str(e)
            }