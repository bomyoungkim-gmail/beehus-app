# Beehus App - Passo a Passo de Deploy / Atualização

## Pré-requisitos
- Acesso SSH ao EC2: `ssh ubuntu@ip-172-31-72-204`
- AWS Security Group com portas abertas: 80, 443, 7901-7905

---

## 1. Deploy completo (primeira vez ou reset)

```bash
cd ~/beehus-app

# Garantir env file na raiz
cp .env.example .env

# Subir todos os serviços
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Build frontend
sudo docker run --rm \
  -v ~/beehus-app/beehus-web:/app \
  -w /app node:20-alpine \
  sh -c "npm install && npm run build"

sudo docker restart beehus-app-frontend-prod
```

---

## 2. Atualizar código (git pull + redeploy)

```bash
cd ~/beehus-app
git pull origin main

# Se mudou backend (Python/tasks/settings):
sudo docker compose restart celery-worker app-console celery-beat

# Se mudou frontend (beehus-web/):
sudo docker run --rm \
  -v ~/beehus-app/beehus-web:/app \
  -w /app node:20-alpine \
  sh -c "npm install && npm run build"
sudo docker restart beehus-app-frontend-prod

# Se mudou docker-compose.yml:
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate <serviço>
```

---

## 3. Atualizar nginx

```bash
# Editar o arquivo
sudo nano /etc/nginx/sites-available/beehus

# Testar e recarregar
sudo nginx -t && sudo nginx -s reload

# ATENÇÃO: nunca sobrescrever com cp do repo — o certbot adiciona blocos SSL
# Para adicionar novos blocos VNC, usar tee -a
```

---

## 4. Verificar saúde do sistema

```bash
# Containers
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Portas nginx
sudo ss -tlnp | grep nginx

# Testar endpoints
curl -sk https://beehus.placestecnologia.com.br/login -o /dev/null -w "%{http_code}\n"
curl -sk https://beehus.placestecnologia.com.br:7902 -o /dev/null -w "vnc1: %{http_code}\n"
curl -sk https://beehus.placestecnologia.com.br:7903 -o /dev/null -w "vnc2: %{http_code}\n"
curl -sk https://beehus.placestecnologia.com.br:7901 -o /dev/null -w "worker-vnc: %{http_code}\n"

# Logs worker
sudo docker logs beehus-app-celery-worker-1 --tail=30
```

---

## 5. Adicionar novo chrome-node (ex: node-3)

### docker-compose.yml:
```yaml
chrome-node-3:
  <<: *chrome-node
  ports:
    - "17904:7900"
  environment:
    <<: *chrome-node-env
    SE_NODE_HOST: chrome-node-3
    SE_NODE_PORT: "5555"
```

### nginx (adicionar bloco):
```bash
sudo tee -a /etc/nginx/sites-available/beehus > /dev/null << 'EOF'
server {
    listen 7904 ssl;
    server_name beehus.placestecnologia.com.br;
    ssl_certificate /etc/letsencrypt/live/beehus.placestecnologia.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/beehus.placestecnologia.com.br/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    location / {
        proxy_pass http://127.0.0.1:17904/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
        proxy_hide_header X-Frame-Options;
    }
}
EOF
sudo nginx -t && sudo nginx -s reload
```

---

## 6. Renovar certificado SSL

```bash
sudo certbot renew --dry-run   # testar
sudo certbot renew             # renovar
sudo nginx -s reload
```

---

## 7. Limpeza de espaço em disco

```bash
# Imagens não usadas
sudo docker image prune -a -f

# Build cache
sudo docker builder prune -f

# Volumes órfãos (CUIDADO: verificar antes)
sudo docker volume ls --filter "dangling=true"
sudo docker volume prune -f

# Ver uso total
sudo docker system df
```

---

## 8. Problemas comuns e soluções

| Problema | Causa | Solução |
|---|---|---|
| 502 Bad Gateway | Container parado ou porta errada no nginx | `docker ps` + verificar proxy_pass |
| 404 No frontend | SPA routing sem fallback ou dist desatualizado | Rebuild frontend |
| Task não executa | Celery não conecta ao RabbitMQ | Verificar RABBITMQ_URL no .env |
| VNC não abre | nginx não escuta nas portas 7901-7905 | `tee -a` nos blocos VNC + reload |
| x11vnc falha | Timing do Xvfb | Container reinicia automaticamente |
| MongoDB URI error no Celery | mongodb+srv não suportado | CELERY_RESULT_BACKEND = redis://redis:6379/0 |

---

## Mapeamento de portas (resumo)

```
Usuário → https://beehus.placestecnologia.com.br       (443) → nginx → 3000 → frontend-prod
Usuário → https://api.beehus.placestecnologia.com.br   (443) → nginx → 8000 → app-console
Usuário → https://beehus.placestecnologia.com.br:7901  (SSL) → nginx → 17901 → celery-worker NoVNC
Usuário → https://beehus.placestecnologia.com.br:7902  (SSL) → nginx → 17902 → chrome-node-1 NoVNC
Usuário → https://beehus.placestecnologia.com.br:7903  (SSL) → nginx → 17903 → chrome-node-2 NoVNC
```
