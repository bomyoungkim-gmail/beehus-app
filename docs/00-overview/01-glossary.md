# Glossary
**Purpose:** Define common terms used across the Beehus Platform code and documentation.
**Audience:** All

- **Workspace**: A tenant or logical grouping of jobs and integrations (e.g., a specific client or project).
- **Job**: A definition of a scraping task (e.g., "Scrape Amazon Products"). Contains configuration but not execution state.
- **Run**: A single execution instance of a Job. Has status (queued, running, success, failed), logs, and outputs.
- **Payload**: The raw data extracted during a Run (e.g., HTML, JSON). Stored in MongoDB.
- **Evidence**: Screenshots or other proof of execution collected during a Run.
- **Connector**: A Python class responsible for the logic of interacting with a specific target site (e.g., `AmazonConnector`).
- **Orchestrator**: (Legacy term) The system responsible for managing job queues and worker dispatch. Now handled by Celery.
- **Inbox Integration**: A connection to an email provider (Gmail) used to capture OTPs or verification emails.
- **OTP Rule**: A regex pattern used to extract specific codes from emails received via Inbox Integrations.
- **Selenium Grid**: A cluster of browser nodes allowing parallel execution of scraping tasks.
