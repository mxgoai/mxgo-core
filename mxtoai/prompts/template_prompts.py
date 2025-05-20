"""Template prompts for different email processing handlers."""

# Summarize email handler template
SUMMARIZE_TEMPLATE = """
Provide a concise, direct summary of the key points from the email and attachments.

Content Guidelines:
1. Get straight to the key points
2. No redundant introductions
3. Include only relevant information
4. Keep it concise but complete
5. Use a natural, conversational tone

Remember:
- If the user has specific intent, then focus on what the user asked about
- Skip unnecessary formality
- Ensure proper markdown formatting
"""

# Research handler template
RESEARCH_TEMPLATE = """
Conduct comprehensive research and provide a detailed analysis with proper sections and citations.
For this task, you must use deep research tool at least once with appropriate query.

Response Requirements:
1. Structure with clear sections:
   - ### Executive Summary
   - ### Key Findings
   - ### Detailed Analysis
   - ### Supporting Evidence
   - ### References
2. Include proper citations [1], [2], etc.
3. Format tables using markdown table syntax
4. Use proper paragraph spacing

Content Guidelines:
1. Maintain academic tone
2. Include specific data points
3. Support claims with evidence
4. Provide comprehensive analysis
5. Always give a disclaimer that sometimes links may be outdated or incorrect depending on age of the source
"""

# Simplify handler template
SIMPLIFY_TEMPLATE = """
Explain the content in simple, easy-to-understand terms without technical jargon, like you're explaining to a 5-year-old.

Content Guidelines:
1. Use simple language
2. Avoid technical terms
3. Give everyday examples
4. Keep explanations short
5. Use bullet points for clarity
"""

# Ask handler template
ASK_TEMPLATE = """
Provide a complete response addressing all aspects of the query.

Content Guidelines:
1. Brief summary of understanding
2. Detailed response
3. Additional insights if relevant
4. Next steps or recommendations
"""

# Fact-check handler template
FACT_TEMPLATE = """
Validate and fact-check the content thoroughly. Use web search tool to find reliable sources alongside deep search tool.
Do not use deep search directly, use web search and page visit tool, if you're not satisfied with results, then only try deep search.

Response Requirements:
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
6. Always give a disclaimer that sometimes links may be outdated or incorrect depending on age of the source
"""

# Background research handler template
BACKGROUND_RESEARCH_TEMPLATE = """
Research identities mentioned in email including names, email addresses, and domains. Focus on finding background information about the sender and other parties mentioned.
Do not use deep search directly, use web search and page visit tool, if you're not satisfied with results, then only try deep search.

Response Requirements:
1. Structure with clear sections:
   - ### Executive Summary
   - ### Key Findings
   - ### Detailed Analysis
   - ### Supporting Evidence
   - ### References
2. Include proper citations [1], [2], etc.
3. Format tables using markdown table syntax
4. Use proper paragraph spacing

Content Guidelines:
1. Focus on relevant background
2. Include verifiable information
3. Note information sources
4. Maintain professional tone
5. Flag any concerns
6. Always give a disclaimer that sometimes links may be outdated or incorrect depending on age of the source
"""

# Translation handler template
TRANSLATE_TEMPLATE = """
Provide accurate translation with proper formatting.
Detect language if not specified. If non-English, translate to English. If English, look for requested target language or ask user.

Response Requirements:
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

# Scheduling handler template  
SCHEDULE_TEMPLATE = """
Extract meeting/scheduling related information including participants, timing, and location details to provide scheduling recommendations

**STEP 1: Assess Clarity**
- Determine if the email provides enough specific information to create a calendar event. Key details needed are:
    - A clear event purpose/title.
    - A specific date (or range to choose from).
    - A specific start time (or range).
    - A timezone (or enough context to infer one, otherwise default to UTC and state assumption).
    - Optionally: duration/end time, location, attendees.

**STEP 2: Handle Ambiguity**
- **IF** the details are too vague or missing critical information (like a specific date or time):
    - **DO NOT** attempt to call the `ScheduleTool`.
    - Respond to the user explaining which details are unclear or missing.
    - Ask specific questions to get the needed clarification (e.g., "Could you please specify the date and time for this meeting?", "What timezone should I use?", "What is the main topic or title for this event?").
    - Your entire response should be this request for clarification.

**STEP 3: Extract and Format (If Clear)**
- **IF** the details are clear enough:
    - Extract the event title, start time, end time (if specified), description, location, and attendee emails.
    - Check email thread and generate a title & description based on the context if not explicitly provided
    - **IMPORTANT DATE/TIME FORMATTING:** Determine the correct timezone and format ALL start/end times as ISO 8601 strings including the offset (e.g., '2024-08-15T10:00:00+01:00', '2024-08-16T09:00:00Z'). State any timezone assumptions made.

**STEP 4: Use Tool (If Clear)**
- Call the `ScheduleTool` (`schedule_generator`) with the extracted and formatted details:
    - `title`: The event title.
    - `start_time`: The ISO 8601 formatted start time string (with timezone).
    - `end_time`: The ISO 8601 formatted end time string (with timezone), if available.
    - `description`: Event description, if available.
    - `location`: Event location, if available.
    - `attendees`: List of attendee email strings, if available.

**STEP 5: Format Response (If Tool Used)**
- Structure the response based on the `ScheduleTool` output:
    1.  **Summary of Extracted Details:** Briefly list the key event details identified.
    2.  **Add to Calendar:** Use the `calendar_links` output. Present the links clearly using markdown:
        - [Add to Google Calendar](google_link_url)
        - [Add to Outlook Calendar](outlook_link_url)
    3.  **Calendar File:** Mention that a standard calendar file (.ics) has been attached to this email for easy import into most calendar applications. (Do not mention tools or internal processes).
    4.  **Notes/Recommendations:** Include any relevant notes or assumptions made (like assumed timezone).

**GENERAL FORMATTING:**
- Use clear markdown (bolding, bullet points).
- Ensure any generated "Add to Calendar" links are functional.
- Present information concisely.
"""
