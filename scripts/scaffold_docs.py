import shutil
from pathlib import Path

DOCS_DIR = Path("docs")
STD_TEMPLATE = DOCS_DIR / "_templates" / "standard_template.md"
ADR_TEMPLATE = DOCS_DIR / "_templates" / "adr_template.md"

# Map of file path -> template to use
FILES_TO_CREATE = {
    # Product
    "01-product/01-user-journeys.md": STD_TEMPLATE,
    "01-product/02-requirements.md": STD_TEMPLATE,
    
    # Business Rules
    "02-business-rules/01-job-scheduling.md": STD_TEMPLATE,
    "02-business-rules/03-rate-limits.md": STD_TEMPLATE,
    "02-business-rules/04-error-handling.md": STD_TEMPLATE,
    
    # System Design
    "03-system-design/00-system-context.md": STD_TEMPLATE,
    "03-system-design/01-service-boundaries.md": STD_TEMPLATE,
    
    # Data
    "04-data/00-schema.md": STD_TEMPLATE,
    "04-data/01-migrations.md": STD_TEMPLATE,
    
    # API
    "05-api/00-api-overview.md": STD_TEMPLATE,
    "05-api/01-rest-contracts.md": STD_TEMPLATE,
    
    # Frontend
    "06-frontend/00-frontend-architecture.md": STD_TEMPLATE,
    "06-frontend/01-console-ui.md": STD_TEMPLATE,
    
    # Jobs & AI
    "07-jobs-and-ai/00-workers.md": STD_TEMPLATE,
    "07-jobs-and-ai/01-selenium-grid.md": STD_TEMPLATE,
    
    # Testing
    "08-testing/00-testing-strategy.md": STD_TEMPLATE,
    
    # Operations
    "09-operations/00-local-dev.md": STD_TEMPLATE,
    "09-operations/01-deploy.md": STD_TEMPLATE,
    
    # Decisions (ADR)
    "10-decisions/adr-0001-tech-stack.md": ADR_TEMPLATE,
}

def main():
    if not STD_TEMPLATE.exists():
        print("Template missing!")
        return

    created_count = 0
    for rel_path, template_path in FILES_TO_CREATE.items():
        dest = DOCS_DIR / rel_path
        if not dest.exists():
            shutil.copy(template_path, dest)
            print(f"Created: {dest}")
            created_count += 1
        else:
            print(f"Skipped (exists): {dest}")
            
    print(f"✅ Scaffolding complete. Created {created_count} files.")

if __name__ == "__main__":
    main()
