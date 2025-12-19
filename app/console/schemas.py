from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from core.schemas.enums import JobStatus, RunStatus

class JobCreate(BaseModel):
    workspace_id: str
    name: str
    connector: str
    params: Dict[str, Any] = {}

class JobResponse(JobCreate):
    id: str
    status: JobStatus
    created_at: datetime
    
    class Config:
        from_attributes = True

class RunResponse(BaseModel):
    id: str
    job_id: str
    status: RunStatus
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_summary: Optional[str]
    logs: List[str] = []
    
    class Config:
        from_attributes = True
