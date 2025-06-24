"""
Scheduler module for email task scheduling.

Provides both class-based and legacy function-based APIs for scheduling.
"""

from .scheduler import (
    Scheduler,
    is_one_time_task,
)

__all__ = [
    "Scheduler",
    "is_one_time_task",
]
