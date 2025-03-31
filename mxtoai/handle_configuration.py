from typing import Optional

from pydantic import BaseModel


class EmailHandleInstructions(BaseModel):
    handle: str
    aliases: list[str]
    process_attachments: bool
    deep_research_mandatory: bool
    specific_research_instructions: Optional[str] = None
    rejection_message: Optional[str] = "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
    task_template: Optional[str] = None
    requires_language_detection: bool = False  # Specifically for translate handle
    requires_schedule_extraction: bool = False  # Specifically for schedule handle
    add_summary: bool = False  # Default to False, enable only where needed
    target_model: Optional[str] = "gpt-4"  # Default to gpt-4, can be overridden per handle
    output_template: Optional[str] = None  # Template for structuring the output

# Define all email handle configurations
EMAIL_HANDLES = [
    EmailHandleInstructions(
        handle="summarize",
        aliases=["summarise"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Provide a concise, direct summary of the key points from the email and attachments. Focus only on the main information requested.",
        add_summary=False,  # No need for additional summary section
        target_model="gpt-4",
        task_template="""
Process this email with a focus on delivering a clear, concise summary.

Content Guidelines:
1. Get straight to the key points
2. No redundant introductions
3. Include only relevant information
4. Keep it concise but complete
5. Use a natural, conversational tone

Remember:
- Focus on what the user asked about
- Skip unnecessary formality
- Ensure proper markdown formatting
"""
    ),
    EmailHandleInstructions(
        handle="research",
        aliases=["deep-research"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Conduct comprehensive research and provide a detailed analysis with proper sections and citations.",
        add_summary=True,
        target_model="gpt-4-reasoning",
        task_template="""
Conduct thorough research and present findings in a structured format.
For this task, you must use deep research tool at least once with appropriate query.

FORMATTING REQUIREMENTS:
1. Use proper markdown formatting:
   - ### for section headers
   - **bold** for emphasis and key terms
   - _italics_ for quotes
   - Proper bullet points and numbered lists
   - [text](url) for links
   - > for quotations
2. Structure with clear sections:
   - ### Executive Summary
   - ### Key Findings
   - ### Detailed Analysis
   - ### Supporting Evidence
   - ### References
3. Include proper citations [1], [2], etc.
4. Format tables using markdown table syntax
5. Use proper paragraph spacing

Content Guidelines:
1. Maintain academic tone
2. Include specific data points
3. Support claims with evidence
4. Provide comprehensive analysis
"""
    ),
    EmailHandleInstructions(
        handle="simplify",
        aliases=["eli5"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Explain the content in simple, easy-to-understand terms without technical jargon.",
        add_summary=False,
        target_model="gpt-4",
        task_template="""
Simplify the content for easy understanding.

Content Guidelines:
1. Use simple language
2. Avoid technical terms
3. Give everyday examples
4. Keep explanations short
5. Use bullet points for clarity
"""
    ),
    EmailHandleInstructions(
        handle="ask",
        aliases=["custom", "agent", "assist", "assistant"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Provide a comprehensive response addressing all aspects of the query.",
        add_summary=True,
        target_model="gpt-4",
        task_template="""
Provide a complete response addressing all aspects of the query.

Content Guidelines:
1. Brief summary of understanding
2. Detailed response
3. Additional insights if relevant
4. Next steps or recommendations
"""
    ),
    EmailHandleInstructions(
        handle="fact-check",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Validate all facts claimed in the email and provide citations from reliable sources",
        add_summary=False,
        target_model="gpt-4-reasoning",
        task_template="""
Validate and fact-check the content thoroughly.

FORMATTING REQUIREMENTS:
1. Use proper markdown formatting:
   - **Claim**: for stating each claim
   - _Source_: for source citations
   - ✓ or ❌ for verification status
   - Bullet points for supporting evidence
   - [text](url) for reference links
2. Structure each fact-check:
   - Original claim
   - Verification status
   - Supporting evidence
   - Source citations
3. Use clear paragraph breaks between checks

Content Guidelines:
1. State each claim clearly
2. Provide verification status
3. Include supporting evidence
4. Cite reliable sources
5. Note any uncertainties
"""
    ),
    EmailHandleInstructions(
        handle="background-research",
        aliases=["background-check"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Research identities mentioned in email including names, email addresses, and domains. Focus on finding background information about the sender and other parties mentioned.",
        add_summary=True,
        target_model="gpt-4-reasoning",
        task_template="""
Research and present background information in a structured format.

FORMATTING REQUIREMENTS:
1. Use proper markdown formatting:
   - ### for entity sections
   - **bold** for key findings
   - _italics_ for dates and locations
   - Bullet points for discrete facts
   - [text](url) for reference links
2. Structure with clear sections:
   - Entity name/identifier
   - Key background points
   - Relevant history
   - Current status
   - Source citations
3. Use proper spacing between sections

Content Guidelines:
1. Focus on relevant background
2. Include verifiable information
3. Note information sources
4. Maintain professional tone
5. Flag any concerns
"""
    ),
    EmailHandleInstructions(
        handle="translate",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Detect language if not specified. If non-English, translate to English. If English, look for requested target language or ask user.",
        add_summary=False,
        target_model="gpt-4",
        task_template="""
Provide accurate translation with proper formatting.

FORMATTING REQUIREMENTS:
1. Use proper markdown formatting:
   - **Original**: for source text
   - **Translation**: for translated text
   - _Notes_: for translation notes
   - > for quoted text blocks
   - Proper paragraph breaks
2. Structure the response:
   - Language detection result
   - Original text block
   - Translation block
   - Any relevant notes
3. Preserve original formatting

Content Guidelines:
1. Maintain original meaning
2. Note any ambiguities
3. Preserve cultural context
4. Include helpful notes
"""
    ),
    EmailHandleInstructions(
        handle="schedule",
        aliases=["schedule-action"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Extract meeting/scheduling related information including participants, timing, and location details to provide scheduling recommendations",
        add_summary=True,
        target_model="gpt-4",
        task_template="""
Extract and present scheduling information clearly.

FORMATTING REQUIREMENTS:
1. Use proper markdown formatting:
   - **Event**: for event title
   - **When**: for date/time
   - **Where**: for location
   - **Who**: for participants
   - Bullet points for details
   - _Notes_ for additional info
2. Structure the response:
   - Event overview
   - Key details
   - Action items
   - Recommendations
3. Use clear formatting for times and dates

Content Guidelines:
1. Extract all scheduling details
2. Format dates consistently
3. List all participants
4. Note any conflicts
5. Provide clear next steps
"""
    )
]

# Create a mapping of handles (including aliases) to their configurations
HANDLE_MAP = {}
for config in EMAIL_HANDLES:
    HANDLE_MAP[config.handle] = config
    for alias in config.aliases:
        HANDLE_MAP[alias] = config
