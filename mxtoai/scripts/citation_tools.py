"""
Citation-aware wrapper tools for the Email Deep Research Agent.

This module provides wrapper classes that extend the original tools but collect URL
information for a simple references section without embedding citations in text.
"""

import re
import time
from typing import Optional

from smolagents import GoogleSearchTool, Tool


# Import the existing search tools to wrap them
try:
    from mxtoai.tools.web_search import DDGSearchTool, BraveSearchTool
except ImportError:
    DDGSearchTool = None
    BraveSearchTool = None

# Global store for all URLs visited during research
_all_visited_urls = []


def reset_citation_counter():
    """
    Reset the global URL store
    """
    global _all_visited_urls
    _all_visited_urls = []


def add_url_to_references(url: str, title: Optional[str] = None, date: Optional[str] = None) -> None:
    """
    Add a URL to the global references collection.

    Args:
        url: URL of the source
        title: Title of the source (optional)
        date: Publication date (optional)

    """
    global _all_visited_urls

    # Don't add duplicates
    if url not in [u.get("url") for u in _all_visited_urls]:
        _all_visited_urls.append(
            {"url": url, "title": title or url, "date": date or "n.d.", "timestamp": int(time.time())}
        )


class CitationAwareGoogleSearchTool(GoogleSearchTool):
    """
    Extension of GoogleSearchTool that collects URL information.
    """

    def forward(self, query: str, filter_year: Optional[int] = None) -> str:
        """
        Perform a Google search and collect URL information.

        Args:
            query: Search query
            filter_year: Optional year filter

        Returns:
            Original search results

        """
        original_results = super().forward(query, filter_year)

        # Extract URLs from search results
        urls = re.findall(r"\[.*?\]\((https?://.*?)\)", original_results)
        title_url_matches = re.findall(r"\[(.*?)\]\((https?://.*?)\)", original_results)

        for match in title_url_matches:
            title, url = match
            add_url_to_references(url=url, title=title)

        for url in urls:
            if url not in [u.get("url") for u in _all_visited_urls]:
                add_url_to_references(url=url)

        return original_results


class CitationAwareVisitTool(Tool):
    """
    Extension of VisitTool that collects URL information.
    """
    name = "citation_aware_visit_tool"
    description = "Visits a webpage at the given url and reads its content as a markdown string while collecting URL information for references."
    inputs = {
        "url": {"type": "string", "description": "The URL of the webpage to visit."}
    }
    output_type = "string"

    def __init__(self, max_output_length: int = 40000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_output_length = max_output_length

    def _truncate_content(self, content: str, max_length: int) -> str:
        if len(content) <= max_length:
            return content
        return (
            content[: max_length // 2]
            + f"\n..._This content has been truncated to stay below {max_length} characters_...\n"
            + content[-max_length // 2 :]
        )

    def forward(self, url: str) -> str:
        """
        Visit a webpage and collect URL information.

        Args:
            url: URL to visit

        Returns:
            Webpage content as markdown with URL information collected

        """
        try:
            import requests
            from markdownify import markdownify
            from requests.exceptions import RequestException
        except ImportError as e:
            raise ImportError(
                "You must install packages `markdownify` and `requests` to run this tool: for instance run `pip install markdownify requests`."
            ) from e
        
        try:
            # Send a GET request to the URL with a 20-second timeout
            response = requests.get(url, timeout=20)
            response.raise_for_status()

            # Convert the HTML content to Markdown
            markdown_content = markdownify(response.text).strip()
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
            original_content = self._truncate_content(markdown_content, self.max_output_length)

            # Extract title for citation
            title_match = (
                re.search(r"<title>(.*?)</title>", response.text, re.IGNORECASE)
                or re.search(r"<h1>(.*?)</h1>", response.text, re.IGNORECASE)
                or re.search(r"# (.*?)$", markdown_content, re.MULTILINE)
            )
            title = title_match.group(1).strip() if title_match else None

            # Collect URL information for references
            add_url_to_references(url=url, title=title)
            return original_content

        except requests.exceptions.Timeout:
            return "The request timed out. Please try again later or check the URL."
        except RequestException as e:
            return f"Error fetching the webpage: {str(e)}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"


class CitationAwareDDGSearchTool(DDGSearchTool):
    """
    Extension of DDGSearchTool that collects URL information.
    """

    def __init__(self, max_results: int = 5):
        """Initialize citation-aware DDG search tool."""
        if DDGSearchTool is None:
            raise ImportError("DDGSearchTool not available")
        super().__init__(max_results=max_results)

    def forward(self, query: str) -> str:
        """
        Perform a DDG search and collect URL information.

        Args:
            query: Search query

        Returns:
            Original search results

        """
        original_results = super().forward(query)

        # Extract URLs from search results (similar pattern to Google search)
        urls = re.findall(r"\[.*?\]\((https?://.*?)\)", original_results)
        title_url_matches = re.findall(r"\[(.*?)\]\((https?://.*?)\)", original_results)

        for match in title_url_matches:
            title, url = match
            add_url_to_references(url=url, title=title)

        for url in urls:
            if url not in [u.get("url") for u in _all_visited_urls]:
                add_url_to_references(url=url)

        return original_results


class CitationAwareBraveSearchTool(BraveSearchTool):
    """
    Extension of BraveSearchTool that collects URL information.
    """

    def __init__(self, max_results: int = 5):
        """Initialize citation-aware Brave search tool."""
        if BraveSearchTool is None:
            raise ImportError("BraveSearchTool not available")
        super().__init__(max_results=max_results)

    def forward(self, query: str) -> str:
        """
        Perform a Brave search and collect URL information.

        Args:
            query: Search query

        Returns:
            Original search results

        """
        original_results = super().forward(query)

        # Extract URLs from search results (similar pattern to Google search)
        urls = re.findall(r"\[.*?\]\((https?://.*?)\)", original_results)
        title_url_matches = re.findall(r"\[(.*?)\]\((https?://.*?)\)", original_results)

        for match in title_url_matches:
            title, url = match
            add_url_to_references(url=url, title=title)

        for url in urls:
            if url not in [u.get("url") for u in _all_visited_urls]:
                add_url_to_references(url=url)

        return original_results


def extract_citations(text: str) -> dict[str, dict[str, str]]:
    """
    Extract citations from text and map them to collected URLs.
    
    Supports various citation formats:
    - Numbered citations: [1], [2], etc.
    - Named citations: [Source Name], [Title]
    - Inline URLs: direct URL mentions
    - Parenthetical citations: (Source 1), (Author, Year)
    
    Args:
        text: Text to analyze for citations
        
    Returns:
        Dictionary mapping citation markers to URL information
        Format: {citation_marker: {url, title, date}}
    """
    global _all_visited_urls
    
    if not _all_visited_urls:
        return {}
    
    citations = {}
    
    # Pattern 1: Numbered citations [1], [2], etc.
    numbered_citations = re.findall(r'\[(\d+)\]', text)
    for num_str in numbered_citations:
        num = int(num_str)
        citation_key = f"[{num}]"
        
        # Map to collected URLs by index (1-based)
        if 1 <= num <= len(_all_visited_urls):
            url_info = _all_visited_urls[num - 1]
            citations[citation_key] = {
                'url': url_info['url'],
                'title': url_info.get('title', url_info['url']),
                'date': url_info.get('date', 'n.d.')
            }
    
    # Pattern 2: Named citations [Title] or [Source Name]
    named_citations = re.findall(r'\[([^\d\]]+)\]', text)
    for name in named_citations:
        citation_key = f"[{name}]"
        
        # Find matching URL by title similarity
        best_match = None
        best_score = 0
        
        for url_info in _all_visited_urls:
            title = url_info.get('title', '').lower()
            name_lower = name.lower()
            
            # Simple similarity check
            if name_lower in title or title in name_lower:
                score = len(set(name_lower.split()) & set(title.split()))
                if score > best_score:
                    best_score = score
                    best_match = url_info
        
        if best_match:
            citations[citation_key] = {
                'url': best_match['url'],
                'title': best_match.get('title', best_match['url']),
                'date': best_match.get('date', 'n.d.')
            }
    
    # Pattern 3: Inline URLs mentioned in text
    inline_urls = re.findall(r'https?://[^\s\)]+', text)
    for url in inline_urls:
        # Clean URL (remove trailing punctuation)
        clean_url = re.sub(r'[.,;:]$', '', url)
        
        # Find matching collected URL
        for url_info in _all_visited_urls:
            if url_info['url'] == clean_url or clean_url in url_info['url']:
                citation_key = clean_url
                citations[citation_key] = {
                    'url': url_info['url'],
                    'title': url_info.get('title', url_info['url']),
                    'date': url_info.get('date', 'n.d.')
                }
                break
    
    # Pattern 4: Parenthetical citations (Source 1), (Author, Year)
    paren_citations = re.findall(r'\(([^)]+)\)', text)
    for paren_content in paren_citations:
        citation_key = f"({paren_content})"
        
        # Check if it's a numbered reference
        if re.match(r'^\d+$', paren_content.strip()):
            num = int(paren_content.strip())
            if 1 <= num <= len(_all_visited_urls):
                url_info = _all_visited_urls[num - 1]
                citations[citation_key] = {
                    'url': url_info['url'],
                    'title': url_info.get('title', url_info['url']),
                    'date': url_info.get('date', 'n.d.')
                }
        else:
            # Try to match by title or author name
            best_match = None
            best_score = 0
            
            for url_info in _all_visited_urls:
                title = url_info.get('title', '').lower()
                paren_lower = paren_content.lower()
                
                # Check for partial matches
                words_in_common = len(set(paren_lower.split()) & set(title.split()))
                if words_in_common > best_score and words_in_common > 0:
                    best_score = words_in_common
                    best_match = url_info
            
            if best_match:
                citations[citation_key] = {
                    'url': best_match['url'],
                    'title': best_match.get('title', best_match['url']),
                    'date': best_match.get('date', 'n.d.')
                }
    
    # Pattern 5: Markdown-style links [text](url) that might be citations
    markdown_links = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', text)
    for link_text, url in markdown_links:
        citation_key = f"[{link_text}]"
        
        # Find matching collected URL
        for url_info in _all_visited_urls:
            if url_info['url'] == url or url in url_info['url']:
                citations[citation_key] = {
                    'url': url_info['url'],
                    'title': url_info.get('title', link_text),
                    'date': url_info.get('date', 'n.d.')
                }
                break
    
    return citations


def create_references_section() -> str:
    """
    Create a properly formatted references section from all collected URLs.

    Returns:
        Formatted references section

    """
    if not _all_visited_urls:
        return ""

    references = ["## References"]

    # Sort references by timestamp (newest first)
    sorted_urls = sorted(_all_visited_urls, key=lambda x: x["timestamp"], reverse=True)

    for i, url_info in enumerate(sorted_urls, 1):
        title = url_info.get("title", url_info["url"])
        url = url_info["url"]
        date = url_info.get("date", "n.d.")

        # Format reference
        reference = f"{i}. *{title}*. Retrieved on {date} from [{url}]({url})"
        references.append(reference)

    return "\n\n".join(references)


def insert_citations_in_text(text: str, auto_cite: bool = True) -> str:
    """
    Insert proper citation markers in text and link them to collected URLs.
    
    Args:
        text: Original text
        auto_cite: Whether to automatically add citations for mentioned sources
        
    Returns:
        Text with proper citation markers
    """
    global _all_visited_urls
    
    if not _all_visited_urls:
        return text
    
    modified_text = text
    
    if auto_cite:
        # Auto-cite inline URLs
        for i, url_info in enumerate(_all_visited_urls, 1):
            url = url_info['url']
            title = url_info.get('title', '')
            
            # Replace bare URLs with numbered citations
            url_pattern = re.escape(url)
            if re.search(url_pattern, modified_text):
                modified_text = re.sub(url_pattern, f"[{i}]", modified_text)
            
            # Replace title mentions with citations (if title is mentioned)
            if title and len(title) > 10:  # Only for substantial titles
                title_words = title.split()[:3]  # First few words of title
                title_start = ' '.join(title_words)
                
                if title_start.lower() in modified_text.lower():
                    # Be careful to only replace clear title mentions
                    pattern = re.compile(re.escape(title_start), re.IGNORECASE)
                    if not re.search(f'\\[\\d+\\]', modified_text[modified_text.lower().find(title_start.lower()):]):
                        modified_text = pattern.sub(f"{title_start} [{i}]", modified_text, count=1)
    
    return modified_text


def format_text_with_citations(text: str, include_references: bool = True) -> str:
    """
    Format text with proper citations and optionally append references section.
    
    Args:
        text: Original text
        include_references: Whether to append references section
        
    Returns:
        Formatted text with citations and references
    """
    # Insert citations in text
    formatted_text = insert_citations_in_text(text)
    
    # Add references section if requested
    if include_references:
        references = create_references_section()
        if references:
            formatted_text += "\n\n" + references
    
    return formatted_text


def get_citation_summary() -> dict:
    """
    Get a summary of all collected citations.
    
    Returns:
        Dictionary with citation statistics and info
    """
    global _all_visited_urls
    
    return {
        'total_sources': len(_all_visited_urls),
        'urls': [url_info['url'] for url_info in _all_visited_urls],
        'titles': [url_info.get('title', 'No title') for url_info in _all_visited_urls],
        'recent_sources': _all_visited_urls[-5:] if len(_all_visited_urls) > 5 else _all_visited_urls
    }
