import logging
from datetime import datetime
from typing import ClassVar, Optional
from urllib.parse import urlencode

import pytz
from ics import Calendar, Event
from pydantic import BaseModel, EmailStr, Field, field_validator

# Import Smol Gents Tool
from smolagents import Tool

logger = logging.getLogger(__name__)


class EventDetails(BaseModel):
    """Data model for event details extracted by the LLM."""

    title: str = Field(..., description="The title or summary of the event.")
    start_time: datetime = Field(..., description="The start date and time of the event. Must include timezone info.")
    end_time: Optional[datetime] = Field(
        None, description="The end date and time of the event. Must include timezone info if provided."
    )
    description: Optional[str] = Field(None, description="A detailed description of the event.")
    location: Optional[str] = Field(
        None, description="The location of the event (physical address or virtual meeting link)."
    )
    attendees: Optional[list[EmailStr]] = Field(None, description="List of attendee email addresses.")

    @field_validator("start_time", "end_time")
    @classmethod
    def check_timezone_awareness(cls, v):
        if v is not None and (v.tzinfo is None or v.tzinfo.utcoffset(v) is None):
            # Attempt to default to UTC if naive, log warning
            logger.warning(f"Received naive datetime '{v}'. Assuming UTC. LLM should provide timezone-aware datetimes.")
            return v.replace(tzinfo=pytz.UTC)
        return v


# Inherit from smolagents.Tool
class ScheduleTool(Tool):
    """Tool to generate iCalendar (.ics) data and 'Add to Calendar' links."""

    # Add required attributes for Smol Gents
    name = "schedule_generator"
    description = (
        "Generates iCalendar (.ics) file content and 'Add to Calendar' links (Google, Outlook) "
        "based on provided event details. Expects ISO 8601 date/time strings with timezone."
    )

    inputs: ClassVar[dict] = {
        "title": {"type": "string", "description": "The title or summary of the event."},
        "start_time": {
            "type": "string",
            "description": "The start date and time (ISO 8601 format with timezone, e.g., '2024-08-15T10:00:00+01:00' or '2024-08-16T09:00:00Z').",
        },
        "end_time": {
            "type": "string",
            "description": "The optional end date and time (ISO 8601 format with timezone). Defaults to start time + standard duration if omitted.",
            "nullable": True,
        },
        "description": {
            "type": "string",
            "description": "A detailed description of the event (optional).",
            "nullable": True,
        },
        "location": {
            "type": "string",
            "description": "The location (physical address or virtual meeting link) (optional).",
            "nullable": True,
        },
        "attendees": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of attendee email addresses (optional).",
            "nullable": True,
        },
    }
    output_type = (
        "object"  # Changed from "dict". Output is a dictionary with status, ics_content, calendar_links, message
    )

    def generate_ics_content(self, details: EventDetails) -> str:
        """Generates the content for an .ics calendar file."""
        c = Calendar()
        e = Event()

        e.name = details.title
        e.begin = details.start_time
        if details.end_time:
            e.end = details.end_time
        # If no end time, ics library defaults to a standard duration (usually 1 hour or uses start time)
        # or you could define a default duration:
        # else:
        #   e.duration = timedelta(hours=1)

        if details.description:
            e.description = details.description
        if details.location:
            e.location = details.location
        if details.attendees:
            # Ensure attendees is a list before iterating
            attendees_list = details.attendees if isinstance(details.attendees, list) else []
            for attendee_email in attendees_list:
                # Add attendee using the mailto: URI scheme
                e.add_attendee(f"mailto:{attendee_email}")

        c.events.add(e)
        # Return the calendar data as a string
        # Ensure trailing newline for compatibility
        return str(c) + "\\n"

    def generate_calendar_links(self, details: EventDetails) -> dict[str, str]:
        """Generates 'Add to Calendar' links for popular services."""
        links = {}

        # Ensure start_time is timezone-aware (validator should handle this, but double-check)
        start_utc = details.start_time.astimezone(pytz.utc)
        end_utc = details.end_time.astimezone(pytz.utc) if details.end_time else None

        # Format dates for URLs (YYYYMMDDTHHMMSSZ)
        start_format = start_utc.strftime("%Y%m%dT%H%M%SZ")
        end_format = end_utc.strftime("%Y%m%dT%H%M%SZ") if end_utc else start_format  # Use start if no end

        # Google Calendar Link
        google_params = {
            "action": "TEMPLATE",
            "text": details.title,
            "dates": f"{start_format}/{end_format}",
            "details": details.description or "",
            "location": details.location or "",
            # 'add': ','.join(details.attendees or []) # Requires specific formatting/permissions sometimes unreliable
        }
        if details.attendees:
            google_params["add"] = ",".join(details.attendees)

        links["google"] = f"https://www.google.com/calendar/render?{urlencode(google_params)}"

        # Outlook Calendar Link (Web)
        # Note: Outlook link format can be less reliable and might change.
        # It typically requires start/end times in the user's local time zone,
        # making UTC conversion tricky without knowing the target user's TZ.
        # Providing UTC times is the most standard approach.
        outlook_params = {
            "path": "/calendar/action/compose",
            "rru": "addevent",
            "startdt": start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            # Outlook needs TZ info sometimes, but URL format varies. Sticking to UTC base format.
            "enddt": end_utc.strftime("%Y-%m-%dT%H:%M:%S") if end_utc else start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "subject": details.title,
            "body": details.description or "",
            "location": details.location or "",
        }
        links["outlook"] = f"https://outlook.live.com/calendar/0/deeplink/compose?{urlencode(outlook_params)}"
        # Yahoo link generation is similar but omitted for brevity

        return links

    # Rename 'run' to 'forward' for Smol Gents compatibility
    def forward(
        self,
        title: str,
        start_time: str,
        end_time: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[str]] = None,
    ) -> dict:
        """
        Main execution method for the tool (renamed from run). Parses input and generates outputs.
        Expects datetime strings in ISO 8601 format (or similar parsable format).
        LLM should be prompted to provide dates in this format including timezone offset.
        e.g., "2024-07-29T14:30:00+01:00" or "2024-07-29T13:30:00Z"
        """
        logger.info(f"Running {self.name} tool with title: '{title}'")  # Added logging
        try:
            # Use Pydantic for parsing and validation including timezone handling
            event_details = EventDetails(
                title=title,
                start_time=datetime.fromisoformat(start_time),
                end_time=datetime.fromisoformat(end_time) if end_time else None,
                description=description,
                location=location,
                attendees=attendees,  # Pydantic handles EmailStr validation here
            )

            ics_content = self.generate_ics_content(event_details)
            calendar_links = self.generate_calendar_links(event_details)

            result = {
                "status": "success",
                "ics_content": ics_content,
                "calendar_links": calendar_links,
                "message": "Successfully generated calendar data. The 'ics_content' should be used to create an email attachment.",
            }
            logger.info(f"{self.name} completed successfully.")  # Added logging
            # return result # Moved to else block
        except Exception as e:
            logger.exception(f"Error in {self.name}") # TRY401: Removed e from message
            logger.error(f"Details of error in {self.name}: {e!s}") # Log details separately
            # Provide specific error feedback for the LLM
            return {
                "status": "error",
                "message": f"Failed to generate calendar data using {self.name}. Check input format, especially date/time (must be ISO 8601 with timezone).",
            }
        else:  # Added else block for TRY300
            return result


# Example usage (for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tool = ScheduleTool()

    # Example 1: Basic event
    details_basic = {
        "title": "Team Meeting",
        "start_time": "2024-08-15T10:00:00+01:00",  # BST
        "end_time": "2024-08-15T11:00:00+01:00",
        "description": "Discuss project updates.",
        "location": "Meeting Room 3",
        "attendees": ["test1@example.com", "test2@example.com"],
    }
    result_basic = tool.forward(**details_basic)  # Changed run to forward
    # print("\nICS Content:\n", result_basic.get('ics_content'))

    # Example 2: Event with UTC time and no end time (defaults may apply in calendar apps)
    details_utc_no_end = {
        "title": "Quick Sync",
        "start_time": "2024-08-16T14:00:00Z",  # UTC
        "location": "Virtual",
    }
    result_utc_no_end = tool.forward(**details_utc_no_end)  # Changed run to forward
    # print("\nICS Content:\n", result_utc_no_end.get('ics_content'))

    # Example 3: Naive time (should log warning and assume UTC)
    details_naive = {
        "title": "Coffee Chat",
        "start_time": "2024-08-17T09:00:00",  # Naive time
    }
    result_naive = tool.forward(**details_naive)  # Changed run to forward
