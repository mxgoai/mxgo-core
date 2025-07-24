import json
import os
import uuid
from typing import TYPE_CHECKING

from mxgo._logging import get_logger
from mxgo.email_handles import DEFAULT_EMAIL_HANDLES
from mxgo.routed_litellm_model import RoutedLiteLLMModel
from mxgo.schemas import EmailSuggestionRequest, EmailSuggestionResponse, SuggestionDetail

if TYPE_CHECKING:
    from smolagents import ChatMessage

logger = get_logger(__name__)

# Constants for suggestion limits
MIN_SUGGESTIONS = 3
MAX_SUGGESTIONS = 7

# System capabilities - extracted from email handles and their templates
SYSTEM_CAPABILITIES = """## Available Email Processing Handles

- **summarize**: Systematically analyze and summarize content from all sources with clear structure and action focus. Processes email content, attachments, and external references to provide executive summaries, main points, action items, and additional context.

- **research**: Conduct comprehensive research and provide detailed analysis with proper sections and citations. Uses deep research tools to gather current information, analyze findings, and provide supporting evidence with academic tone.

- **simplify**: Transform complex content into clear, accessible explanations using simple language and relatable examples. Breaks down technical jargon, adds helpful analogies, and makes content understandable to general audiences.

- **ask**: Execute custom tasks and workflows systematically with research, analysis, and professional presentation. Handles any custom request, research needs, content creation, and provides comprehensive solutions with proper formatting.

- **fact-check**: Systematically verify claims and statements with comprehensive source validation and transparent uncertainty handling. Extracts all verifiable claims, searches for evidence, cross-references multiple sources, and provides clear verification status.

- **background-research**: Conduct comprehensive business intelligence research on individuals and organizations. Provides strategic insights for business decisions, company analysis, professional profiles, and competitive context.

- **translate**: Provide accurate translations with cultural context preservation and clear explanation of translation decisions. Detects source language, chooses appropriate translation approach, and provides cultural adaptations.

- **meeting**: Intelligently extract, research, and schedule meetings or appointments with proper validation. Handles participant research, time resolution, and generates calendar invitations with comprehensive meeting details.

- **pdf**: Intelligently analyze email content and create professional PDF document exports. Removes email metadata, preserves content structure, and generates clean, formatted documents for sharing or archiving.

- **schedule**: Analyze email content to extract scheduling requirements for future or recurring task processing. Creates appropriate cron expressions for reminders, recurring tasks, and future email processing.

- **delete**: Analyze email content to identify and delete scheduled tasks. Handles task ID extraction and provides clear confirmation of task removal.

- **news**: Search for current news and breaking stories with comprehensive analysis and grouping. Provides structured news summaries with source citations, grouped by themes to avoid repetition.
"""

SUGGESTION_INSTRUCTIONS = f"""## Email Analysis and Suggestion Guidelines

You are an intelligent email assistant that suggests appropriate email processing handles based on email content. Analyze the provided email and suggest 1-3 relevant handles that would be most beneficial for the user.

### Suggestion Patterns:

**For first-time or unfamiliar senders:**
- Suggest **background-research** to learn about the sender, their company, and context
- Instructions: Can be empty (auto-research) OR specific like "Research sender's company financial status and recent funding news"

**For promotional/marketing content:**
- Suggest **fact-check** for claims about products, discounts, or company achievements
- Instructions: Specific claims to verify, e.g., "Verify the 50% discount claim and check if customer testimonials are authentic"

**For news articles or subjective content:**
- Suggest **fact-check** for political news, controversial topics, or opinion pieces
- Instructions: Specific claims to verify, e.g., "Verify the unemployment statistics and check sources for bias"

**For news and current events requests:**
- Suggest **news** for breaking news, current events, or topics requiring latest updates
- Instructions: Specific topics to search for, e.g., "Find latest news about AI regulation" OR empty for general news

**For long emails or emails with attachments:**
- Suggest **summarize** to extract key points and action items efficiently
- Instructions: Usually empty (auto-summarize) OR specific focus like "Focus on action items and deadlines"

**For meeting requests or scheduling:**
- Suggest **meeting** for coordinating times, creating calendar invites, or scheduling appointments
- Instructions: Specific when finding services, e.g., "Find a therapist in Beverly Hills accepting Cigna insurance" OR empty for simple scheduling

**For complex or technical content:**
- Suggest **simplify** for legal documents, technical specifications, or industry jargon
- Instructions: Usually empty (auto-simplify) OR specific focus like "Focus on explaining the legal obligations and risks"

**For information that needs verification:**
- Suggest **fact-check** for statistics, claims, news reports, or research findings
- Instructions: Specific claims to verify, important for investment advice, health claims, or market predictions

**For content worth preserving:**
- Suggest **pdf** for important documents, research findings, or content worth archiving
- Instructions: Usually empty (auto-export) OR formatting preferences

**For research needs:**
- Suggest **research** for topics requiring deep investigation or current market analysis
- Instructions: Specific research focus, e.g., "Focus on competitive analysis and market trends for AI startups"

**For custom requests:**
- Suggest **ask** for specific questions, custom analysis, or unique workflows
- Instructions: Specific when complex, e.g., "Compare these 3 products and recommend best option for small business" OR empty for general help

### Output Requirements:

Generate {MIN_SUGGESTIONS}-{MAX_SUGGESTIONS} suggestions as a JSON object with this exact structure, ordered by relevance (most relevant first):
```json
{{
    "suggestions": [
    {{
        "suggestion_title": "Short, crisp title (e.g., 'Research sender', 'Verify claims', 'Summarize email')",
      "suggestion_to_email": "appropriate_handle@mxgo.com",
      "suggestion_cc_emails": [],
      "suggestion_email_instructions": "Specific instruction to forward to the handle (optional - can be empty if handle can process automatically)"
    }}
  ]
}}
```

### Title Guidelines:
- Keep titles to 2-4 words maximum
- Use action verbs (Research, Verify, Summarize, Check, Schedule, etc.)
- Make titles immediately understandable
- Examples of good titles: "Research sender", "Verify claims", "Schedule meeting", "Check facts", "Summarize content"
- Examples of bad titles: "Research sender's company background and recent news", "Verify all the claims made in this promotional email"

### Guidelines for suggestion_email_instructions:
- **Leave EMPTY** when the email handle can process the original email automatically (e.g., summarize, translate, pdf export)
- **Include SPECIFIC instructions** when you need to guide the handle for better results
- **Examples of when to include instructions:**
  - fact-check: "Verify the 50% discount claim and check if the company testimonials are real"
  - background-research: "Research the sender's company financial status and recent news"
  - ask: "Compare this product with alternatives and recommend the best option"
  - meeting: "Find a therapist in Beverly Hills who accepts Cigna insurance"
- **Examples of when to leave empty:**
  - summarize: (handle will automatically summarize the email content)
  - translate: (handle will detect and translate automatically)
  - pdf: (handle will export the email content automatically)
  - simplify: (handle will automatically simplify complex content)

### General Guidelines:
- Provide {MIN_SUGGESTIONS}-{MAX_SUGGESTIONS} most relevant suggestions ordered by relevance (most relevant first)
- Make suggestion titles short, crisp, and actionable (max 3-4 words)
- Always include varied suggestions that address different aspects
- Prioritize suggestions that provide immediate value
- Consider the user's likely intent and context
- Order suggestions by relevance: most valuable/applicable suggestions first
- Avoid duplicate or very similar suggestions
"""


def get_default_suggestions() -> list[SuggestionDetail]:
    """
    Get default suggestions with fresh UUIDs.

    Returns:
        list[SuggestionDetail]: List of default suggestions with unique IDs

    """
    return [
        SuggestionDetail(
            suggestion_title="Ask anything",
            suggestion_id=str(uuid.uuid4()),  # Generate fresh ID each time
            suggestion_to_email="ask@mxgo.com",
            suggestion_cc_emails=[],
            suggestion_email_instructions="",  # Empty - ask handle can process any email automatically
        )
    ]


def validate_suggestion_to_email(suggestion_to_email: str) -> str:
    """
    Validate that the suggestion_to_email corresponds to a valid email handle alias.

    Args:
        suggestion_to_email: The email address to validate (e.g., "summarize" from "summarize@mxgo.com")

    Returns:
        str: The validated email address, or "ask@mxgo.com" if invalid

    """
    # Extract handle from email (e.g., "summarize" from "summarize@mxgo.com")
    if "@" not in suggestion_to_email:
        return "ask@mxgo.com"

    handle_part = suggestion_to_email.split("@")[0]

    # Check if handle or any alias matches
    valid_handles = set()
    for handle_config in DEFAULT_EMAIL_HANDLES:
        valid_handles.add(handle_config.handle)
        valid_handles.update(handle_config.aliases)

    if handle_part in valid_handles:
        return suggestion_to_email
    logger.warning(
        f"Invalid handle '{handle_part}' in suggestion_to_email '{suggestion_to_email}', defaulting to ask@mxgo.com"
    )
    return "ask@mxgo.com"


def get_suggestions_model() -> RoutedLiteLLMModel:
    """
    FastAPI dependency to get the suggestions model.

    Returns:
        RoutedLiteLLMModel: Configured model for generating suggestions

    """
    # Get the suggestions model group from environment
    suggestions_model_group = os.getenv("LITELLM_SUGGESTIONS_MODEL_GROUP", "gpt-4")

    # Create model with direct target model specification
    return RoutedLiteLLMModel(
        target_model=suggestions_model_group,
        flatten_messages_as_text=False,
    )


def build_suggestion_prompt(request: EmailSuggestionRequest) -> str:
    """
    Build the suggestion prompt by combining system capabilities, instructions, and email data.

    Args:
        request: EmailSuggestionRequest containing email data

    Returns:
        str: Complete prompt for the LLM

    """
    # Format attachment information
    attachment_info = ""
    if request.attachments:
        attachment_info = "\n**Attachments:**\n"
        for att in request.attachments:
            file_type_info = f" ({att.file_type})" if att.file_type else ""
            attachment_info += f"- {att.filename}{file_type_info} - {att.file_size} bytes\n"

    # Build the complete prompt
    return f"""{SYSTEM_CAPABILITIES}

{SUGGESTION_INSTRUCTIONS}

## Email to Analyze:

**From:** {request.sender_email}
**To:** {request.user_email_id}
**Subject:** {request.subject}
**CC:** {", ".join(request.cc_emails) if request.cc_emails else "None"}
{attachment_info}
**Content:**
{request.email_content}

## Analysis Context:
- Email ID: {request.email_identified}
- User: {request.user_email_id}

Please analyze this email and provide {MIN_SUGGESTIONS}-{MAX_SUGGESTIONS} relevant suggestions in the required JSON format, ordered by relevance (most relevant first). Focus on the most valuable actions the user could take with this email content. Keep suggestion titles short and crisp (2-4 words max)."""


async def generate_suggestions(
    request: EmailSuggestionRequest,
    model: RoutedLiteLLMModel | None = None,
) -> EmailSuggestionResponse:
    """
    Generate suggestions for an email using the LLM model.

    Args:
        request: EmailSuggestionRequest containing email data
        model: RoutedLiteLLMModel for generating suggestions

    Returns:
        EmailSuggestionResponse: Response containing suggested actions

    """
    # If model is not provided, get the default suggestions model
    if model is None:
        model = get_suggestions_model()

    try:
        logger.info(f"Generating suggestions for email {request.email_identified}")

        # Build the prompt
        prompt = build_suggestion_prompt(request)

        # Prepare messages for the model
        messages = [
            {
                "role": "system",
                "content": "You are an intelligent email assistant that suggests appropriate email processing handles based on email content. Always respond with valid JSON in the specified format.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        # Generate suggestions using JSON mode
        response: ChatMessage = model(
            messages=messages,
            response_format={"type": "json_object"},  # Enable JSON mode
            temperature=0.3,  # Lower temperature for more consistent suggestions
        )

        # Parse the JSON response
        try:
            suggestions_data = json.loads(response.content)
            suggestions_list = suggestions_data.get("suggestions", [])

            # Convert to SuggestionDetail objects
            generated_suggestions = []
            for suggestion in suggestions_list:
                # Validate and potentially correct the suggestion_to_email
                suggested_email = validate_suggestion_to_email(suggestion.get("suggestion_to_email", "ask@mxgo.com"))

                generated_suggestions.append(
                    SuggestionDetail(
                        suggestion_title=suggestion.get("suggestion_title", "Suggestion"),
                        suggestion_id=str(uuid.uuid4()),  # Generate unique ID programmatically
                        suggestion_to_email=suggested_email,
                        suggestion_cc_emails=suggestion.get("suggestion_cc_emails", []),
                        suggestion_email_instructions=suggestion.get("suggestion_email_instructions", ""),
                    )
                )

            # Ensure we have at least MIN_SUGGESTIONS total (including default)
            default_suggestions = get_default_suggestions()

            # If we have fewer than MAX_SUGGESTIONS generated suggestions, add default
            if len(generated_suggestions) < MAX_SUGGESTIONS:
                all_suggestions = generated_suggestions + default_suggestions
            else:
                # Take top (MAX_SUGGESTIONS - 1) generated suggestions and add default
                all_suggestions = generated_suggestions[: MAX_SUGGESTIONS - 1] + default_suggestions

            logger.info(
                f"Generated {len(generated_suggestions)} suggestions for email {request.email_identified}, total returned: {len(all_suggestions)}"
            )

            return EmailSuggestionResponse(
                email_identified=request.email_identified,
                user_email_id=request.user_email_id,
                suggestions=all_suggestions,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response content: {response.content}")

            # Return default suggestions on JSON parse error
            return EmailSuggestionResponse(
                email_identified=request.email_identified,
                user_email_id=request.user_email_id,
                suggestions=get_default_suggestions(),
            )

    except Exception as e:
        logger.error(f"Error generating suggestions for email {request.email_identified}: {e}")

        # Return default suggestions on any error
        return EmailSuggestionResponse(
            email_identified=request.email_identified,
            user_email_id=request.user_email_id,
            suggestions=get_default_suggestions(),
        )
