from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskState(StrEnum):
    pending = "PENDING"
    queued = "QUEUED"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"


class TaskAccepted(BaseModel):
    task_id: str
    status: TaskState = TaskState.queued
    status_url: str
    message: str = "Task accepted and queued for background processing."


class TaskStatus(BaseModel):
    task_id: str
    status: TaskState
    filename: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str


class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Task not found"])
