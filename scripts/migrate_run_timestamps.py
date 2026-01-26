"""
Migration script to fix timezone-aware timestamps in Run documents.
Converts UTC timestamps to America/Sao_Paulo timezone.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from core.db import init_db
from core.models.mongo_models import Run

async def migrate_run_timestamps():
    """
    Migrates all Run documents to have timezone-aware timestamps.
    Converts UTC timestamps to America/Sao_Paulo timezone.
    """
    await init_db()
    
    # Timezone definitions
    utc = ZoneInfo("UTC")
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    
    # Fetch all runs
    runs = await Run.find_all().to_list()
    
    print(f"Found {len(runs)} runs to migrate")
    
    migrated_count = 0
    for run in runs:
        needs_update = False
        update_dict = {}
        
        # Check and fix created_at
        if run.created_at:
            # If datetime is naive (no timezone), assume it's UTC
            if run.created_at.tzinfo is None:
                # Convert naive UTC to timezone-aware Sao Paulo
                utc_time = run.created_at.replace(tzinfo=utc)
                sp_time = utc_time.astimezone(sao_paulo)
                update_dict["created_at"] = sp_time
                needs_update = True
                print(f"Run {run.id}: {run.created_at} (naive UTC) -> {sp_time} (SP)")
            elif run.created_at.tzinfo == utc:
                # Convert UTC to Sao Paulo
                sp_time = run.created_at.astimezone(sao_paulo)
                update_dict["created_at"] = sp_time
                needs_update = True
                print(f"Run {run.id}: {run.created_at} (UTC) -> {sp_time} (SP)")
        
        # Check and fix updated_at
        if run.updated_at:
            if run.updated_at.tzinfo is None:
                utc_time = run.updated_at.replace(tzinfo=utc)
                sp_time = utc_time.astimezone(sao_paulo)
                update_dict["updated_at"] = sp_time
                needs_update = True
            elif run.updated_at.tzinfo == utc:
                sp_time = run.updated_at.astimezone(sao_paulo)
                update_dict["updated_at"] = sp_time
                needs_update = True
        
        # Check and fix started_at
        if run.started_at:
            if run.started_at.tzinfo is None:
                utc_time = run.started_at.replace(tzinfo=utc)
                sp_time = utc_time.astimezone(sao_paulo)
                update_dict["started_at"] = sp_time
                needs_update = True
            elif run.started_at.tzinfo == utc:
                sp_time = run.started_at.astimezone(sao_paulo)
                update_dict["started_at"] = sp_time
                needs_update = True
        
        # Check and fix finished_at
        if run.finished_at:
            if run.finished_at.tzinfo is None:
                utc_time = run.finished_at.replace(tzinfo=utc)
                sp_time = utc_time.astimezone(sao_paulo)
                update_dict["finished_at"] = sp_time
                needs_update = True
            elif run.finished_at.tzinfo == utc:
                sp_time = run.finished_at.astimezone(sao_paulo)
                update_dict["finished_at"] = sp_time
                needs_update = True
        
        # Apply updates if needed
        if needs_update:
            await run.update({"$set": update_dict})
            migrated_count += 1
    
    print(f"\n✅ Migration complete! Updated {migrated_count} runs.")
    return migrated_count

if __name__ == "__main__":
    asyncio.run(migrate_run_timestamps())
