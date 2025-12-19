from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional

class JobRequest(BaseModel):
    job_id: str
    run_id: str
    workspace_id: str
    connector: str
    params: Dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ScrapeResult(BaseModel):
    run_id: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
