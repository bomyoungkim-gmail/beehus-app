# beehus-app

**Beehus App** is a scalable Automation & Web Scraping Platform built with FastAPI, Celery, MongoDB, and Selenium Grid. It allows you to orchestrate and execute browser-based automation tasks in parallel using a distributed architecture.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Start the Platform
1. Clone the repository
2. Create your `.env` file (copy example if available or use defaults):
   ```bash
   # .env
   MONGO_DB_NAME=beehus
   SELENIUM_REMOTE_URL=http://selenium:4444/wd/hub
   ```
3. Run with Docker Compose:
   ```bash
   docker compose up --build -d
   ```

## 🔌 Services & Architecture

Below is a breakdown of each container and its role in the platform:

| Component | Service Name | Role & Description |
|:---|:---|:---|
| **API** | `app-console` | **REST API (FastAPI)**<br>Main entrypoint. Manages Workspaces, Jobs, and triggers Runs. Dispatches tasks to RabbitMQ. |
| **Worker** | `celery-worker` | **Task Executor**<br>Consumes tasks from RabbitMQ. Initializes Selenium WebDriver and executes the scraping logic using `core/connectors`. Persists results to MongoDB. |
| **Scheduler** | `celery-beat` | **Cron Scheduler**<br>Triggers periodic tasks (e.g., `cleanup_old_runs`) based on the schedule defined in `core/celery_app.py`. |
| **Monitor** | `flower` | **Dashboards**<br>Web UI for monitoring Celery tasks, worker health, and queue statistics. |
| **Browser** | `selenium` | **Selenium Standalone**<br>Runs Chrome/Firefox browsers in a headless environment. The worker connects here to drive the browser remotely. |
| **Broker** | `rabbitmq` | **Message Broker**<br>Handles communication between API and Workers. Stores task queues (`default`, `celery`). |
| **DB** | `mongo` | **Database (NoSQL)**<br>Stores all application data: job configurations, run status, and scraped payloads. |
| **Cache** | `redis` | **Cache & Result Backend**<br>Used by Celery for result storage and coordination. |

### 🛠 Usage Ports

| Service | Address (Host) |
|:---|:---|
| **API Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Flower (Task Monitor)** | [http://localhost:5555](http://localhost:5555) |
| **Selenium Grid UI** | [http://localhost:4444](http://localhost:4444) |
| **RabbitMQ Admin** | [http://localhost:15672](http://localhost:15672) |

## 🛠 Usage

### 1. Monitor Tasks (Flower)
Access [http://localhost:5555](http://localhost:5555) to see:
- Active / Processed Tasks
- Worker Health
- Task Args and Results

### 2. Watch Browser Activity (Selenium)
Access [http://localhost:4444](http://localhost:4444) to:
- See active Chrome Slots (3 available).
- View live sessions (Sessions tab -> Click on camera icon if VNC is enabled, or just see the session list).
- Debug failed sessions.

### 3. API Examples
Trigger a scrape via **App Console** Swagger UI ([http://localhost:8000/docs](http://localhost:8000/docs)):

1. **Create Workspace**: `POST /workspaces`
2. **Create Job**: `POST /jobs`
3. **Run Job**: `POST /jobs/{job_id}/run`

The run will be queued in RabbitMQ, picked up by `celery-worker`, and executed on `selenium`.
id **Gmail Refresh Token** and Client credentials.

### 2. Configure OTP
```bash
# A. Create Workspace
curl -X POST http://localhost:8000/workspaces \
     -d '{"name": "production"}'
# RESPONSE: {"id": "WORKSPACE_UUID", ...}

# B. Add Gmail Integration (Manual)
# Replace WORKSPACE_UUID and Credentials
curl -X POST http://localhost:8000/workspaces/WORKSPACE_UUID/integrations/gmail/manual \
     -H "Content-Type: application/json" \
     -d '{
       "client_id": "CLIENT_ID",
       "client_secret": "CLIENT_SECRET",
       "refresh_token": "REFRESH_TOKEN",
       "email_address": "your@email.com"
     }'

# C. Create OTP Rule
curl -X POST http://localhost:8000/workspaces/WORKSPACE_UUID/otp-rules \
     -H "Content-Type: application/json" \
     -d '{
       "name": "default-login",
       "provider": "gmail",
       "gmail_query": "subject:(Code) newer_than:1d",
       "otp_regex": "(\\d{6})",
       "ttl_seconds": 300,
       "timeout_seconds": 180
     }'
```

### 3. Run OTP Scrape
Use the `example_otp` connector which simulates asking for OTP.

```bash
# Create Job
curl -X POST "http://localhost:8000/jobs" \
     -H "Content-Type: application/json" \
     -d '{
           "workspace_id": "WORKSPACE_UUID",
           "name": "OTP Test",
           "connector": "example_otp",
           "params": {"url": "https://example.com"}
         }'

# Run Job
curl -X POST "http://localhost:8000/jobs/{job_id}/run"
```

### 4. Verify Execution
1. The **Core Worker** will log `Published OTP Request... Waiting...`.
2. The **Inbox Worker** will start polling Gmail.
3. **Action:** Send an email to the configured address with subject "Code" and body containing "123456" (or similar 6 digits).
4. **Inbox Worker** will log `OTP Found`.
5. **Core Worker** will log `OTP Code received!` and finish successfully.
