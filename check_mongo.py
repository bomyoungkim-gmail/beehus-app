import asyncio
import motor.motor_asyncio
import sys
from pprint import pprint

async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://admin:adminpass@mongo:27017')
    db = client['platform_db']
    runs = await db.runs.find().sort('created_at', -1).limit(5).to_list(length=5)
    for run in runs:
        print(f"Run ID: {run['_id']} | Connector: {run.get('connector')} | Status: {run.get('status')}")
        for log in run.get('logs', []):
            if 'ERROR' in log or '❌' in log or 'Starting' in log:
                print(f"  {log}")

asyncio.run(main())
