import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

# CRITICAL: Minimal apps, NO DATABASE
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django_celery_beat',
    'django_celery_results',
]

MIDDLEWARE = []  # Empty - no HTTP middleware needed

# NO DATABASE!
DATABASES = {}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@rabbitmq:5672/')
CELERY_RESULT_BACKEND = 'mongodb'
CELERY_MONGODB_BACKEND_SETTINGS = {
    'host': os.getenv('MONGO_URI', 'mongodb://admin:adminpass@mongo:27017'),
    'database': 'celery_results',
    'taskmeta_collection': 'celery_taskmeta',
}

CELERY_TIMEZONE = 'America/Sao_Paulo'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 min timeout
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Beanie (MongoDB ODM) - inicializado separadamente
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'platform_db')

# Selenium
SELENIUM_REMOTE_URL = os.getenv('SELENIUM_REMOTE_URL', 'http://selenium-hub:4444/wd/hub')
