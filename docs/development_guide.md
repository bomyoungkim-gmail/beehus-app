# Development & Usage Guide

This guide details how to organize your code and the workflow to add new features (Scrapers) to the platform.

## 1. Code Organization

The project follows a strict separation between **Control** (App) and **Execution** (Core).

### 📂 `core/` (The Engine)
**Modify this folder when you are writing Scraping Logic.**

- **`core/connectors/`**: This is where your Scrapers live.
  - Each site/scraper should be a separate file (e.g., `amazon.py`, `linkedin.py`).
  - Must inherit from `BaseConnector`.
- **`core/worker/`**: Logic for the background worker (RabbitMQ consumer).
- **`core/orchestrator/`**: The internal API that talks to the workers.

### 📂 `app/` (The Console)
**Modify this folder when you are changing the API/Database models.**

- **`app/console/`**: The FastAPI application exposed to the user (port 8000).
- **`app/console/models.py`**: Database tables (Jobs, Runs, Workspaces).

---

## 2. workflow: Adding a New Scraper

Follow these steps to add a new scraper (e.g., for "MySite").

### Step 1: Create the Connector File
Create a new file `core/connectors/mysite.py`. Use the template below:

```python
from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
# Import Selenium tools
from selenium.webdriver.common.by import By

class MySiteScraper(BaseConnector):
    @property
    def name(self):
        return "mysite_scraper"  # <--- ID used in the Job

    async def scrape(self, driver, params: dict) -> ScrapeResult:
        # Your Selenium Logic Here
        driver.get(params.get("url"))
        title = driver.title
        
        return ScrapeResult(
            run_id=params.get("run_id"),
            success=True,
            data={"title": title}
        )
```

### Step 2: Register the Connector
Open `core/connectors/registry.py` and import your class:

```python
from core.connectors.mysite import MySiteScraper # <--- Import

# Register it
ConnectorRegistry.register(MySiteScraper)
```

### Step 3: Apply Changes
Since the Core Worker runs inside Docker, you must restart it to load the new code (unless volumes are mounted with reload, but explicit restart is safer for new files):

```bash
docker compose restart core-worker
```

---

## 3. Usage: Running the Scraper

You control the platform via the **App Console API** (Swagger UI).

**URL:** [http://localhost:8000/docs](http://localhost:8000/docs)

### 1. Create a Workspace (One-time)
- **POST** `/workspaces`
- Body: `{"name": "Dev Environment"}`
- Copy the returned `id` (e.g., `ws-123`).

### 2. Create the Job
This tells the system "I want to run `mysite_scraper` with these parameters".

- **POST** `/jobs`
- Body:
  ```json
  {
    "workspace_id": "ws-123",
    "name": "Extract MySite Homepage",
    "connector": "mysite_scraper", 
    "params": {
      "url": "https://mysite.com"
    }
  }
  ```
- Copy the returned `id` (Job ID).

### 3. Run the Job
- **POST** `/jobs/{job_id}/run`
- Click Execute.
- The system will queue the job. The `core-worker` will pick it up, run your Selenium code, and save the result.

### 4. Check Results
- **GET** `/runs/{run_id}`
- Check the `status` ("success" or "failed").
- Check MongoDB (or logs) for the extracted data.
