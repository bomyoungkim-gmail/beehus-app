"""
Migration script to rename export fields from Portuguese to English.
Run this once to update all existing jobs in the database.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

async def migrate_field_names():
    """Rename export fields from Portuguese to English."""
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]
    jobs_collection = db.jobs
    
    # Find all jobs
    all_jobs = await jobs_collection.find({}).to_list(length=None)
    
    print(f"Found {len(all_jobs)} jobs to update")
    
    updated_count = 0
    for job in all_jobs:
        update_operations = {}
        rename_operations = {}
        
        # Rename fields
        if "export_relatorio" in job:
            rename_operations["export_relatorio"] = "export_holdings"
        if "export_extrato" in job:
            rename_operations["export_extrato"] = "export_history"
        if "relatorio_lag_days" in job:
            rename_operations["relatorio_lag_days"] = "holdings_lag_days"
        if "extrato_lag_days" in job:
            rename_operations["extrato_lag_days"] = "history_lag_days"
        if "relatorio_date" in job:
            rename_operations["relatorio_date"] = "holdings_date"
        if "extrato_date" in job:
            rename_operations["extrato_date"] = "history_date"
        
        if rename_operations:
            await jobs_collection.update_one(
                {"_id": job["_id"]},
                {"$rename": rename_operations}
            )
            updated_count += 1
            print(f"Updated job: {job.get('name', 'Unknown')} (ID: {job['_id']})")
    
    print(f"\n✅ Migration complete! Updated {updated_count} jobs.")
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate_field_names())
