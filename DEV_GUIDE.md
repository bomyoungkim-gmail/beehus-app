# 🚀 Desenvolvimento com Hot-Reload

## Como funciona

Os containers estão configurados com **volumes** que sincronizam a pasta do projeto em tempo real:

```yaml
volumes:
  - .:/app  # Sincroniza tudo do host para /app dentro do container
```

## Fluxo de desenvolvimento

### 1️⃣ Mudanças em arquivos Python (recomendado)

```bash
# Editar arquivo, salvar
# Normalmente não precisa fazer nada - o Django/Celery detecta automaticamente!

# Mas se quiser forçar reload do worker:
./reload.ps1           # Windows PowerShell
# ou
bash reload.sh         # Linux/Mac
```

**O que funciona sem restart:**

- ✅ Mudanças em `tasks.py`
- ✅ Mudanças em `models.py` (sem nova migration)
- ✅ Mudanças em signal handlers
- ✅ Mudanças em settings (algumas)
- ✅ Mudanças em views Django

### 2️⃣ Alterações que requerem rebuild

Se você adicionar **dependências novas**:

```bash
# 1. Editar requirements.txt
# 2. Fazer rebuild:
docker-compose up -d --build

# Isso reinstala packages sem perder dados no BD
```

### 3️⃣ Quando usar cada comando

| Situação | Comando |
|----------|---------|
| Mudança em `.py` | `./reload.ps1` (ou nada se detecção automática) |
| Editar `requirements.txt` | `docker-compose up -d --build` |
| Mudança em `settings.py` | `./reload.ps1` |
| Mudança em `signal_handlers.py` | `./reload.ps1` |
| Criar nova migration | `docker-compose exec web python manage.py migrate` |
| Aplicar migration | `docker-compose exec web python manage.py migrate` |
| Parar tudo e recomeçar | `docker-compose down && docker-compose up -d` |
| Limpar dados (start fresh) | `docker-compose down -v && docker-compose up -d --build` |

## Monitorando em tempo real

### Ver logs do Django

```bash
docker-compose logs -f web
```

### Ver logs do Celery

```bash
docker-compose logs -f celery
```

### Ver todos os logs

```bash
docker-compose logs -f
```

## Exemplo prático

Você está editando `crawl_log/tasks.py`:

```bash
# 1. Editar o arquivo e salvar
# (por exemplo, adicionar uma nova task ou mudar lógica)

# 2. Celery pode detectar automático, mas para garantir:
./reload.ps1 celery

# 3. Ver logs para confirmar:
docker-compose logs -f celery
```

## Troubleshooting

### Mudança não foi refletida?

```bash
./reload.ps1 celery  # Força restart do worker
```

### Erro de import ou syntax?

```bash
# Verificar logs:
docker-compose logs celery

# Se problema persistir:
docker-compose down
docker-compose up -d
```

### Dados do banco desapareceram?

```bash
# Você deve ter usado: docker-compose down -v
# Para recuperar, executar migrations novamente:
docker-compose exec web python manage.py migrate
```

---

**💡 Resumo:** Com volumes já configurados, você **não precisa fazer rebuild** para mudanças em código Python! Use `./reload.ps1` se o Celery não detectar mudanças automaticamente, e `docker-compose up -d --build` apenas quando adicionar dependências.
