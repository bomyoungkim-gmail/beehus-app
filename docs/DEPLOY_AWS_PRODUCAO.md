# Deploy AWS em Producao (Frontend na Raiz `/`)

Este guia coloca a aplicacao em producao na AWS, com:

- Frontend servido na raiz do dominio: `https://seu-dominio.com/`
- API no mesmo dominio via proxy: `https://seu-dominio.com/api/...`
- Convite de usuario funcionando com link publico correto

## 1. Arquitetura recomendada

- 1 EC2 Ubuntu 22.04
- Docker + Docker Compose
- Stack da aplicacao via `docker-compose.yml` + `docker-compose.prod.yml`
- Nginx no host (porta 80/443) para:
  - `/` -> container frontend (`127.0.0.1:5173`)
  - `/api/` -> container API (`127.0.0.1:8000`)
- Certificado TLS com Certbot (Let's Encrypt)

## 2. Pre-requisitos

- Dominio configurado (ex.: `app.seudominio.com`)
- DNS `A` apontando para IP publico da EC2
- Security Group da EC2:
  - `22` (seu IP)
  - `80` (0.0.0.0/0)
  - `443` (0.0.0.0/0)

## 3. Preparar EC2

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git nginx

# Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker
```

## 4. Clonar projeto e entrar na pasta raiz

```bash
cd /opt
sudo git clone <URL_DO_REPOSITORIO> beehus-app
sudo chown -R $USER:$USER /opt/beehus-app
cd /opt/beehus-app
```

## 5. Configurar `.env` de producao

Crie/edite `/opt/beehus-app/.env`:

```env
MONGO_URI=mongodb://admin:adminpass@mongo:27017
MONGO_DB_NAME=beehus
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672//
REDIS_URL=redis://redis:6379/0

JWT_SECRET_KEY=troque_isto_por_um_secret_forte
DATABASE_ENCRYPTION_KEY=troque_isto_por_uma_chave_fernet_valida

ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=troque_isto
ADMIN_FULL_NAME=Admin

# Importante para convite/reset
FRONTEND_URL=https://app.seudominio.com

# SMTP (necessario para email de convite real)
SMTP_HOST=smtp.seuprovedor.com
SMTP_PORT=587
SMTP_USER=usuario_smtp
SMTP_PASSWORD=senha_smtp
SMTP_FROM_EMAIL=no-reply@seudominio.com
SMTP_FROM_NAME=Beehus Platform
SMTP_USE_TLS=true
```

## 6. Build do frontend para producao

Como o frontend e estatico, `VITE_API_URL` precisa estar correto no build.

```bash
cd /opt/beehus-app/beehus-web
echo "VITE_API_URL=https://app.seudominio.com/api" > .env.production
npm ci
npm run build
cd /opt/beehus-app
```

## 7. Subir containers em producao

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps
```

## 8. Configurar Nginx no host (raiz `/` + `/api`)

Crie `/etc/nginx/sites-available/beehus`:

```nginx
server {
    listen 80;
    server_name app.seudominio.com;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ative o site:

```bash
sudo ln -s /etc/nginx/sites-available/beehus /etc/nginx/sites-enabled/beehus
sudo nginx -t
sudo systemctl restart nginx
```

## 9. HTTPS com Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d app.seudominio.com
sudo systemctl enable certbot.timer
```

## 10. Ajuste de CORS no backend (obrigatorio)

No arquivo `app/console/main.py`, inclua seu dominio em `allow_origins`.

Exemplo:

- `https://app.seudominio.com`
- `https://www.app.seudominio.com` (se usar)

Depois reinicie o backend:

```bash
cd /opt/beehus-app
docker compose restart app-console
```

## 11. Testes finais

1. Abrir `https://app.seudominio.com/`
2. Abrir docs da API: `https://app.seudominio.com/api/docs`
3. Convidar usuario na tela de Users
4. Validar fluxo de processamento em `Runs`:
   - quando run estiver em `pending_file_selection`/`pending_sheet_selection`, selecionar arquivo/aba
   - confirmar que arquivo processado aparece em `Downloads` com marcador `Latest`
5. Validar:
   - link gerado com `https://app.seudominio.com/accept-invitation?...`
   - email enviado (`email_sent = true`)
   - aceite do convite conclui login

## 12. Operacao do dia a dia

```bash
cd /opt/beehus-app
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose logs -f app-console celery-worker frontend
```

## 13. Problemas comuns

- Convite cria usuario mas nao envia email:
  - SMTP nao configurado ou bloqueado
- Link de convite abre localhost:
  - `FRONTEND_URL` incorreto no `.env`
- Frontend nao chama API em producao:
  - `VITE_API_URL` errado no build do frontend
- Erro CORS no browser:
  - dominio de producao ausente em `allow_origins`
