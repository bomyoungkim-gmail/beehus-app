"""
Migration script to add export and date configuration fields to existing jobs.
Run this once to update all existing jobs in the database.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

async def migrate_jobs():
    """Add missing export and date fields to existing jobs."""
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]
    jobs_collection = db.jobs
    
    # Find all jobs that don't have the new fields
    jobs_to_update = await jobs_collection.find({
        "$or": [
            {"export_relatorio": {"$exists": False}},
            {"export_extrato": {"$exists": False}},
            {"date_mode": {"$exists": False}}
        ]
    }).to_list(length=None)
    
    print(f"Found {len(jobs_to_update)} jobs to update")
    
    updated_count = 0
    for job in jobs_to_update:
        update_fields = {}
        
        # Add missing fields with default values
        if "export_relatorio" not in job:
            update_fields["export_relatorio"] = True
        if "export_extrato" not in job:
            update_fields["export_extrato"] = False
        if "date_mode" not in job:
            update_fields["date_mode"] = "lag"
        if "relatorio_lag_days" not in job:
            update_fields["relatorio_lag_days"] = 1
        if "extrato_lag_days" not in job:
            update_fields["extrato_lag_days"] = 2
        if "relatorio_date" not in job:
            update_fields["relatorio_date"] = None
        if "extrato_date" not in job:
            update_fields["extrato_date"] = None
        
        if update_fields:
            await jobs_collection.update_one(
                {"_id": job["_id"]},
                {"$set": update_fields}
            )
            updated_count += 1
            print(f"Updated job: {job.get('name', 'Unknown')} (ID: {job['_id']})")
    
    print(f"\n✅ Migration complete! Updated {updated_count} jobs.")
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate_jobs())
