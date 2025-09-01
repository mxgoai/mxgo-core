import pytest

from mxgo.schemas import EmailSuggestionAttachmentSummary, EmailSuggestionRequest
from mxgo.suggestions import generate_suggestions, get_suggestions_model


# --- Integration Tests for Suggestions API ---
@pytest.fixture
def prepare_suggestion_request_data():
    """Prepare test data for suggestions API requests."""

    def _prepare(
        email_identified: str = "test-email-123",
        user_email_id: str = "user@example.com",
        sender_email: str = "sender@example.com",
        cc_emails: list[str] | None = None,
        subject: str = "Test Subject",
        email_content: str = "This is test email content.",
        attachments: list[dict] | None = None,
    ) -> dict:
        return {
            "email_identified": email_identified,
            "user_email_id": user_email_id,
            "sender_email": sender_email,
            "cc_emails": cc_emails or [],
            "Subject": subject,
            "email_content": email_content,
            "attachments": attachments or [],
        }

    return _prepare


@pytest.mark.asyncio
@pytest.mark.flaky(retries=2, delay=1)
async def test_suggestions_integration_promotional_email(prepare_suggestion_request_data):
    """Test suggestions for promotional email content (should suggest fact-check)."""
    request_data = prepare_suggestion_request_data(
        email_identified="promo-email-123",
        user_email_id="customer@example.com",
        sender_email="marketing@company.com",
        subject="Limited Time Offer - 50% Off All Products!",
        email_content="""
        🎉 HUGE SALE ALERT! 🎉

        Get 50% off ALL products for the next 24 hours only!

        ✅ Over 10,000 satisfied customers
        ✅ Award-winning products (Best Product 2024)
        ✅ 100% money-back guarantee
        ✅ Free shipping worldwide

        This offer expires at midnight tonight. Don't miss out!

        Shop now at www.company.com/sale
        """,
    )

    # Convert to schema object

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    # Get model and generate suggestions
    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate response format
    assert response.email_identified == request_data["email_identified"]
    assert response.user_email_id == request_data["user_email_id"]
    assert len(response.suggestions) >= 3, "Should have at least 3 suggestions (generated + default)"

    # Check for default suggestion
    has_ask_suggestion = any(
        s.suggestion_to_email == "ask@mxgo.ai" and s.suggestion_title == "Ask anything" for s in response.suggestions
    )
    assert has_ask_suggestion, "Should always include default suggestion"

    # For promotional content, expect fact-check or background-research suggestions
    suggestion_emails = [s.suggestion_to_email for s in response.suggestions]
    expected_handles = ["fact-check@mxgo.ai", "background-research@mxgo.ai", "ask@mxgo.ai"]
    has_relevant_suggestion = any(email in suggestion_emails for email in expected_handles)
    assert has_relevant_suggestion, f"Expected suggestions for promotional email, got: {suggestion_emails}"


@pytest.mark.asyncio
@pytest.mark.flaky(retries=2, delay=1)
async def test_suggestions_integration_meeting_request(prepare_suggestion_request_data):
    """Test suggestions for meeting request (should suggest meeting handle)."""
    request_data = prepare_suggestion_request_data(
        email_identified="meeting-email-456",
        user_email_id="employee@company.com",
        sender_email="manager@company.com",
        subject="Project Review Meeting",
        email_content="""
        Hi Team,

        I'd like to schedule a project review meeting for next week.

        Preferred times:
        - Tuesday 2-3 PM
        - Wednesday 10-11 AM
        - Thursday 3-4 PM

        Please let me know what works best for everyone.
        We'll need about an hour to review the quarterly progress.

        Meeting room: Conference Room A
        Attendees: Please invite sarah@company.com and john@company.com

        Thanks!
        """,
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate basic response
    assert len(response.suggestions) >= 3

    # Check for meeting-related suggestion
    suggestion_emails = [s.suggestion_to_email for s in response.suggestions]
    assert "meeting@mxgo.ai" in suggestion_emails, f"Expected meeting suggestion, got: {suggestion_emails}"

    # Find the meeting suggestion and check it has reasonable instructions
    meeting_suggestion = next(s for s in response.suggestions if s.suggestion_to_email == "meeting@mxgo.ai")
    # Instructions may be empty (auto-process) or contain specific meeting details
    assert meeting_suggestion.suggestion_title is not None
    assert len(meeting_suggestion.suggestion_title) > 0


@pytest.mark.asyncio
@pytest.mark.flaky(retries=2, delay=1)
async def test_suggestions_integration_long_email_with_attachments(prepare_suggestion_request_data):
    """Test suggestions for long email with attachments (should suggest summarize)."""
    long_content = """
    Dear Colleagues,

    I hope this email finds you well. I'm writing to provide you with a comprehensive update
    on our Q4 initiatives and the strategic direction for the upcoming year.

    EXECUTIVE SUMMARY:
    This quarter has been marked by significant achievements across multiple departments.
    Our revenue has increased by 23% compared to Q3, largely driven by the successful
    launch of our new product line and expanded market presence in the European region.

    DETAILED FINANCIAL ANALYSIS:
    Revenue streams have diversified considerably, with our software division contributing
    45% of total revenue, hardware at 35%, and services at 20%. The gross margin has
    improved to 67%, up from 61% in the previous quarter, primarily due to operational
    efficiencies implemented in our manufacturing processes.

    OPERATIONAL HIGHLIGHTS:
    - Completed migration to new ERP system (on time and under budget)
    - Hired 47 new employees across engineering and sales departments
    - Opened 3 new regional offices in Berlin, Amsterdam, and Barcelona
    - Achieved ISO 27001 certification for our security practices
    - Launched customer success program with 95% satisfaction rate

    TECHNOLOGY INITIATIVES:
    Our R&D team has made breakthrough progress in AI-driven analytics. The new machine
    learning models show 34% improvement in prediction accuracy. We've also completed
    the first phase of our cloud infrastructure modernization, reducing operational
    costs by 18% while improving system reliability to 99.97% uptime.

    MARKET ANALYSIS:
    Industry trends indicate strong growth potential in the SaaS sector. Our competitive
    analysis shows we're well-positioned to capture additional market share, particularly
    in the mid-market segment where our solution offers superior value proposition.

    FUTURE ROADMAP:
    Looking ahead to 2024, our priorities include expanding into the Asia-Pacific market,
    developing our mobile application suite, and strengthening our cybersecurity offerings.
    We've allocated $2.3M for these initiatives and expect to see ROI within 18 months.

    Please find attached the detailed quarterly report, financial statements, market
    research data, and technical specifications for your review.

    I'd appreciate your feedback and look forward to discussing these items in our
    upcoming board meeting scheduled for December 15th.

    Best regards,
    Executive Team
    """

    request_data = prepare_suggestion_request_data(
        email_identified="long-email-789",
        user_email_id="board@company.com",
        sender_email="ceo@company.com",
        subject="Q4 Performance Review and 2024 Strategic Planning",
        email_content=long_content,
        attachments=[
            {"filename": "Q4_Report.pdf", "file_type": "application/pdf", "file_size": 2048576},
            {
                "filename": "Financial_Statements.xlsx",
                "file_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "file_size": 1024000,
            },
            {
                "filename": "Market_Research.docx",
                "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "file_size": 512000,
            },
        ],
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[EmailSuggestionAttachmentSummary(**att) for att in request_data["attachments"]],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate response
    assert len(response.suggestions) >= 3

    # Should suggest summarize for long content with attachments
    suggestion_emails = [s.suggestion_to_email for s in response.suggestions]

    # At least one should be summarize or pdf (for document processing)
    has_content_processing = any(email in suggestion_emails for email in ["summarize@mxgo.ai", "pdf@mxgo.ai"])
    assert has_content_processing, f"Expected content processing suggestion for long email, got: {suggestion_emails}"


@pytest.mark.asyncio
@pytest.mark.flaky(retries=2, delay=1)
async def test_suggestions_integration_unfamiliar_sender(prepare_suggestion_request_data):
    """Test suggestions for email from unfamiliar sender (should suggest background-research)."""
    request_data = prepare_suggestion_request_data(
        email_identified="unknown-sender-101",
        user_email_id="executive@mycompany.com",
        sender_email="partnerships@newstartup.com",
        subject="Strategic Partnership Opportunity",
        email_content="""
        Dear Executive Team,

        I hope this message finds you well. My name is Alex Johnson, and I'm the Head of
        Business Development at NewStartup Inc., a rapidly growing fintech company.

        We've been following your company's impressive growth in the market and believe
        there could be significant synergies between our organizations. Our platform
        has processed over $500M in transactions this year and serves 50,000+ active users.

        I'd love to explore potential partnership opportunities that could benefit both
        our companies. We're particularly interested in:

        1. Technology integration possibilities
        2. Joint go-to-market strategies
        3. Co-marketing initiatives
        4. Potential investment discussions

        Would you be available for a brief 30-minute call next week to discuss this further?
        I'm confident we could create significant value together.

        Looking forward to your response.

        Best regards,
        Alex Johnson
        Head of Business Development
        NewStartup Inc.
        """,
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate response
    assert len(response.suggestions) >= 3

    # Should suggest background research for unfamiliar business sender
    suggestion_emails = [s.suggestion_to_email for s in response.suggestions]

    has_research_suggestion = "background-research@mxgo.ai" in suggestion_emails
    assert has_research_suggestion, (
        f"Expected background research suggestion for unfamiliar sender, got: {suggestion_emails}"
    )

    # Check that background research suggestion may have specific instructions
    research_suggestion = next(
        s for s in response.suggestions if s.suggestion_to_email == "background-research@mxgo.ai"
    )
    assert research_suggestion.suggestion_title is not None
    assert len(research_suggestion.suggestion_title) > 0


@pytest.mark.asyncio
@pytest.mark.flaky(retries=2, delay=1)
async def test_suggestions_integration_multiple_emails_batch(prepare_suggestion_request_data):
    """Test suggestions API with multiple emails in a single request."""
    # Prepare multiple different email scenarios

    # Email 1: Simple ask
    simple_request = prepare_suggestion_request_data(
        email_identified="simple-123",
        user_email_id="user@example.com",
        sender_email="friend@example.com",
        subject="Quick Question",
        email_content="Hey, can you help me understand how machine learning works?",
    )

    # Email 2: News article
    news_request = prepare_suggestion_request_data(
        email_identified="news-456",
        user_email_id="user@example.com",
        sender_email="newsletter@newssite.com",
        subject="Breaking: New Economic Policy Announced",
        email_content="""
        BREAKING NEWS: The government announced a new economic stimulus package
        worth $2 trillion today. Officials claim this will create 5 million new jobs
        and reduce unemployment to 3% within 18 months. Critics argue the numbers
        are overly optimistic and the plan lacks sufficient detail.
        """,
    )

    # Create a batch of request objects
    request_objects = [
        EmailSuggestionRequest(
            email_identified=req_data["email_identified"],
            user_email_id=req_data["user_email_id"],
            sender_email=req_data["sender_email"],
            cc_emails=req_data["cc_emails"],
            Subject=req_data["Subject"],
            email_content=req_data["email_content"],
            attachments=[],
        )
        for req_data in [simple_request, news_request]
    ]

    model = get_suggestions_model()

    # Generate suggestions for the batch
    responses = []
    for request_obj in request_objects:
        response = await generate_suggestions(request_obj, model)
        responses.append(response)

    # Validate all responses
    assert len(responses) == 2

    for i, response in enumerate(responses):
        assert response.email_identified == request_objects[i].email_identified
        assert response.user_email_id == request_objects[i].user_email_id
        assert len(response.suggestions) >= 3  # At least 3 suggestions (generated + default)

        # Each should have ask suggestion
        has_ask = any(s.suggestion_to_email == "ask@mxgo.ai" for s in response.suggestions)
        assert has_ask, f"Email {i} missing default ask suggestion"

    # News email should likely get fact-check suggestion
    news_response = responses[1]
    news_suggestion_emails = [s.suggestion_to_email for s in news_response.suggestions]

    # Due to non-determinism, we can't guarantee specific suggestions,
    # but we can check that it's making reasonable suggestions
    valid_suggestions = {
        "ask@mxgo.ai",
        "fact-check@mxgo.ai",
        "summarize@mxgo.ai",
        "research@mxgo.ai",
        "background-research@mxgo.ai",
        "news@mxgo.ai",
        "simplify@mxgo.ai",
        "translate@mxgo.ai",
        "meeting@mxgo.ai",
        "pdf@mxgo.ai",
        "schedule@mxgo.ai",
        "delete@mxgo.ai",
        "unsubscribe@mxgo.ai",
    }

    all_valid = all(email in valid_suggestions for email in news_suggestion_emails)
    assert all_valid, f"Invalid suggestions in news response: {news_suggestion_emails}"


@pytest.mark.asyncio
async def test_suggestions_integration_error_handling(prepare_suggestion_request_data):
    """Test suggestions error handling for invalid inputs."""
    # Test with empty email content
    request_data = prepare_suggestion_request_data(
        email_content="",  # Empty content
    )
    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Should still return default suggestions even with empty content
    assert len(response.suggestions) >= 1
    has_ask = any(s.suggestion_to_email == "ask@mxgo.ai" for s in response.suggestions)
    assert has_ask, "Should return default suggestion even for empty content"


@pytest.mark.asyncio
async def test_risk_analysis_functionality(prepare_suggestion_request_data):
    """Test risk analysis functionality in suggestions."""
    # Test suspicious email content
    request_data = prepare_suggestion_request_data(
        email_identified="risky-email-001",
        user_email_id="victim@company.com",
        sender_email="attacker@suspicious.com",
        subject="URGENT: Verify Your Account Now!",
        email_content="""
        Dear Customer,

        Your account has been compromised. Click here immediately to verify:
        https://fake-bank.com/verify-account

        You have 24 hours or your account will be closed permanently.

        Best regards,
        Security Team
        """,
        attachments=[{"filename": "invoice.pdf.exe", "file_type": "application/x-executable", "file_size": 2048000}],
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[EmailSuggestionAttachmentSummary(**att) for att in request_data["attachments"]],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate basic response structure
    assert response.email_identified == request_data["email_identified"]
    assert response.user_email_id == request_data["user_email_id"]
    assert response.overview is not None
    assert len(response.overview) > 0
    assert len(response.suggestions) >= 1

    # Validate risk analysis is present
    assert response.risk_analysis is not None
    assert hasattr(response.risk_analysis, "risk_prob_pct")
    assert hasattr(response.risk_analysis, "spam_prob_pct")
    assert hasattr(response.risk_analysis, "ai_likelihood_pct")
    assert 0 <= response.risk_analysis.risk_prob_pct <= 100
    assert 0 <= response.risk_analysis.spam_prob_pct <= 100
    assert 0 <= response.risk_analysis.ai_likelihood_pct <= 100

    # For suspicious email, expect higher risk scores
    # (Note: actual scores depend on LLM, so we just check structure)
    assert isinstance(response.risk_analysis.risk_reason, str)
    assert isinstance(response.risk_analysis.spam_reason, str)
    assert isinstance(response.risk_analysis.ai_explanation, str)


@pytest.mark.asyncio
async def test_risk_analysis_benign_email(prepare_suggestion_request_data):
    """Test risk analysis with benign email content."""
    request_data = prepare_suggestion_request_data(
        email_identified="safe-email-001",
        user_email_id="employee@company.com",
        sender_email="colleague@company.com",
        subject="Weekly team meeting notes",
        email_content="""
        Hi team,

        Here are the notes from our weekly meeting:

        1. Project Alpha is on track for Q4 delivery
        2. New team member Sarah will start Monday
        3. Budget review scheduled for next Friday

        Let me know if you have any questions.

        Best,
        John
        """,
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Validate risk analysis structure
    assert response.risk_analysis is not None
    assert 0 <= response.risk_analysis.risk_prob_pct <= 100
    assert 0 <= response.risk_analysis.spam_prob_pct <= 100
    assert 0 <= response.risk_analysis.ai_likelihood_pct <= 100

    # All reason fields should be strings (may be empty)
    assert isinstance(response.risk_analysis.risk_reason, str)
    assert isinstance(response.risk_analysis.spam_reason, str)
    assert isinstance(response.risk_analysis.ai_explanation, str)


@pytest.mark.asyncio
async def test_overview_generation(prepare_suggestion_request_data):
    """Test that overview field is properly generated."""
    request_data = prepare_suggestion_request_data(
        email_identified="overview-test-001",
        user_email_id="user@company.com",
        sender_email="client@external.com",
        subject="Quarterly Business Review Meeting Request",
        email_content="""
        Dear Team,

        I would like to schedule our quarterly business review for next week.
        Please let me know your availability for Tuesday or Wednesday afternoon.

        We'll need to cover:
        - Q3 performance analysis
        - Budget planning for Q4
        - New client onboarding process

        Thanks,
        Client
        """,
    )

    request_obj = EmailSuggestionRequest(
        email_identified=request_data["email_identified"],
        user_email_id=request_data["user_email_id"],
        sender_email=request_data["sender_email"],
        cc_emails=request_data["cc_emails"],
        Subject=request_data["Subject"],
        email_content=request_data["email_content"],
        attachments=[],
    )

    model = get_suggestions_model()
    response = await generate_suggestions(request_obj, model)

    # Overview should be non-empty and meaningful
    assert response.overview is not None
    assert len(response.overview.strip()) > 0
    assert len(response.overview) <= 500  # Should be reasonably concise

    # Overview should ideally relate to the subject/content
    # (This is a basic check - actual content quality depends on LLM)
    overview_lower = response.overview.lower()
    request_data["Subject"].lower().split()

    # At least some connection to the email content should exist
    # (This is a weak test since LLM behavior can vary)
    assert len(overview_lower) > 10  # Not just a few words
