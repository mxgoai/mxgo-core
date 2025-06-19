"""
Brave search tool - Better quality results with moderate API cost.
"""

import json
import logging
import os
import re
from typing import Optional

from smolagents import Tool

from mxtoai.request_context import RequestContext
from mxtoai.schemas import ToolOutputWithCitations

logger = logging.getLogger(__name__)


class BraveSearchTool(Tool):
    """
    Brave search tool - Better quality results than DDG, moderate API cost.
    Use when DDG results are insufficient or when you need more comprehensive information.
    """

    name = "brave_search"
    description = (
        "Performs a web search using Brave Search API. You can do Web search, Images, Videos, News, and more."
        "It might give better results than DuckDuckGo but has moderate API costs. Use this when DDG results are insufficient "
        "or when you need more detailed, current, or specialized information. Good for research and detailed queries."
    )
    inputs = {
        "query": {"type": "string", "description": "The user's search query term. Max 400 chars, 50 words."},
        "country": {"type": "string", "description": "2-char country code for results (e.g., 'US', 'DE'). Default: 'US'.", "nullable": True},
        "search_lang": {"type": "string", "description": "Language code for search results (e.g., 'en', 'es'). Default: 'en'.", "nullable": True},
        "ui_lang": {"type": "string", "description": "UI language for response (e.g., 'en-US'). Default: 'en-US'.", "nullable": True},
        "safesearch": {"type": "string", "description": "Filter adult content: 'off', 'moderate', 'strict'. Default: 'moderate'.", "nullable": True},
        "freshness": {"type": "string", "description": "Filter by discovery date: 'pd' (day), 'pw' (week), 'pm' (month), 'py' (year), or 'YYYY-MM-DDtoYYYY-MM-DD'. Default: None.", "nullable": True},
        "result_filter": {"type": "string", "description": "Comma-separated result types (e.g., 'web,news,videos'). Default: 'web'.", "nullable": True},
    }
    output_type = "object"

    def __init__(self, context: RequestContext, max_results: int = 5):
        """
        Initialize Brave search tool.

        Args:
            context: Request context containing email data and citation manager
            max_results: Maximum number of results to return

        """
        self.context = context
        self.max_results = max_results
        self.api_key = os.getenv("BRAVE_SEARCH_API_KEY")
        super().__init__()

        if not self.api_key:
            logger.warning("BRAVE_SEARCH_API_KEY not found. Brave search will not be available.")
        else:
            logger.debug(f"BraveSearchTool initialized with max_results={max_results}")

    def forward(
        self,
        query: str,
        country: str = "US",
        search_lang: str = "en",
        ui_lang: str = "en-US",
        safesearch: str = "moderate",
        freshness: Optional[str] = None,
        result_filter: str = "web",
    ) -> str:
        """Execute Brave search and return results with citations."""
        if not self.api_key:
            msg = "Brave Search API key not configured. Cannot perform search."
            raise ValueError(msg)

        try:
            log_params = {
                "query": query,
                "country": country,
                "search_lang": search_lang,
                "ui_lang": ui_lang,
                "safesearch": safesearch,
                "freshness": freshness,
                "result_filter": result_filter,
            }
            logger.info(f"Performing Brave search with params: {log_params}")

            import requests

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }

            params = {
                "q": query,
                "count": self.max_results,
                "country": country,
                "search_lang": search_lang,
                "ui_lang": ui_lang,
                "safesearch": safesearch,
                "result_filter": result_filter,
                "text_decorations": False,
                "spellcheck": True,
            }
            if freshness:
                params["freshness"] = freshness

            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()

            # Process different types of results according to API documentation
            content_parts = []
            citations_added = 0

            # 1. Handle web search results - Search model with results[] of SearchResult
            web_search = data.get("web")
            if web_search and web_search.get("results"):
                web_results = web_search["results"]
                content_parts.append("**Web Results:**")
                for i, result in enumerate(web_results[:self.max_results], 1):
                    # SearchResult inherits from Result: has title, url, description
                    title = result.get("title", "No title")
                    url = result.get("url", "")
                    description = result.get("description", "No description")
                    age = result.get("age", "")

                    # Add citation for this result
                    if url:
                        citation_id = self.context.add_web_citation(url, title, visited=False)
                        formatted_result = f"{i}. **{title}** [#{citation_id}]"
                        if age:
                            formatted_result += f" *({age})*"
                        formatted_result += f"\n   URL: {url}\n   {description}"
                        citations_added += 1
                    else:
                        formatted_result = f"{i}. **{title}**"
                        if age:
                            formatted_result += f" *({age})*"
                        formatted_result += f"\n   {description}"

                    content_parts.append(formatted_result)
                content_parts.append("")  # Add spacing

            # 2. Handle news results - News model with results[] of NewsResult
            news_data = data.get("news")
            if news_data and news_data.get("results"):
                news_results = news_data["results"]
                content_parts.append("**News Results:**")
                for i, result in enumerate(news_results, 1):
                    # NewsResult inherits from Result: has title, url, description
                    title = result.get("title", "No title")
                    url = result.get("url", "")
                    description = result.get("description", "No description")
                    age = result.get("age", "")
                    source = result.get("source", "")
                    breaking = result.get("breaking", False)

                    if url:
                        citation_id = self.context.add_web_citation(url, f"{title} (News)", visited=False)
                        formatted_result = f"{i}. **{title}** [#{citation_id}]"
                        if breaking:
                            formatted_result += " *🔴 BREAKING*"
                        if age:
                            formatted_result += f" *({age})*"
                        if source:
                            formatted_result += f" *- {source}*"
                        formatted_result += f"\n   URL: {url}\n   {description}"
                        citations_added += 1
                    else:
                        formatted_result = f"{i}. **{title}**"
                        if breaking:
                            formatted_result += " *🔴 BREAKING*"
                        if age:
                            formatted_result += f" *({age})*"
                        if source:
                            formatted_result += f" *- {source}*"
                        formatted_result += f"\n   {description}"

                    content_parts.append(formatted_result)
                content_parts.append("")  # Add spacing

            # 3. Handle infobox - GraphInfobox with results field
            infobox_data = data.get("infobox")
            if infobox_data and infobox_data.get("results"):
                infobox_results = infobox_data["results"]
                content_parts.append("**Information Box:**")

                # Handle different infobox types
                if isinstance(infobox_results, list):
                    infobox_list = infobox_results
                else:
                    infobox_list = [infobox_results]

                for infobox in infobox_list:
                    title = infobox.get("title", "")
                    long_desc = infobox.get("long_desc", "")
                    website_url = infobox.get("website_url", "")
                    category = infobox.get("category", "")

                    if title:
                        content_parts.append(f"**{title}**")
                    if category:
                        content_parts.append(f"*Category: {category}*")
                    if long_desc:
                        content_parts.append(long_desc)
                    if website_url:
                        citation_id = self.context.add_web_citation(website_url, f"{title} (Official Website)", visited=False)
                        content_parts.append(f"Website: {website_url} [#{citation_id}]")
                        citations_added += 1
                content_parts.append("")  # Add spacing

            # 4. Handle FAQ results - FAQ model with results[] of QA
            faq_data = data.get("faq")
            if faq_data and faq_data.get("results"):
                faq_results = faq_data["results"]
                content_parts.append("**Frequently Asked Questions:**")
                for i, faq in enumerate(faq_results, 1):
                    # QA model has question, answer, title, url
                    question = faq.get("question", "")
                    answer = faq.get("answer", "")
                    title = faq.get("title", "")
                    url = faq.get("url", "")

                    if question:
                        content_parts.append(f"{i}. **Q: {question}**")
                    if answer:
                        content_parts.append(f"   A: {answer}")
                    if url:
                        citation_title = title if title else f"FAQ: {question[:50]}..."
                        citation_id = self.context.add_web_citation(url, citation_title, visited=False)
                        content_parts.append(f"   Source: {url} [#{citation_id}]")
                        citations_added += 1
                content_parts.append("")  # Add spacing

            # 5. Handle video results - Videos model with results[] of VideoResult
            videos_data = data.get("videos")
            if videos_data and videos_data.get("results"):
                video_results = videos_data["results"]
                content_parts.append("**Video Results:**")
                for i, video in enumerate(video_results, 1):
                    # VideoResult inherits from Result: has title, url, description
                    title = video.get("title", "No title")
                    url = video.get("url", "")
                    description = video.get("description", "")
                    age = video.get("age", "")

                    # VideoResult also has video field with VideoData
                    video_data = video.get("video", {})
                    duration = video_data.get("duration", "")
                    views = video_data.get("views", "")
                    creator = video_data.get("creator", "")

                    if url:
                        citation_id = self.context.add_web_citation(url, f"{title} (Video)", visited=False)
                        formatted_result = f"{i}. **{title}** [#{citation_id}]"
                        if duration:
                            formatted_result += f" *({duration})*"
                        if views:
                            formatted_result += f" *{views} views*"
                        if creator:
                            formatted_result += f" *by {creator}*"
                        if age:
                            formatted_result += f" *({age})*"
                        formatted_result += f"\n   URL: {url}\n   {description}"
                        citations_added += 1
                    else:
                        formatted_result = f"{i}. **{title}**"
                        if duration:
                            formatted_result += f" *({duration})*"
                        if views:
                            formatted_result += f" *{views} views*"
                        if creator:
                            formatted_result += f" *by {creator}*"
                        if age:
                            formatted_result += f" *({age})*"
                        formatted_result += f"\n   {description}"

                    content_parts.append(formatted_result)
                content_parts.append("")  # Add spacing

            # 6. Handle discussions - Discussions model with results[] of DiscussionResult
            discussions_data = data.get("discussions")
            if discussions_data and discussions_data.get("results"):
                discussion_results = discussions_data["results"]
                content_parts.append("**Forum Discussions:**")
                for i, discussion in enumerate(discussion_results, 1):
                    # DiscussionResult inherits from SearchResult (which inherits from Result)
                    # So it has title, url, description at top level
                    title = discussion.get("title", "No title")
                    url = discussion.get("url", "")
                    description = discussion.get("description", "")

                    # DiscussionResult also has data field with ForumData
                    forum_data = discussion.get("data", {})
                    forum_name = forum_data.get("forum_name", "")
                    question = forum_data.get("question", "")
                    top_comment = forum_data.get("top_comment", "")
                    num_answers = forum_data.get("num_answers", "")
                    score = forum_data.get("score", "")

                    # Build formatted result
                    formatted_result = f"{i}. **{title}**"
                    if forum_name:
                        formatted_result += f" *(from {forum_name})*"
                    if num_answers:
                        formatted_result += f" *({num_answers} answers)*"
                    if score:
                        formatted_result += f" *Score: {score}*"

                    if description:
                        formatted_result += f"\n   {description}"
                    if question and question != title:
                        formatted_result += f"\n   Question: {question}"
                    if top_comment:
                        formatted_result += f"\n   Top comment: {top_comment[:100]}..."

                    if url:
                        citation_id = self.context.add_web_citation(url, f"{title} (Discussion)", visited=False)
                        formatted_result += f"\n   URL: {url} [#{citation_id}]"
                        citations_added += 1

                    content_parts.append(formatted_result)
                content_parts.append("")  # Add spacing

            # Check if we have any results
            if not content_parts:
                logger.warning(f"Brave search returned no results for query: {query}")
                result = ToolOutputWithCitations(
                    content=f"No results found for query: {query}",
                    metadata={"query": query, "total_results": 0}
                )
                return json.dumps(result.model_dump())

            content = "\n".join(content_parts).strip()

            # Create structured output with local citations
            from mxtoai.schemas import CitationCollection

            # Create a local citation collection for this tool's output
            local_citations = CitationCollection()

            # Get only the citations that were added by this tool call
            if citations_added > 0:
                # Get citations from the request context
                context_citations = self.context.get_citations()
                # Get the last 'citations_added' number of citations
                recent_citations = context_citations.sources[-citations_added:] if context_citations.sources else []
                for citation in recent_citations:
                    local_citations.add_source(citation)

            # Count results properly
            web_count = len(web_search.get("results", [])) if web_search else 0
            news_count = len(news_data.get("results", [])) if news_data else 0
            video_count = len(videos_data.get("results", [])) if videos_data else 0
            discussion_count = len(discussions_data.get("results", [])) if discussions_data else 0
            faq_count = len(faq_data.get("results", [])) if faq_data else 0
            infobox_count = 1 if infobox_data and infobox_data.get("results") else 0

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "query": query,
                    "total_results": web_count + news_count + video_count + discussion_count + faq_count + infobox_count,
                    "search_engine": "Brave",
                    "params": log_params,
                    "citations_added": citations_added,
                    "result_types": {
                        "web": web_count,
                        "news": news_count,
                        "videos": video_count,
                        "discussions": discussion_count,
                        "faq": faq_count,
                        "infobox": infobox_count
                    }
                }
            )

            logger.info(f"Brave search completed successfully with {citations_added} citations")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"Brave search failed: {e}")
            raise
