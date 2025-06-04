"""
Template prompts for different email processing handlers.
"""

# Summarize email handler template
SUMMARIZE_TEMPLATE = """
Systematically analyze and summarize content from all available sources with clear structure and action focus.

# Summarization Process

## STEP 1: Content Analysis
- **Process ALL sources**: Email content, attachments, embedded links, external references
- **Assess complexity**: Determine appropriate detail level (concise/detailed/executive summary)
- **Identify priorities**: Key messages, action items, deadlines, stakeholder impact

## STEP 2: Structured Summary Format
```
## Executive Summary
[2-3 sentences capturing core message and significance]

## Key Information
- **From**: [Sender and context]
- **Topic**: [Main subject/purpose]
- **Urgency**: [Timeline/priority level]
- **Stakeholders**: [Who needs to know/act]

## Main Points
[Organized breakdown of key information from all sources]

## Action Items
- [Specific actions required with deadlines]
- [Responsible parties if mentioned]

## Additional Context
[Important background, implications, supporting details]
```

## STEP 3: Quality Standards
- **Process all content sources** before summarizing
- **Highlight action items** clearly
- **Note any inaccessible content** transparently
- **Match detail level** to content complexity
- **Maintain context** while being concise

**Example Output:**
```
## Executive Summary
Q3 sales report shows 12% revenue growth with West region leading performance, requiring strategy review meeting.

## Key Information
- **From**: Sales Director Sarah Chen
- **Topic**: Q3 2024 Sales Performance Review
- **Urgency**: Standard quarterly review
- **Stakeholders**: Management team, regional leads

## Main Points
**Sales Performance (from Excel attachment):**
- Total revenue: $4.2M (12% increase from Q2)
- West region: 23% growth, exceeding targets
- Product line A: 18% growth, strongest performer
- Customer acquisition: 156 new accounts

## Action Items
- Review West region strategies for replication
- Address East region performance decline
- Quarterly review meeting: Next Friday

## Additional Context
Strong Q3 performance driven by West region success and Product A growth. East region needs attention.
```

**Critical Requirements:**
- Process ALL available content sources (email, attachments, links)
- Structure information for easy scanning
- Clearly identify action items and deadlines
- Note any content processing limitations
- Adapt detail level to content complexity
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
2. Include proper citations [1], [2], etc. if the deep_research tool provides them. For web_search results, extract the title and URL for each source and list them under the 'References' section using markdown link format (e.g., 1. [Page Title](URL)).
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
Transform complex content into clear, accessible explanations using simple language and relatable examples.

# Simplification Process

## STEP 1: Complexity Assessment
- **Identify complexity sources**: Technical jargon, abstract concepts, complex processes, dense information
- **Determine target level**: General public understanding (assume no specialized knowledge)
- **Preserve core truth**: Maintain essential accuracy while removing complexity

## STEP 2: Simplification Strategy
**Language Techniques:**
- Replace technical terms with everyday language
- Break complex sentences into shorter, clearer ones
- Use active voice and concrete examples
- Add helpful analogies from familiar experiences

**Structure Format:**
```
## The Simple Version
[One clear sentence explaining the core concept]

## What This Means
[2-3 sentences expanding on the main idea]

## Here's How It Works
[Step-by-step breakdown in simple terms]

## Think of It Like This
[Relatable analogy or real-world example]

## Why This Matters
[Practical significance in everyday terms]

## The Bottom Line
[Key takeaway anyone can remember]
```

## STEP 3: Quality Check
- Could a 12-year-old understand the main point?
- Are technical terms explained or replaced?
- Do analogies help rather than confuse?
- Is the essential message preserved?

**Example:**
```
## The Simple Version
Blockchain is like a permanent record book that many people keep copies of, making it almost impossible to cheat.

## What This Means
Instead of one person keeping important records, thousands of computers around the world each keep identical copies. When something new happens, all computers must agree before it gets written down permanently.

## Think of It Like This
Imagine if everyone in your class had a copy of the attendance record. If someone tried to fake their attendance, everyone else would notice because their copies wouldn't match.

## Why This Matters
This makes it very hard to fake records or steal things, because you'd have to fool thousands of computers at the same time.

## The Bottom Line
Many computers protecting the same records together = super secure information.
```

**Requirements:**
- Use simple, everyday language
- Include helpful analogies and examples
- Preserve accuracy while removing jargon
- Make content accessible to general audiences
- Maintain respectful tone (not condescending)
"""

# Ask handler template
ASK_TEMPLATE = """
Execute custom tasks and workflows systematically with research, analysis, and professional presentation.

# General Task Execution Process

## STEP 1: Task Analysis & Planning
- **Understand the request**: Break down what the user wants accomplished
- **Identify components**: Research needs, data gathering, analysis, formatting requirements
- **Determine approach**: What tools and steps are needed to complete this task
- **Set quality standards**: How should the final output be structured and presented

## STEP 2: Systematic Execution
**Research & Data Gathering:**
- Use web search for current information and trends
- Visit relevant websites and sources
- Process any attachments or provided materials
- Gather comprehensive data before analysis

**Analysis & Curation:**
- Filter and prioritize information based on relevance and quality
- Identify key insights, patterns, or important details
- Apply criteria for selection (trending, popularity, importance)
- Add context and explanatory information

**Content Creation:**
- Structure information logically and professionally
- Create engaging and informative content
- Include proper citations and links
- Format for easy reading and comprehension

## STEP 3: Professional Presentation
**Standard Output Structure:**
```
## [Task Title/Summary]
[Brief overview of what was accomplished]

## [Main Content Sections]
[Organized, formatted content with clear headers]

### [Subsections as needed]
- [Bullet points, lists, or structured information]
- [Include links, sources, and references]

## Key Insights/Summary
[Important takeaways or conclusions]

## Sources & References
[All sources used with proper attribution]
```

## STEP 4: Quality Standards
- **Comprehensive research** using available tools
- **Professional formatting** with clear structure
- **Accurate information** with proper source attribution
- **Engaging presentation** that's easy to read and understand
- **Complete execution** of all requested components

**Example Task: "Prepare a newsletter with top 10 trending HN posts"**

```
## Hacker News Top 10 Trending Posts Newsletter
Daily digest of the most engaging discussions and innovations from the HN community.

## Today's Top Trending Posts

### 1. [Post Title](HN-link)
**Summary**: Brief description of the post content and significance
**Why It's Trending**: Key reasons for community engagement
**Discussion Highlights**: Notable comments or insights from HN users
**Relevance**: Why this matters to the tech community

### 2. [Next Post Title](HN-link)
[Same format structure]

[Continue for all 10 posts]

## Key Themes Today
- [Pattern 1]: Multiple posts about [topic]
- [Pattern 2]: Community interest in [area]
- [Pattern 3]: Emerging trends in [field]

## Community Insights
Notable discussions, debates, or expert opinions from today's conversations.

## Sources
- Hacker News front page and trending algorithms
- Individual post discussions and comment threads
- Community engagement metrics and voting patterns
```

**Requirements:**
- Execute any custom task or workflow systematically
- Use all available tools for research and analysis
- Present results professionally with proper structure
- Include comprehensive sources and attribution
- Adapt format and approach to specific task requirements
"""

# Fact-check handler template
FACT_TEMPLATE = """
Systematically verify claims and statements with comprehensive source validation and transparent uncertainty handling.

# Fact-Checking Methodology - SYSTEMATIC VERIFICATION PROCESS

## STEP 1: CLAIM EXTRACTION & CATEGORIZATION
**Extract ALL verifiable claims from the content:**
- **Factual Claims**: Statistics, dates, events, scientific facts
- **Attribution Claims**: Quotes, statements attributed to people/organizations
- **Causal Claims**: "X causes Y", "Due to X, Y happened"
- **Comparative Claims**: Rankings, comparisons, "better/worse than"
- **Current Status Claims**: Current prices, status, availability

**Claim Prioritization:**
- **High Priority**: Core claims central to the message
- **Medium Priority**: Supporting details and context
- **Low Priority**: Tangential or well-established facts

## STEP 2: SYSTEMATIC VERIFICATION STRATEGY
**Verification Hierarchy:**
1. **Primary Sources**: Official websites, government data, organization statements
2. **Academic Sources**: Peer-reviewed research, institutional studies, wikipedia
3. **Established News Sources**: Reuters, AP, BBC, established newspapers
4. **Industry Sources**: Trade publications, industry reports
5. **Secondary Analysis**: Expert commentary, analysis pieces

**Search Strategy:**
1. **Direct Claim Search**: Search exact claim or paraphrased version
2. **Source Verification**: Search for original source of claimed information
3. **Counter-Evidence Search**: Actively search for contradicting information
4. **Recent Updates**: Check for more recent information that might contradict
5. **Context Search**: Understand broader context around the claim

## STEP 3: SOURCE QUALITY ASSESSMENT
**Evaluate each source on:**
<source_quality_checklist>
✓ Authority: Is the source authoritative on this topic?
✓ Recency: How current is the information?
✓ Bias Assessment: Any obvious political, commercial, or ideological bias?
✓ Corroboration: Do multiple independent sources agree?
✓ Original vs. Secondary: Is this the original source or reporting on it?
✓ Methodology: For studies/surveys, is methodology sound?
</source_quality_checklist>

## STEP 4: VERIFICATION STATUS DETERMINATION
**Classification System:**
- ✅ **VERIFIED**: Multiple reliable sources confirm
- ⚠️ **PARTIALLY VERIFIED**: Some aspects confirmed, others unclear
- ❌ **FALSE**: Reliable sources contradict the claim
- 🔍 **UNVERIFIABLE**: Insufficient reliable sources available
- 📅 **OUTDATED**: Was true but circumstances have changed
- 🤔 **DISPUTED**: Reliable sources disagree

## STEP 5: UNCERTAINTY & LIMITATION HANDLING
**When verification is unclear:**
- **Multiple conflicting sources**: Present different perspectives with source quality
- **Insufficient information**: Clearly state limitations and what's unknown
- **Rapidly changing situations**: Note information currency and change potential
- **Complex claims**: Break down into verifiable components

**Fallback Strategy:**
```
Unable to fully verify this claim due to:

**Verification Challenges:**
- [Specific challenge, e.g., "Limited reliable sources available"]
- [Another challenge, e.g., "Conflicting expert opinions"]

**What We Found:**
- [Partial information available]
- [Related verified information]

**Recommendation:**
- [Suggested approach for the user]
- [When to check for updates]
```

## STEP 6: COMPREHENSIVE REPORTING FORMAT

**For Each Claim:**
```
**Claim**: [Original statement]
**Status**: [Verification symbol + status]
**Evidence**:
- [Supporting evidence with source quality]
- [Contradicting evidence if any]
**Source Quality**: [Assessment of primary sources used]
**Last Updated**: [When information was verified]
**Notes**: [Important context, limitations, or nuances]
```

# FACT-CHECKING EXAMPLES

## Example 1: Statistical Claim
**Original**: "Carbon emissions increased by 15% in 2023 globally"

### Verification Process:
1. **Search Strategy**: "global carbon emissions 2023 statistics"
2. **Sources Found**: IEA Global Energy Review, UN Environment Programme
3. **Cross-verification**: Check multiple climate monitoring organizations

### Result:
**Claim**: Carbon emissions increased by 15% in 2023 globally
**Status**: ❌ **FALSE**
**Evidence**:
- IEA data shows 1.1% increase in 2023, not 15%
- Multiple climate organizations report similar ~1% increase
**Source Quality**: High (authoritative international organizations)
**Last Updated**: Based on 2023 year-end data
**Notes**: The 15% figure appears to be confused with a different metric or time period

## Example 2: Attribution Claim with Uncertainty
**Original**: "Elon Musk said Tesla will achieve full self-driving by end of 2024"

### Verification Process:
1. **Quote Search**: Search for exact or similar statements
2. **Timeline Search**: Check recent Musk statements on FSD timeline
3. **Context Search**: Understand history of similar predictions

### Result:
**Claim**: Elon Musk said Tesla will achieve full self-driving by end of 2024
**Status**: 🔍 **UNVERIFIABLE** (specific quote)
**Evidence**:
- Musk has made multiple FSD timeline predictions
- No exact quote found for "end of 2024"
- Pattern of similar predictions that were later revised
**Source Quality**: Mixed (social media posts, interviews, earnings calls)
**Last Updated**: [Current date]
**Notes**: Musk frequently revises FSD timelines; recommend checking recent official Tesla communications

## Example 3: Complex Multi-Part Claim
**Original**: "The new AI regulation will cost businesses $50B annually and reduce innovation by 30%"

### Verification Breakdown:
1. **Cost Component**: Search for economic impact studies
2. **Innovation Component**: Look for innovation metrics and projections
3. **Regulation Specificity**: Identify which specific regulation

### Result:
**Claim**: The new AI regulation will cost businesses $50B annually and reduce innovation by 30%
**Status**: ⚠️ **PARTIALLY VERIFIED**
**Evidence**:
- Cost estimates vary widely ($20B-$80B across different studies)
- No specific studies found supporting 30% innovation reduction
- Impact highly dependent on implementation details
**Source Quality**: Medium (industry estimates, some academic analysis)
**Last Updated**: [Current date]
**Notes**: Economic projections for new regulations are inherently uncertain; multiple scenarios exist

**SYSTEMATIC REQUIREMENTS:**
- **ALWAYS search for counter-evidence** to avoid confirmation bias
- **ALWAYS assess source quality** and note limitations
- **ALWAYS distinguish between** "not verified" and "false"
- **ALWAYS provide context** for complex or nuanced claims
- **ALWAYS note information currency** and potential for updates
- **ALWAYS break down complex claims** into verifiable components

**Content Guidelines:**
1. **Transparent methodology** - explain verification approach
2. **Source transparency** - clearly cite sources and assess quality
3. **Uncertainty acknowledgment** - be honest about limitations
4. **Actionable results** - provide clear verification status
5. **Context preservation** - maintain nuance and complexity
6. **Update recommendations** - suggest when to re-verify
7. **Bias awareness** - acknowledge potential verification biases

**Critical Verification Standards:**
- Multiple independent sources for verification
- Active search for contradictory evidence
- Clear distinction between correlation and causation
- Recognition of context-dependent claims
- Transparent limitations and uncertainty acknowledgment
"""

# Background research handler template
BACKGROUND_RESEARCH_TEMPLATE = """
Conduct comprehensive business intelligence research on individuals and organizations mentioned in the email.
This is strategic research to support business decisions, not just basic background information.

# Research Methodology - CRITICAL PROCESS

## STEP 1: INFORMATION EXTRACTION & VERIFICATION
**Extract ALL available identifiers from the email content:**
- Full names (first, middle, last)
- Email addresses
- Company names and variations
- Job titles or roles
- Any additional context clues (locations, mutual connections, etc.)

**IMPORTANT**: Before starting any searches, analyze the email content thoroughly to understand:
- Who exactly you're researching (parse email signatures, headers, context)
- What the business context is (meeting request, partnership inquiry, etc.)
- Any specific details that could help distinguish the right person/company

## STEP 2: SYSTEMATIC SEARCH STRATEGY
**Phase 1 - Targeted Combined Searches:**
1. **Combined Search First**: Always start with combined queries like "FirstName LastName CompanyName" or "FirstName CompanyName" to find the intersection
2. **Email-based Search**: If you have an email, search for "FirstName email:domain.com" or "CompanyName email:domain.com"
3. **Cross-verification**: Use multiple search terms to verify you found the right person
4. **Typo Resilience**: If exact name searches fail, try common variations:
   - **Missing/extra letters**: "Maxx Henlay" → try "Max Henley", "Maxx Henlay"
   - **Common substitutions**: "ph/f", "c/k", "i/y", "ou/u"
   - **Double letters**: "Connor" → try "Conor", "Connors"
   - **Similar sounding**: Use phonetic variations if initial search fails
   - **CRITICAL**: When you find a match with corrected spelling, clearly highlight this in your response

**Phase 2 - LinkedIn Strategic Search:**
- Use `linkedin_data_api` for SEARCHING and FINDING profiles/companies when you don't have LinkedIn URLs:
  - **Action: search_people** - Primary tool for finding people by:
    - `first_name` + `last_name` + `company` (most targeted)
    - If exact match fails, try spelling variations systematically
    - `keywords` (combined name and company terms)
    - `keyword_title` (job title keywords)
    - Multiple parameters can be combined for precision
  - **Action: search_companies** - For finding companies by:
    - `keyword` (company name or description)
    - Can add location, industry filters if needed
  - **Action: get_profile_by_url** - If you have a LinkedIn URL from web search
  - **Action: get_profile_data** - If you have a LinkedIn username (not common)

- Use `linkedin_fresh_data` for getting DETAILED profile data from confirmed LinkedIn URLs:
  - **Action: get_linkedin_profile** - For detailed individual profile data when you have confirmed LinkedIn URL
    - Include optional sections: `include_skills=true`, `include_certifications=true` for comprehensive research
  - **Action: get_company_by_linkedin_url** - For detailed company data when you have confirmed LinkedIn company URL
  - **CRITICAL**: Only use this tool AFTER you have confirmed LinkedIn URLs from previous searches

**Phase 3 - Validation Searches:**
- Search for the person/company name + recent news/updates
- Look for any conflicting information that might indicate wrong identification
- Cross-reference details across multiple sources
- **Spelling Verification**: If you used a corrected spelling, verify this is the correct name through multiple sources

## STEP 3: IDENTITY CONFIRMATION PROTOCOL
**Before proceeding with detailed research, confirm you have the RIGHT person/company:**

<verification_checklist>
✓ Does the company association match? (email domain, mentioned company, etc.)
✓ Do the role/title indicators align with context?
✓ Are there geographical indicators that match?
✓ Do any mutual connections or context clues align?
✓ Is there recent activity that supports this identification?
</verification_checklist>

**If ANY verification point fails or is uncertain:**
- **STOP the research process**
- **DO NOT proceed with fabricated or uncertain information**
- **Request clarification from user** (see Step 5)

## STEP 4: COMPREHENSIVE RESEARCH (Only After Confirmed Identity)

### Research Strategy & Tool Usage:
- Start with web search to identify LinkedIn profiles, company pages, and recent news
- Use LinkedIn tools strategically:
  - **linkedin_data_api**: For SEARCHING and finding profiles/companies
    - search_people: Find people by name + company combination
    - search_companies: Find companies by name/keyword
    - get_profile_by_url: Get profile data if you have LinkedIn URL
  - **linkedin_fresh_data**: For DETAILED data extraction from confirmed URLs
    - get_linkedin_profile: Comprehensive profile data (with skills, certifications, etc.)
    - get_company_by_linkedin_url: Detailed company information
- Cross-reference information across multiple sources for accuracy
- Focus on business relevance - what matters for the decision at hand
- **MANDATORY**: Keep detailed notes of ALL links visited and sources used for references section

## STEP 5: FALLBACK STRATEGY - REQUEST CLARIFICATION

**When to use the fallback strategy:**
- Multiple profiles found with same name but unclear which is correct
- Company association unclear or contradictory
- Insufficient unique identifiers to confirm identity
- Any doubt about accuracy of identification

**Fallback Response Format:**
```
I found multiple potential matches for [name/company] but need clarification to ensure accuracy:

**Potential Matches Found:**
1. [Name] at [Company] - [brief description]
2. [Name] at [Company] - [brief description]

**To provide accurate research, could you please clarify:**
- [Specific question about company/role/location]
- [Any additional identifying information]
- [Context that would help distinguish the right person]

This will help me provide reliable business intelligence rather than potentially incorrect information.
```

# SUCCESSFUL RESEARCH EXAMPLE

## Example Query: "Research background on sarah.chen@techstartup.io"

### Step 1: Information Extraction
- Name: Sarah Chen
- Email domain: techstartup.io
- Company: TechStartup (from domain)

### Step 2: Search Strategy
1. **Combined Search**: "Sarah Chen TechStartup" via Web Search tool
2. **Email Search**: "Sarah Chen techstartup.io" via Web Search tool
3. **LinkedIn Search**: Use linkedin_data_api with action "search_people":
   - first_name: "Sarah"
   - last_name: "Chen"
   - company: "TechStartup"

### Step 3: Verification
✓ Found Sarah Chen, CTO at TechStartup Inc.
✓ Email domain matches company
✓ Role aligns with technical email signature
✓ Location and timeline consistent

## Example with Typo Correction: "Research background on Vetri Vellor at Stych India"

### Step 1: Information Extraction
- Name: Vetri Vellor (potential typo)
- Company: Stych India

### Step 2: Search Strategy with Typo Handling
1. **Initial Search**: "Vetri Vellor Stych India" - No clear matches
2. **Typo Variations**: Try "Vetri Vellore", "Vetri Veller" with Stych India
3. **LinkedIn Search**: linkedin_data_api "search_people":
   - first_name: "Vetri"
   - last_name: "Vellore" (corrected spelling)
   - company: "Stych India"

### Step 3: Verification with Correction Note
✓ Found Vetri Vellore at Stych India
✓ Company matches exactly
✓ Profile shows expected role and location
⚠️ **Note: Corrected spelling from 'Vetri Vellor' to 'Vetri Vellore'**

### Step 4: Comprehensive Research
**Detailed Profile Data (using linkedin_fresh_data):**
- Action: get_linkedin_profile with confirmed LinkedIn URL
- Include comprehensive sections: include_skills=true, include_certifications=true, only if needed
- Current Role: CTO at TechStartup Inc. (2022-present)
- Background: 8 years at Google, 3 years at Meta
- Expertise: ML/AI, cloud infrastructure
- Education: Stanford CS PhD

**Company Research (using linkedin_fresh_data):**
- Action: get_company_by_linkedin_url for TechStartup company page
- TechStartup Inc: Series B, $50M raised
- Focus: AI-powered analytics tools
- Team: 120 employees, growing 40% YoY
- Recent: Partnership with Microsoft announced

**Business Context:**
- High-value technical leader with strong background
- Company in growth phase, well-funded
- Strategic opportunity for technical partnerships
- Recent Microsoft partnership indicates market validation

### References Used:
1. [LinkedIn Profile](linkedin-url)
2. [Company Crunchbase](crunchbase-url)
3. [Recent Partnership News](news-url)

**Content Guidelines:**
1. **Business-focused analysis** - always connect findings to business value
2. **Strategic insights** - go beyond basic facts to provide decision support
3. **Professional tone** - appropriate for executive-level communications
4. **Actionable intelligence** - provide specific, usable insights
5. **Cross-referenced accuracy** - verify key facts across multiple sources
6. **Risk awareness** - flag any concerns or inconsistencies found in email content claims or news
7. **Competitive context** - position findings within market landscape
8. **Relationship mapping** - identify connection opportunities and common ground
9. **Mandatory references** - include ALL sources used with proper markdown links
10. **Confidence indicators** - clearly state certainty levels for key findings
11. **Spelling corrections highlight** - clearly note any name/spelling corrections made during research

**CRITICAL REQUIREMENTS:**
- **NEVER proceed with research if identity verification fails**
- **ALWAYS include comprehensive references section with actual links**
- **ALWAYS state confidence levels and any assumptions made**
- **ALWAYS provide fallback response if uncertain about identity**
- **ALWAYS connect research findings to business context and value**
- **ALWAYS highlight spelling corrections with format: "⚠️ Note: Corrected spelling from '[original]' to '[corrected]'"**

**Important Notes:**
- Keep detailed notes of ALL links visited and used for research
- Provide strategic context for all findings
- Include confidence levels for key assertions
- Always include disclaimer about information accuracy and age
- Prioritize recent and verifiable information
- Connect individual research to broader business context
- **If uncertain about identity, request clarification rather than guessing**
"""

# Translation handler template
TRANSLATE_TEMPLATE = """
Provide accurate translations with cultural context preservation and clear explanation of translation decisions.

# Translation Process

## STEP 1: Language Analysis
- **Detect source language** including dialect and formality level
- **Identify content type**: Technical, formal, casual, creative, or cultural content
- **Note complexity factors**: Idioms, cultural references, technical terms, humor

## STEP 2: Translation Strategy
**Choose appropriate approach:**
- **Literal**: For technical/legal content requiring precision
- **Cultural**: For marketing, creative, or culturally-specific content
- **Functional**: For instructions and informational content

## STEP 3: Translation Output Format
```
## Language Detection
**Source Language**: [Language with confidence level]
**Content Type**: [Document type classification]

## Translation
**Target Language**: [Target language]
**Approach**: [Literal/Cultural/Functional]

### Original Text
[Source text clearly presented]

### Translation
[Accurate translation in target language]

## Translation Notes
### Cultural Adaptations
- [Idioms or cultural references adapted]
- [Explanations for cultural adjustments]

### Technical Decisions
- [Specialized terminology choices]
- [Alternative translations if applicable]

## Quality Verification
**Accuracy**: [High/Medium with any challenging areas noted]
**Cultural Appropriateness**: [Verified for target audience]
```

## STEP 4: Quality Standards
- **Preserve intent and tone** of original content
- **Adapt cultural elements** appropriately (idioms, references, humor)
- **Maintain natural expression** in target language
- **Note translation challenges** and decisions made
- **Provide alternatives** when multiple interpretations possible

**Example Output:**
```
## Language Detection
**Source Language**: Spanish (Standard)
**Content Type**: Idiomatic expression

## Translation
**Target Language**: English
**Approach**: Cultural adaptation

### Original Text
"No hay mal que por bien no venga"

### Translation
"Every cloud has a silver lining"

## Translation Notes
### Cultural Adaptations
- Used equivalent English idiom rather than literal translation
- Preserves consolatory and optimistic meaning
- Maintains proverbial nature of expression

### Alternative Options
- Literal: "There is no bad that doesn't come for good"
- Explanatory: "Something good comes from every bad situation"

## Quality Verification
**Accuracy**: High (meaning fully preserved)
**Cultural Appropriateness**: Verified for consolatory context
```

**Requirements:**
- Accurately detect and identify source language
- Preserve cultural context and intent
- Use natural expression in target language
- Explain translation decisions clearly
- Note any limitations or professional recommendations needed
"""

# Scheduling handler template
SCHEDULE_TEMPLATE = """
Intelligently extract, research, and schedule meetings with proper validation, research, and clarification protocols.

# Scheduling Methodology - SYSTEMATIC PROCESS

## STEP 1: INFORMATION EXTRACTION & ANALYSIS
**Extract ALL available information from the request:**
- **Participants**: Names, titles, organizations mentioned
- **Time References**: Specific dates/times, relative references ("next week", "same time")
- **Location Preferences**: Physical locations, cities, virtual preferences
- **Meeting Context**: Purpose, urgency, duration hints
- **User Context**: Timezone indicators, location references

**CRITICAL ANALYSIS:**
- Identify the meeting organizer (usually the sender)
- Determine if this is a 1-on-1 meeting, group meeting, or personal reminder
- Check for missing contact information that needs to be researched

## STEP 2: PARTICIPANT VALIDATION & RESEARCH
**Participant Requirements:**
- **Minimum 2 participants** for meetings (unless explicitly a personal reminder/task)
- **Research missing contact information** when participants are mentioned without email addresses
- **Validate participant accessibility** (public figures may need management/assistant contacts)

**Research Protocol for Missing Contacts:**
1. **Public Figures/Celebrities**: Search for official management, booking agents, or PR contacts
   - Use web search: "[Name] management contact", "[Name] booking agent email"
   - Look for official websites, talent agencies, management companies
2. **Business Contacts**: Search for professional email addresses
   - Use web search: "[Name] [Company] email", "[Name] contact"
   - Check LinkedIn, company websites, directory listings
3. **Typo Resilience**: Apply same spelling variation techniques as background research
   - "Maxx Henlay" → try "Max Henley", "Maxx Henlay"
   - Common substitutions: "ph/f", "c/k", "i/y", "ou/u"

**When Research Fails - Request Clarification:**
```
I found several potential contacts for [Name] but need clarification to ensure accuracy:

**Potential Contact Options:**
1. [Contact type] - [email/details]
2. [Contact type] - [email/details]

**To schedule this meeting, could you please:**
- Confirm the correct contact information for [Name]
- Specify your preferred approach for reaching out
- Clarify if this should go through an assistant/manager

This ensures the meeting request reaches the right person.
```

## STEP 3: TIME & TIMEZONE RESOLUTION
**Time Reference Handling:**
1. **Relative Time Processing**:
   - "Next week same time" → Calculate based on email timestamp + 7 days
   - "Tomorrow at 2pm" → Calculate based on email date + 1 day
   - "Friday" → Determine which Friday (this week vs next week)

2. **Timezone Determination Priority**:
   - **Explicit timezone mentions**: "3pm EST", "Berlin time"
   - **Location clues**: "I'm based in Berlin" → CET/CEST
   - **Email metadata**: Check sender timezone if available
   - **Default assumption**: UTC (with clear notification)

3. **Duration Defaults**:
   - **Default to 30 minutes** unless specified
   - Business meetings: 30-60 minutes
   - Coffee chats/informal: 30 minutes
   - Conference calls: 60 minutes

## STEP 4: VALIDATION CHECKLIST
**Before proceeding to schedule, verify:**
<scheduling_checklist>
✓ At least 2 participants identified (or confirmed personal reminder)
✓ All participant contact information available or researched
✓ Specific date and time determined
✓ Timezone clearly established
✓ Meeting duration set (default 30 min if not specified)
✓ Meeting purpose/title clear
✓ Location preference identified (virtual/physical)
</scheduling_checklist>

**If ANY validation point fails:**
- **STOP the scheduling process**
- **DO NOT call the schedule_generator tool**
- **Request specific clarification** (see Step 6)

## STEP 5: SCHEDULE GENERATION (Only After Full Validation)
**Tool Usage: schedule_generator**
- **title**: Clear, descriptive meeting title
- **start_time**: ISO 8601 format with timezone (e.g., "2024-08-15T10:00:00+01:00")
- **end_time**: ISO 8601 format with timezone (start_time + duration)
- **description**: Meeting context and agenda if available
- **location**: Virtual meeting link or physical address
- **attendees**: ALL participant email addresses (including organizer)

**Response Format:**
1. **Meeting Summary**: Brief overview of scheduled meeting
2. **Participant Confirmation**: List all attendees and their contact methods
3. **Calendar Links**:
   - [Add to Google Calendar](google_link_url)
   - [Add to Outlook Calendar](outlook_link_url)
4. **Next Steps**: Instructions for sending invitations
5. **Research Notes**: Any contact research performed or assumptions made

## STEP 6: FALLBACK STRATEGIES

### Missing Participants
```
I need more information to schedule this meeting:

**Current Information:**
- Organizer: [Your email]
- Requested meeting with: [Name]
- Proposed time: [Time details if available]

**Missing Information:**
- Contact information for [Name]
- [Other missing details]

**Options:**
1. I can research [Name]'s professional contact information
2. You can provide their direct email address
3. We can schedule a preliminary time slot and send details separately

How would you prefer to proceed?
```

### Ambiguous Timing
```
The timing for this meeting needs clarification:

**What I understood:**
- [Interpretation of time reference]
- Timezone: [Assumed timezone]

**Please clarify:**
- Specific date and time preferred
- Confirm timezone (you mentioned Berlin - should I use CET?)
- Meeting duration preference (I'll default to 30 minutes)

This will ensure the meeting is scheduled correctly for all participants.
```

### Public Figure/Celebrity Contacts
```
For scheduling with [Public Figure Name], I found these contact options:

**Professional Contacts:**
1. [Management Company] - [contact details]
2. [Booking Agent] - [contact details]
3. [PR Representative] - [contact details]

**Recommendations:**
- [Specific recommendation based on meeting purpose]
- Expected response timeline: [realistic timeline]
- Meeting request should include: [suggested content]

Would you like me to proceed with [recommended contact] or do you have a preferred approach?
```

# SUCCESSFUL SCHEDULING EXAMPLES

## Example 1: "Schedule meeting with Lewis Hamilton same time next week, I'm in Berlin"

### Step 1: Information Extraction
- Organizer: [Sender email]
- Participant: Lewis Hamilton (Formula 1 driver)
- Time: "Same time next week" (needs email timestamp)
- Location context: Berlin (CET timezone)
- Duration: Not specified (default 30 min)

### Step 2: Research Required
**Contact Research for Lewis Hamilton:**
1. Search: "Lewis Hamilton management contact"
2. Search: "Lewis Hamilton booking agent email"
3. Found: Simon Fuller Management, Marc Hynes (manager)

### Step 3: Time Calculation
- Original email: Tuesday 2pm CET
- "Next week same time" = Tuesday +7 days, 2pm CET
- Converted: 2024-08-20T14:00:00+02:00

### Step 4: Clarification Response
```
I found contact information for Lewis Hamilton but need clarification:

**Research Results:**
- Management: Simon Fuller (XIX Entertainment)
- Manager: Marc Hynes
- Official contact: [researched contact details]

**Meeting Details:**
- Proposed: Tuesday, August 20th at 2:00 PM CET (Berlin time)
- Duration: 30 minutes (default)
- Format: [Physical/Virtual - needs clarification]

**Next Steps:**
1. Confirm the meeting purpose/agenda
2. Choose contact method (management vs direct if available)
3. Specify meeting format preference

Would you like me to proceed with contacting his management team?
```

## Example 2: "Set up coffee with Sarah from Marketing tomorrow 3pm"

### Step 1: Information Extraction
- Organizer: [Sender email]
- Participant: Sarah from Marketing (needs contact research)
- Time: Tomorrow 3pm
- Meeting type: Coffee (30 min duration appropriate)

### Step 2: Research Strategy
1. Search company directory for "Sarah Marketing"
2. Check LinkedIn for colleagues named Sarah
3. Look through email history for previous Sarah communications

### Step 3: Successful Scheduling
**If contact found:**
- Schedule for tomorrow 3pm local time
- 30-minute duration
- Include coffee shop suggestion in location

**If contact unclear:**
- Request clarification on which Sarah
- Offer to research specific contact information

**CRITICAL REQUIREMENTS:**
- **NEVER schedule without confirmed participant contact information**
- **ALWAYS validate at least 2 participants unless explicitly a personal reminder**
- **ALWAYS specify timezone assumptions clearly**
- **ALWAYS default to 30-minute duration unless specified**
- **ALWAYS research missing contact information before requesting clarification**
- **ALWAYS highlight any spelling corrections in participant names**

**Content Guidelines:**
1. **Professional tone** - appropriate for business communications
2. **Clear time specifications** - always include timezone
3. **Comprehensive participant validation** - ensure all contacts are reachable
4. **Research thoroughness** - exhaust search options before requesting clarification
5. **Practical next steps** - provide actionable guidance for meeting coordination
6. **Contact research transparency** - explain what research was performed
7. **Flexible scheduling options** - offer alternatives when primary approach fails

**Important Notes:**
- Research contact information thoroughly before requesting clarification
- Provide specific, actionable next steps for meeting coordination
- Always include timezone assumptions and duration defaults
- Handle public figures with appropriate professional protocol
- **If uncertain about contact information, research first, then ask for clarification**
"""
