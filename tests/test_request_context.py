"""
Tests for RequestContext functionality.
"""

from mxgo.request_context import CitationManager, RequestContext, _sanitize_api_title
from mxgo.schemas import EmailAttachment, EmailRequest


def test_citation_manager_basic():
    """Test basic citation manager functionality."""
    manager = CitationManager()

    # Test initial state
    assert not manager.has_citations()
    assert manager.get_citations().sources == []

    # Add a web citation
    citation_id = manager.add_web_source("https://example.com", "Example", visited=True)
    assert citation_id == "1"
    assert manager.has_citations()

    # Check citations
    citations = manager.get_citations()
    assert len(citations.sources) == 1
    assert citations.sources[0].url == "https://example.com"
    assert citations.sources[0].title == "Example"
    assert citations.sources[0].description == "visited"


def test_citation_manager_deduplication():
    """Test that duplicate URLs are handled correctly."""
    manager = CitationManager()

    # Add same URL twice
    id1 = manager.add_web_source("https://example.com", "Example 1")
    id2 = manager.add_web_source("https://example.com", "Example 2")

    # Should return the same ID
    assert id1 == id2
    assert len(manager.get_citations().sources) == 1


def test_citation_manager_references_section():
    """Test references section generation."""
    manager = CitationManager()

    # Add different types of sources
    manager.add_web_source("https://example.com", "Example Website", visited=True)
    manager.add_web_source("https://search.com", "Search Result", visited=False)
    manager.add_attachment_source("document.pdf", "Important document")
    manager.add_api_source("LinkedIn Profile Data")

    # Generate references section
    references = manager.generate_references_section()

    assert "### References" in references
    assert "#### Visited Pages" in references
    assert "#### Search Results" in references
    assert "#### Attachments" in references
    assert "#### Data Sources" in references


def test_request_context_basic():
    """Test basic RequestContext functionality."""
    email_request = EmailRequest(
        from_email="test@example.com", to="recipient@example.com", subject="Test Subject", textContent="Test content"
    )

    context = RequestContext(email_request)

    # Test email request access
    assert context.email_request.from_email == "test@example.com"
    assert context.email_request.subject == "Test Subject"

    # Test citation methods
    citation_id = context.add_web_citation("https://example.com", "Example")
    assert citation_id == "1"
    assert context.has_citations()

    # Test references generation
    references = context.get_references_section()
    assert "### References" in references


def test_request_context_attachment_paths():
    """Test attachment path extraction."""
    attachment = EmailAttachment(
        filename="test.pdf", contentType="application/pdf", size=1024, path="/path/to/test.pdf"
    )

    email_request = EmailRequest(
        from_email="test@example.com",
        to="recipient@example.com",
        subject="Test Subject",
        textContent="Test content",
        attachments=[attachment],
    )

    context = RequestContext(email_request)
    paths = context.get_attachment_paths()

    assert len(paths) == 1
    assert paths[0] == "/path/to/test.pdf"


def test_citation_manager_api_title_sanitization():
    """Test API title sanitization."""
    # Test basic sanitization
    assert _sanitize_api_title("LinkedIn Profile via RapidAPI") == "LinkedIn Profile"
    assert _sanitize_api_title("Data Source (RapidAPI)") == "Data Source"
    assert _sanitize_api_title("") == "External Data Source"
    assert _sanitize_api_title("ab") == "External Data Source"  # Too short
    assert _sanitize_api_title("Normal Title") == "Normal Title"


def test_request_context_attachment_service():
    """Test attachment service loading functionality."""
    email_request = EmailRequest(
        from_email="test@example.com", to="recipient@example.com", subject="Test Subject", textContent="Test content"
    )

    # Test attachment info
    attachment_info = [
        {
            "filename": "test.txt",
            "path": "/nonexistent/path",  # Won't actually load in test
            "type": "text/plain",
            "size": 100,
        }
    ]

    context = RequestContext(email_request, attachment_info)

    # Verify attachment service is initialized
    assert context.attachment_service is not None
    assert isinstance(context.attachment_service.list_attachments(), list)


def test_request_context_backward_compatibility():
    """Test that RequestContext still works without attachment_info."""
    email_request = EmailRequest(
        from_email="test@example.com", to="recipient@example.com", subject="Test Subject", textContent="Test content"
    )

    # Should work without attachment_info parameter
    context = RequestContext(email_request)
    assert context.attachment_service is not None
    assert len(context.attachment_service.list_attachments()) == 0
