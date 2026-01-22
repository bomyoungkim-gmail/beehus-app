from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from core.schemas.enums import JobStatus, RunStatus

class JobCreate(BaseModel):
    workspace_id: str
    name: str
    connector: str
    credential_id: Optional[str] = None
    params: Dict[str, Any] = {}
    schedule: Optional[str] = None  # Cron expression for periodic execution

class JobResponse(JobCreate):
    id: str
    status: JobStatus
    schedule: Optional[str] = None  # Include in response
    created_at: datetime
    
    class Config:
        from_attributes = True

class RunResponse(BaseModel):
    id: str
    job_id: str
    status: RunStatus
    report_date: Optional[str] = None
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    error_summary: Optional[str]
    logs: List[str] = []
    
    class Config:
        from_attributes = True
