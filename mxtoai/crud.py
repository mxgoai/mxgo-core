"""
CRUD operations for database entities.

This module provides reusable database operations for Tasks and TaskRuns
to avoid code duplication and centralize database logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from mxtoai._logging import get_logger
from mxtoai.models import (
    ACTIVE_TASK_STATUSES,
    TaskRun,
    TaskRunStatus,
    Tasks,
    TaskStatus,
    clear_task_data_if_terminal,
)

logger = get_logger("crud")


# Task CRUD operations
def get_task_by_id(session: Session, task_id: str | uuid.UUID) -> Tasks | None:
    """
    Get a task by its ID.

    Args:
        session: Database session
        task_id: Task ID to search for

    Returns:
        Task object or None if not found

    """
    statement = select(Tasks).where(Tasks.task_id == task_id)
    return session.exec(statement).first()


def get_tasks_by_user_email(
    session: Session, user_email: str, statuses: list[TaskStatus] | None = None, limit: int = 10
) -> list[Tasks]:
    """
    Get tasks for a specific user email.

    Args:
        session: Database session
        user_email: Email address to search for
        statuses: Optional list of statuses to filter by (defaults to active statuses)
        limit: Maximum number of tasks to return

    Returns:
        List of task objects

    """
    if statuses is None:
        statuses = ACTIVE_TASK_STATUSES

    statement = (
        select(Tasks)
        .where(Tasks.email_request.op("->>")("from") == user_email)
        .where(Tasks.status.in_(statuses))
        .order_by(Tasks.created_at.desc())
        .limit(limit)
    )
    return session.exec(statement).all()


def get_tasks_by_status(
    session: Session, statuses: list[TaskStatus], *, has_scheduler_job_id: bool | None = None
) -> list[Tasks]:
    """
    Get tasks by their status.

    Args:
        session: Database session
        statuses: List of statuses to filter by
        has_scheduler_job_id: If True, only return tasks with scheduler_job_id.
                             If False, only return tasks without scheduler_job_id.
                             If None, don't filter by scheduler_job_id.

    Returns:
        List of task objects

    """
    statement = select(Tasks).where(Tasks.status.in_(statuses))

    if has_scheduler_job_id is True:
        statement = statement.where(Tasks.scheduler_job_id.is_not(None))
    elif has_scheduler_job_id is False:
        statement = statement.where(Tasks.scheduler_job_id.is_(None))

    return session.exec(statement).all()


def create_task(
    session: Session,
    task_id: str | uuid.UUID,
    email_id: str,
    cron_expression: str,
    email_request: dict,
    scheduler_job_id: str | None = None,
    start_time: datetime | None = None,
    expiry_time: datetime | None = None,
    status: TaskStatus = TaskStatus.INITIALISED,
) -> Tasks:
    """
    Create a new task.

    Args:
        session: Database session
        task_id: Unique task identifier
        email_id: Email ID associated with the task
        cron_expression: Cron expression for scheduling
        email_request: Email request data
        scheduler_job_id: APScheduler job ID
        start_time: Optional start time for the task
        expiry_time: Optional expiry time for the task
        status: Initial task status

    Returns:
        Created task object

    """
    current_time = datetime.now(timezone.utc)

    task = Tasks(
        task_id=task_id,
        email_id=email_id,
        cron_expression=cron_expression,
        email_request=email_request,
        scheduler_job_id=scheduler_job_id,
        start_time=start_time,
        expiry_time=expiry_time,
        status=status,
        created_at=current_time,
        updated_at=current_time,
    )

    session.add(task)
    session.commit()
    session.refresh(task)

    logger.info(f"Created task {task_id} with status {status}")
    return task


def update_task_status(
    session: Session, task_id: str | uuid.UUID, status: TaskStatus, *, clear_email_data_if_terminal: bool = True
) -> Tasks | None:
    """
    Update a task's status.

    Args:
        session: Database session
        task_id: Task ID to update
        status: New status
        clear_email_data_if_terminal: Whether to clear email data if status is terminal

    Returns:
        Updated task object or None if not found

    """
    task = get_task_by_id(session, task_id)
    if not task:
        return None

    task.status = status
    task.updated_at = datetime.now(timezone.utc)

    if clear_email_data_if_terminal:
        clear_task_data_if_terminal(task)

    session.add(task)
    session.commit()
    session.refresh(task)

    logger.info(f"Updated task {task_id} status to {status}")
    return task


def delete_task(session: Session, task_id: str | uuid.UUID) -> bool:
    """
    Delete a task from the database.

    Args:
        session: Database session
        task_id: Task ID to delete

    Returns:
        True if task was deleted, False if not found

    """
    task = get_task_by_id(session, task_id)
    if not task:
        return False

    session.delete(task)
    session.commit()

    logger.info(f"Deleted task {task_id}")
    return True


def count_active_tasks_for_user(session: Session, user_email: str) -> int:
    """
    Count active tasks for a user.

    Args:
        session: Database session
        user_email: Email address to count tasks for

    Returns:
        Number of active tasks

    """
    statement = (
        select(Tasks)
        .where(Tasks.email_request.op("->>")("from") == user_email)
        .where(Tasks.status.in_(ACTIVE_TASK_STATUSES))
    )
    tasks = session.exec(statement).all()
    return len(tasks)


# TaskRun CRUD operations
def get_task_run_by_id(session: Session, run_id: str | uuid.UUID) -> TaskRun | None:
    """
    Get a task run by its ID.

    Args:
        session: Database session
        run_id: Task run ID to search for

    Returns:
        TaskRun object or None if not found

    """
    statement = select(TaskRun).where(TaskRun.run_id == run_id)
    return session.exec(statement).first()


def get_latest_task_run(session: Session, task_id: str | uuid.UUID) -> TaskRun | None:
    """
    Get the latest task run for a task.

    Args:
        session: Database session
        task_id: Task ID to get latest run for

    Returns:
        Latest TaskRun object or None if no runs found

    """
    statement = select(TaskRun).where(TaskRun.task_id == task_id).order_by(TaskRun.created_at.desc())
    return session.exec(statement).first()


def create_task_run(
    session: Session,
    run_id: str | uuid.UUID,
    task_id: str | uuid.UUID,
    status: TaskRunStatus = TaskRunStatus.INITIALISED,
) -> TaskRun:
    """
    Create a new task run.

    Args:
        session: Database session
        run_id: Unique run identifier
        task_id: Task ID this run belongs to
        status: Initial run status

    Returns:
        Created TaskRun object

    """
    current_time = datetime.now(timezone.utc)

    task_run = TaskRun(
        run_id=run_id,
        task_id=task_id,
        status=status,
        created_at=current_time,
        updated_at=current_time,
    )

    session.add(task_run)
    session.commit()
    session.refresh(task_run)

    logger.info(f"Created task run {run_id} for task {task_id}")
    return task_run


def update_task_run_status(session: Session, run_id: str | uuid.UUID, status: TaskRunStatus) -> TaskRun | None:
    """
    Update a task run's status.

    Args:
        session: Database session
        run_id: Task run ID to update
        status: New status

    Returns:
        Updated TaskRun object or None if not found

    """
    task_run = get_task_run_by_id(session, run_id)
    if not task_run:
        return None

    task_run.status = status
    task_run.updated_at = datetime.now(timezone.utc)

    session.add(task_run)
    session.commit()
    session.refresh(task_run)

    logger.info(f"Updated task run {run_id} status to {status}")
    return task_run


# Utility functions for common operations
def get_task_execution_status(session: Session, task_id: str | uuid.UUID) -> dict[str, Any] | None:
    """
    Get comprehensive execution status for a task.

    Args:
        session: Database session
        task_id: Task ID to get status for

    Returns:
        Dictionary with task and latest run information or None if task not found

    """
    task = get_task_by_id(session, task_id)
    if not task:
        return None

    latest_run = get_latest_task_run(session, task_id)

    result = {
        "task_id": str(task_id),
        "task_status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "cron_expression": task.cron_expression,
        "scheduler_job_id": task.scheduler_job_id,
        "start_time": task.start_time,
        "expiry_time": task.expiry_time,
    }

    if latest_run:
        result["latest_run"] = {
            "run_id": str(latest_run.run_id),
            "status": latest_run.status,
            "created_at": latest_run.created_at,
            "updated_at": latest_run.updated_at,
        }

    return result


def find_user_tasks_formatted(session: Session, user_email: str, limit: int = 10) -> list[dict]:
    """
    Find tasks for a user and return them in a formatted dictionary structure.

    Args:
        session: Database session
        user_email: Email address of the user
        limit: Maximum number of tasks to return

    Returns:
        List of task dictionaries with formatted information

    """
    tasks = get_tasks_by_user_email(session, user_email, limit=limit)

    user_tasks = [
        {
            "task_id": str(task.task_id),
            "description": f"Cron: {task.cron_expression}",
            "email_id": task.email_id,
            "status": task.status.value,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        for task in tasks
    ]

    logger.info(f"Found {len(user_tasks)} tasks for user {user_email}")
    return user_tasks
