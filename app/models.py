from enum import Enum
from typing import Optional
from pydantic import BaseModel


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: str


class TaskMetadata(BaseModel):
    pages: Optional[int] = None
    tables: Optional[int] = None
    images: Optional[int] = None
    processing_time_ms: Optional[int] = None


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: Optional[int] = None
    metadata: Optional[TaskMetadata] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
