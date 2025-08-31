import asyncio
import json
import os
import uuid
from typing import TYPE_CHECKING

from mxgo._logging import get_logger
from mxgo.email_handles import DEFAULT_EMAIL_HANDLES
from mxgo.routed_litellm_model import RoutedLiteLLMModel
from mxgo.schemas import EmailSuggestionRequest, EmailSuggestionResponse, RiskAnalysisResponse, SuggestionDetail

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

You are an intelligent email assistant that analyzes email content to provide a crisp overview and suggest appropriate processing handles. 

### Overview Generation:
Generate a concise 1-2 sentence overview that captures the essence of what's happening in this email thread. Focus on:
- **Subject importance**: Use the subject line as primary context
- **Most recent developments**: Prioritize the latest email content and any urgent matters
- **Key actionable items**: Highlight what requires immediate attention or response
- **Crisp language**: Use professional, clear sentences that provide instant situational awareness

### Suggestion Generation:
Analyze the provided email and suggest 1-3 relevant handles that would be most beneficial for the user.

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

Generate a JSON object with this exact structure, ordered by relevance (most relevant first):
```json
{{
    "overview": "Brief, crisp 1-2 sentence summary emphasizing subject and most recent developments that require attention",
    "suggestions": [
    {{
        "suggestion_title": "Short, crisp title (e.g., 'Research sender', 'Verify claims', 'Summarize email')",
      "suggestion_to_email": "appropriate_handle@mxgo.ai",
      "suggestion_cc_emails": [],
      "suggestion_email_instructions": "Specific instruction to forward to the handle (optional - can be empty if handle can process automatically)"
    }}
  ]
}}
```

The overview should provide instant situational awareness - what's happening, why it matters, and what needs attention. Include {MIN_SUGGESTIONS}-{MAX_SUGGESTIONS} relevant suggestions.

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


RISK_INSTRUCTIONS = """
## Risk and Spam Scoring Instructions

You are an email risk & spam scorer. Use only the fields provided. Do not invent headers or do network lookups.
“Risk” = phishing/malware/fraud/BEC likelihood.
“Spam” = unsolicited/low-value bulk/marketing/scam likelihood.
Output MUST be JSON only with keys:
{ "risk_prob_pct": 0-100, "risk_reason": string, "spam_prob_pct": 0-100, "spam_reason": string }
No extra text.

Scoring guidance (consistency > creativity):
- Map signals to bands:
  • Risk 0–10: benign; 15–35: mildly suspicious; 40–60: unclear but multiple flags;
    65–85: strong risk; 90–100: obvious phish/malware.
  • Spam 0–15: transactional/personal; 20–40: unsolicited but relevant; 50–70: typical marketing/bulk; 80–100: scammy bulk.
- Prefer one crisp 1-line reason (≤120 chars). If prob <15 or no clear reason, use "".
- When both risk & spam signals exist, set both independently (e.g., BEC: high risk, low spam).

What to analyze from provided fields:
- sender_email vs user_email_id: compare domains; if different, that’s normal, but consider impersonation tone.
- cc_emails: large list or many mixed domains → higher spam.
- subject + email_content:
  • Risky intents: verify/login/password reset, wire/gift cards/invoice payment, secrecy/urgency (“24 hours”, “final notice”).
  • Look for links/domains in text (http/https) and brand-mismatch wording.
  • Requests for credentials or payment near links → raise risk.
  • Overblown promos, coupons, “unsubscribe”, generic greetings → raise spam.
- attachments (filename, type, size):
  • Dangerous extensions: .exe, .scr, .js, .vbs, .hta, .iso, .img, .lnk, .jar, .ps1, .bat, .cmd
  • Double extensions (e.g., .pdf.exe) are high risk. Archives with “invoice/payment” wording → risk up.
- De-risking cues: specific prior ticket/order refs, personal context, polite transactional tone; no links/attachments.

If information is insufficient for a dimension, keep that probability low and reason "".

User input (JSON):
{
  "email_identified": "{email_identified}",
  "user_email_id": "{user_email_id}",
  "sender_email": "{sender_email}",
  "cc_emails": {cc_emails_json},
  "Subject": "{subject}",
  "email_content": "{email_content}",
  "attachments": {attachments_json}
}

Return JSON only with:
{ "risk_prob_pct": int, "risk_reason": string, "spam_prob_pct": int, "spam_reason": string }
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
            suggestion_to_email="ask@mxgo.ai",
            suggestion_cc_emails=[],
            suggestion_email_instructions="",  # Empty - ask handle can process any email automatically
        )
    ]


def validate_suggestion_to_email(suggestion_to_email: str) -> str:
    """
    Validate that the suggestion_to_email corresponds to a valid email handle alias.

    Args:
        suggestion_to_email: The email address to validate (e.g., "summarize" from "summarize@mxgo.ai")

    Returns:
        str: The validated email address, or "ask@mxgo.ai" if invalid

    """
    # Extract handle from email (e.g., "summarize" from "summarize@mxgo.ai")
    if "@" not in suggestion_to_email:
        return "ask@mxgo.ai"

    handle_part = suggestion_to_email.split("@")[0]

    # Check if handle or any alias matches
    valid_handles = set()
    for handle_config in DEFAULT_EMAIL_HANDLES:
        valid_handles.add(handle_config.handle)
        valid_handles.update(handle_config.aliases)

    if handle_part in valid_handles:
        return suggestion_to_email
    logger.warning(
        f"Invalid handle '{handle_part}' in suggestion_to_email '{suggestion_to_email}', defaulting to ask@mxgo.ai"
    )
    return "ask@mxgo.ai"


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


def build_risk_prompt(request: EmailSuggestionRequest) -> str:
    """
    Build the risk analysis prompt for the given email request.

    Args:
        request: EmailSuggestionRequest containing email data

    Returns:
        str: Complete prompt for risk analysis LLM
    """
    # Format attachments as JSON for the risk prompt
    attachments_json = json.dumps([
        {
            "filename": att.filename,
            "file_type": att.file_type,
            "file_size": att.file_size
        }
        for att in request.attachments
    ])
    
    # Format CC emails as JSON
    cc_emails_json = json.dumps(request.cc_emails)
    
    # Build the risk analysis prompt by inserting actual email data
    return f"""{RISK_INSTRUCTIONS}

User input (JSON):
{{
  "email_identified": "{request.email_identified}",
  "user_email_id": "{request.user_email_id}",
  "sender_email": "{request.sender_email}",
  "cc_emails": {cc_emails_json},
  "Subject": "{request.subject}",
  "email_content": "{request.email_content}",
  "attachments": {attachments_json}
}}"""


async def analyse_risk(
    request: EmailSuggestionRequest,
    model: RoutedLiteLLMModel | None = None,
) -> RiskAnalysisResponse:
    """
    Analyze risk and spam probability for an email using the LLM model.

    Args:
        request: EmailSuggestionRequest containing email data
        model: RoutedLiteLLMModel for generating risk analysis

    Returns:
        RiskAnalysisResponse: Response containing risk and spam analysis
    """
    # Build the risk prompt
    prompt = build_risk_prompt(request)
    logger.info("Risk analysis prompt built {}", prompt)

    # Prepare messages for the model
    messages = [
        {
            "role": "system",
            "content": "You are an email risk and spam analyzer. Always respond with valid JSON in the specified format.",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    # Generate risk analysis using JSON mode
    response: ChatMessage = model(
        messages=messages,
        response_format={"type": "json_object"},  # Enable JSON mode
        temperature=0.1,  # Very low temperature for consistent risk scoring
    )

    risk_data = json.loads(response.content)
    return RiskAnalysisResponse(
        risk_prob_pct=risk_data.get("risk_prob_pct", 0),
        risk_reason=risk_data.get("risk_reason", ""),
        spam_prob_pct=risk_data.get("spam_prob_pct", 0),
        spam_reason=risk_data.get("spam_reason", ""),
    )


async def generate_suggestions(
    request: EmailSuggestionRequest,
    model: RoutedLiteLLMModel | None = None,
) -> EmailSuggestionResponse:
    """
    Generate suggestions and risk analysis for an email using the LLM model.

    Args:
        request: EmailSuggestionRequest containing email data
        model: RoutedLiteLLMModel for generating suggestions and risk analysis

    Returns:
        EmailSuggestionResponse: Response containing suggested actions and risk analysis

    """
    try:
        logger.info(f"Generating suggestions and risk analysis for email {request.email_identified}")

        # Execute both suggestions and risk analysis in parallel
        suggestions_task = asyncio.create_task(_generate_suggestions_only(request, model))
        risk_task = asyncio.create_task(analyse_risk(request, model))

        # Wait for both responses
        suggestions_result, risk_result = await asyncio.gather(
            suggestions_task, risk_task, return_exceptions=True
        )

        # Handle suggestion response (with error checking)
        if isinstance(suggestions_result, Exception):
            logger.exception(f"Error in suggestion generation {suggestions_result}")
            overview = ""
            all_suggestions = get_default_suggestions()
        else:
            overview, all_suggestions = suggestions_result

        # Handle risk response (with error checking)
        if isinstance(risk_result, Exception):
            logger.error(f"Error in risk analysis {risk_result}")
            risk_analysis = None
        else:
            risk_analysis = risk_result

        return EmailSuggestionResponse(
            email_identified=request.email_identified,
            user_email_id=request.user_email_id,
            overview=overview,
            suggestions=all_suggestions,
            risk_analysis=risk_analysis,
        )

    except Exception as e:
        logger.error(f"Error generating suggestions for email {request.email_identified}: {e}")

        # Return default suggestions on any error
        return EmailSuggestionResponse(
            email_identified=request.email_identified,
            user_email_id=request.user_email_id,
            overview="",
            suggestions=get_default_suggestions(),
            risk_analysis=None,
        )


async def _generate_suggestions_only(
    request: EmailSuggestionRequest,
    model: RoutedLiteLLMModel,
) -> tuple[str, list[SuggestionDetail]]:
    """
    Internal function to generate only suggestions (not risk analysis).
    
    Returns:
        tuple[str, list[SuggestionDetail]]: Overview and suggestions list
    """
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
    suggestions_data = json.loads(response.content)
    overview = suggestions_data.get("overview", "")
    suggestions_list = suggestions_data.get("suggestions", [])

    # Convert to SuggestionDetail objects
    generated_suggestions = []
    for suggestion in suggestions_list:
        # Validate and potentially correct the suggestion_to_email
        suggested_email = validate_suggestion_to_email(suggestion.get("suggestion_to_email", "ask@mxgo.ai"))

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

    return overview, all_suggestions
