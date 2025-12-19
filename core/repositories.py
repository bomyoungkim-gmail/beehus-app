"""
Repository for Run-related operations using Beanie ODM.
Replaces SQLAlchemy/raw SQL implementation.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings
from core.models.mongo_models import Run
from datetime import datetime


class RunRepository:
    """Repository for managing Run documents and raw data"""
    
    def __init__(self):
        self.mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
        self.mongo_db = self.mongo_client[settings.MONGO_DB_NAME]

    async def save_run_status(self, run_id: str, status: str, error: str = None):
        """
        Update run status in MongoDB.
        
        Args:
            run_id: Run document ID
            status: New status (queued, running, success, failed)
            error: Optional error message
        """
        update_data = {
            "status": status,
            "error_summary": error
        }
        
        if status == "running":
            update_data["started_at"] = datetime.utcnow()
        elif status in ["success", "failed"]:
            update_data["finished_at"] = datetime.utcnow()
        
        # Use Beanie model for type-safe updates
        run = await Run.find_one(Run.id == run_id)
        if run:
            for key, value in update_data.items():
                setattr(run, key, value)
            await run.save()
        else:
            # Run doesn't exist yet - this shouldn't happen in normal flow
            # but handle gracefully
            print(f"⚠️  Warning: Run {run_id} not found for status update")

    async def save_raw_payload(self, run_id: str, url: str, content: str):
        """
        Save raw scraping payload to MongoDB.
        
        Args:
            run_id: Associated run ID
            url: URL that was scraped
            content: Raw content (HTML/JSON)
        """
        await self.mongo_db.raw_payloads.insert_one({
            "run_id": run_id,
            "url": url,
            "content": content,
            "captured_at": datetime.utcnow()
        })
    
    async def save_evidence(self, run_id: str, screenshot_path: str = None, html_path: str = None):
        """
        Save evidence (screenshots, HTML dumps) for failed runs.
        
        Args:
            run_id: Associated run ID
            screenshot_path: Path to screenshot file
            html_path: Path to HTML dump file
        """
        await self.mongo_db.evidences.insert_one({
            "run_id": run_id,
            "screenshot_path": screenshot_path,
            "html_path": html_path,
            "created_at": datetime.utcnow()
        })


# Global singleton instance
repo = RunRepository()
