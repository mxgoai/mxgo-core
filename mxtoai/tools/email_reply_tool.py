import logging
from typing import Optional, List, Dict, Any

from smolagents import Tool

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_reply_tool")

class EmailReplyTool(Tool):
    """
    Tool for generating appropriate replies to emails.
    """
    
    name = "email_reply"
    description = "Generates a natural and contextually appropriate reply to an email."
    
    inputs = {
        "subject": {
            "type": "string",
            "description": "The email subject"
        },
        "body": {
            "type": "string",
            "description": "The email body content"
        },
        "sender": {
            "type": "string",
            "description": "The email sender"
        },
        "date": {
            "type": "string",
            "description": "The email date"
        },
        "attachments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "type": {"type": "string"}
                }
            },
            "description": "List of attachment information dictionaries",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self):
        """Initialize the email reply tool."""
        super().__init__()
    
    def forward(
        self,
        subject: str,
        body: str,
        sender: str,
        date: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Generate a reply to an email based on its content.
        
        Args:
            subject: The email subject
            body: The email body content
            sender: The email sender
            date: The email date
            attachments: List of attachment information dictionaries (optional)
            
        Returns:
            A contextually appropriate email reply
        """
        # Format the inputs for the prompt
        prompt_inputs = f"""
        Email Subject: {subject}
        From: {sender}
        Date: {date}
        
        Body:
        {body}
        """
        
        if attachments:
            prompt_inputs += "\n\nAttachments:\n"
            for att in attachments:
                # Include any available content summaries
                file_info = f"- {att.get('filename', 'Unknown file')} ({att.get('type', 'unknown type')})"
                
                if "summary" in att:
                    file_info += f"\n  Summary: {att['summary']}"
                if "description" in att:
                    file_info += f"\n  Description: {att['description']}"
                    
                prompt_inputs += file_info + "\n"
        
        # Generate a more detailed and informative reply
        greeting = f"Dear {sender.split('<')[0].strip()},"
        
        # Start with a contextual introduction
        reply_body = f"Thank you for your email regarding '{subject}'."
        
        # Add specific content based on the email and attachments
        if "question" in body.lower() or "?" in body:
            # Try to identify the specific question
            if "?" in body:
                question_parts = body.split("?")
                for i in range(len(question_parts)-1):
                    potential_question = question_parts[i].split("\n")[-1] + "?"
                    if len(potential_question) > 10:  # Reasonable length for a question
                        reply_body += f" Regarding your question about {potential_question.strip()}, "
                        break
            
            reply_body += " I've reviewed your inquiry and have the following information for you."
        elif "urgent" in body.lower() or "asap" in body.lower():
            reply_body += " I understand this is urgent and have prioritized my response accordingly."
        else:
            reply_body += " I've analyzed the information you've shared and prepared a response."
            
        # Add content specific to attachments
        attachment_insights = ""
        
        if attachments:
            # Look for document summaries and image descriptions
            doc_summaries = []
            image_descriptions = []
            
            for att in attachments:
                if att.get('type', '').startswith('application/pdf') or 'document' in att.get('type', ''):
                    if "summary" in att and att["summary"]:
                        doc_summaries.append(f"In your document '{att.get('filename')}', I found: {att['summary']}")
                elif att.get('type', '').startswith('image/'):
                    if "description" in att and att["description"]:
                        image_descriptions.append(f"For the image '{att.get('filename')}', I can see: {att['description']}")
            
            # Add document insights
            if doc_summaries:
                attachment_insights += "\n\nRegarding your documents:\n" + "\n".join(doc_summaries)
                
            # Add image insights
            if image_descriptions:
                attachment_insights += "\n\nRegarding your images:\n" + "\n".join(image_descriptions)
                
            # Generic attachment acknowledgment if no specific content
            if not attachment_insights and attachments:
                if len(attachments) == 1:
                    attachment_insights += f"\n\nI've received your attachment '{attachments[0].get('filename', 'file')}' and will process it accordingly."
                else:
                    attachment_insights += f"\n\nI've received your {len(attachments)} attachments and will process them accordingly."
        
        # Add the attachment insights to the reply
        reply_body += attachment_insights
        
        # Add a closing with next steps or follow-up information
        reply_body += "\n\nPlease let me know if you need any additional information or have follow-up questions."
        
        # Add a closing
        closing = """

Best regards,
AI Assistant
        """
        
        full_reply = f"{greeting}\n\n{reply_body}\n{closing}"
        
        logger.debug("Generated email reply with content-focused response")
        return full_reply 