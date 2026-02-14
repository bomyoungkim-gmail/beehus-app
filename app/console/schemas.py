from pydantic import BaseModel, field_validator
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

    @field_validator("credential_id", mode="before")
    @classmethod
    def normalize_credential_id(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

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
    vnc_url: Optional[str] = None
    logs: List[str] = []
    
    class Config:
        from_attributes = True


class ProcessorCreate(BaseModel):
    credential_id: str
    name: str
    script_content: str


class ProcessorUpdate(BaseModel):
    name: Optional[str] = None
    script_content: Optional[str] = None
    is_active: Optional[bool] = None


class ProcessorResponse(BaseModel):
    id: str
    credential_id: str
    name: str
    version: int
    processor_type: str
    is_active: bool
    created_at: str
    updated_at: str
    script_preview: str
