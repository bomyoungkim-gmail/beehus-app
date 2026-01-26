import asyncio
from core.db import init_db
from core.models.mongo_models import Run

async def check_run(run_id):
    await init_db()
    run = await Run.get(run_id)
    if run:
        print(f"Run {run_id[:8]}: status={run.status}, started={run.started_at}, finished={run.finished_at}")
    else:
        print(f"Run {run_id} NOT FOUND")

# Check the most recent run
asyncio.run(check_run('c1d75087-76d2-44bd-a34f-f38146fa2518'))
