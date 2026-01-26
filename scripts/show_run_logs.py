import asyncio
from core.db import init_db
from core.models.mongo_models import Run

async def show_logs():
    await init_db()
    run = await Run.get('4fd9d2a8-b312-4df6-a79b-da2dccd3e2ba')
    print("=" * 70)
    print(f"LOGS DO RUN: {run.id}")
    print(f"Status: {run.status}")
    print(f"Erro: {run.error_summary[:200] if run.error_summary else 'N/A'}")
    print("=" * 70)
    print()
    for log in run.logs:
        print(log)

asyncio.run(show_logs())
