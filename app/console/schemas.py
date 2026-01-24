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
    
    # Export options
    export_holdings: bool = True
    export_history: bool = False
    
    # Date configuration
    date_mode: str = "lag"  # "lag" or "specific"
    holdings_lag_days: int = 1
    history_lag_days: int = 2
    holdings_date: Optional[str] = None
    history_date: Optional[str] = None

class JobResponse(JobCreate):
    id: str
    status: JobStatus
    created_at: datetime
    
    class Config:
        from_attributes = True

class RunResponse(BaseModel):
    id: str
    job_id: str
    connector: Optional[str] = None
    status: RunStatus
    report_date: Optional[str] = None
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    error_summary: Optional[str]
    logs: List[str] = []
    
    class Config:
        from_attributes = True
