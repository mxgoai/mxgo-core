import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SQLAEnum
from sqlmodel import Field, Relationship, SQLModel


class TaskStatus(str, Enum):
    INITIALISED = "INITIALISED"
    ACTIVE = "ACTIVE"
    EXECUTING = "EXECUTING"
    FINISHED = "FINISHED"
    DELETED = "DELETED"


class TaskRunStatus(str, Enum):
    INITIALISED = "INITIALISED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ERRORED = "ERRORED"


class BaseMixin(SQLModel):
    created_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(timezone.utc),
    )


class Tasks(BaseMixin, table=True):
    __tablename__ = "tasks"

    task_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email_id: str = Field(index=True, nullable=False, description="Email ID associated with the task")
    cron_expression: str = Field(description="Cron expression for scheduled tasks")
    scheduler_job_id: Optional[str] = Field(default=None, nullable=True, description="APScheduler job ID for tracking")
    status: TaskStatus = Field(
        sa_column=Column(SQLAEnum(TaskStatus), nullable=False),
        default=TaskStatus.INITIALISED,
        description="Current status of the task",
    )

    email_request: dict = Field(sa_column=Column(JSON), default_factory=dict)
    start_time: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True),
        default=None,
        description="Start time for the task - task will not execute before this time"
    )
    expiry_time: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True),
        default=None,
        description="End time for the task - task will not execute after this time"
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
    task: Optional[Tasks] = Relationship(back_populates="runs")
