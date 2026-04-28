# beehus-app

**Beehus App** is a scalable Automation & Web Scraping Platform built with FastAPI, Celery, MongoDB, and Selenium Grid. It allows you to orchestrate and execute browser-based automation tasks in parallel using a distributed architecture.

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Start the Platform

1. Clone the repository
2. Create your centralized env file:
   ```bash
   cp .env.example .env
   ```
3. Edit `.env` with your environment values.
4. Run with Docker Compose:
   ```bash
   docker compose up --build -d
   ```

### Windows Development Setup

The Docker setup is consolidated in `docker-compose.yml`, including the frontend service.

**Setup:**

1. Start all services:
   ```bash
   docker compose up --build -d
   ```
2. Access the application at:
   - **Frontend**: http://localhost:5173
   - **Backend API**: http://localhost:8000/docs

**Optional (native frontend fallback):**

If you prefer running Vite natively on Windows, stop only the frontend container and run it locally:

```bash
docker compose stop frontend
cd beehus-web
npm install
npm run dev
```

---

## 🔌 Services & Architecture

Below is a breakdown of each container and its role in the platform:

| Component     | Service Name    | Role & Description                                                                                                                                                                                                     |
| :------------ | :-------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **API**       | `app-console`   | **REST API (FastAPI)**<br>Main entrypoint. Manages Workspaces, Jobs, and triggers Runs. Dispatches tasks to RabbitMQ.                                                                                                  |
| **Worker**    | `celery-worker` | **Task Executor**<br>Consumes tasks from RabbitMQ. Initializes Selenium WebDriver and executes the scraping logic using `core/connectors`. Persists results to MongoDB. Concurrency: 1 (optimized for I/O-bound jobs). |
| **Scheduler** | `celery-beat`   | **Cron Scheduler**<br>Triggers periodic tasks using a custom **MongoScheduler**, allowing dynamic schedule management via the database.                                                                                |
| **Browser**   | `selenium`      | **Selenium Standalone**<br>Runs Chrome browsers in a headless environment. The worker connects here to drive the browser remotely. 2 nodes for concurrent execution.                                                   |
| **Broker**    | `rabbitmq`      | **Message Broker**<br>Handles communication between API and Workers. Stores task queues (`default`, `celery`).                                                                                                         |
| **DB**        | `mongo`         | **Database (NoSQL)**<br>Stores all application data: job configurations, run status, and scraped payloads.                                                                                                             |
| **Cache**     | `redis`         | **Cache & Result Backend**<br>Used by Celery for result storage and coordination.                                                                                                                                      |
| **Frontend**  | `frontend`      | **React SPA**<br>Modern dashboard for managing workspaces, jobs, and monitoring runs. Built with Vite, React, and Tailwind.                                                                                            |

### 🔐 Environment Variables

### Frontend (`.env` or Docker env)

| Variable                  | Description                                                | Default                 |
| :------------------------ | :--------------------------------------------------------- | :---------------------- |
| `VITE_API_URL`            | URL of the Backend API (accessible from browser)           | `http://localhost:8000` |
| `VITE_VNC_URL_BASE`       | Base URL used to build Selenium/worker VNC endpoints       | `http://localhost`      |
| `VITE_VNC_HOST_PORT_BASE` | Base public host port for VNC mapping                      | `17901`                 |
| `VITE_VNC_PASSWORD`       | Password for VNC connection (must match `SE_VNC_PASSWORD`) | `secret`                |

### Backend (`.env`)

| Variable              | Description                                 | Default                       |
| :-------------------- | :------------------------------------------ | :---------------------------- |
| `MONGO_DB_NAME`       | Name of the MongoDB database                | `beehus`                      |
| `SE_VNC_PASSWORD`     | Password for Selenium VNC server            | `secret`                      |
| `SELENIUM_REMOTE_URL` | Internal URL for Celery to talk to Selenium | `http://selenium:4444/wd/hub` |

## 🛠 Usage Ports

| Service                | Address (Host)                                           |
| :--------------------- | :------------------------------------------------------- |
| **Frontend Dashboard** | [http://localhost:5173](http://localhost:5173)           |
| **API Documentation**  | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Selenium Grid UI**   | [http://localhost:4444](http://localhost:4444)           |
| **RabbitMQ Admin**     | [http://localhost:15672](http://localhost:15672)         |

## 🛠 Usage

### 1. Access the Dashboard (Frontend)

Access [http://localhost:5173](http://localhost:5173) to:

- **Monitor Live Executions:** View active and queued runs with real-time status updates.
- **Manage Jobs/Workspaces:** Create and configure scraping jobs.
- **Execution History:** View detailed logs of past runs via the "Runs" page.
- **Processing Selection in Runs:** For ambiguous downloads, choose file and Excel sheet directly in "Runs"; recurring jobs reuse the last selection automatically.
- **Downloads & Reports:** Access downloaded and processed files via the "Downloads" page.
  - Reprocessed outputs keep version history and the newest processed file is marked as `Latest`.
- **Credential Processors:** Configure per-credential file processing scripts with version history.
- **Processamento Automatizado:** Processamento em lote por upload de pastas ou por caminhos no servidor (allowlist), com opcao de sandbox Docker.
- **Collapsible Sidebar:** Toggle the sidebar to maximize screen real estate.

### 2. Monitor Tasks (CLI)

> **Note**: Flower web UI has been disabled to save ~300MB RAM. Use CLI monitoring instead:

**Windows (PowerShell)**:

```powershell
# Show active tasks
.\scripts\monitor_celery.ps1 active

# Show worker statistics
.\scripts\monitor_celery.ps1 stats

# Show all available commands
.\scripts\monitor_celery.ps1 help
```

**Linux/Mac (Bash)**:

```bash
# Show active tasks
./scripts/monitor_celery.sh active

# Show worker statistics
./scripts/monitor_celery.sh stats
```

**Direct Docker Commands**:

```bash
# Active tasks
docker exec beehus-app-celery-worker-1 celery -A core.celery_app inspect active

# Worker stats
docker exec beehus-app-celery-worker-1 celery -A core.celery_app inspect stats

# Ping workers
docker exec beehus-app-celery-worker-1 celery -A core.celery_app inspect ping
```

> **To re-enable Flower**: Uncomment the `flower` service in `docker-compose.yml` and restart with `docker compose up -d`

### 2. Watch Browser Activity (Selenium)

Access [http://localhost:4444](http://localhost:4444) to:

- See active Chrome Slots (2 available).
- View live sessions (Sessions tab -> Click on camera icon if VNC is enabled, or just see the session list).
- Debug failed sessions.

### 3. API Examples

Trigger a scrape via **App Console** Swagger UI ([http://localhost:8000/docs](http://localhost:8000/docs)):

1. **Create Workspace**: `POST /workspaces`
2. **Create Job**: `POST /jobs`
3. **Run Job**: `POST /jobs/{job_id}/run`

The run will be queued in RabbitMQ, picked up by `celery-worker`, and executed on `selenium`.
id **Gmail Refresh Token** and Client credentials.

### Processing Selection Endpoints

Use these endpoints when a run requires manual processing selection:

- `GET /downloads/{run_id}/processing/options`
- `POST /downloads/{run_id}/processing/select-file`
- `GET /downloads/{run_id}/processing/excel-options?filename=...`
- `POST /downloads/{run_id}/processing/select-sheet`
- `POST /downloads/{run_id}/processing/process` (manual reprocess with versioned output)

### Automated Folder Processing Endpoints

- `GET /processamento-automatizado/sandbox-health`
  - valida disponibilidade do Docker e (opcionalmente) executa `docker pull` da imagem configurada
  - query params: `sandbox_mode`, `pull_image`, `run_probe`, `timeout_seconds`
  - `run_probe=true` executa um `docker run` de validacao com as mesmas flags de hardening do sandbox para detectar bloqueios de execucao antes do upload
- `POST /processamento-automatizado/process`
  - multipart upload de arquivos organizados por pasta relativa
  - query params: `timeout_seconds`, `sandbox_mode=none|docker`
- `POST /processamento-automatizado/process-server-paths`
  - body JSON: `folder_paths[]`, `timeout_seconds`, `sandbox_mode=none|docker`, `write_to_source=true|false`
  - valida cada caminho com allowlist de seguranca (`AUTOMATED_PROCESSING_SERVER_ALLOWLIST`)
  - com `write_to_source=true`, os arquivos processados tambem permanecem na pasta de origem no servidor

Status por pasta:

- cada pasta incluida recebe status de execucao (`success` ou `failed`),
- em falhas, o retorno `detail.errors` inclui `folder`, `status` e `error`,
- em sucesso, o `processing_report.json` dentro do ZIP inclui `folder_statuses`.

Sandbox Docker (opcional):

- Configure `AUTOMATED_PROCESSING_SANDBOX_IMAGE` com uma imagem restrita contendo as dependencias do script.
- O runner aplica `--network none`, limite de CPU/memoria/PIDs e `no-new-privileges`.
- Ajuste `AUTOMATED_PROCESSING_SANDBOX_HEALTH_TIMEOUT` para controlar timeout de health-check/pull.

Imagem customizada recomendada (padrao):

```bash
docker build -f docker/Dockerfile.automated-processing-sandbox -t beehus-automated-processing-sandbox:latest .
```

- O valor padrao em `.env.example` para `AUTOMATED_PROCESSING_SANDBOX_IMAGE` e `beehus-automated-processing-sandbox:latest`.
- Se o `docker pull` dessa tag falhar, o health-check aceita a imagem local caso ela ja exista no host Docker.

### 4. Configure OTP

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

### 5. Run OTP Scrape

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

### 6. Verify Execution

1. The **Core Worker** will log `Published OTP Request... Waiting...`.
2. The **Inbox Worker** will start polling Gmail.
3. **Action:** Send an email to the configured address with subject "Code" and body containing "123456" (or similar 6 digits).
4. **Inbox Worker** will log `OTP Found`.
5. **Core Worker** will log `OTP Code received!` and finish successfully.


https://login.morganstanleyclientserv.com/ux/#/accounts/holdings?referer=mso-menu	L: Beehus	S: Beehus2025!