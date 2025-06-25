import random
import time
from collections.abc import Generator
from typing import Any

import faker

fake = faker.Faker()

# Constants
THINKING_MARKER_PROBABILITY = 0.2


class MockJinaService:
    """
    Mock service to simulate Jina AI's DeepSearch API behavior for load testing.
    """

    def __init__(self):
        """
        Initialize the mock service with configuration.
        """
        self.min_delay = 60  # 1 minute minimum
        self.max_delay = 600  # 10 minutes maximum

    def _generate_mock_urls(self, num_urls: int = 10) -> dict[str, list]:
        """
        Generate mock visited and read URLs.

        Args:
            num_urls: Number of URLs to generate

        Returns:
            dict: Dictionary containing visited and read URLs

        """
        domains = ["arxiv.org", "wikipedia.org", "github.com", "research-papers.org", "academic-journals.com"]

        all_urls = [
            f"https://{random.choice(domains)}/{fake.slug()}-{fake.random_int(1000, 9999)}" for _ in range(num_urls)
        ]

        # Randomly select some URLs as "read"
        read_urls = random.sample(all_urls, random.randint(3, len(all_urls)))  # noqa: S311

        return {"visitedURLs": all_urls, "readURLs": read_urls}

    def _generate_mock_annotations(self, urls: dict[str, list]) -> list:
        """
        Generate mock annotations for the URLs.

        Args:
            urls: Dictionary containing visited and read URLs

        Returns:
            list: List of annotations for the URLs

        """
        annotations = []
        for i, url in enumerate(urls["readURLs"], 1):
            annotations.append(
                {
                    "type": "url_citation",
                    "url_citation": {
                        "id": f"citation_{i}",
                        "url": url,
                        "title": f"Research Paper {i}: {' '.join(fake.words(4))}",
                        "dateTime": fake.date_time_this_year().isoformat(),
                    },
                }
            )
        return annotations

    def _generate_mock_content(self, query: str, annotations: list) -> str:
        """
        Generate mock research content with citations.

        Args:
            query: Research query
            annotations: List of annotations for the URLs

        Returns:
            str: Generated content with citations

        """
        sections = ["Introduction", "Background", "Methodology", "Results", "Discussion", "Conclusion"]

        content_parts = []

        # Add a brief summary of the query
        content_parts.append(f"Based on the research query regarding {query}, here are our findings:\n")

        # Generate content for each section with citations
        for section in sections:
            content_parts.append(f"### {section}")

            # Generate 2-3 paragraphs for each section
            for _ in range(random.randint(2, 3)):  # noqa: S311
                paragraph = fake.paragraph()

                # Add 1-2 random citations to each paragraph
                for _ in range(random.randint(1, 2)):  # noqa: S311
                    if annotations:
                        citation = random.choice(annotations)  # noqa: S311
                        citation_id = citation["url_citation"]["id"]
                        paragraph += f" |^{citation_id}]"

                content_parts.append(paragraph + "\n")

        return "\n".join(content_parts)

    def _generate_mock_response(self, query: str) -> dict[str, Any]:
        """
        Generate a complete mock response.

        Args:
            query: Research query

        Returns:
            dict: Mock response containing choices, URLs, and usage information

        """
        # Generate mock URLs
        urls = self._generate_mock_urls()

        # Generate mock annotations
        annotations = self._generate_mock_annotations(urls)

        # Generate mock content
        content = self._generate_mock_content(query, annotations)

        return {
            "choices": [{"message": {"role": "assistant", "content": content, "annotations": annotations}}],
            **urls,
            "usage": {
                "prompt_tokens": random.randint(100, 500),  # noqa: S311
                "completion_tokens": random.randint(1000, 3000),  # noqa: S311
                "total_tokens": random.randint(1500, 4000),  # noqa: S311
            },
            "numURLs": len(urls["visitedURLs"]),
        }

    def _stream_mock_response(self, response: dict[str, Any]) -> Generator[dict[str, Any]]:
        """
        Stream a mock response with realistic delays.

        Args:
            response: Mock response containing choices, URLs, and usage information
        Yields:
            dict: Streamed response with role, content, and annotations

        """
        content = response["choices"][0]["message"]["content"]
        annotations = response["choices"][0]["message"]["annotations"]

        # Split content into chunks
        chunks = content.split("\n")
        chunk_delay = random.uniform(0.5, 2.0)  # Delay between chunks  # noqa: S311

        # Stream the role first
        yield {"choices": [{"delta": {"role": "assistant"}}]}
        time.sleep(chunk_delay)

        # Stream content chunks
        for _i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue

            # Occasionally add thinking markers
            if random.random() < THINKING_MARKER_PROBABILITY:  # noqa: S311
                yield {"choices": [{"delta": {"type": "think", "content": "<think>Analyzing sources...</think>"}}]}
                time.sleep(chunk_delay)

            # Stream the chunk
            yield {"choices": [{"delta": {"content": chunk + "\n"}}]}
            time.sleep(chunk_delay)

        # Stream annotations at the end
        yield {"choices": [{"delta": {"annotations": annotations}}]}

        # Final response with URLs
        yield {**{k: v for k, v in response.items() if k not in ["choices"]}, "choices": [{"delta": {}}]}

    def process_request(
        self, query: str, *, stream: bool = False, reasoning_effort: str = "medium"
    ) -> dict[str, Any] | Generator[dict[str, Any]]:
        """
        Process a mock request with realistic delays.

        Args:
            query: Research query
            stream: Whether to stream the response
            reasoning_effort: Level of reasoning effort ("low", "medium", "high")

        Returns:
            dict or Generator: Mock response or streamed response

        """
        # Calculate delay based on reasoning effort
        effort_multipliers = {"low": 0.7, "medium": 1.0, "high": 1.3}

        base_delay = random.uniform(self.min_delay, self.max_delay)  # noqa: S311
        total_delay = base_delay * effort_multipliers[reasoning_effort]

        # Generate mock response
        response = self._generate_mock_response(query)

        if stream:
            # For streaming, we'll distribute the delay across chunks
            time.sleep(total_delay * 0.1)  # Initial delay
            return self._stream_mock_response(response)
        # For non-streaming, use the full delay
        time.sleep(total_delay)
        return response
