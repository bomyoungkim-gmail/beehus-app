"""
Migration: Initial schema and indexes
Date: 2025-12-19
Author: System

Creates all necessary indexes for optimal query performance.
"""

async def up(db):
    """Apply migration"""
    print("  Creating indexes...")
    
    # Workspaces
    await db.workspaces.create_index("name", unique=True)
    print("    ✓ workspaces.name (unique)")
    
    # Jobs
    await db.jobs.create_index([("workspace_id", 1), ("status", 1)])
    await db.jobs.create_index("connector")
    print("    ✓ jobs.workspace_id + status")
    print("    ✓ jobs.connector")
    
    # Runs
    await db.runs.create_index([("job_id", 1), ("created_at", -1)])
    await db.runs.create_index("status")
    print("    ✓ runs.job_id + created_at")
    print("    ✓ runs.status")
    
    # Inbox Integrations
    await db.inbox_integrations.create_index("workspace_id")
    await db.inbox_integrations.create_index("email_address")
    print("    ✓ inbox_integrations.workspace_id")
    print("    ✓ inbox_integrations.email_address")
    
    # OTP Rules
    await db.otp_rules.create_index("workspace_id")
    print("    ✓ otp_rules.workspace_id")
    
    # OTP Audit
    await db.otp_audit.create_index("run_id")
    print("    ✓ otp_audit.run_id")
    
    # Raw Payloads (for cleanup queries)
    await db.raw_payloads.create_index("run_id")
    await db.raw_payloads.create_index("captured_at")
    print("    ✓ raw_payloads.run_id")
    print("    ✓ raw_payloads.captured_at")
    
    # Evidences
    await db.evidences.create_index("run_id")
    print("    ✓ evidences.run_id")
    
    print("  ✅ All indexes created")


async def down(db):
    """Rollback migration"""
    print("  Dropping indexes...")
    
    # Drop all non-_id indexes
    await db.workspaces.drop_indexes()
    await db.jobs.drop_indexes()
    await db.runs.drop_indexes()
    await db.inbox_integrations.drop_indexes()
    await db.otp_rules.drop_indexes()
    await db.otp_audit.drop_indexes()
    await db.raw_payloads.drop_indexes()
    await db.evidences.drop_indexes()
    
    print("  ✅ All indexes dropped")
