import os
import sys
import importlib.util
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

class MigrationRunner:
    """
    MongoDB migration runner with version tracking.
    Tracks applied migrations in '_migrations' collection.
    """
    
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.migrations_col = self.db['_migrations']  # Use bracket notation for collections starting with _
    
    async def get_applied(self):
        """Get list of applied migration filenames"""
        cursor = self.migrations_col.find().sort('applied_at', 1)
        return [doc['name'] async for doc in cursor]
    
    async def run_pending(self):
        """Run all pending migrations"""
        applied = await self.get_applied()
        
        # Get all migration files
        migrations_dir = os.path.join(os.path.dirname(__file__))
        files = sorted([
            f for f in os.listdir(migrations_dir) 
            if f.endswith('.py') and f not in ['runner.py', 'template.py', '__init__.py']
        ])
        
        pending_count = 0
        for filename in files:
            if filename in applied:
                print(f"⏭️  Skipping {filename} (already applied)")
                continue
            
            print(f"🔄 Running {filename}...")
            module = self._load_module(filename)
            
            try:
                await module.up(self.db)
                await self.migrations_col.insert_one({
                    'name': filename,
                    'applied_at': datetime.utcnow()
                })
                print(f"✅ Applied {filename}")
                pending_count += 1
            except Exception as e:
                print(f"❌ Failed {filename}: {e}")
                raise
        
        if pending_count == 0:
            print("✅ No pending migrations")
        else:
            print(f"\n✅ Applied {pending_count} migration(s)")
        
        return pending_count
    
    async def rollback_last(self):
        """Rollback the most recently applied migration"""
        last = await self.migrations_col.find_one(sort=[('applied_at', -1)])
        if not last:
            print("⚠️  No migrations to rollback")
            return
        
        filename = last['name']
        print(f"🔄 Rolling back {filename}...")
        module = self._load_module(filename)
        
        try:
            await module.down(self.db)
            await self.migrations_col.delete_one({'name': filename})
            print(f"✅ Rolled back {filename}")
        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            raise
    
    async def status(self):
        """Show migration status"""
        applied = await self.get_applied()
        migrations_dir = os.path.join(os.path.dirname(__file__))
        all_files = sorted([
            f for f in os.listdir(migrations_dir) 
            if f.endswith('.py') and f not in ['runner.py', 'template.py', '__init__.py']
        ])
        
        print("\n📊 Migration Status:\n")
        print(f"{'Status':<12} {'Migration':<40} {'Applied At'}")
        print("-" * 80)
        
        for filename in all_files:
            if filename in applied:
                # Get applied date
                doc = await self.migrations_col.find_one({'name': filename})
                applied_at = doc['applied_at'].strftime('%Y-%m-%d %H:%M:%S') if doc else 'Unknown'
                print(f"{'✅ Applied':<12} {filename:<40} {applied_at}")
            else:
                print(f"{'⏳ Pending':<12} {filename:<40} {'-'}")
        
        print(f"\nTotal: {len(all_files)} migrations ({len(applied)} applied, {len(all_files) - len(applied)} pending)")
    
    def _load_module(self, filename):
        """Load migration module from file"""
        filepath = os.path.join(os.path.dirname(__file__), filename)
        spec = importlib.util.spec_from_file_location(filename, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    async def close(self):
        """Close MongoDB connection"""
        self.client.close()


async def main():
    # Load config from environment or defaults
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://admin:adminpass@localhost:27017')
    db_name = os.getenv('MONGO_DB_NAME', 'platform_db')
    
    runner = MigrationRunner(mongo_uri, db_name)
    
    if len(sys.argv) < 2:
        print("Usage: python migrations/runner.py [migrate|rollback|status]")
        print("\nCommands:")
        print("  migrate   - Run all pending migrations")
        print("  rollback  - Rollback the last applied migration")
        print("  status    - Show migration status")
        await runner.close()
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == 'migrate':
            await runner.run_pending()
        elif command == 'rollback':
            await runner.rollback_last()
        elif command == 'status':
            await runner.status()
        else:
            print(f"❌ Unknown command: {command}")
            sys.exit(1)
    finally:
        await runner.close()


if __name__ == '__main__':
    asyncio.run(main())
