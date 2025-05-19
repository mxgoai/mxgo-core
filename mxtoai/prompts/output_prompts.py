"""Output formatting guidelines for different email processing handlers.

These guidelines complement the template prompts by focusing specifically on 
output structure and formatting, while avoiding redundancy with the template content.
"""

# Summarize handler output guidelines
SUMMARIZE_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with a brief overview sentence
2. Use bullet points for key details
3. Group related information together
4. Keep the summary to 3-5 main points
5. End with any action items or next steps
"""

# Research handler output guidelines  
RESEARCH_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Executive Summary: Brief overview (2-3 sentences)
2. Key Findings: 3-5 bullet points of most important insights
3. Detailed Analysis: In-depth exploration with subheadings
4. Supporting Evidence: Data, quotes, statistics
5. References: Numbered citations with links when available
"""

# Simplify handler output guidelines
SIMPLIFY_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Short sentences (10 words or less when possible)
2. One idea per paragraph
3. Use concrete examples and metaphors
4. Include visual descriptions
5. Avoid complex vocabulary
"""

# Ask handler output guidelines
ASK_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Begin with acknowledgment of the question
2. Structure response with clear sections
3. Use examples to illustrate complex points
4. Include actionable recommendations when applicable
5. End with a concise summary
"""

# Fact-check handler output guidelines
FACT_CHECK_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Present each claim in this format:
   - **Claim**: [Original statement]
   - **Status**: [Verified ✓ / Not verified ❌ / Partially verified ⚠️]
   - **Evidence**: [Supporting information]
   - **Sources**: [Citations with links]
2. Use consistent status symbols throughout
"""

# Background research handler output guidelines
BACKGROUND_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with executive summary of key findings
2. Organize information by entity (person, organization, domain)
3. Use tables for comparative information
4. Flag any security concerns prominently
"""

# Translation handler output guidelines
TRANSLATION_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Structure with language detection result
2. Original text in blockquote format
3. Translation with clear heading
4. Notes section for context or ambiguities
5. Use italics for alternative translations
"""

# Scheduling handler output guidelines
SCHEDULE_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Structure sections clearly:
   - **Event Details**: Title, date, time, location
   - **Calendar Links**: Google Calendar, Outlook links
   - **ICS File Notice**: Standard mention of attachment
   - **Notes**: Any assumptions or clarifications
2. Format times consistently with timezone
"""