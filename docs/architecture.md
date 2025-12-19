# Application Architecture & Structure

This document describes the high-level architecture and directory organization of the platform.

## Architecture Patterns

The system validates the **Separation of Concerns** principle by dividing the "Business Logic/Control" (App) from the "Execution Engine" (Core).

### 1. CORE (Engine)
The reusable engine accessible via internal API and Queues. It is agnostic of the "User" or "Console" business logic.

- **Core Orchestrator**: 
  - Internal API (`port 8001`) that accepts raw job execution requests.
  - Publishes messages to RabbitMQ.
- **Core Worker**:
  - Headless daemon that consumes `job` messages.
  - Connects to Selenium to perform scraping.
  - Loads "Connectors" dynamically.
- **Inbox Worker**:
  - Specialized worker for handling OTP/2FA challenges.
  - Consumes `otp.request` messages.
  - Polls Gmail based on defined rules.

### 2. APP (Console)
The customer-facing layer. This acts as the "Client" of the Core Engine.

- **App Console API**:
  - Public API (`port 8000`).
  - Manages tenant data: Workspaces, Users (future), stored configurations.
  - Communicates with Core Orchestrator via HTTP to enqueue jobs.

### 3. Data Flow (Happy Path)
1. **User** POSTs a Job to `App Console`.
2. **User** POSTs a Run Trigger to `App Console`.
3. **App Console** creates a `Run` record (Status: QUEUED) and POSTs payload to `Core Orchestrator`.
4. **Core Orchestrator** publishes message to RabbitMQ (`scrape.default`).
5. **Core Worker** consumes message:
   - Sets Status: RUNNING.
   - Executes `Connector.scrape()`.
   - If OTP needed:
     - Sets Status: WAITING_OTP (internally tracked via logs/state).
     - Publishes `otp.request`.
     - Waits for Redis key.
6. **Inbox Worker** sees `otp.request`:
   - Scans Gmail.
   - Puts code in Redis.
7. **Core Worker** resumes, finishes scrape.
8. **Core Worker** updates Status: SUCCESS and saves Raw Data to Mongo.

## Directory Structure

```
/
├── .env                  # Environment Variables (Secrets, Config)
├── docker-compose.yml    # Infrastructure Definition
├── Dockerfile.core       # Image definition for Workers & Orchestrator
├── Dockerfile.app        # Image definition for App Console
├── README.md             # Usage Guide
│
├── app/                  # Application Context (Console)
│   ├── console/
│   │   ├── main.py       # FastAPI Entrypoint
│   │   ├── models.py     # App-Specific DB Models (Jobs, Runs)
│   │   └── schemas.py    # App-Specific Pydantic Schemas
│
├── core/                 # Engine Context (Reusable)
│   ├── config.py         # Shared Configuration
│   ├── db.py             # Database Connection (Async)
│   ├── mq.py             # Message Queue Utils
│   ├── schemas/          # Shared Data Contracts (JobRequest, OtpRequest)
│   ├── models/           # Shared/Core DB Models (Inbox, Audit)
│   │
│   ├── orchestrator/     # Core Orchestrator Service
│   │   └── main.py
│   │
│   ├── worker/           # Scraping Worker Service
│   │   ├── main.py       # Consumer & Loop
│   │   ├── executor.py   # Selenium Lifecycle
│   │   └── utils.py      # Helpers (wait_for_otp)
│   │
│   ├── connectors/       # Plugins / Scrapers
│   │   ├── base.py       # Interface
│   │   ├── registry.py   # Loader
│   │   └── ...           # Implementations (example.py)
│   │
│   └── inbox_worker_gmail/ # Email Worker Service
│       └── main.py
│
└── doc/                  # Documentation
    ├── technologies.md
    └── architecture.md
```
