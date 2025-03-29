import random
import time
import json
from typing import Dict, Any, Generator
import lorem
import faker

fake = faker.Faker()

class MockJinaService:
    """Mock service to simulate Jina AI's DeepSearch API behavior for load testing."""
    
    def __init__(self):
        """Initialize the mock service with configuration."""
        self.min_delay = 60  # 1 minute minimum
        self.max_delay = 600  # 10 minutes maximum
        
    def _generate_mock_urls(self, num_urls: int = 10) -> Dict[str, list]:
        """Generate mock visited and read URLs."""
        domains = ['arxiv.org', 'wikipedia.org', 'github.com', 'research-papers.org', 'academic-journals.com']
        
        all_urls = [
            f"https://{random.choice(domains)}/{fake.slug()}-{fake.random_int(1000, 9999)}"
            for _ in range(num_urls)
        ]
        
        # Randomly select some URLs as "read"
        read_urls = random.sample(all_urls, random.randint(3, len(all_urls)))
        
        return {
            "visitedURLs": all_urls,
            "readURLs": read_urls
        }
    
    def _generate_mock_annotations(self, urls: Dict[str, list]) -> list:
        """Generate mock annotations for the URLs."""
        annotations = []
        for i, url in enumerate(urls["readURLs"], 1):
            annotations.append({
                "type": "url_citation",
                "url_citation": {
                    "id": f"citation_{i}",
                    "url": url,
                    "title": f"Research Paper {i}: {' '.join(fake.words(4))}",
                    "dateTime": fake.date_time_this_year().isoformat()
                }
            })
        return annotations
    
    def _generate_mock_content(self, query: str, annotations: list) -> str:
        """Generate mock research content with citations."""
        sections = [
            "Introduction",
            "Background",
            "Methodology",
            "Results",
            "Discussion",
            "Conclusion"
        ]
        
        content_parts = []
        
        # Add a brief summary of the query
        content_parts.append(f"Based on the research query regarding {query}, here are our findings:\n")
        
        # Generate content for each section with citations
        for section in sections:
            content_parts.append(f"### {section}")
            
            # Generate 2-3 paragraphs for each section
            for _ in range(random.randint(2, 3)):
                paragraph = lorem.paragraph()
                
                # Add 1-2 random citations to each paragraph
                for _ in range(random.randint(1, 2)):
                    if annotations:
                        citation = random.choice(annotations)
                        citation_id = citation["url_citation"]["id"]
                        paragraph += f" |^{citation_id}]"
                
                content_parts.append(paragraph + "\n")
        
        return "\n".join(content_parts)
    
    def _generate_mock_response(self, query: str) -> Dict[str, Any]:
        """Generate a complete mock response."""
        # Generate mock URLs
        urls = self._generate_mock_urls()
        
        # Generate mock annotations
        annotations = self._generate_mock_annotations(urls)
        
        # Generate mock content
        content = self._generate_mock_content(query, annotations)
        
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content,
                    "annotations": annotations
                }
            }],
            **urls,
            "usage": {
                "prompt_tokens": random.randint(100, 500),
                "completion_tokens": random.randint(1000, 3000),
                "total_tokens": random.randint(1500, 4000)
            },
            "numURLs": len(urls["visitedURLs"])
        }
    
    def _stream_mock_response(self, response: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """Stream a mock response with realistic delays."""
        content = response["choices"][0]["message"]["content"]
        annotations = response["choices"][0]["message"]["annotations"]
        
        # Split content into chunks
        chunks = content.split("\n")
        chunk_delay = random.uniform(0.5, 2.0)  # Delay between chunks
        
        # Stream the role first
        yield {
            "choices": [{
                "delta": {
                    "role": "assistant"
                }
            }]
        }
        time.sleep(chunk_delay)
        
        # Stream content chunks
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            # Occasionally add thinking markers
            if random.random() < 0.2:
                yield {
                    "choices": [{
                        "delta": {
                            "type": "think",
                            "content": "<think>Analyzing sources...</think>"
                        }
                    }]
                }
                time.sleep(chunk_delay)
            
            # Stream the chunk
            yield {
                "choices": [{
                    "delta": {
                        "content": chunk + "\n"
                    }
                }]
            }
            time.sleep(chunk_delay)
        
        # Stream annotations at the end
        yield {
            "choices": [{
                "delta": {
                    "annotations": annotations
                }
            }]
        }
        
        # Final response with URLs
        yield {
            **{k: v for k, v in response.items() if k not in ["choices"]},
            "choices": [{"delta": {}}]
        }
    
    def process_request(
        self,
        query: str,
        stream: bool = False,
        reasoning_effort: str = "medium"
    ) -> Dict[str, Any] | Generator[Dict[str, Any], None, None]:
        """Process a mock request with realistic delays."""
        # Calculate delay based on reasoning effort
        effort_multipliers = {
            "low": 0.7,
            "medium": 1.0,
            "high": 1.3
        }
        
        base_delay = random.uniform(self.min_delay, self.max_delay)
        total_delay = base_delay * effort_multipliers[reasoning_effort]
        
        # Generate mock response
        response = self._generate_mock_response(query)
        
        if stream:
            # For streaming, we'll distribute the delay across chunks
            time.sleep(total_delay * 0.1)  # Initial delay
            return self._stream_mock_response(response)
        else:
            # For non-streaming, use the full delay
            time.sleep(total_delay)
            return response 