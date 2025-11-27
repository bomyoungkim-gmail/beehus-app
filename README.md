# Beehus

Um projeto Python com integração de **Celery** para processamento assíncrono de tarefas, **Selenium** para automação web e **Django** para gerenciamento de dados.

## 📋 Descrição

Este projeto automatiza fluxos de trabalho incluindo:

- **Automação Web**: Login automático em plataformas (JPMorgan Chase) usando Selenium WebDriver
- **Processamento Assíncrono**: Execução de tarefas em background com Celery
- **API REST**: Endpoints RESTful com Django e Django REST Framework
- **Agendamento**: Tasks recorrentes com django-celery-beat

## 🚀 Requisitos

- **Python 3.11+**
- **RabbitMQ** (broker AMQP)
- **Redis** (opcional, para cache/resultados)
- **Google Chrome** (para Selenium WebDriver)

## 📦 Instalação

### 1. Clone o repositório e configure o ambiente

```bash
# Criar ambiente Conda (recomendado)
conda create -n beehus python=3.11
conda activate beehus

# Ou usar venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
JP_USERID=seu_usuario_jpmorgan
JP_PASSWORD=sua_senha_jpmorgan
CELERY_BROKER_URL=pyamqp://guest:guest@localhost//
```

### 4. Inicie o RabbitMQ

```bash
# Windows (com Chocolatey)
choco install rabbitmq

# macOS (com Homebrew)
brew services start rabbitmq

# Linux (Docker)
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

## 🔧 Uso

### Iniciar o Worker Celery

```bash
# Com multi-processing (padrão)
celery -A tasks worker --loglevel=info

# Com single thread (útil para desenvolvimento/debugging)
celery -A tasks worker --loglevel=info --pool=solo
```

### Executar uma tarefa assíncrona

```bash
# Via Python
python app.py

# Ou dentro de Python
from tasks import hello
result = hello.delay('João')
print(result.get(timeout=5))
```

### Iniciar o servidor Django

```bash
python manage.py runserver
```

### Executar migrations do Django

```bash
python manage.py migrate
```

## 📂 Estrutura do Projeto

```
beehus/
├── tasks.py              # Definição de tasks Celery
├── main.py               # Lógica de automação (Selenium/JPMorgan)
├── app.py                # Script de teste simples
├── manage.py             # CLI do Django
├── requirements.txt      # Dependências Python
├── .env                  # Variáveis de ambiente (não versionar)
├── .gitignore            # Arquivos a ignorar no Git
├── README.md             # Este arquivo
└── __pycache__/          # Cache Python (ignorado)
```

## 🔑 Tasks Disponíveis

### `hello(name)`
Uma tarefa simples de teste.

**Exemplo:**
```python
from tasks import hello
result = hello.delay('Mundo')
print(result.get())  # Output: "Olá, Mundo"
```

### `login_to_jpmorgan(user, password)`
Automação de login no portal JPMorgan Chase.

**Exemplo:**
```python
from main import login_to_jpmorgan
login_to_jpmorgan('seu_usuario', 'sua_senha')
```

## 🐛 Troubleshooting

### Erro: `ValueError: not enough values to unpack (expected 3, got 0)`

**Causa**: Instância Celery configurada incorretamente (uso de `main=` como named argument).

**Solução**: Use o nome do app como primeiro argumento posicional:
```python
# ✗ Incorreto
app = Celery(main='tasks', broker='...')

# ✓ Correto
app = Celery('tasks', broker='...')
```

### Erro: Conexão recusada ao RabbitMQ

**Solução**: Verifique se o RabbitMQ está em execução:
```bash
# Verificar status (Linux/Mac)
sudo systemctl status rabbitmq-server

# Ou testar conexão
python -c "import pika; pika.BlockingConnection(pika.ConnectionParameters('localhost'))"
```

### Worker não encontra tarefas

**Solução**: Certifique-se de que o módulo é importado corretamente:
```bash
celery -A tasks worker --loglevel=debug
```

## 🛠️ Desenvolvimento

### Adicionar nova tarefa

Em `tasks.py`:
```python
@app.task
def minha_tarefa(parametro):
    resultado = processar(parametro)
    return resultado
```

### Testar tarefa localmente (síncrono)

```python
# Sem disparar para o worker
resultado = minha_tarefa(valor)
```

### Testar tarefa remotamente (assíncrono)

```python
# Dispara para o worker
resultado = minha_tarefa.delay(valor)
print(resultado.get(timeout=10))
```

## 📚 Dependências Principais

| Pacote | Versão | Uso |
|--------|--------|-----|
| celery | 5.5.3 | Processamento assíncrono |
| django | 5.2.8 | Framework web |
| selenium | 4.38.0 | Automação de browser |
| redis | 7.1.0 | Cache/resultados (opcional) |
| python-dotenv | 1.2.1 | Variáveis de ambiente |

Para a lista completa, veja `requirements.txt`.

## 📞 Suporte

Em caso de dúvidas ou erros, consulte a documentação oficial:

- **Celery**: https://docs.celeryproject.io/
- **Django**: https://docs.djangoproject.com/
- **Selenium**: https://www.selenium.dev/documentation/

## 📄 Licença

Este projeto é fornecido como está, sem garantias. Use por sua conta e risco.

---

**Última atualização**: 27 de novembro de 2025
