from doctest import debug
from fastapi import FastAPI, Response, status
import random
import uvicorn
import json
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from mxtoai.ai import ask_llm
from mxtoai.email import email_sender

app = FastAPI()


# Pydantic model for the incoming email data
class EmailRequest(BaseModel):
    from_email: str = Field(..., alias="from")
    to: str
    subject: Optional[str] = ""
    rawContent: Optional[str] = ""
    recipients: Optional[List[str]] = []
    messageId: Optional[str] = None
    date: Optional[str] = None
    inReplyTo: Optional[str] = None
    references: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    replyTo: Optional[str] = None
    returnPath: Optional[str] = None
    textContent: Optional[str] = ""
    htmlContent: Optional[str] = ""
    headers: Optional[Dict[str, str]] = {}
    attachments: Optional[List[Dict]] = []
    
    class Config:
        populate_by_name = True  # Allows alias fields

@app.post("/process-emails")
async def process_email(email_data: EmailRequest):
    # Log the received email
    print("Received email:")
    print(f"From: {email_data.from_email}")
    print(f"Subject: {email_data.subject}")
    
    # Convert Pydantic model to dictionary for ask_llm
    # Handle both Pydantic v1 and v2 compatibility
    try:
        # Pydantic v2 approach
        email_dict = email_data.model_dump(by_alias=True)
    except AttributeError:
        # Fallback to Pydantic v1 approach
        email_dict = email_data.dict(by_alias=True)
    
    # Process the email with ask_llm
    prompt = "Summarise the email"
    summary = await ask_llm(prompt=prompt, email_data=email_dict)
    
    # Create a reply text with the summary
    reply_text = f"Here's a summary of your email:\n\n{summary}\n\nThis is an automated response from the AI assistant."
    
    # Create HTML version of the reply
    reply_html = f"""
    <div>
        <p>Here's a summary of your email:</p>
        <blockquote style="border-left: 2px solid #ccc; padding-left: 10px; margin-left: 10px;">
            <p>{summary}</p>
        </blockquote>
        <p>This is an automated response from the AI assistant.</p>
    </div>
    """
    
    # Send the reply email
    try:
        # Send the reply
        email_response = await email_sender.send_reply(
            original_email=email_dict,
            reply_text=reply_text,
            reply_html=reply_html
        )
        
        # Return success response
        return Response(
            content=json.dumps({
                "message": "Email processed and reply sent",
                "summary": summary,
                "email_id": email_response.get("MessageId", "")
            }),
            status_code=status.HTTP_200_OK,
            media_type="application/json"
        )
    except Exception as e:
        # Log the error
        print(f"Error sending email reply: {str(e)}")
        
        # Return error response but still include the summary
        return Response(
            content=json.dumps({
                "message": "Email processed but reply could not be sent",
                "summary": summary,
                "error": str(e)
            }),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json"
        )

if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
