# Technology Stack

This document outlines the technologies and libraries used in the Automation & Web Scraping Platform MVP.

## Core Infrastructure

The platform is designed to be cloud-agnostic and container-native.

- **Docker & Docker Compose**: Orchestration of all services. No local installation required beyond Docker.
- **Python 3.11**: Main programming language for all back-end logic.

## Back-End Services

### Frameworks & Libraries
- **FastAPI**: Used for both `App Console` and `Core Orchestrator` APIs. Provides automatic OpenAPI documentation.
- **SQLAlchemy (Async)**: ORM for interacting with PostgreSQL.
- **Pydantic**: Data validation and settings management (`pydantic-settings`).
- **AioPika**: Asynchronous RabbitMQ client for publishing and consuming messages.
- **Motor / AsyncIOMotor**: Asynchronous MongoDB driver.
- **Google Client Library**: `google-api-python-client` for interacting with Gmail API.
- **Cryptography**: Using `Fernet` (symmetric encryption) for securing stored API tokens.

### Web Scraping / Browser Automation
- **Selenium WebDriver**: Browser automation interface.
- **Selenium Standalone Chrome**: Official Docker image providing a headless Chrome instance manageable via Remote WebDriver.

## Data Storage

- **PostgreSQL (15-alpine)**:
  - Stores relational data: Workspaces, Jobs, Runs, Inbox Integrations.
  - Ensures strong consistency for state management.
- **MongoDB (6-jammy)**:
  - Stores unstructured/semi-structured data: Raw scraping payloads (HTML/JSON dumps), Evidence metadata.
  - Ideal for high-volume write operations of raw data.
- **Redis (7-alpine)**:
  - Used for ephemeral state: Distributed Locks (future use), Rate Limiting, and **OTP Synchronization** (passing codes between Inbox Worker and Scraper Worker).

## Message Broker

- **RabbitMQ (3-management)**:
  - Decouples the API from the execution workers.
  - Exchanges:
    - `jobs`: Direct exchange for routing tasks.
  - Queues:
    - `scrape.default`: Main scraping tasks.
    - `otp.request`: OTP challenge requests.
    - DLQs (Dead Letter Queues): Configured for failed messages processing.
