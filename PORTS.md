# 🌐 Beehus - Service Ports Reference

Quick reference for all accessible URLs.

## 🚀 Services

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| **Frontend** | **5173** | http://localhost:5173 | React UI (Vite dev server) |
| **Backend API** | **8000** | http://localhost:8000 | FastAPI (Swagger: /docs) |
| **Flower** | **5555** | http://localhost:5555 | Celery monitoring UI |
| MongoDB | 27017 | mongodb://localhost:27017 | Database (internal) |
| RabbitMQ UI | 15672 | http://localhost:15672 | RabbitMQ console (guest/guest) |
| Redis | 6379 | redis://localhost:6379 | Cache (internal) |

---

## 📱 Quick Access

### For Development:
```bash
# Frontend
open http://localhost:5173

# API Docs
open http://localhost:8000/docs

# Celery Monitor
open http://localhost:5555
```

### Common Pages:
- Dashboard: http://localhost:5173/
- Jobs: http://localhost:5173/jobs
- Workspaces: http://localhost:5173/workspaces
- Live Execution: http://localhost:5173/live/{run_id}

---

## 🔍 Troubleshooting

**Port already in use?**
```bash
# Find process using port
netstat -ano | findstr :5173

# Kill process (Windows)
taskkill /PID <PID> /F
```

**Service not responding?**
```bash
# Check if container is running
docker compose ps

# View logs
docker compose logs frontend
docker compose logs app-console
```

---

**Last updated:** 2025-12-19  
**Note:** All ports use the same number internally and externally (no mapping confusion).
