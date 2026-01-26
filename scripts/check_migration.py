"""
Check if migration worked correctly
"""
import asyncio
from core.db import init_db
from core.models.mongo_models import Run

async def check_migration():
    await init_db()
    
    # Get a few sample runs
    runs = await Run.find().limit(5).to_list()
    
    print("Sample runs after migration:")
    print("-" * 80)
    for run in runs:
        print(f"Run ID: {run.id[:8]}")
        print(f"  created_at: {run.created_at}")
        print(f"  Timezone: {run.created_at.tzinfo if run.created_at else 'None'}")
        print()

if __name__ == "__main__":
    asyncio.run(check_migration())
