import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from croniter import croniter
from pydantic import BaseModel, Field, validator
from smolagents import Tool
from mxtoai.db import DbConnection, init_db_connection
from mxtoai.models import TaskStatus, Tasks

logger = logging.getLogger(__name__)

db_connection = DbConnection()


class ScheduledTaskInput(BaseModel):
    """Input model for scheduled task creation"""
    
    cron_expression: str = Field(..., description="Valid cron expression for task scheduling")
    email_request: Dict[str, Any] = Field(..., description="Complete email request data to reprocess")
    task_description: str = Field(..., description="Human-readable description of the task")
    next_run_time: Optional[str] = Field(None, description="Next execution time (ISO format)")
    
    @validator('cron_expression')
    def validate_cron_expression(cls, v):
        """Validate that the cron expression is valid"""
        try:
            # Test if cron expression is valid
            cron = croniter(v, datetime.now(timezone.utc))
            # Test getting next execution
            cron.get_next(datetime)
            return v
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {e}")
    
    @validator('email_request')
    def validate_email_request(cls, v):
        """Validate that email_request contains necessary data"""
        if not isinstance(v, dict):
            raise ValueError("email_request must be a dictionary")
        if not v.get('from'):
            raise ValueError("email_request must contain 'from' field")
        return v


class ScheduledTasksTool(Tool):
    """
    Tool to store scheduled tasks in the database for future processing.
    """
    
    name = "scheduled_tasks_storage"
    description = (
        "Stores scheduled tasks in the database with cron expressions for future email processing. "
        "Used when users want to schedule email tasks for future execution (recurring or one-time)."
    )
    
    inputs = {
        "cron_expression": {
            "type": "string",
            "description": "Valid cron expression (minute hour day month day_of_week) in UTC timezone"
        },
        "email_request": {
            "type": "object",
            "description": "Complete email request data that will be reprocessed at scheduled time"
        },
        "task_description": {
            "type": "string", 
            "description": "Human-readable description of what the task does"
        },
        "next_run_time": {
            "type": "string",
            "description": "Optional: Next execution time in ISO format. Will be calculated from cron if not provided",
            "nullable": True
        }
    }
    
    output_type = "object"
    
    def _calculate_next_run_time(self, cron_expression: str) -> datetime:
        """Calculate the next run time from cron expression"""
        try:
            cron = croniter(cron_expression, datetime.now(timezone.utc))
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Error calculating next run time for cron '{cron_expression}': {e}")
            raise ValueError(f"Invalid cron expression: {e}")
    
    async def forward(
        self,
        cron_expression: str,
        email_request: Dict[str, Any],
        task_description: str,
        next_run_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Store a scheduled task in the database.
        
        Args:
            cron_expression: Valid cron expression in UTC
            email_request: Complete email request data for future processing
            task_description: Human-readable task description
            next_run_time: Optional next execution time (ISO format)
            
        Returns:
            Dictionary with task_id, status, and execution details
        """
        logger.info(f"Storing scheduled task: {task_description}")
        logger.debug(f"Email request keys: {email_request.keys()}")
        logger.debug(f"Cron expression: {cron_expression}")
        
        try:
            # Validate input
            logger.debug("Validating input...")
            task_input = ScheduledTaskInput(
                cron_expression=cron_expression,
                email_request=email_request,
                task_description=task_description,
                next_run_time=next_run_time
            )
            
            # Calculate next run time if not provided
            logger.debug("Calculating next run time...")
            if next_run_time:
                try:
                    next_execution = datetime.fromisoformat(next_run_time.replace('Z', '+00:00'))
                    logger.debug(f"Using provided next_run_time: {next_execution}")
                except ValueError:
                    logger.warning(f"Invalid next_run_time format: {next_run_time}. Calculating from cron.")
                    next_execution = self._calculate_next_run_time(cron_expression)
            else:
                next_execution = self._calculate_next_run_time(cron_expression)
                logger.debug(f"Calculated next execution time: {next_execution}")
            
            # Create task record
            logger.debug("Creating task record...")
            task_id = uuid.uuid4()
            email_id = email_request.get('emailId', f"scheduled_{uuid.uuid4().hex[:8]}")
            logger.debug(f"Using email_id: {email_id}")
            
            task = Tasks(
                task_id=task_id,
                email_id=email_id,
                cron_expression=cron_expression,
                status=TaskStatus.INITIALISED,
                email_request=email_request
            )
            
            # Initialize DB connection if needed
            try:
                # Ensure DB connection is initialized
                logger.debug("Initializing DB connection...")
                # Use a new connection for this operation
                conn = await init_db_connection()
                
                # Store in database
                logger.debug(f"Storing task in database with ID: {task_id}")
                async with conn.get_session() as session:
                    logger.debug("Obtained database session")
                    try:
                        session.add(task)
                        logger.debug("Task added to session, committing...")
                        await session.commit()
                        logger.debug("Session committed successfully")
                        logger.info(f"Task successfully stored with ID: {task_id}")
                    except Exception as tx_error:
                        logger.error(f"Transaction error: {tx_error}", exc_info=True)
                        raise tx_error
            except Exception as db_error:
                logger.error(f"Database session error: {db_error}", exc_info=True)
                raise db_error
                
            result = {
                "status": "success",
                "task_id": str(task_id),
                "description": task_description,
                "next_execution": next_execution.isoformat(),
                "email_id": email_id,
                "message": f"Successfully stored scheduled task with ID: {task_id}"
            }
            
            logger.info(f"Scheduled task result prepared: {result}")
            return result
                
        except Exception as e:
            error_msg = f"Failed to store scheduled task: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": error_msg,
                "task_description": task_description
            }


# Example usage for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio
    import os
    
    # Set required environment variables for testing
    if 'DB_USER' not in os.environ:
        os.environ['DB_USER'] = 'postgres'
        os.environ['DB_PASSWORD'] = 'postgres'
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_PORT'] = '5432'
        os.environ['DB_NAME'] = 'mxtoai'
    
    async def test_tool():
        # Create and initialize tool
        tool = ScheduledTasksTool()
        
        # Example task
        sample_email_request = {
            "from": "test@example.com",
            "to": "remind@mxtoai.com",
            "subject": "Weekly Report Reminder",
            "textContent": "Remind me to review the weekly sales report",
            "emailId": "test_email_123"
        }
        
        result = await tool.forward(
            cron_expression="0 14 * * 1",  # Every Monday at 2 PM UTC
            email_request=sample_email_request,
            task_description="Weekly reminder to review sales report"
        )
        
        print("Task creation result:", result)
    
    # Run the test
    asyncio.run(test_tool()) 