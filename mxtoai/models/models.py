import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SQLAEnum
from sqlmodel import Field, Relationship, SQLModel


class TaskStatus(str, Enum):
    INITIALISED = "INITIALISED"
    ACTIVE = "ACTIVE"
    EXECUTING = "EXECUTING"
    FINISHED = "FINISHED"
    DELETED = "DELETED"


# Task status categories
ACTIVE_TASK_STATUSES = [TaskStatus.INITIALISED, TaskStatus.ACTIVE, TaskStatus.EXECUTING]
TERMINAL_TASK_STATUSES = [TaskStatus.FINISHED, TaskStatus.DELETED]


def is_active_status(status: TaskStatus) -> bool:
    """Check if a task status is active (non-terminal)."""
    return status in ACTIVE_TASK_STATUSES


def is_terminal_status(status: TaskStatus) -> bool:
    """Check if a task status is terminal."""
    return status in TERMINAL_TASK_STATUSES


def clear_task_data_if_terminal(task: "Tasks") -> None:
    """
    Clear sensitive email_request data if task has reached terminal status.
    This should be called whenever a task status is updated.
    """
    if is_terminal_status(task.status) and task.email_request:
        task.email_request = {}  # Clear the email data for privacy/cleanup


class TaskRunStatus(str, Enum):
    INITIALISED = "INITIALISED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ERRORED = "ERRORED"


class BaseMixin(SQLModel):
    created_at: datetime | None = Field(
        sa_type=DateTime(timezone=True),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime | None = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(timezone.utc),
    )


class Tasks(BaseMixin, table=True):
    __tablename__ = "tasks"

    task_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email_id: str = Field(index=True, nullable=False, description="Email ID associated with the task")
    cron_expression: str = Field(description="Cron expression for scheduled tasks")
    scheduler_job_id: str | None = Field(default=None, nullable=True, description="APScheduler job ID for tracking")
    status: TaskStatus = Field(
        sa_column=Column(SQLAEnum(TaskStatus), nullable=False),
        default=TaskStatus.INITIALISED,
        description="Current status of the task",
    )

    email_request: dict = Field(sa_column=Column(JSON), default_factory=dict)
    start_time: datetime | None = Field(
        sa_type=DateTime(timezone=True),
        default=None,
        description="Start time for the task - task will not execute before this time",
    )
    expiry_time: datetime | None = Field(
        sa_type=DateTime(timezone=True),
        default=None,
        description="End time for the task - task will not execute after this time",
    )

    runs: list["TaskRun"] = Relationship(back_populates="task")


class TaskRun(BaseMixin, table=True):
    __tablename__ = "task_runs"
    run_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_id: uuid.UUID = Field(
        foreign_key="tasks.task_id",
        nullable=False,
        description="ID of the task this run belongs to",
    )
    status: TaskRunStatus = Field(
        sa_column=Column(SQLAEnum(TaskRunStatus), nullable=False),
        default=TaskRunStatus.INITIALISED,
        description="Current status of the task run",
    )
    task: Tasks | None = Relationship(back_populates="runs")
