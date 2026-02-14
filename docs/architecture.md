# Beehus App - Arquitetura Tecnológica Completa

## 📋 Visão Geral

**Beehus App** é uma plataforma escalável de automação e web scraping construída com arquitetura distribuída baseada em microserviços. O sistema permite orquestrar e executar tarefas de automação baseadas em navegador (Selenium) de forma paralela e assíncrona.

---

## 🏗️ Stack Tecnológica

### Backend (Python)

| Componente            | Versão  | Propósito                                                          |
| --------------------- | ------- | ------------------------------------------------------------------ |
| **Python**            | 3.11    | Runtime principal                                                  |
| **FastAPI**           | 0.104.1 | Framework web assíncrono para REST API                             |
| **Uvicorn**           | 0.24.0  | Servidor ASGI de alta performance                                  |
| **Django**            | 4.2.7   | Framework auxiliar (modo headless) para integração com Celery Beat |
| **Celery**            | 5.3.4   | Sistema de filas distribuídas para processamento assíncrono        |
| **Flower**            | 2.0.1   | Dashboard de monitoramento do Celery                               |
| **Pydantic**          | 2.5.0   | Validação de dados e schemas                                       |
| **Pydantic Settings** | 2.1.0   | Gerenciamento de configurações via variáveis de ambiente           |

### Banco de Dados & Persistência

| Componente  | Versão     | Propósito                                            |
| ----------- | ---------- | ---------------------------------------------------- |
| **MongoDB** | 6 (Jammy)  | Banco de dados NoSQL principal                       |
| **Motor**   | 3.3.2      | Driver assíncrono para MongoDB                       |
| **PyMongo** | 4.6.0      | Driver síncrono para MongoDB                         |
| **Beanie**  | 1.23.6     | ODM (Object-Document Mapper) assíncrono para MongoDB |
| **Redis**   | 7 (Alpine) | Cache e backend de resultados do Celery              |

### Message Broker & Queue

| Componente   | Versão                | Propósito                                      |
| ------------ | --------------------- | ---------------------------------------------- |
| **RabbitMQ** | 3 (Management Alpine) | Message broker para comunicação entre serviços |
| **aio-pika** | 9.3.0                 | Cliente assíncrono para RabbitMQ               |
| **AMQP**     | 5.2.0                 | Protocolo de mensageria                        |

### Automação & Scraping

| Componente        | Versão                     | Propósito                                          |
| ----------------- | -------------------------- | -------------------------------------------------- |
| **Selenium**      | 4.15.2                     | Framework de automação de navegador                |
| **Selenium Grid** | Latest (Standalone Chrome) | Infraestrutura distribuída para execução de testes |

### Segurança & Autenticação

| Componente          | Versão | Propósito                               |
| ------------------- | ------ | --------------------------------------- |
| **Cryptography**    | 41.0.7 | Biblioteca de criptografia (Fernet AES) |
| **python-jose**     | 3.3.0  | Implementação de JWT para autenticação  |
| **bcrypt**          | 4.0.1  | Hashing de senhas                       |
| **email-validator** | Latest | Validação de endereços de e-mail        |

### Integrações Externas

| Componente                   | Versão  | Propósito                                |
| ---------------------------- | ------- | ---------------------------------------- |
| **google-api-python-client** | 2.108.0 | Cliente para APIs do Google (Gmail)      |
| **google-auth-oauthlib**     | 1.1.0   | Autenticação OAuth2 para Google          |
| **google-auth-httplib2**     | 0.1.1   | Transporte HTTP para autenticação Google |

### Frontend (React)

| Componente           | Versão | Propósito                                   |
| -------------------- | ------ | ------------------------------------------- |
| **React**            | 19.2.0 | Biblioteca para construção de interfaces    |
| **React DOM**        | 19.2.0 | Renderização do React no navegador          |
| **React Router DOM** | 7.11.0 | Roteamento client-side                      |
| **Vite**             | 7.2.4  | Build tool e dev server de alta performance |
| **TypeScript**       | 5.9.3  | Superset tipado de JavaScript               |
| **Tailwind CSS**     | 4.1.18 | Framework CSS utility-first                 |
| **Axios**            | 1.13.2 | Cliente HTTP para requisições à API         |

### Infraestrutura & DevOps

| Componente         | Versão | Propósito                   |
| ------------------ | ------ | --------------------------- |
| **Docker**         | Latest | Containerização de serviços |
| **Docker Compose** | Latest | Orquestração de containers  |

---

## 🔧 Arquitetura de Serviços

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  React SPA (Vite)                                        │  │
│  │  - Dashboard de Jobs/Workspaces                          │  │
│  │  - Monitoramento de Runs                                 │  │
│  │  - Gerenciamento de Credenciais (Vault)                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP/REST
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI (app-console)                                   │  │
│  │  - REST API                                              │  │
│  │  - Autenticação JWT                                      │  │
│  │  - CRUD de Workspaces/Jobs/Credentials                   │  │
│  │  - Disparo de tarefas via Celery                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ RabbitMQ
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         WORKER LAYER                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Celery Worker                                           │  │
│  │  - Consumo de tarefas (scrape_task)                      │  │
│  │  - Resolução e descriptografia de credenciais            │  │
│  │  - Execução de conectores via Selenium                   │  │
│  │  - Persistência de resultados no MongoDB                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Celery Beat                                             │  │
│  │  - Agendamento de jobs periódicos (cron)                 │  │
│  │  - MongoScheduler (schedules dinâmicos)                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ WebDriver Protocol
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AUTOMATION LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Selenium Grid (Standalone Chrome)                       │  │
│  │  - Execução de navegadores headless                      │  │
│  │  - VNC para debug visual                                 │  │
│  │  - Shared memory (2GB) para performance                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       PERSISTENCE LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   MongoDB    │  │    Redis     │  │     RabbitMQ         │  │
│  │              │  │              │  │                      │  │
│  │ - Jobs       │  │ - Cache      │  │ - Task Queues        │  │
│  │ - Runs       │  │ - Results    │  │ - Message Routing    │  │
│  │ - Credentials│  │ - Locks      │  │                      │  │
│  │ - Users      │  │              │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Detalhamento dos Serviços

### 1. **app-console** (FastAPI)

**Porta:** 8000  
**Função:** API REST principal

**Responsabilidades:**

- Gerenciamento de Workspaces, Jobs, Runs e Credentials
- Autenticação e autorização de usuários (JWT)
- Validação de schemas via Pydantic
- Disparo assíncrono de tarefas para o Celery
- Documentação automática via Swagger/OpenAPI

**Endpoints principais:**

- `POST /workspaces` - Criar workspace
- `POST /jobs` - Criar job de scraping
- `POST /jobs/{id}/run` - Executar job
- `POST /credentials` - Criar credencial criptografada
- `GET /runs` - Listar execuções

---

### 2. **celery-worker**

**Concorrência:** 4 workers  
**Função:** Executor de tarefas assíncronas

**Responsabilidades:**

- Consumir tarefas da fila RabbitMQ
- Resolver e descriptografar credenciais do Vault
- Inicializar sessões Selenium no Grid
- Executar lógica de scraping via conectores
- Capturar arquivos baixados e executar processadores por credential
- Salvar resultados e logs no MongoDB
- Heartbeat para detecção de zombies

**Tarefas principais:**

- `scrape_task` - Execução de scraping
- `cleanup_stale_runs` - Limpeza de runs órfãos
- `cleanup_old_runs_task` - Remoção de runs antigos
- `otp_request_task` - Requisição de OTP via Gmail

---

### 3. **celery-beat**

**Função:** Agendador de tarefas periódicas

**Responsabilidades:**

- Executar jobs com schedule (cron expressions)
- Usar MongoScheduler para schedules dinâmicos
- Disparar `scheduled_job_runner` automaticamente

**Características:**

- Schedules armazenados no MongoDB (não em arquivo)
- Suporte a cron expressions padrão
- Criação automática de Runs para jobs agendados

---

### 4. **selenium** (Selenium Grid Standalone)

**Portas:** 4444 (WebDriver), 7900 (VNC)  
**Função:** Infraestrutura de automação de navegador

**Responsabilidades:**

- Fornecer sessões Chrome headless
- Executar comandos WebDriver remotamente
- Permitir debug visual via VNC
- Gerenciar recursos de memória compartilhada

**Configurações:**

- Shared memory: 2GB
- VNC password: `secret` (configurável)
- Healthcheck via `/wd/hub/status`

---

### 5. **mongo** (MongoDB 6)

**Porta:** 27017 (interna)  
**Função:** Banco de dados principal

**Collections:**

- `users` - Usuários da plataforma
- `workspaces` - Organizações/projetos
- `jobs` - Configurações de scraping
- `runs` - Histórico de execuções
- `credentials` - Credenciais criptografadas
- `file_processors` - Processadores de arquivos versionados por credential
- `inbox_integrations` - Integrações Gmail
- `otp_rules` - Regras de captura de OTP
- `otp_audit` - Logs de OTP
- `raw_payloads` - Dados brutos capturados
- `evidences` - Screenshots e dumps HTML

---

### 6. **rabbitmq** (RabbitMQ 3)

**Portas:** 5672 (AMQP), 15672 (Management UI)  
**Função:** Message broker

**Filas:**

- `celery` - Fila padrão de tarefas
- `default` - Fila alternativa
- `otp.request` - Requisições de OTP (futuro)

---

### 7. **redis** (Redis 7)

**Porta:** 6379 (interna)  
**Função:** Cache e backend de resultados

**Uso:**

- Armazenamento de resultados de tarefas Celery
- Cache de sessões
- Locks distribuídos
- Rate limiting

---

### 8. **flower**

**Porta:** 5555  
**Função:** Dashboard de monitoramento do Celery

**Recursos:**

- Visualização de tarefas ativas/concluídas
- Estatísticas de workers
- Inspeção de argumentos e resultados
- Gráficos de performance

---

### 9. **frontend** (React SPA)

**Porta:** 5173  
**Função:** Interface web do usuário

**Páginas:**

- Dashboard - Visão geral de execuções
- Jobs - Gerenciamento de jobs
- Runs - Histórico de execuções com logs
- Credentials - Vault de credenciais (futuro)
- Workspaces - Gerenciamento de workspaces

**Tecnologias:**

- Vite para build e HMR
- React Router para navegação
- Axios para comunicação com API
- Tailwind CSS para estilização

---

## 🔐 Camada de Segurança

### Criptografia de Credenciais

**Algoritmo:** Fernet (AES-128 em modo CBC)  
**Implementação:** `core/security.py`

```python
# Fluxo de criptografia
1. Usuário cria credencial via UI
2. Frontend envia senha em HTTPS
3. Backend criptografa com encrypt_value()
4. Armazena encrypted_password no MongoDB
5. Durante execução, decrypt_value() recupera senha
6. Senha é injetada no params do conector
7. Nunca aparece em logs ou responses
```

**Variável de ambiente:**

```bash
DATABASE_ENCRYPTION_KEY=<32-byte-base64-string>
```

### Autenticação de Usuários

**Método:** JWT (JSON Web Tokens)  
**Biblioteca:** python-jose  
**Hash de senhas:** bcrypt

**Fluxo:**

1. Login via `POST /auth/login`
2. Validação de credenciais
3. Geração de token JWT
4. Token enviado em header `Authorization: Bearer <token>`
5. Middleware valida token em rotas protegidas

---

## 🌐 Modelo de Dados

### Separação de Identidades

```
┌─────────────────────────────────────────────────────────────┐
│                    IDENTITY LAYER                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │  User (Usuário da Plataforma)                      │    │
│  │  - email                                           │    │
│  │  - password_hash (bcrypt)                          │    │
│  │  - role (admin/user)                               │    │
│  │                                                     │    │
│  │  Usado para: Login na plataforma Beehus           │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Gerencia
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   CREDENTIAL LAYER                          │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Credential (Credencial de Scraping)               │    │
│  │  - workspace_id                                    │    │
│  │  - label (ex: "Conta Itaú - Empresa X")           │    │
│  │  - username                                        │    │
│  │  - encrypted_password (Fernet AES)                 │    │
│  │  - metadata (dados extras)                         │    │
│  │                                                     │    │
│  │  Usado para: Bots acessarem sites externos        │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Fluxo de Execução de um Job

```
1. [Frontend] Usuário clica "Run Job"
   │
   ▼
2. [API] POST /jobs/{id}/run
   │
   ├─ Cria documento Run (status: queued)
   ├─ Dispara scrape_task.delay() no Celery
   │
   ▼
3. [RabbitMQ] Tarefa entra na fila
   │
   ▼
4. [Celery Worker] Consome tarefa
   │
   ├─ Atualiza Run (status: running)
   ├─ Busca Job no MongoDB
   ├─ Se job.credential_id existe:
   │  ├─ Busca Credential
   │  ├─ Descriptografa senha
   │  └─ Injeta username/password nos params
   │
   ▼
5. [Selenium Executor] Inicia sessão WebDriver
   │
   ├─ Conecta ao Selenium Grid (http://selenium:4444)
   ├─ Obtém sessão Chrome
   │
   ▼
6. [Connector] Executa lógica de scraping
   │
   ├─ Navega para URL
   ├─ Preenche formulários
   ├─ Clica botões
   ├─ Captura dados
   │
   ▼
7. [Worker] Salva resultados
   │
   ├─ Atualiza Run (status: success/failed)
   ├─ Salva raw_payload no MongoDB
   ├─ Adiciona logs ao Run.logs[]
   │
   ▼
8. [Selenium] Encerra sessão
   │
   ▼
9. [Frontend] Polling detecta mudança de status
   │
   └─ Atualiza UI com resultado
```

---

## 📊 Monitoramento e Observabilidade

### Logs

- **Celery Worker:** Logs estruturados com níveis INFO/ERROR
- **FastAPI:** Logs de requisições via Uvicorn
- **MongoDB:** Logs de execução armazenados em `Run.logs[]`

### Métricas

- **Flower:** Dashboard de tarefas Celery
- **Selenium Grid:** UI de status de sessões
- **RabbitMQ Management:** Estatísticas de filas

### Healthchecks

- **MongoDB:** `db.runCommand("ping")`
- **RabbitMQ:** `rabbitmq-diagnostics -q ping`
- **Selenium:** `curl http://localhost:4444/wd/hub/status`

---

## 🔄 Escalabilidade

### Horizontal Scaling

- **Celery Workers:** Aumentar `--concurrency` ou adicionar mais containers
- **Selenium Grid:** Migrar para Grid distribuído (Hub + Nodes)
- **MongoDB:** Configurar replica set
- **RabbitMQ:** Configurar cluster

### Vertical Scaling

- **Shared Memory:** Aumentar `shm_size` do Selenium
- **Worker Memory:** Ajustar limites de memória no Docker
- **MongoDB:** Aumentar recursos de CPU/RAM

---

## 🛡️ Boas Práticas de Segurança

1. **Credenciais:**
   - Nunca armazenar senhas em plain text
   - Usar `DATABASE_ENCRYPTION_KEY` forte (32+ bytes)
   - Rotacionar chaves periodicamente

2. **Rede:**
   - Usar rede Docker isolada (`scrape-net`)
   - Expor apenas portas necessárias
   - Usar HTTPS em produção

3. **Autenticação:**
   - Tokens JWT com expiração curta
   - Refresh tokens para sessões longas
   - Rate limiting em endpoints de login

4. **Auditoria:**
   - Logs de todas as ações críticas
   - Timestamps em todos os documentos
   - Rastreabilidade de quem executou cada job

---

## 📝 Notas de Desenvolvimento

### Windows Development

- Frontend deve rodar nativamente (não no Docker)
- Backend roda normalmente no Docker
- Usar `docker-compose.override.yml` para hot-reload

### Debugging

- VNC disponível em `http://localhost:7900` (senha: `secret`)
- Flower em `http://localhost:5555`
- Swagger UI em `http://localhost:8000/docs`

### Testes

- Unit tests: `pytest tests/`
- Integration tests: Usar MongoDB de teste
- E2E tests: Selenium + mocks de APIs externas

---

## 🔮 Roadmap Técnico

### Curto Prazo

- [ ] Implementar UI do Vault de Credenciais
- [ ] Adicionar testes automatizados
- [ ] Migração de credenciais antigas

### Médio Prazo

- [ ] Suporte a múltiplos navegadores (Firefox, Edge)
- [ ] Sistema de plugins para conectores
- [ ] API GraphQL complementar

### Longo Prazo

- [ ] Kubernetes deployment
- [ ] Multi-tenancy completo
- [ ] Machine learning para detecção de anomalias

---

**Versão do Documento:** 1.0  
**Última Atualização:** 2025-12-30  
**Mantido por:** Equipe Beehus
