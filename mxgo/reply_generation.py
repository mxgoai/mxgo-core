import json
from typing import Any

from mxgo._logging import get_logger
from mxgo.schemas import GenerateEmailReplyRequest, ReplyCandidate
from mxgo.suggestions import get_suggestions_model

logger = get_logger(__name__)


def parse_email_body(email_content: str) -> str:
    """
    Parse email body and focus on latest actionable content.
    Removes quoted/forwarded history, signatures, legal footers, etc.
    """
    lines = email_content.split("\n")
    filtered_lines = []

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines
        if not line_stripped:
            filtered_lines.append(line)
            continue

        # Skip quoted content (starts with >)
        if line_stripped.startswith(">"):
            continue

        # Skip forwarded messages
        if any(
            pattern in line_stripped.lower()
            for pattern in ["forwarded message", "original message", "from:", "sent:", "to:", "subject:"]
        ) and "-----" in "".join(lines[max(0, len(filtered_lines) - 2) : len(filtered_lines) + 2]):
            continue

        # Skip signatures and footers
        if any(
            pattern in line_stripped.lower()
            for pattern in [
                "unsubscribe",
                "confidential",
                "disclaimer",
                "legal",
                "privacy policy",
                "this email was sent",
                "best regards",
                "sincerely",
                "thank you",
            ]
        ):
            continue

        # Skip tracking and S/MIME content
        if any(pattern in line_stripped for pattern in ["http", "utm_", "BEGIN PGP", "BEGIN CERTIFICATE", "SMIME"]):
            continue

        filtered_lines.append(line)

    return "\n".join(filtered_lines).strip()


def extract_receiver_style() -> dict[str, Any]:
    """
    Extract style profile from receiver-authored text (not quotes).
    Returns style characteristics for mirroring.
    """
    # For now, return default neutral-professional style
    # In a full implementation, this would analyze the receiver's writing patterns
    return {
        "formality": "neutral-professional",
        "sentence_length": "medium",
        "punctuation_style": "standard",
        "greeting_pattern": "standard",
        "closing_pattern": "standard",
        "emoji_usage": False,
        "paragraph_length": "medium",
    }


def build_response_prompt(request: GenerateEmailReplyRequest) -> str:
    """Build the prompt for response generation based on the email request."""
    # Parse email content
    parsed_content = parse_email_body(request.email_content)

    # Format attachments
    attachments_list = [
        {"filename": att.filename, "file_type": att.file_type, "file_size": att.file_size}
        for att in request.attachments
    ]

    # Build YAML input
    yaml_input = f"""email:
  subject: "{request.subject}"
  from: "{request.sender_email}"
  cc: {json.dumps(request.cc_emails)}
  attachments: {json.dumps(attachments_list)}
  body: |
{parsed_content}

user_instructions: |
{request.user_instructions}"""

    return f"""You are an assistant that drafts email replies.

Goal
Given (a) the source email and (b) optional user_instructions, produce 3 distinct reply candidates and rank them by likelihood-of-fit (confidence). Return JSON only.

Parsing & Scope
- Focus on the latest actionable content in the email body.
- Ignore quoted/forwarded history, signatures, legal/confidentiality footers, unsubscribe blocks, tracking parameters, and S/MIME/PGP blobs—except when sampling style (see below).

Style Mirroring & Tone Selection
- If the thread includes text authored by the receiver (the person we're replying to), build a brief style profile from their most recent authored lines (not quotes of others):
  - formality level, sentence length variation, punctuation habits (commas/semicolons/exclamations), greeting/closing patterns, register (casual vs. corporate), emoji usage, and paragraph length.
  - Lightly mirror (≈70-80% similarity): keep the user's voice clear and readable; do not copy idiosyncratic errors that hurt clarity.
- If no receiver-authored text is available, infer tone from context: choose among {{formal, neutral-professional, friendly, concise, apologetic, assertive}}. Prefer neutral-professional.
- Anti-AI tells: avoid clichés ("Hope this finds you well"), corporate buzzwords, templated symmetry, over-polished filler, and verbose hedging. Do not use em dashes (—); use commas or hyphens. Vary sentence length naturally. Use contractions if compatible with the mirrored tone. Avoid exclamation marks unless the receiver used them.

Safety & Truthfulness
- Never invent facts, commitments, dates, prices, or attachments.
- Use placeholders when details are missing: {{{{date}}}}, {{{{time}}}}, {{{{link}}}}, {{{{file}}}}, {{{{amount}}}}, {{{{name}}}}.
- Keep English language. Each reply ≤150 words. No emojis unless mirrored.

When user_instructions are empty → diversify by intent:
  1) Direct answer/commitment.
  2) Clarification request + partial progress.
  3) Alternative proposal or boundary-setting.
When user_instructions are present → create three distinct interpretations (e.g., concise, detailed-with-bullets, friendly) while honoring instructions.

Scoring (confidence_pct 0-100)
- Fit to user_instructions and the email's ask.
- Specificity without hallucinations; actionable clarity.
- Appropriateness of tone and accuracy of style mirroring.
Calibration: short/ambiguous emails → moderate scores (40-70) unless cues are strong.

Output EXACTLY this JSON array (length 3), sorted by confidence_pct DESC. No surrounding text or markdown.
[
  {{"response":"<candidate #1>", "confidence_pct": <int 0-100>, "variant": "<direct|clarifying|alternative|concise|detailed|friendly|formal|other>", "rationale":"<≤12 words>"}},
  {{"response":"<candidate #2>", "confidence_pct": <int 0-100>, "variant": "<...>", "rationale":"<≤12 words>"}},
  {{"response":"<candidate #3>", "confidence_pct": <int 0-100>, "variant": "<...>", "rationale":"<≤12 words>"}}
]

Input (YAML):
{yaml_input}

Task:
1) Parse and infer the main ask and constraints.
2) Build/Infer style; mirror lightly or set tone per rules.
3) Draft three distinct, high-quality replies per rules.
4) Rank and return them as the JSON array, highest confidence first."""


async def generate_replies(request: GenerateEmailReplyRequest) -> list[ReplyCandidate]:
    """
    Generate email response candidates using the AI model.

    Args:
        request: The email generate response request

    Returns:
        List of response candidates sorted by confidence (highest first)

    """
    try:
        # Get the model (same as suggestions)
        model = get_suggestions_model()

        # Build the prompt
        prompt = build_response_prompt(request)

        logger.info(f"Generating response candidates for email {request.email_identified}")

        # Call the model
        response = model(messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=2000)

        # Parse the JSON response
        response_text = response.content.strip()

        # Remove any markdown code blocks if present
        response_text = response_text.removeprefix("```json")
        response_text = response_text.removesuffix("```")

        response_text = response_text.strip()

        # Parse JSON
        candidates_json = json.loads(response_text)

        # Convert to ResponseCandidate objects
        candidates = []
        for candidate_data in candidates_json:
            candidate = ReplyCandidate(
                response=candidate_data["response"],
                confidence_pct=candidate_data["confidence_pct"],
                variant=candidate_data["variant"],
                rationale=candidate_data["rationale"],
            )
            candidates.append(candidate)

        logger.info(f"Generated {len(candidates)} response candidates")
        return candidates  # noqa: TRY300

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Raw response: {response_text}")
        error_msg = f"Invalid JSON response from model: {e}"
        raise ValueError(error_msg) from e
    except Exception as e:
        logger.error(f"Error generating response candidates: {e}")
        raise
